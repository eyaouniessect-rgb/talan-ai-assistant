# app/api/pipeline/pipeline.py
# ═══════════════════════════════════════════════════════════════
# Endpoints FastAPI du pipeline PM (analyse de CDC).
#
# Prérequis avant d'appeler ces endpoints :
#   1. Client créé       → POST /crm/clients
#   2. Projet créé       → POST /crm/projects
#   3. CDC uploadé       → POST /projects/{id}/document
#
# Routes :
#   GET  /pipeline/projects                  → liste des projets du PM avec avancement
#   POST /pipeline/{project_id}/start        → lancer l'analyse du CDC
#   GET  /pipeline/{project_id}              → état détaillé des 12 phases
#   POST /pipeline/{project_id}/validate     → validation/rejet d'une phase
#
# Responsabilités :
#   - Endpoint start : vérifie le projet + le document, lance pm_graph
#   - node_extraction : lit le fichier via file_path récupéré en DB (document_id)
#   - node02+         : traitements LLM avec persistence après chaque phase
#
# Accès : réservé au rôle "pm" (RBAC).
# ═══════════════════════════════════════════════════════════════

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.crm.project import Project
from app.database.models.pm.pipeline_state import PipelineState
from app.database.models.pm.project_document import ProjectDocument
from app.database.models.pm.enums import PipelineStatusEnum

from agents.pm.graph import get_pm_graph
from agents.pm.db import (
    upsert_pipeline_state,
    get_all_pipeline_states,
    get_employee_id_by_user,
)
from agents.pm.state import PMPipelineState

router = APIRouter(prefix="/pipeline", tags=["Pipeline PM"])


# ──────────────────────────────────────────────────────────────
# RBAC
# ──────────────────────────────────────────────────────────────

async def require_pm(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "pm":
        raise HTTPException(status_code=403, detail="Accès réservé aux Project Managers.")
    return current_user


# ──────────────────────────────────────────────────────────────
# GET /pipeline/projects — Liste des projets avec état pipeline
# ──────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_pipeline_projects(
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne les projets du PM connecté enrichis de leur état pipeline.
    Utilisé par MesProjets.jsx pour afficher la progression des 12 phases.
    """
    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        return []

    projects = (await db.execute(
        select(Project)
        .where(Project.project_manager_id == employee_id)
        .options(selectinload(Project.client))
    )).scalars().all()

    result = []
    for project in projects:
        phases = (await db.execute(
            select(PipelineState)
            .where(PipelineState.project_id == project.id)
            .order_by(PipelineState.id)
        )).scalars().all()

        phases_done = sum(1 for p in phases if p.status == PipelineStatusEnum.VALIDATED)

        # Phase courante = première phase non validée
        current_phase  = None
        current_status = None
        for p in phases:
            if p.status != PipelineStatusEnum.VALIDATED:
                current_phase  = p.phase.value  if p.phase  else None
                current_status = p.status.value if p.status else None
                break

        # Statut global du projet
        if phases_done == 12:
            global_status = "completed"
        elif current_status == "pending_validation":
            global_status = "pending_human"
        elif current_status == "rejected":
            global_status = "rejected"
        elif phases_done > 0 or current_status:
            global_status = "in_progress"
        else:
            global_status = "not_started"

        result.append({
            "project_id":     project.id,
            "project_name":   project.name,
            "client_name":    project.client.name if project.client else "—",
            "phases_done":    phases_done,
            "phases_total":   12,
            "current_phase":  current_phase,
            "current_status": current_status,
            "global_status":  global_status,
            "created_at":     project.created_at.isoformat() if project.created_at else None,
        })

    return result


# ──────────────────────────────────────────────────────────────
# SCHÉMAS PYDANTIC
# ──────────────────────────────────────────────────────────────

class StartPipelineRequest(BaseModel):
    """Corps de la requête POST /pipeline/{project_id}/start."""
    document_id:      int
    jira_project_key: Optional[str] = ""


class ValidateRequest(BaseModel):
    """Corps de la requête POST /pipeline/{project_id}/validate."""
    approved: bool
    feedback: Optional[str] = None  # obligatoire si approved=False


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/start — Lancement du pipeline
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/start")
async def start_pipeline(
    project_id:   int,
    body:         StartPipelineRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Lance le pipeline IA sur le CDC d'un projet existant.

    Prérequis :
      - Le projet doit exister et appartenir au PM connecté
      - Le document doit exister et appartenir au même projet

    Flux :
      1. Vérifie projet + document
      2. Construit le state initial avec document_id (pas file_path)
      3. Lance pm_graph.ainvoke() → tourne jusqu'au premier interrupt()
         (node_validate après node_epics, phase "epics" en attente de validation)
    """
    user_id = current_user["user_id"]

    # ── 1. Vérifier projet ────────────────────────────────────
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(403, "Votre compte n'est pas lié à un profil employé.")

    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")
    if proj.project_manager_id != employee_id:
        raise HTTPException(403, "Ce projet ne vous appartient pas.")

    # ── 2. Vérifier document ──────────────────────────────────
    doc = (await db.execute(
        select(ProjectDocument).where(
            ProjectDocument.id         == body.document_id,
            ProjectDocument.project_id == project_id,
        )
    )).scalar_one_or_none()

    if not doc:
        raise HTTPException(
            404,
            f"Document {body.document_id} introuvable pour le projet {project_id}. "
            "Uploadez un CDC via POST /projects/{id}/document."
        )

    # ── 3. Vérifier que le graph PM est initialisé ────────────
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas encore initialisé.")

    # ── 4. Construction du state initial ─────────────────────
    # document_id remplace cdc_file_path : node_extraction lit le path depuis la DB
    initial_state: PMPipelineState = {
        # Input
        "project_id":          project_id,
        "user_id":             user_id,
        "document_id":         body.document_id,
        "cdc_text":            "",           # rempli par node_extraction
        # Phases — vides au départ
        "epics":               [],
        "stories":             [],
        "refinement_rounds":   [],
        "refined_stories":     [],
        "story_dependencies":  [],
        "priorities":          [],
        "tasks":               [],
        "task_dependencies":   [],
        "cpm_result":          {},
        "critical_path":       [],
        "sprints":             [],
        "staffing":            {},
        "monitoring_plan":     {},
        # Contrôle
        "current_phase":       "extract",
        "pipeline_state_id":   0,
        # Validation
        "validation_status":   "pending_ai",
        "human_feedback":      None,
        # Jira
        "jira_project_key":    body.jira_project_key or "",
        "jira_epic_map":       {},
        "jira_story_map":      {},
        "jira_task_map":       {},
        "jira_sprint_map":     {},
        "jira_synced_phases":  [],
        # Erreur
        "error":               None,
    }

    # ── 5. Lancement du graph ─────────────────────────────────
    config = {"configurable": {"thread_id": str(project_id)}}
    try:
        await pm_graph.ainvoke(initial_state, config=config)
    except Exception as e:
        if "GraphInterrupt" not in type(e).__name__:
            raise HTTPException(500, f"Erreur lors du lancement du pipeline : {str(e)}")

    return {
        "project_id":  project_id,
        "document_id": body.document_id,
        "status":      "running",
        "message":     "Pipeline lancé. En attente de validation de la phase Epics.",
    }


# ──────────────────────────────────────────────────────────────
# GET /pipeline/{project_id} — État détaillé d'un projet
# ──────────────────────────────────────────────────────────────

@router.get("/{project_id}")
async def get_project_pipeline(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Retourne l'état de toutes les phases pipeline pour un projet."""
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")

    phases = await get_all_pipeline_states(project_id)

    phase_list = [
        {
            "id":           p.id,
            "phase":        p.phase.value,
            "status":       p.status.value,
            "ai_output":    p.ai_output,
            "pm_comment":   p.pm_comment,
            "validated_by": p.validated_by,
            "validated_at": p.validated_at.isoformat() if p.validated_at else None,
            "updated_at":   p.updated_at.isoformat()   if p.updated_at   else None,
        }
        for p in phases
    ]

    # Si extraction n'est pas en base mais d'autres phases existent,
    # l'extraction a forcément réussi (sinon les phases suivantes n'auraient pas tourné).
    # On l'injecte comme validée pour que le frontend puisse l'afficher.
    existing_phase_keys = {p["phase"] for p in phase_list}
    if "phase_1_extraction" not in existing_phase_keys and phase_list:
        phase_list.insert(0, {
            "id":           None,
            "phase":        "phase_1_extraction",
            "status":       "validated",
            "ai_output":    None,   # données non conservées (ancienne exécution)
            "pm_comment":   None,
            "validated_by": None,
            "validated_at": None,
            "updated_at":   None,
        })

    return {
        "project_id":   project_id,
        "project_name": proj.name,
        "phases":       phase_list,
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/validate — Validation PM
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/validate")
async def validate_phase(
    project_id:   int,
    body:         ValidateRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Valide ou rejette la phase courante d'un projet.

    - validé  → le graph avance à la phase suivante
    - rejeté  → la phase est relancée avec human_feedback injecté dans le prompt
    """
    if not body.approved and not (body.feedback or "").strip():
        raise HTTPException(400, "Un feedback est obligatoire en cas de rejet.")

    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)

    # Trouver la phase en attente de validation
    pending = (await db.execute(
        select(PipelineState).where(
            PipelineState.project_id == project_id,
            PipelineState.status     == PipelineStatusEnum.PENDING_VALIDATION,
        )
    )).scalar_one_or_none()

    if not pending:
        raise HTTPException(404, "Aucune phase en attente de validation pour ce projet.")

    # Mise à jour en base
    new_status = PipelineStatusEnum.VALIDATED if body.approved else PipelineStatusEnum.REJECTED
    await upsert_pipeline_state(
        project_id   = project_id,
        phase        = pending.phase,
        status       = new_status,
        pm_comment   = body.feedback,
        validated_by = employee_id,
        validated_at = datetime.utcnow(),
    )

    # Reprise du graph LangGraph
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    validation_status = "validated" if body.approved else "rejected"
    config = {"configurable": {"thread_id": str(project_id)}}

    await pm_graph.aupdate_state(
        config,
        {
            "validation_status": validation_status,
            "human_feedback":    body.feedback if not body.approved else None,
        },
        as_node="node_validate",
    )

    try:
        await pm_graph.ainvoke(None, config=config)
    except Exception as e:
        if "GraphInterrupt" not in type(e).__name__:
            raise HTTPException(500, f"Erreur lors de la reprise du pipeline : {str(e)}")

    return {
        "project_id": project_id,
        "phase":      pending.phase.value,
        "decision":   validation_status,
        "message": (
            "Phase validée, pipeline en cours."
            if body.approved else
            "Phase rejetée, l'IA va relancer avec votre feedback."
        ),
    }
