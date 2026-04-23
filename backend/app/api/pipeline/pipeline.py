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
import os
import json
import asyncio

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from jose import JWTError, jwt
from app.core.security import SECRET_KEY, ALGORITHM
from app.database.connection import get_db
from app.database.models.crm.project import Project
from app.database.models.pm.pipeline_state import PipelineState
from app.database.models.pm.project_document import ProjectDocument
from app.database.models.pm.enums import PipelineStatusEnum, PipelinePhaseEnum, ProjectGlobalStatus

from agents.pm.graph import get_pm_graph
from agents.pm.db import (
    upsert_pipeline_state,
    get_all_pipeline_states,
    get_employee_id_by_user,
)
from agents.pm.agents.stories.repository import (
    get_stories,
    update_story,
    delete_story,
)
from agents.pm.state import PMPipelineState

router = APIRouter(prefix="/pipeline", tags=["Pipeline PM"])

_JIRA_ENABLED = bool(os.getenv("JIRA_BASE_URL") and os.getenv("JIRA_API_TOKEN"))


# ──────────────────────────────────────────────────────────────
# RBAC
# ──────────────────────────────────────────────────────────────

async def require_pm(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "pm":
        raise HTTPException(status_code=403, detail="Accès réservé aux Project Managers.")
    return current_user


# ──────────────────────────────────────────────────────────────
# GET /pipeline/config — Configuration publique du pipeline
# ──────────────────────────────────────────────────────────────

@router.get("/config")
async def get_pipeline_config():
    """Retourne la configuration du pipeline visible par le frontend."""
    return {"jira_enabled": _JIRA_ENABLED}


# ──────────────────────────────────────────────────────────────
# GET /pipeline/projects — Liste des projets avec état pipeline
# ──────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_pipeline_projects(
    archived:     bool         = Query(False, description="Inclure uniquement les projets archivés"),
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

    # Par défaut : projets actifs (archived=False). ?archived=true pour les archivés.
    projects = (await db.execute(
        select(Project)
        .where(
            Project.project_manager_id == employee_id,
            Project.archived.is_(archived),
        )
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

        # Statut global du projet (calculé depuis les phases pipeline)
        if phases_done == 12:
            global_status = ProjectGlobalStatus.PIPELINE_DONE
        elif any(p.status == PipelineStatusEnum.PENDING_VALIDATION for p in phases):
            global_status = ProjectGlobalStatus.PENDING_HUMAN
        elif phases_done > 0 or current_status:
            global_status = ProjectGlobalStatus.IN_PROGRESS
        else:
            global_status = ProjectGlobalStatus.NOT_STARTED

        # Synchroniser project.status en DB si différent
        if project.status != global_status.value:
            project.status = global_status.value
            await db.commit()

        result.append({
            "project_id":     project.id,
            "project_name":   project.name,
            "client_name":    project.client.name if project.client else "—",
            "phases_done":    phases_done,
            "phases_total":   12,
            "current_phase":  current_phase,
            "current_status": current_status,
            "global_status":  global_status,
            "archived":       project.archived,
            "archive_reason": project.archive_reason,
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


class UpdateStoryRequest(BaseModel):
    """Corps de la requête PUT /pipeline/stories/{story_id}."""
    title:               Optional[str]       = None
    description:         Optional[str]       = None
    story_points:        Optional[int]       = None
    acceptance_criteria: Optional[list[str]] = None


class ResyncJiraRequest(BaseModel):
    """Corps de la requête POST /pipeline/{project_id}/jira-resync."""
    phase: Optional[str] = None   # ex: "stories", "epics" — défaut = phase courante


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

    # ── 3. Valider la clé Jira si Jira est activé ────────────
    # Priorité : body → clé déjà stockée en DB (relancement du pipeline)
    resolved_jira_key = (body.jira_project_key or "").strip() or (proj.jira_project_key or "")
    if _JIRA_ENABLED and not resolved_jira_key:
        raise HTTPException(
            400,
            "La clé du projet Jira est obligatoire (ex: TALAN). "
            "Renseignez-la dans le champ 'Clé Jira' de l'étape Lancement."
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
        "security_scan":       None,         # rempli par node_extraction
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
        "jira_project_key":    resolved_jira_key,
        "jira_epic_map":       {},
        "jira_story_map":      {},
        "jira_task_map":       {},
        "jira_sprint_map":     {},
        "jira_synced_phases":  [],
        # Erreur
        "error":               None,
    }

    # ── 5. Persistance de la clé Jira + statut projet ─────────
    proj.jira_project_key = resolved_jira_key or None
    proj.status           = ProjectGlobalStatus.IN_PROGRESS.value
    await db.commit()

    # Préfixe "pm_" pour éviter les collisions avec les threads de chat
    config = {"configurable": {"thread_id": f"pm_{project_id}"}}
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
        "project_id":       project_id,
        "project_name":     proj.name,
        "jira_project_key": proj.jira_project_key,
        "phases":           phase_list,
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
    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

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

    # Mettre à jour project.status si toutes les phases sont validées
    all_phases = await get_all_pipeline_states(project_id)
    validated_count = sum(1 for p in all_phases if p.status == PipelineStatusEnum.VALIDATED)
    has_pending     = any(p.status == PipelineStatusEnum.PENDING_VALIDATION for p in all_phases)

    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj:
        if validated_count == 12:
            proj.status = ProjectGlobalStatus.PIPELINE_DONE.value
        elif has_pending:
            proj.status = ProjectGlobalStatus.PENDING_HUMAN.value
        else:
            proj.status = ProjectGlobalStatus.IN_PROGRESS.value
        await db.commit()

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


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/resume — Débloquer un pipeline planté
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/resume")
async def resume_pipeline(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Relance un pipeline bloqué (phase pending_ai sans pending_validation en DB).

    Cas d'usage : le graph a crashé en cours d'exécution d'un nœud
    (exception non capturée avant l'interrupt). On ré-invoque simplement
    le graph depuis le dernier checkpoint LangGraph.
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    # Vérifier qu'il y a bien une phase en pending_ai (bloquée)
    phases = await get_all_pipeline_states(project_id)
    stuck  = [p for p in phases if p.status.value == "pending_ai"]
    if not stuck and not phases:
        raise HTTPException(404, f"Aucune phase en cours pour le projet {project_id}.")

    try:
        await pm_graph.ainvoke(None, config=config)
    except Exception as e:
        if "GraphInterrupt" not in type(e).__name__:
            raise HTTPException(500, f"Erreur lors de la reprise : {str(e)}")

    return {
        "project_id": project_id,
        "message": "Pipeline relancé depuis le dernier checkpoint.",
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/stories/restart — Génère les epics manquants
# ──────────────────────────────────────────────────────────────

async def _background_generate_missing_stories(
    project_id:          int,
    all_epics:           list[dict],
    missing_epics:       list[dict],
    missing_indices:     list[int],
    existing_stories:    list[dict],
    human_feedback:      str | None,
    architecture_details: dict | None,
) -> None:
    from agents.pm.agents.stories.service    import generate_stories
    from agents.pm.agents.stories.repository import save_stories

    try:
        print(f"[restart_stories] ▶ projet={project_id} | épics manquants={missing_indices}")

        # Génère uniquement pour les epics manquants (indexés 0..N localement)
        new_stories = await generate_stories(
            epics                = missing_epics,
            human_feedback       = human_feedback,
            architecture_details = architecture_details,
            project_id           = project_id,
        )

        # Corrige epic_id local (0..N) → index original dans all_epics
        local_to_orig = {local: orig for local, orig in enumerate(missing_indices)}
        for s in new_stories:
            s["epic_id"] = local_to_orig.get(s.get("epic_id", 0), s.get("epic_id", 0))

        # Fusionne avec les stories déjà générées
        all_stories = existing_stories + new_stories

        await save_stories(project_id, all_stories)
        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_3_STORIES,
            status     = PipelineStatusEnum.PENDING_VALIDATION,
            ai_output  = {"stories": all_stories, "epics": all_epics},
        )
        print(f"[restart_stories] ✓ {len(new_stories)} nouvelles + {len(existing_stories)} existantes = {len(all_stories)} stories")
    except Exception as e:
        print(f"[restart_stories] ❌ {e}")
        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_3_STORIES,
            status     = PipelineStatusEnum.PENDING_VALIDATION,
        )


@router.post("/{project_id}/stories/restart")
async def restart_missing_stories(
    project_id:       int,
    background_tasks: BackgroundTasks,
    current_user:     dict         = Depends(require_pm),
    db:               AsyncSession = Depends(get_db),
):
    """Génère les user stories pour les epics qui n'en ont pas encore."""
    phases = await get_all_pipeline_states(project_id)

    epics_phase = next(
        (p for p in phases if p.phase.value == PipelinePhaseEnum.PHASE_2_EPICS.value), None
    )
    if not epics_phase or not epics_phase.ai_output:
        raise HTTPException(400, "La phase épics n'a pas de résultat disponible.")

    all_epics = epics_phase.ai_output.get("epics", [])
    if not all_epics:
        raise HTTPException(400, "Aucun epic trouvé pour ce projet.")

    # Stories et epics déjà couverts
    stories_phase = next(
        (p for p in phases if p.phase.value == PipelinePhaseEnum.PHASE_3_STORIES.value), None
    )
    existing_stories: list[dict] = []
    covered_ids: set[int] = set()
    if stories_phase and stories_phase.ai_output:
        existing_stories = stories_phase.ai_output.get("stories", [])
        covered_ids = {
            s.get("epic_id") for s in existing_stories if s.get("epic_id") is not None
        }

    missing_indices = [i for i in range(len(all_epics)) if i not in covered_ids]
    if not missing_indices:
        return {"status": "complete", "message": "Toutes les stories sont déjà présentes."}

    missing_epics = [all_epics[i] for i in missing_indices]

    # Architecture (optionnelle)
    extract_phase = next(
        (p for p in phases if p.phase.value == PipelinePhaseEnum.PHASE_1_EXTRACTION.value), None
    )
    architecture_details = None
    if extract_phase and extract_phase.ai_output:
        if extract_phase.ai_output.get("architecture_detected"):
            architecture_details = extract_phase.ai_output.get("architecture_details")

    human_feedback = stories_phase.pm_comment if stories_phase else None

    # Remettre en pending_ai → le frontend affichera le StoriesStreamCard
    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_3_STORIES,
        status     = PipelineStatusEnum.PENDING_AI,
    )

    background_tasks.add_task(
        _background_generate_missing_stories,
        project_id           = project_id,
        all_epics            = all_epics,
        missing_epics        = missing_epics,
        missing_indices      = missing_indices,
        existing_stories     = existing_stories,
        human_feedback       = human_feedback,
        architecture_details = architecture_details,
    )

    return {
        "status":  "started",
        "message": f"Génération lancée pour {len(missing_epics)} epic(s) manquant(s).",
        "missing": missing_indices,
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/refinement/restart — Relancer le raffinement
# ──────────────────────────────────────────────────────────────

async def _background_run_one_round(
    project_id:           int,
    stories:              list,
    epics:                list,
    round_number:         int,
    architecture_details: dict | None,
    previous_rounds:      list,
) -> None:
    """
    Background task : exécute UN seul round de raffinement et suspend
    en PENDING_VALIDATION avec awaiting_round_review=True.
    Le PM valide story par story avant le round suivant.
    """
    from agents.pm.agents.refinement.service import run_one_round

    try:
        stories_before_round = list(stories)

        updated_stories, round_data = await run_one_round(
            stories              = stories,
            epics                = epics,
            round_number         = round_number,
            architecture_details = architecture_details,
            previous_rounds      = previous_rounds,
        )

        all_rounds = previous_rounds + [round_data]

        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_4_REFINEMENT,
            status     = PipelineStatusEnum.PENDING_VALIDATION,
            ai_output  = {
                "refined_stories":      updated_stories,
                "stories_before_round": stories_before_round,
                "current_round":        round_number,
                "refinement_rounds":    all_rounds,
                "epics":                epics,
                "consensus":            round_data.get("consensus", False),
                "awaiting_round_review": True,
            },
        )
        print(f"[round/{round_number}] ✓ projet={project_id} | en attente validation PM")
    except Exception as e:
        print(f"[round/{round_number}] ✗ projet={project_id}: {type(e).__name__}: {e}")
        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_4_REFINEMENT,
            status     = PipelineStatusEnum.PENDING_VALIDATION,
            ai_output  = None,
        )


@router.post("/{project_id}/refinement/restart")
async def restart_refinement(
    project_id:       int,
    background_tasks: BackgroundTasks,
    current_user:     dict         = Depends(require_pm),
    db:               AsyncSession = Depends(get_db),
):
    """Relance le raffinement PO↔TL en arrière-plan à partir des stories existantes."""
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config   = {"configurable": {"thread_id": f"pm_{project_id}"}}
    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    state: dict = dict(snapshot.values)

    stories              = state.get("stories") or state.get("refined_stories") or []
    epics                = state.get("epics", [])
    human_feedback       = state.get("human_feedback")
    architecture_details = state.get("architecture_details") if state.get("architecture_detected") else None

    if not stories:
        raise HTTPException(400, "Aucune story disponible pour relancer le raffinement.")

    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_4_REFINEMENT,
        status     = PipelineStatusEnum.PENDING_AI,
        ai_output  = None,
    )

    background_tasks.add_task(
        _background_run_one_round,
        project_id           = project_id,
        stories              = stories,
        epics                = epics,
        round_number         = 1,
        architecture_details = architecture_details,
        previous_rounds      = [],
    )

    return {"status": "started", "message": "Round 1 du raffinement lancé."}


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/refinement/round/apply — Décision PM par story
# ──────────────────────────────────────────────────────────────

class RoundApplyRequest(BaseModel):
    story_choices:        dict   # { "db_id_str": "new" | "old" }
    continue_refinement:  bool = True


@router.post("/{project_id}/refinement/round/apply")
async def apply_refinement_round(
    project_id:       int,
    body:             RoundApplyRequest,
    background_tasks: BackgroundTasks,
    current_user:     dict         = Depends(require_pm),
    db:               AsyncSession = Depends(get_db),
):
    """
    Le PM a choisi pour chaque story : garder la version raffinée ("new")
    ou revenir à la version précédente ("old").
    Ensuite : lancer le round suivant ou finaliser le raffinement.
    """
    phases = await get_all_pipeline_states(project_id)
    ref_phase = next(
        (p for p in phases if p.phase.value == PipelinePhaseEnum.PHASE_4_REFINEMENT.value),
        None,
    )
    if not ref_phase or not ref_phase.ai_output:
        raise HTTPException(404, "Aucun état de raffinement trouvé.")

    ao = ref_phase.ai_output
    refined_stories     = ao.get("refined_stories", [])
    stories_before      = ao.get("stories_before_round", [])
    epics               = ao.get("epics", [])
    current_round       = ao.get("current_round", 1)
    all_rounds          = ao.get("refinement_rounds", [])
    consensus           = ao.get("consensus", False)

    # ── 1. Appliquer les choix du PM (new / old) story par story ─
    before_by_id = {str(s["db_id"]): s for s in stories_before if s.get("db_id")}
    merged: list[dict] = []
    for s in refined_stories:
        db_id_str = str(s.get("db_id", ""))
        choice = body.story_choices.get(db_id_str, "new")
        if choice == "old" and db_id_str in before_by_id:
            merged.append(dict(before_by_id[db_id_str]))
        else:
            merged.append(dict(s))

    # ── 2. Sauvegarder en base ────────────────────────────────────
    from agents.pm.agents.refinement.repository import save_refined_stories
    await save_refined_stories(project_id, merged)

    # ── 3. Récupérer le graph + config ───────────────────────────
    pm_graph = get_pm_graph()
    config   = {"configurable": {"thread_id": f"pm_{project_id}"}}

    # ── 4. Mettre à jour le state LangGraph avec les stories choisies ─
    # Indispensable : les phases suivantes (5, 6…) lisent refined_stories
    # depuis le checkpoint LangGraph, pas depuis pipeline_state.
    if pm_graph:
        await pm_graph.aupdate_state(
            config,
            {
                "refined_stories":      merged,
                "stories_before_round": None,
            },
        )

    # ── 5. Continuer ou finaliser ─────────────────────────────────
    next_round = current_round + 1

    if body.continue_refinement and not consensus and next_round <= MAX_ROUNDS:
        architecture_details = None
        if pm_graph:
            snapshot = await pm_graph.aget_state(config)
            if snapshot and snapshot.values:
                s = dict(snapshot.values)
                if s.get("architecture_detected"):
                    architecture_details = s.get("architecture_details")

        await upsert_pipeline_state(
            project_id = project_id,
            phase      = PipelinePhaseEnum.PHASE_4_REFINEMENT,
            status     = PipelineStatusEnum.PENDING_AI,
            ai_output  = None,
        )

        background_tasks.add_task(
            _background_run_one_round,
            project_id           = project_id,
            stories              = merged,
            epics                = epics,
            round_number         = next_round,
            architecture_details = architecture_details,
            previous_rounds      = all_rounds,
        )
        return {"status": "started", "message": f"Round {next_round} lancé en arrière-plan."}

    # ── 6. Finaliser : reprendre l'interrupt LangGraph ────────────
    # Le graph était suspendu dans node_validate après node_refinement.
    # On le reprend avec approved=True pour passer à la Phase 5.
    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_4_REFINEMENT,
        status     = PipelineStatusEnum.PENDING_VALIDATION,
        ai_output  = {
            "refined_stories":       merged,
            "stories_before_round":  None,
            "current_round":         current_round,
            "refinement_rounds":     all_rounds,
            "epics":                 epics,
            "consensus":             consensus,
            "awaiting_round_review": False,
        },
    )
    return {"status": "finalized", "message": "Raffinement finalisé. Vous pouvez valider la phase."}


MAX_ROUNDS = 3


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/jira-resync — Force re-sync Jira d'une phase
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/jira-resync")
async def jira_resync_phase(
    project_id:   int,
    body:         ResyncJiraRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Force la re-synchronisation d'une phase vers Jira sans relancer tout le pipeline.

    Cas d'usage : les stories/epics ont été générés mais la sync Jira a échoué
    (token invalide, projet Jira inexistant, erreur réseau). On appelle ce endpoint
    pour rejouer uniquement le nœud jira_sync sur la phase demandée.

    Corps : { "phase": "stories" }  (optionnel — défaut = phase courante du checkpoint)
    """
    if not _JIRA_ENABLED:
        raise HTTPException(400, "Jira n'est pas configuré sur ce serveur.")

    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    # ── 1. Lire l'état courant depuis le checkpoint LangGraph ─
    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet. Lancez d'abord le pipeline.")

    current_state: dict = dict(snapshot.values)

    # ── 2. Déterminer la phase à re-syncer ───────────────────
    phase = (body.phase or current_state.get("current_phase") or "").strip()
    if not phase:
        raise HTTPException(400, "Impossible de déterminer la phase. Fournissez 'phase' dans le corps.")

    syncable = {"epics", "stories", "tasks", "sprints"}
    if phase not in syncable:
        raise HTTPException(400, f"Phase '{phase}' non synchronisable. Phases supportées : {sorted(syncable)}.")

    # ── 3. Vérifier la clé Jira ───────────────────────────────
    jira_key = (current_state.get("jira_project_key") or "").strip()
    if not jira_key:
        proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        jira_key = (proj.jira_project_key or "").strip() if proj else ""
    if not jira_key:
        raise HTTPException(400, "Aucune clé projet Jira trouvée. Relancez le pipeline en fournissant une clé Jira.")

    # ── 4. Retirer la phase de jira_synced_phases → force re-sync ─
    synced = list(current_state.get("jira_synced_phases") or [])
    if phase in synced:
        synced.remove(phase)

    # Construire l'état partiel pour le nœud
    state_for_sync = {
        **current_state,
        "current_phase":      phase,
        "jira_project_key":   jira_key,
        "jira_synced_phases": synced,
    }

    # ── 5. Appeler directement le nœud jira_sync ─────────────
    from agents.pm.graph.node_jira_sync import node_jira_sync
    try:
        patch = await node_jira_sync(state_for_sync)
    except Exception as e:
        raise HTTPException(500, f"Erreur lors de la re-sync Jira : {str(e)}")

    # ── 6. Persister le patch dans le checkpoint LangGraph ────
    if patch:
        await pm_graph.aupdate_state(config, patch, as_node="jira_sync")

    nb_synced = len(patch.get(f"jira_{phase[:-1] if phase.endswith('s') else phase}_map", {}) or patch)
    return {
        "project_id":   project_id,
        "phase":        phase,
        "jira_key":     jira_key,
        "patch_keys":   list(patch.keys()) if patch else [],
        "message":      f"Re-sync Jira phase '{phase}' terminée." if patch else f"Aucun objet créé pour la phase '{phase}'.",
    }


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/status — Transition manuelle de statut
# ──────────────────────────────────────────────────────────────
# Transitions autorisées (PM décide) :
#   pipeline_done  → in_development  (lancement du développement)
#   in_development → delivered       (projet livré)

MANUAL_TRANSITIONS = {
    "pipeline_done":  "in_development",
    "in_development": "delivered",
}

@router.patch("/{project_id}/status")
async def update_project_status(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Fait avancer le projet vers la prochaine étape manuelle (pipeline_done→in_development→delivered)."""
    employee_id = await get_employee_id_by_user(current_user["user_id"])
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")
    if proj.project_manager_id != employee_id:
        raise HTTPException(403, "Ce projet ne vous appartient pas.")

    next_status = MANUAL_TRANSITIONS.get(proj.status)
    if not next_status:
        raise HTTPException(400, f"Le statut '{proj.status}' ne permet pas de transition manuelle.")

    proj.status = next_status
    if next_status == "delivered":
        proj.progress = 100.0
    await db.commit()

    return {"project_id": project_id, "status": next_status}


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/unarchive — Désarchiver un projet
# ──────────────────────────────────────────────────────────────

@router.patch("/{project_id}/unarchive")
async def unarchive_project(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Remet un projet archivé dans la liste active."""
    employee_id = await get_employee_id_by_user(current_user["user_id"])
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")
    if proj.project_manager_id != employee_id:
        raise HTTPException(403, "Ce projet ne vous appartient pas.")

    proj.archived       = False
    proj.archive_reason = None
    await db.commit()

    return {"project_id": project_id, "archived": False}


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/archive — Archiver un projet
# ──────────────────────────────────────────────────────────────

ARCHIVE_REASONS = {"completed", "cancelled", "on_hold", "other"}

class ArchiveProjectRequest(BaseModel):
    reason: str   # completed | cancelled | on_hold | other


@router.patch("/{project_id}/archive")
async def archive_project(
    project_id:   int,
    body:         ArchiveProjectRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Archive un projet (masqué dans la vue principale, visible dans l'onglet Archivés)."""
    if body.reason not in ARCHIVE_REASONS:
        raise HTTPException(400, f"Raison invalide. Valeurs acceptées : {sorted(ARCHIVE_REASONS)}")

    employee_id = await get_employee_id_by_user(current_user["user_id"])
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")
    if proj.project_manager_id != employee_id:
        raise HTTPException(403, "Ce projet ne vous appartient pas.")

    proj.archived       = True
    proj.archive_reason = body.reason
    await db.commit()

    return {"project_id": project_id, "archived": True, "reason": body.reason}


# ──────────────────────────────────────────────────────────────
# DELETE /pipeline/{project_id} — Supprimer un projet
# ──────────────────────────────────────────────────────────────

@router.delete("/{project_id}")
async def delete_project(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Supprime définitivement un projet et toutes ses données pipeline."""
    employee_id = await get_employee_id_by_user(current_user["user_id"])
    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")
    if proj.project_manager_id != employee_id:
        raise HTTPException(403, "Ce projet ne vous appartient pas.")

    # Suppression manuelle dans l'ordre des FK (pas de CASCADE en base avant migration)
    from sqlalchemy import text
    await db.execute(text("""
        DELETE FROM project_management.task_dependencies
        WHERE task_id IN (
            SELECT t.id FROM project_management.tasks t
            JOIN project_management.user_stories us ON t.user_story_id = us.id
            JOIN project_management.epics e ON us.epic_id = e.id
            WHERE e.project_id = :pid
        )
    """), {"pid": project_id})
    await db.execute(text("""
        DELETE FROM project_management.story_dependencies
        WHERE story_id IN (
            SELECT us.id FROM project_management.user_stories us
            JOIN project_management.epics e ON us.epic_id = e.id
            WHERE e.project_id = :pid
        )
    """), {"pid": project_id})
    await db.execute(text("""
        DELETE FROM project_management.tasks
        WHERE user_story_id IN (
            SELECT us.id FROM project_management.user_stories us
            JOIN project_management.epics e ON us.epic_id = e.id
            WHERE e.project_id = :pid
        )
    """), {"pid": project_id})
    await db.execute(text("""
        DELETE FROM project_management.user_stories
        WHERE epic_id IN (SELECT id FROM project_management.epics WHERE project_id = :pid)
    """), {"pid": project_id})
    await db.execute(text("DELETE FROM project_management.epics         WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM project_management.sprints        WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM project_management.pipeline_state WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM project_management.project_documents WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM crm.assignments                   WHERE project_id = :pid"), {"pid": project_id})
    await db.execute(text("DELETE FROM crm.projects                      WHERE id = :pid"),         {"pid": project_id})
    await db.commit()

    return {"project_id": project_id, "deleted": True}


# ──────────────────────────────────────────────────────────────
# GET /pipeline/{project_id}/stories — Stories du projet (avec IDs DB)
# ──────────────────────────────────────────────────────────────

@router.get("/{project_id}/stories")
async def list_stories(
    project_id:   int,
    current_user: dict = Depends(require_pm),
):
    """Retourne toutes les user stories du projet depuis la DB (avec db_id)."""
    stories = await get_stories(project_id)
    return [
        {
            "db_id":               s.id,
            "epic_id":             s.epic_id,
            "title":               s.title,
            "description":         s.description,
            "story_points":        s.story_points,
            "splitting_strategy":  s.splitting_strategy,
            "acceptance_criteria": json.loads(s.acceptance_criteria) if s.acceptance_criteria else [],
            "status":              s.status.value if s.status else "draft",
            "jira_issue_key":      s.jira_issue_key,
        }
        for s in stories
    ]


# ──────────────────────────────────────────────────────────────
# PUT /pipeline/stories/{story_id} — Modifier une story
# ──────────────────────────────────────────────────────────────

@router.put("/stories/{story_id}")
async def update_story_endpoint(
    story_id:     int,
    body:         UpdateStoryRequest,
    current_user: dict = Depends(require_pm),
):
    """Modifie les champs éditables d'une user story."""
    updates = body.model_dump(exclude_none=True)
    found   = await update_story(story_id, updates)
    if not found:
        raise HTTPException(404, f"Story {story_id} introuvable.")
    return {"story_id": story_id, "updated": True}


# ──────────────────────────────────────────────────────────────
# DELETE /pipeline/stories/{story_id} — Supprimer une story
# ──────────────────────────────────────────────────────────────

@router.delete("/stories/{story_id}")
async def delete_story_endpoint(
    story_id:     int,
    current_user: dict = Depends(require_pm),
):
    """Supprime définitivement une user story."""
    found = await delete_story(story_id)
    if not found:
        raise HTTPException(404, f"Story {story_id} introuvable.")
    return {"story_id": story_id, "deleted": True}


# ──────────────────────────────────────────────────────────────
# GET /pipeline/{project_id}/stories/stream — SSE streaming ReAct
# ──────────────────────────────────────────────────────────────

@router.get("/{project_id}/stories/stream")
async def stream_stories_events(
    project_id: int,
    token:      str = Query(..., description="JWT Bearer token (EventSource ne supporte pas les headers)"),
):
    """
    Server-Sent Events — diffuse en temps réel les événements de génération des stories.

    Événements émis :
      epic_start     : début du traitement d'un epic
      tool_start     : démarrage d'un tool (estimate, criteria, review)
      gap_detected   : gaps fonctionnels détectés par review_coverage
      retry_start    : régénération ciblée avec les fonctionnalités manquantes
      coverage_ok    : couverture validée → passage à l'epic suivant
      epic_done      : stories complètes pour cet epic
      llm_token      : token LLM en streaming (thinking)
      done           : génération terminée
      error          : erreur fatale
      heartbeat      : keepalive toutes les 15s

    Auth : le JWT est passé en query param ?token=xxx
    """
    # Vérification JWT depuis query param (EventSource ne supporte pas les headers)
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        role    = payload.get("role", "")
        if role != "pm":
            raise HTTPException(403, "Accès réservé aux PM.")
    except JWTError:
        raise HTTPException(401, "Token invalide.")

    from agents.pm.agents.stories.react_agent import get_or_create_queue

    async def event_generator():
        queue = get_or_create_queue(project_id)
        try:
            while True:
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n"
                    if evt.get("type") in ("done", "error"):
                        break
                except asyncio.TimeoutError:
                    # Heartbeat pour maintenir la connexion ouverte
                    yield 'data: {"type":"heartbeat"}\n\n'
        except Exception as e:
            err_msg = str(e)[:200].replace('"', "'")
            yield f'data: {{"type":"error","message":"{err_msg}"}}\n\n'

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )
