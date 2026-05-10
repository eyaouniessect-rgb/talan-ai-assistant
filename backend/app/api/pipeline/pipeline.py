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
from app.database.models.pm.epic import Epic

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
    get_all_stories_as_dicts,
)
from app.database.connection import AsyncSessionLocal
from app.database.models.pm.user_story import UserStory
from agents.pm.agents.epics.repository import (
    get_epics,
    update_epic,
    delete_epic,
    add_epic,
)
from agents.pm.state import PMPipelineState

router = APIRouter(prefix="/pipeline", tags=["Pipeline PM"])

_JIRA_ENABLED = bool(os.getenv("JIRA_BASE_URL") and os.getenv("JIRA_API_TOKEN"))

# Verrou par projet — empêche deux pm_graph.ainvoke() concurrents sur le même
# thread_id (causerait des appels NVIDIA en parallèle qui se piétinent les clés).
# Utilisé par tous les endpoints qui invoquent le graph (validate, restart…).
_pm_graph_running: set[int] = set()


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
        if phases_done == 11:
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
            "phases_total":   11,
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
    feedback: Optional[str] = None            # obligatoire si approved=False
    targeted_story_ids: Optional[list[int]] = None  # IDs DB stories à corriger (None = tout)
    targeted_epic_ids:  Optional[list[int]] = None  # IDs DB epics  à corriger (None = tout)


class UpdateStoryRequest(BaseModel):
    """Corps de la requête PUT /pipeline/stories/{story_id}."""
    title:               Optional[str]       = None
    description:         Optional[str]       = None
    story_points:        Optional[int]       = None
    acceptance_criteria: Optional[list[str]] = None


class StoryCreateRequest(BaseModel):
    """Corps de la requête POST /pipeline/{project_id}/stories."""
    epic_idx:            int                  # index 0-based de l'epic dans le projet
    title:               str
    description:         str                  = ""
    story_points:        int                  = 3
    acceptance_criteria: Optional[list[str]]  = None


class ResyncJiraRequest(BaseModel):
    """Corps de la requête POST /pipeline/{project_id}/jira-resync."""
    phase: Optional[str] = None   # ex: "stories", "epics" — défaut = phase courante


class UpdateStaffingProfilesRequest(BaseModel):
    """Corps de la requête PATCH /pipeline/{project_id}/staffing/profiles."""
    stories_profiles: list[dict]


class UpdateNormalizationDecisionsRequest(BaseModel):
    """Corps de la requête PATCH /pipeline/{project_id}/staffing/normalization-decisions."""
    pm_decisions: dict[str, str]   # { required_profile: "accept" | "recruit" }


class UpdateSprintCapacitiesRequest(BaseModel):
    """Corps de la requête PATCH /pipeline/{project_id}/staffing/sprint-capacities.

    capacities : capacité cible (en SP) pour chaque sprint, dans l'ordre.
                 Longueur = nombre de sprints existants. Toutes ≥ 1.
    """
    capacities: list[int]


class ResolveManualDecisionRequest(BaseModel):
    """Corps de la requête PATCH /pipeline/{project_id}/staffing/matching/manual-decision.

    Le PM choisit l'employé à retenir parmi les candidate_options proposés.
    """
    sprint_number:    int
    story_id:         int
    required_profile: str
    employee_id:      int


class ChangeAssignmentRequest(BaseModel):
    """Corps de la requête PATCH /pipeline/{project_id}/staffing/matching/change-assignment.

    Le PM change l'employé affecté à un (sprint, story, profile) parmi les
    alternative_candidates fournies par le matching auto.
    """
    sprint_number:    int
    story_id:         int
    required_profile: str
    new_employee_id:  int


class RecruitmentRequestRequest(BaseModel):
    """Corps de la requête POST /pipeline/{project_id}/staffing/recruitment-request.

    Le PM signale un besoin RH non couvert en interne. Tous les champs sont
    déjà composés côté frontend : le PM édite le sujet, le corps, les
    destinataires et le CC dans une UI type email avant d'envoyer.
    """
    to:               list[str]
    cc:               Optional[list[str]] = None
    subject:          str
    body:             str
    profile:          str
    required_skills:  Optional[list[str]] = None
    required_level:   Optional[str]       = None
    sprint_number:    Optional[int]       = None
    sprint_start:     Optional[str]       = None
    sprint_end:       Optional[str]       = None


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
        "story_dependencies":  [],
        "priorities":          [],
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
        "start_date":       proj.start_date.isoformat() if proj.start_date else None,
        "end_date":         proj.end_date.isoformat()   if proj.end_date   else None,
        "phases":           phase_list,
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/validate — Validation PM
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/validate")
async def validate_phase(
    project_id:   int,
    body:         ValidateRequest,
    background:   BackgroundTasks,
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

    # Guard : refuser si une exécution graph est déjà en cours pour ce projet
    if project_id in _pm_graph_running:
        raise HTTPException(
            409,
            "Une exécution du pipeline est déjà en cours pour ce projet. "
            "Attendez qu'elle termine avant de relancer."
        )

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
        # Diagnostic : chercher si une phase tourne encore (pending_ai)
        running = (await db.execute(
            select(PipelineState).where(
                PipelineState.project_id == project_id,
                PipelineState.status     == PipelineStatusEnum.PENDING_AI,
            )
        )).scalar_one_or_none()

        if running:
            raise HTTPException(
                409,
                f"La phase '{running.phase.value}' est encore en cours de traitement (pending_ai). "
                "Attendez qu'elle termine, ou utilisez POST /pipeline/{project_id}/resume si elle est bloquée."
            )
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
            "validation_status":  validation_status,
            "human_feedback":     body.feedback if not body.approved else None,
            "targeted_story_ids": body.targeted_story_ids if not body.approved else None,
            "targeted_epic_ids":  body.targeted_epic_ids  if not body.approved else None,
        },
        as_node="node_validate",
    )

    # Pour le staffing : exécution en arrière-plan (peut prendre 5+ min)
    # Pour les autres phases : exécution synchrone (rapide, finit avant le timeout HTTP)
    is_staffing = pending.phase.value == PipelinePhaseEnum.PHASE_8_STAFFING.value

    if is_staffing:
        async def _run():
            _pm_graph_running.add(project_id)
            try:
                await pm_graph.ainvoke(None, config=config)
            except Exception as e:
                if "GraphInterrupt" not in type(e).__name__:
                    print(f"[validate_phase] erreur graph projet {project_id} : {e}")
            finally:
                _pm_graph_running.discard(project_id)

        background.add_task(_run)
    else:
        _pm_graph_running.add(project_id)
        try:
            await pm_graph.ainvoke(None, config=config)
        except Exception as e:
            if "GraphInterrupt" not in type(e).__name__:
                raise HTTPException(500, f"Erreur lors de la reprise du pipeline : {str(e)}")
        finally:
            _pm_graph_running.discard(project_id)

    # Mettre à jour project.status si toutes les phases sont validées
    all_phases = await get_all_pipeline_states(project_id)
    validated_count = sum(1 for p in all_phases if p.status == PipelineStatusEnum.VALIDATED)
    has_pending     = any(p.status == PipelineStatusEnum.PENDING_VALIDATION for p in all_phases)

    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if proj:
        if validated_count == 11:
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
# GET /pipeline/staffing/available-profiles — Profils disponibles (PM)
# GET /pipeline/staffing/available-skills   — Compétences disponibles (PM)
# ──────────────────────────────────────────────────────────────

@router.get("/staffing/available-profiles")
async def get_available_profiles(
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne les job_titles distincts des employés (hors management)
    pour alimenter le sélecteur de profils dans l'UI staffing PM.
    """
    from app.database.models.hris import Employee, SeniorityEnum
    from sqlalchemy import select as sa_select

    result = await db.execute(
        sa_select(Employee.job_title)
        .where(
            Employee.job_title.isnot(None),
            Employee.seniority.notin_([SeniorityEnum.LEAD, SeniorityEnum.HEAD, SeniorityEnum.PRINCIPAL]),
        )
        .distinct()
        .order_by(Employee.job_title)
    )
    titles = [row[0] for row in result.all() if row[0] and row[0].strip()]
    return {"profiles": titles}


@router.get("/staffing/available-skills")
async def get_available_skills(
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne toutes les compétences disponibles en base
    pour alimenter le sélecteur de compétences dans l'UI staffing PM.
    """
    from app.database.models.hris import Skill
    from sqlalchemy import select as sa_select

    result = await db.execute(sa_select(Skill.name).order_by(Skill.name))
    skills = [row[0] for row in result.all() if row[0]]
    return {"skills": skills}


# ──────────────────────────────────────────────────────────────
# GET /pipeline/staffing/hr-contacts
# Retourne les utilisateurs actifs avec le rôle RH pour pré-remplir le
# champ "À" du dialog "Signaler un besoin en recrutement". Le PM peut
# ensuite ajouter ou retirer des destinataires comme dans Gmail.
# ──────────────────────────────────────────────────────────────

@router.get("/staffing/hr-contacts")
async def get_hr_contacts(
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne tous les users actifs avec role='rh', triés par nom.
    Format : [{ "id", "name", "email" }, …]
    """
    from app.database.models.public.user import User
    from sqlalchemy import select as sa_select

    rows = (await db.execute(
        sa_select(User.id, User.name, User.email)
        .where(User.role == "rh", User.is_active == True)  # noqa: E712
        .order_by(User.name)
    )).all()

    contacts = [
        {"id": r[0], "name": r[1] or r[2], "email": r[2]}
        for r in rows
        if r[2] and r[2].strip()
    ]
    return {"contacts": contacts}


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/staffing/profiles — Correction manuelle
# ──────────────────────────────────────────────────────────────

@router.patch("/{project_id}/staffing/profiles")
async def update_staffing_profiles(
    project_id:   int,
    body:         UpdateStaffingProfilesRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Permet au PM de corriger manuellement les profils extraits par le LLM
    (profils requis, compétences, niveau) sans relancer toute la phase.

    Met à jour :
      1. Le checkpoint LangGraph (état en mémoire)
      2. Le pipeline_state en base de données (ai_output)
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    # ── 1. Lire l'état courant du checkpoint ──────────────────
    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}
    steps    = staffing.get("steps") or {}

    # ── 2. Mettre à jour profile_extraction.result ────────────
    new_steps = {
        **steps,
        "profile_extraction": {
            **steps.get("profile_extraction", {}),
            "result": {"stories_profiles": body.stories_profiles},
        },
    }
    new_staffing = {**staffing, "steps": new_steps}

    await pm_graph.aupdate_state(
        config,
        {"staffing": new_staffing},
        as_node="node_staffing",
    )

    # ── 3. Mettre à jour pipeline_state en DB ─────────────────
    phases = await get_all_pipeline_states(project_id)
    staffing_phase = next(
        (p for p in phases if p.phase.value in (
            PipelinePhaseEnum.PHASE_8_STAFFING.value,
        )),
        None,
    )
    if staffing_phase:
        from sqlalchemy.orm.attributes import flag_modified
        async with AsyncSessionLocal() as session:
            ps = (await session.execute(
                select(PipelineState).where(PipelineState.id == staffing_phase.id)
            )).scalar_one_or_none()
            if ps:
                current_ai = dict(ps.ai_output or {})
                current_ai["staffing"] = new_staffing
                ps.ai_output = current_ai
                flag_modified(ps, "ai_output")
                await session.commit()

    return {"project_id": project_id, "updated": True, "profiles_count": len(body.stories_profiles)}


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/staffing/normalization-decisions
# ──────────────────────────────────────────────────────────────

@router.patch("/{project_id}/staffing/normalization-decisions")
async def update_normalization_decisions(
    project_id:   int,
    body:         UpdateNormalizationDecisionsRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Permet au PM de modifier les décisions accept/recruit pour chaque profil
    après la normalisation (step 2).

    Met à jour :
      1. Le checkpoint LangGraph
      2. Le pipeline_state en base de données (ai_output)
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}
    steps    = staffing.get("steps") or {}

    norm_step = steps.get("profile_normalization", {})
    if norm_step.get("status") != "done" or not norm_step.get("result"):
        raise HTTPException(400, "La normalisation des profils n'est pas encore terminée.")

    # Valider les valeurs
    for profile, decision in body.pm_decisions.items():
        if decision not in ("accept", "recruit"):
            raise HTTPException(400, f"Décision invalide '{decision}' pour '{profile}'. Valeurs acceptées : accept, recruit.")

    # Mettre à jour pm_decisions dans le résultat de normalization
    updated_norm_result = {
        **norm_step["result"],
        "pm_decisions": body.pm_decisions,
    }
    new_steps = {
        **steps,
        "profile_normalization": {
            **norm_step,
            "result": updated_norm_result,
        },
    }
    new_staffing = {**staffing, "steps": new_steps}

    await pm_graph.aupdate_state(
        config,
        {"staffing": new_staffing},
        as_node="node_staffing",
    )

    # Mettre à jour pipeline_state en DB
    phases = await get_all_pipeline_states(project_id)
    staffing_phase = next(
        (p for p in phases if p.phase.value in (
            PipelinePhaseEnum.PHASE_8_STAFFING.value,
        )),
        None,
    )
    if staffing_phase:
        from sqlalchemy.orm.attributes import flag_modified
        async with AsyncSessionLocal() as session:
            ps = (await session.execute(
                select(PipelineState).where(PipelineState.id == staffing_phase.id)
            )).scalar_one_or_none()
            if ps:
                current_ai = dict(ps.ai_output or {})
                current_ai["staffing"] = new_staffing
                ps.ai_output = current_ai
                flag_modified(ps, "ai_output")
                await session.commit()

    # Synchroniser les besoins de recrutement en base
    await _sync_recruitment_needs(
        project_id   = project_id,
        pm_decisions = body.pm_decisions,
        norm_result  = updated_norm_result,
    )

    print(f"[pipeline] ✅ décisions PM normalization mises à jour pour projet {project_id} : {body.pm_decisions}")
    return {"project_id": project_id, "updated": True, "decisions": body.pm_decisions}


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/staffing/sprint-capacities
# Permet au PM d'ajuster manuellement la capacité cible (SP) de chaque
# sprint après la répartition initiale (step 3). Re-distribue les stories
# selon les nouvelles capacités tout en conservant l'ordre final_rank.
# ──────────────────────────────────────────────────────────────

@router.patch("/{project_id}/staffing/sprint-capacities")
async def update_sprint_capacities(
    project_id:   int,
    body:         UpdateSprintCapacitiesRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Re-répartit les stories selon des capacités cible personnalisées par sprint.

    Logique :
      1. Lit le state LangGraph + résultat actuel de story_distribution
      2. Re-distribue déterministe (sans LLM) avec les nouvelles capacités
      3. Met à jour le checkpoint LangGraph + DB pipeline_state
      4. Reset les étapes aval (candidate_filtering, matching, velocity_feasibility)
         à 'pending' si elles étaient 'done' — leurs résultats sont stales
    """
    if project_id in _pm_graph_running:
        raise HTTPException(409, "Une exécution du pipeline est déjà en cours pour ce projet.")

    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}
    steps    = staffing.get("steps") or {}

    distrib_step = steps.get("story_distribution", {})
    if distrib_step.get("status") != "done" or not distrib_step.get("result"):
        raise HTTPException(400, "La répartition initiale n'est pas encore terminée.")

    distrib_result = distrib_step["result"]
    existing_sprints = distrib_result.get("sprints", []) or []

    if len(body.capacities) != len(existing_sprints):
        raise HTTPException(
            400,
            f"Nombre de capacités fournies ({len(body.capacities)}) "
            f"≠ nombre de sprints existants ({len(existing_sprints)}).",
        )
    if any(c < 1 for c in body.capacities):
        raise HTTPException(400, "Toutes les capacités doivent être ≥ 1 SP.")

    # Recalculer la distribution avec les nouvelles capacités
    from agents.pm.agents.staffing.steps.story_distribution.service import (
        redistribute_with_capacities,
    )

    stories_state    = current_state.get("stories",    []) or []
    priorities_state = current_state.get("priorities", []) or []

    stories_input = [
        {
            "story_id":     s.get("db_id") or s.get("id"),
            "db_id":        s.get("db_id"),
            "title":        s.get("title", ""),
            "story_points": s.get("story_points", 3),
        }
        for s in stories_state
        if (s.get("db_id") or s.get("id")) is not None
    ]

    try:
        new_result = redistribute_with_capacities(
            distrib_result    = distrib_result,
            stories_input     = stories_input,
            priorities        = priorities_state,
            target_capacities = body.capacities,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    # Construire les nouveaux steps : story_distribution mis à jour,
    # et les étapes aval reset à 'pending' (leurs résultats sont obsolètes)
    new_steps = {
        **steps,
        "story_distribution": {
            **distrib_step,
            "result": new_result.model_dump(),
        },
    }
    downstream = ["candidate_filtering", "matching", "velocity_feasibility"]
    reset_keys = [k for k in downstream if (steps.get(k) or {}).get("status") == "done"]
    for k in downstream:
        new_steps[k] = {"status": "pending", "result": None}

    new_staffing = {**staffing, "steps": new_steps}

    # Met à jour le checkpoint LangGraph
    await pm_graph.aupdate_state(
        config,
        {"staffing": new_staffing},
        as_node="node_staffing",
    )

    # Met à jour le pipeline_state en DB
    phases = await get_all_pipeline_states(project_id)
    staffing_phase = next(
        (p for p in phases if p.phase.value == PipelinePhaseEnum.PHASE_8_STAFFING.value),
        None,
    )
    if staffing_phase:
        from sqlalchemy.orm.attributes import flag_modified
        async with AsyncSessionLocal() as session:
            ps = (await session.execute(
                select(PipelineState).where(PipelineState.id == staffing_phase.id)
            )).scalar_one_or_none()
            if ps:
                current_ai = dict(ps.ai_output or {})
                current_ai["staffing"] = new_staffing
                ps.ai_output = current_ai
                flag_modified(ps, "ai_output")
                await session.commit()

    print(
        f"[pipeline] ✅ capacités sprint mises à jour projet {project_id} : "
        f"{body.capacities} | reset aval = {reset_keys or 'aucun'}"
    )
    return {
        "project_id":     project_id,
        "updated":        True,
        "capacities":     body.capacities,
        "result":         new_result.model_dump(),
        "downstream_reset": reset_keys,
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/staffing/restart — Réinitialise et relance
# ──────────────────────────────────────────────────────────────

_STAFFING_EMPTY_STEPS = {
    "profile_extraction":    {"status": "pending", "result": None},
    "profile_normalization": {"status": "pending", "result": None},
    "story_distribution":    {"status": "pending", "result": None},
    "candidate_filtering":   {"status": "pending", "result": None},
    "matching":              {"status": "pending", "result": None},
    "velocity_feasibility":  {"status": "pending", "result": None},
}

_STAFFING_STEP_ORDER = [
    "profile_extraction",
    "profile_normalization",
    "story_distribution",
    "candidate_filtering",
    "matching",
    "velocity_feasibility",
]


@router.post("/{project_id}/staffing/restart")
async def restart_staffing(
    project_id:   int,
    background:   BackgroundTasks,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Réinitialise et relance la phase Staffing depuis l'étape 1 (Profile Extraction).

    Utile quand la phase est en statut VALIDATED ou REJECTED en base mais que
    les sous-étapes internes sont en erreur (ex : timeout NVIDIA, rejet PM).

    Actions :
      1. Remet les steps staffing à all-pending dans le checkpoint LangGraph
      2. Remet la phase à PENDING_VALIDATION en DB
      3. Lance le graph en arrière-plan (protégé contre les doubles appels) :
           node_validate → node_staffing (sous-étapes non done) → node_validate → interrupt
    """
    # Guard : refuser si une exécution graph est déjà en cours pour ce projet
    if project_id in _pm_graph_running:
        raise HTTPException(409, "Le staffing est déjà en cours d'exécution pour ce projet.")

    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}

    # Réinitialiser UNIQUEMENT les étapes à partir de la première non-terminée
    # (l'étape en erreur ou en cours). Les étapes "done" précédentes sont
    # préservées — leurs résultats restent valides et ne sont pas re-calculés.
    existing_steps = dict(staffing.get("steps") or {})
    for k, default in _STAFFING_EMPTY_STEPS.items():
        if k not in existing_steps:
            existing_steps[k] = default.copy()

    reset_idx = next(
        (
            i for i, k in enumerate(_STAFFING_STEP_ORDER)
            if (existing_steps.get(k) or {}).get("status") != "done"
        ),
        None,
    )
    new_steps = {**existing_steps}
    if reset_idx is not None:
        for k in _STAFFING_STEP_ORDER[reset_idx:]:
            new_steps[k] = {"status": "pending", "result": None}
        print(
            f"[restart_staffing] reset à partir de '{_STAFFING_STEP_ORDER[reset_idx]}' "
            f"({len(_STAFFING_STEP_ORDER) - reset_idx} step(s))"
        )
        # Si le reset embarque le step matching → vider la matérialisation DB.
        if "matching" in _STAFFING_STEP_ORDER[reset_idx:]:
            try:
                from agents.pm.agents.staffing.steps.matching.repository import clear_assignments
                cleared = await clear_assignments(project_id)
                if cleared:
                    print(f"[restart_staffing]   ↳ {cleared} affectation(s) supprimées en DB")
            except Exception as clr_err:
                print(f"[restart_staffing] ⚠️  clear assignments échoué : {clr_err}")
    else:
        print("[restart_staffing] toutes les étapes étaient 'done' — aucun reset nécessaire")

    new_staffing = {**staffing, "steps": new_steps}

    # Injecter le nouvel état : steps réinitialisés + validation_status=validated
    # as_node="node_validate" → le graph reprend depuis le routeur de node_validate
    await pm_graph.aupdate_state(
        config,
        {
            "staffing":          new_staffing,
            "current_phase":     "staffing",
            "validation_status": "validated",
            "human_feedback":    None,
            "error":             None,
        },
        as_node="node_validate",
    )

    # Remettre le pipeline_state en PENDING_VALIDATION en DB
    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_8_STAFFING,
        status     = PipelineStatusEnum.PENDING_VALIDATION,
        ai_output  = {"staffing": new_staffing},
    )

    # Lancer l'exécution en arrière-plan pour éviter le timeout HTTP
    async def _run():
        _pm_graph_running.add(project_id)
        try:
            await pm_graph.ainvoke(None, config=config)
        except Exception as e:
            if "GraphInterrupt" not in type(e).__name__:
                print(f"[restart_staffing] erreur graph projet {project_id} : {e}")
        finally:
            _pm_graph_running.discard(project_id)

    background.add_task(_run)

    print(f"[restart_staffing] Phase Staffing réinitialisée pour projet {project_id} — exécution en arrière-plan")
    return {
        "project_id": project_id,
        "message":    "Phase Staffing réinitialisée. L'exécution reprend en arrière-plan.",
    }


# ──────────────────────────────────────────────────────────────
# GET /pipeline/{project_id}/staffing/matching
# Lecture détaillée du résultat du matching (depuis la table persistée
# + sortie complète du state pour les vues détaillées). Utilisé par le
# dashboard PM et l'écran de validation Step 5.
# ──────────────────────────────────────────────────────────────

@router.get("/{project_id}/staffing/matching")
async def get_staffing_matching(
    project_id:   int,
    current_user: dict = Depends(require_pm),
):
    """
    Retourne :
      - matching      : MatchingResult complet depuis le state LangGraph (peut être null)
      - assignments   : liste des affectations persistées en DB (vue à plat pour dashboard)
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}
    snapshot = await pm_graph.aget_state(config)

    matching_result = None
    if snapshot and snapshot.values:
        staffing = snapshot.values.get("staffing") or {}
        steps    = staffing.get("steps") or {}
        m_step   = steps.get("matching") or {}
        if m_step.get("status") == "done":
            matching_result = m_step.get("result")

    from agents.pm.agents.staffing.steps.matching.repository import get_assignments_by_project
    assignments = await get_assignments_by_project(project_id)

    return {
        "project_id":  project_id,
        "matching":    matching_result,
        "assignments": assignments,
    }


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/staffing/matching/manual-decision
# Le PM résout un manual_decision_required en choisissant l'employé.
# Met à jour le state LangGraph + recalcule les statuts story/sprint
# + met à jour la matérialisation DB.
# ──────────────────────────────────────────────────────────────

@router.patch("/{project_id}/staffing/matching/manual-decision")
async def resolve_matching_manual_decision(
    project_id:   int,
    body:         ResolveManualDecisionRequest,
    current_user: dict = Depends(require_pm),
):
    """
    Le PM tranche un manual_decision_required :
      - choisit un employee_id parmi candidate_options ;
      - le ProfileAssignment passe à status="assigned" (warning_type conservé
        si le candidat retenu était dans le groupe medium/weak — calculé d'après
        son match_level enregistré dans options) ;
      - candidate_options est vidé ;
      - story_status & sprint_status sont recalculés ;
      - la table staffing_assignments est resynchronisée.
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    # Guard : si un recalcul tourne en arrière-plan, l'état est en transition.
    if project_id in _pm_graph_running:
        raise HTTPException(
            423,
            "Un recalcul est en cours pour ce projet. "
            "Veuillez rafraîchir la page et réessayer dans quelques secondes.",
        )

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}
    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}
    steps    = staffing.get("steps") or {}
    m_step   = steps.get("matching") or {}
    if m_step.get("status") != "done" or not m_step.get("result"):
        raise HTTPException(400, "Le matching n'est pas encore terminé.")

    matching = dict(m_step["result"])
    sprint_key = f"sprint_{body.sprint_number}"
    sprint = (matching.get("matching_by_sprint") or {}).get(sprint_key)
    if not sprint:
        raise HTTPException(404, f"Sprint {body.sprint_number} introuvable.")

    # Trouver la story + le profil concerné
    target_story  = next(
        (s for s in sprint.get("story_assignments", []) if s.get("story_id") == body.story_id),
        None,
    )
    if not target_story:
        raise HTTPException(404, f"Story {body.story_id} introuvable dans sprint {body.sprint_number}.")

    target_profile_assignment = next(
        (a for a in target_story.get("assignments", [])
         if a.get("required_profile") == body.required_profile),
        None,
    )
    if not target_profile_assignment:
        raise HTTPException(404, f"Profil '{body.required_profile}' introuvable pour la story {body.story_id}.")
    current_status = target_profile_assignment.get("status")
    if current_status != "manual_decision_required":
        # Si déjà résolue avec le même employé → réponse idempotente (200)
        if current_status in ("assigned", "assigned_with_warning") and \
                target_profile_assignment.get("employee_id") == body.employee_id:
            return {
                "project_id":       project_id,
                "sprint_number":    body.sprint_number,
                "story_id":         body.story_id,
                "required_profile": body.required_profile,
                "employee_id":      body.employee_id,
                "story_status":     next(
                    (s.get("story_status") for s in sprint.get("story_assignments", [])
                     if s.get("story_id") == body.story_id),
                    "fully_assigned",
                ),
                "sprint_status":    sprint.get("sprint_status", ""),
                "already_resolved": True,
            }
        raise HTTPException(
            400,
            f"Cette affectation a le statut '{current_status}' et ne peut plus être modifiée. "
            "Rafraîchissez la page pour voir l'état actuel.",
        )

    options = target_profile_assignment.get("candidate_options", []) or []
    chosen  = next((o for o in options if o.get("employee_id") == body.employee_id), None)
    if not chosen:
        raise HTTPException(400, f"Employee {body.employee_id} ne fait pas partie des candidate_options.")

    # Calcul du nouveau status / warning selon le match_level du candidat retenu
    from agents.pm.agents.staffing.steps.matching.selection import (
        compute_sprint_status,
        compute_story_status,
        warning_for_match_level,
    )
    chosen_level = chosen.get("match_level", "good")
    if chosen_level in ("medium", "weak"):
        new_status  = "assigned_with_warning"
        new_warning = warning_for_match_level(chosen_level)
    else:
        new_status  = "assigned"
        new_warning = None

    target_profile_assignment.update({
        "employee_id":       chosen["employee_id"],
        "employee_name":     chosen.get("name"),
        "employee_seniority": chosen.get("seniority"),
        "job_title":         chosen.get("job_title"),
        "skill_score":       chosen.get("skill_score"),
        "match_level":       chosen_level,
        "matched_skills":    chosen.get("matched_skills",   []),
        "inferred_matches":  chosen.get("inferred_matches", []),
        "missing_skills":    chosen.get("missing_skills",   []),
        "status":            new_status,
        "warning_type":      new_warning,
        "candidate_options": [],
        "reason":            f"Décision PM : {chosen.get('name', '')} retenu parmi les candidats équivalents.",
    })

    # Recalcul des statuts story et sprint
    target_story["story_status"] = compute_story_status([
        a.get("status", "") for a in target_story.get("assignments", [])
    ])
    sprint["sprint_status"] = compute_sprint_status([
        s.get("story_status", "") for s in sprint.get("story_assignments", [])
    ])

    # Reconstruire les vues filtrées issues / manual_decisions du sprint
    sprint["issues"] = [
        a for s in sprint.get("story_assignments", [])
        for a in s.get("assignments", [])
        if a.get("status") in ("missing_profile", "capacity_gap", "seniority_gap", "no_available_candidate")
    ]
    sprint["manual_decisions"] = [
        a for s in sprint.get("story_assignments", [])
        for a in s.get("assignments", [])
        if a.get("status") == "manual_decision_required"
    ]

    # Recalcul global_summary (compteurs simples)
    summary = matching.get("global_summary") or {}
    sprints_iter = (matching.get("matching_by_sprint") or {}).values()
    summary["fully_staffed_sprints"]     = sum(1 for s in sprints_iter if s.get("sprint_status") == "fully_staffed")
    sprints_iter = (matching.get("matching_by_sprint") or {}).values()
    summary["partially_staffed_sprints"] = sum(1 for s in sprints_iter if s.get("sprint_status") == "partially_staffed")
    sprints_iter = (matching.get("matching_by_sprint") or {}).values()
    summary["manual_decision_sprints"]   = sum(1 for s in sprints_iter if s.get("sprint_status") == "manual_decision_required")
    sprints_iter = (matching.get("matching_by_sprint") or {}).values()
    summary["not_staffed_sprints"]       = sum(1 for s in sprints_iter if s.get("sprint_status") == "not_staffed")
    matching["global_summary"] = summary

    # Mise à jour state LangGraph
    new_steps    = {**steps, "matching": {**m_step, "result": matching}}
    new_staffing = {**staffing, "steps": new_steps}
    await pm_graph.aupdate_state(config, {"staffing": new_staffing}, as_node="node_staffing")

    # Mise à jour DB pipeline_state. Non bloquant : la source de vérité est le
    # state LangGraph mis à jour ci-dessus. Cette table est une matérialisation
    # pour les vues/lectures.
    try:
        from sqlalchemy.orm.attributes import flag_modified
        async with AsyncSessionLocal() as session:
            ps = (await session.execute(
                select(PipelineState).where(
                    PipelineState.project_id == project_id,
                    PipelineState.phase == PipelinePhaseEnum.PHASE_8_STAFFING,
                )
            )).scalar_one_or_none()
            if ps:
                current_ai = dict(ps.ai_output or {})
                current_ai["staffing"] = new_staffing
                ps.ai_output = current_ai
                flag_modified(ps, "ai_output")
                await session.commit()
    except Exception as state_err:
        import traceback
        print(
            f"[matching] ⚠️  mise à jour pipeline_state après manual decision échouée — "
            f"{type(state_err).__name__}: {state_err}"
        )
        traceback.print_exc()

    # Resynchroniser la matérialisation DB. Non bloquant : le state LangGraph
    # est la source de vérité, la table staffing_assignments sert au dashboard.
    # Si la sync échoue, l'utilisateur voit quand même sa décision appliquée.
    try:
        from agents.pm.agents.staffing.steps.matching.repository import persist_assignments
        await persist_assignments(project_id, matching)
    except Exception as persist_err:
        import traceback
        print(
            f"[matching] ⚠️  persistance DB après manual decision échouée — "
            f"{type(persist_err).__name__}: {persist_err}"
        )
        traceback.print_exc()

    print(
        f"[matching] ✅ manual decision résolue projet={project_id} "
        f"sprint={body.sprint_number} story={body.story_id} "
        f"profile='{body.required_profile}' → employee={body.employee_id}"
    )
    return {
        "project_id":       project_id,
        "sprint_number":    body.sprint_number,
        "story_id":         body.story_id,
        "required_profile": body.required_profile,
        "employee_id":      body.employee_id,
        "story_status":     target_story["story_status"],
        "sprint_status":    sprint["sprint_status"],
    }


# ──────────────────────────────────────────────────────────────
# PATCH /pipeline/{project_id}/staffing/matching/change-assignment
# Permet au PM de changer l'employé affecté à un (sprint, story, profile)
# parmi les alternative_candidates calculés par le matching automatique.
# Recompute les capacités du sprint impacté et le recommended_team.
# ──────────────────────────────────────────────────────────────

@router.patch("/{project_id}/staffing/matching/change-assignment")
async def change_matching_assignment(
    project_id:   int,
    body:         ChangeAssignmentRequest,
    current_user: dict = Depends(require_pm),
):
    """
    Le PM remplace l'employé sur une affectation existante :
      - le candidat doit faire partie des alternative_candidates ;
      - la capacité du sprint est recalculée à partir de toutes les
        affectations du sprint (l'employé sortant récupère ses SP,
        l'entrant en consomme) ;
      - story_status / sprint_status sont rafraîchis ;
      - la table staffing_assignments est resynchronisée.
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    if project_id in _pm_graph_running:
        raise HTTPException(
            423,
            "Un recalcul est en cours pour ce projet. "
            "Veuillez rafraîchir la page et réessayer dans quelques secondes.",
        )

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}
    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}
    steps    = staffing.get("steps") or {}
    m_step   = steps.get("matching") or {}
    if m_step.get("status") != "done" or not m_step.get("result"):
        raise HTTPException(400, "Le matching n'est pas encore terminé.")

    matching = dict(m_step["result"])
    sprint_key = f"sprint_{body.sprint_number}"
    sprint = (matching.get("matching_by_sprint") or {}).get(sprint_key)
    if not sprint:
        raise HTTPException(404, f"Sprint {body.sprint_number} introuvable.")

    target_story = next(
        (s for s in sprint.get("story_assignments", []) if s.get("story_id") == body.story_id),
        None,
    )
    if not target_story:
        raise HTTPException(404, f"Story {body.story_id} introuvable dans sprint {body.sprint_number}.")

    target_assignment = next(
        (a for a in target_story.get("assignments", [])
         if a.get("required_profile") == body.required_profile),
        None,
    )
    if not target_assignment:
        raise HTTPException(404, f"Profil '{body.required_profile}' introuvable pour la story {body.story_id}.")

    # Le PM ne peut changer qu'une affectation existante (pas un missing_profile).
    if target_assignment.get("status") not in ("assigned", "assigned_with_warning"):
        raise HTTPException(
            400,
            f"Cette affectation a le statut '{target_assignment.get('status')}' — "
            "elle ne peut pas être changée. Utilise 'Signaler un besoin RH' à la place.",
        )

    # Vérifier que le nouvel employé fait partie des alternatives proposées
    alternatives = target_assignment.get("alternative_candidates", []) or []
    new_candidate = next(
        (a for a in alternatives if a.get("employee_id") == body.new_employee_id),
        None,
    )
    if not new_candidate:
        raise HTTPException(
            400,
            f"L'employé {body.new_employee_id} ne fait pas partie des candidats alternatifs "
            "pour ce profil.",
        )

    # Idempotence : si on choisit déjà l'employé courant
    if target_assignment.get("employee_id") == body.new_employee_id:
        return {
            "project_id":       project_id,
            "sprint_number":    body.sprint_number,
            "story_id":         body.story_id,
            "required_profile": body.required_profile,
            "employee_id":      body.new_employee_id,
            "already_assigned": True,
            "story_status":     target_story.get("story_status", ""),
            "sprint_status":    sprint.get("sprint_status", ""),
        }

    # Calcul du nouveau status / warning selon le match_level du candidat
    from agents.pm.agents.staffing.steps.matching.selection import (
        compute_sprint_status,
        compute_story_status,
        warning_for_match_level,
        CAPACITY_BY_SENIORITY,
    )
    new_match_level = new_candidate.get("match_level", "good")
    if new_match_level in ("medium", "weak"):
        new_status  = "assigned_with_warning"
        new_warning = warning_for_match_level(new_match_level)
    else:
        new_status  = "assigned"
        new_warning = None

    # Garder seniority_downgrade_from si dégradation initiale
    downgrade = target_assignment.get("seniority_downgrade_from")
    if downgrade and new_status == "assigned":
        new_status = "assigned_with_warning"

    # Mise à jour de l'affectation
    target_assignment.update({
        "employee_id":         body.new_employee_id,
        "employee_name":       new_candidate.get("name"),
        "employee_seniority":  new_candidate.get("seniority"),
        "job_title":           new_candidate.get("job_title"),
        "skill_score":         new_candidate.get("skill_score"),
        "match_level":         new_match_level,
        "matched_skills":      new_candidate.get("matched_skills",   []),
        "inferred_matches":    new_candidate.get("inferred_matches", []),
        "missing_skills":      new_candidate.get("missing_skills",   []),
        "status":              new_status,
        "warning_type":        new_warning,
        "reason":              f"Affectation modifiée par le PM : {new_candidate.get('name', '')}.",
    })

    # Recalcul des capacités et du recommended_team du sprint à partir des
    # affectations actuelles de ce sprint.
    capacity_state: dict[int, dict] = {}
    for st in sprint.get("story_assignments", []):
        for a in st.get("assignments", []):
            eid = a.get("employee_id")
            if eid is None:
                continue
            if eid not in capacity_state:
                seniority = a.get("employee_seniority", "MID") or "MID"
                cap = CAPACITY_BY_SENIORITY.get(seniority, 8)
                capacity_state[eid] = {
                    "employee_id":           eid,
                    "name":                  a.get("employee_name", ""),
                    "job_title":             a.get("job_title", ""),
                    "seniority":             seniority,
                    "capacity_sp":           cap,
                    "assigned_sp":           0.0,
                    "remaining_capacity_sp": float(cap),
                    "stories_handled":       0,
                }
            sp = float(a.get("allocated_sp", 0.0) or 0.0)
            capacity_state[eid]["assigned_sp"]           = round(capacity_state[eid]["assigned_sp"] + sp, 4)
            capacity_state[eid]["remaining_capacity_sp"] = round(capacity_state[eid]["remaining_capacity_sp"] - sp, 4)
            if a.get("status") in ("assigned", "assigned_with_warning"):
                capacity_state[eid]["stories_handled"] += 1

    # Reconstruction du recommended_team
    sprint["recommended_team"] = [
        {
            "employee_id":           s["employee_id"],
            "name":                  s["name"],
            "job_title":             s["job_title"],
            "seniority":             s["seniority"],
            "capacity_sp":           s["capacity_sp"],
            "assigned_sp":           s["assigned_sp"],
            "remaining_capacity_sp": s["remaining_capacity_sp"],
            "stories_handled":       s["stories_handled"],
        }
        for s in capacity_state.values()
        if s["assigned_sp"] > 0
    ]

    # Recalcul story_status et sprint_status
    target_story["story_status"] = compute_story_status([
        a.get("status", "") for a in target_story.get("assignments", [])
    ])
    sprint["sprint_status"] = compute_sprint_status([
        s.get("story_status", "") for s in sprint.get("story_assignments", [])
    ])

    # Reconstruction des vues filtrées du sprint
    sprint["issues"] = [
        a for s in sprint.get("story_assignments", [])
        for a in s.get("assignments", [])
        if a.get("status") in ("missing_profile", "capacity_gap", "seniority_gap", "no_available_candidate")
    ]
    sprint["manual_decisions"] = [
        a for s in sprint.get("story_assignments", [])
        for a in s.get("assignments", [])
        if a.get("status") == "manual_decision_required"
    ]

    # Recalcul global_summary (compteurs)
    summary = matching.get("global_summary") or {}
    sprints_iter = list((matching.get("matching_by_sprint") or {}).values())
    summary["fully_staffed_sprints"]     = sum(1 for s in sprints_iter if s.get("sprint_status") == "fully_staffed")
    summary["partially_staffed_sprints"] = sum(1 for s in sprints_iter if s.get("sprint_status") == "partially_staffed")
    summary["manual_decision_sprints"]   = sum(1 for s in sprints_iter if s.get("sprint_status") == "manual_decision_required")
    summary["not_staffed_sprints"]       = sum(1 for s in sprints_iter if s.get("sprint_status") == "not_staffed")
    matching["global_summary"] = summary

    # Mise à jour state LangGraph
    new_steps    = {**steps, "matching": {**m_step, "result": matching}}
    new_staffing = {**staffing, "steps": new_steps}
    await pm_graph.aupdate_state(config, {"staffing": new_staffing}, as_node="node_staffing")

    # Mise à jour DB pipeline_state (non bloquant)
    try:
        from sqlalchemy.orm.attributes import flag_modified
        async with AsyncSessionLocal() as session:
            ps = (await session.execute(
                select(PipelineState).where(
                    PipelineState.project_id == project_id,
                    PipelineState.phase == PipelinePhaseEnum.PHASE_8_STAFFING,
                )
            )).scalar_one_or_none()
            if ps:
                current_ai = dict(ps.ai_output or {})
                current_ai["staffing"] = new_staffing
                ps.ai_output = current_ai
                flag_modified(ps, "ai_output")
                await session.commit()
    except Exception as state_err:
        import traceback
        print(f"[matching] ⚠️  pipeline_state update échouée — {type(state_err).__name__}: {state_err}")
        traceback.print_exc()

    # Resynchroniser staffing_assignments (non bloquant)
    try:
        from agents.pm.agents.staffing.steps.matching.repository import persist_assignments
        await persist_assignments(project_id, matching)
    except Exception as persist_err:
        import traceback
        print(f"[matching] ⚠️  persistance DB échouée — {type(persist_err).__name__}: {persist_err}")
        traceback.print_exc()

    print(
        f"[matching] ✅ change assignment projet={project_id} "
        f"sprint={body.sprint_number} story={body.story_id} "
        f"profile='{body.required_profile}' → employee={body.new_employee_id}"
    )
    return {
        "project_id":       project_id,
        "sprint_number":    body.sprint_number,
        "story_id":         body.story_id,
        "required_profile": body.required_profile,
        "employee_id":      body.new_employee_id,
        "story_status":     target_story["story_status"],
        "sprint_status":    sprint["sprint_status"],
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/staffing/recruitment-request
# Envoi d'une demande de recrutement à l'équipe RH (email).
# Le PM compose le contenu (To, CC, sujet, corps) côté frontend dans une UI
# type éditeur d'email. Cet endpoint envoie l'email + met à jour la table
# staffing_recruitment_needs (statut "open" + reason enrichie).
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/staffing/recruitment-request")
async def send_recruitment_request(
    project_id:   int,
    body:         RecruitmentRequestRequest,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Le PM signale un besoin RH non couvert en interne :
      - Email à l'équipe RH (et CC) avec un template HTML dédié.
      - Marque le besoin comme "open" dans staffing_recruitment_needs (idempotent).

    Côté frontend, le contenu de l'email a été pré-rempli puis ajusté par le PM
    avant l'envoi (sujet, corps, To, CC).
    """
    if not body.to:
        raise HTTPException(400, "Au moins un destinataire est requis dans le champ 'À'.")
    if not body.subject.strip():
        raise HTTPException(400, "Le sujet ne peut pas être vide.")
    if not body.body.strip():
        raise HTTPException(400, "Le corps de l'email ne peut pas être vide.")
    if not body.profile.strip():
        raise HTTPException(400, "Le profil concerné est requis.")

    # Récupérer le nom du projet
    project = (await db.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one_or_none()
    if not project:
        raise HTTPException(404, f"Projet {project_id} introuvable.")

    project_name = project.name or f"Projet #{project_id}"

    # Composer le label du sprint
    sprint_label = "—"
    if body.sprint_number:
        sprint_label = f"Sprint {body.sprint_number}"
        if body.sprint_start and body.sprint_end:
            sprint_label += f" ({body.sprint_start} → {body.sprint_end})"

    pm_name = current_user.get("name") or current_user.get("email") or None

    # Envoi : 1 email par destinataire (le SMTP gère le CC une seule fois,
    # donc on envoie au premier "to" + CC = reste des destinataires + body.cc).
    primary_to = body.to[0]
    extra_recipients = body.to[1:] + (body.cc or [])

    from utils.email import send_recruitment_request_email
    try:
        send_recruitment_request_email(
            to_email     = primary_to,
            subject      = body.subject,
            body         = body.body,
            project_name = project_name,
            profile      = body.profile,
            seniority    = body.required_level or "—",
            sprint_label = sprint_label,
            skills       = body.required_skills or [],
            pm_name      = pm_name,
            cc_emails    = extra_recipients or None,
        )
    except Exception as e:
        print(f"[recruitment-request] ❌ envoi email échoué : {e}")
        raise HTTPException(502, f"Échec de l'envoi de l'email : {e}")

    # Mise à jour staffing_recruitment_needs (idempotent)
    try:
        from app.database.models.pm.staffing_recruitment_need import StaffingRecruitmentNeed
        from sqlalchemy import select as sa_select
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                sa_select(StaffingRecruitmentNeed).where(
                    StaffingRecruitmentNeed.project_id       == project_id,
                    StaffingRecruitmentNeed.required_profile == body.profile,
                )
            )).scalar_one_or_none()
            enriched_reason = (
                f"Demande RH envoyée par {pm_name or 'le PM'} pour {sprint_label}. "
                + (body.body[:240] + "…" if len(body.body) > 240 else body.body)
            )
            if row:
                row.status = "open"
                row.reason = enriched_reason
            else:
                session.add(StaffingRecruitmentNeed(
                    project_id           = project_id,
                    required_profile     = body.profile,
                    suggested_job_titles = [],
                    reason               = enriched_reason,
                    status               = "open",
                ))
            await session.commit()
    except Exception as persist_err:
        # Non bloquant — l'email a été envoyé.
        print(f"[recruitment-request] ⚠️  upsert staffing_recruitment_needs échoué : {persist_err}")

    print(
        f"[recruitment-request] ✅ projet={project_id} profil='{body.profile}' "
        f"→ {primary_to} (cc: {len(extra_recipients)}) — {sprint_label}"
    )
    return {
        "project_id":  project_id,
        "profile":     body.profile,
        "to":          body.to,
        "cc":          body.cc or [],
        "sprint":      sprint_label,
        "sent":        True,
    }


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/staffing/matching/rerun
# Relance UNIQUEMENT le matching (Step 5) sans toucher aux étapes amont.
# Utile quand le PM a fait recruter un nouveau profil et veut voir si le
# matching est désormais résolu sans re-tourner toute la phase.
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/staffing/matching/rerun")
async def rerun_matching(
    project_id:   int,
    background:   BackgroundTasks,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Relance le step Matching (et velocity_feasibility en aval) sans réinitialiser
    profile_extraction / normalization / story_distribution / candidate_filtering.

    Utile après ajout RH d'un nouveau profil en base : le PM clique pour voir
    si le matching résout les manques précédents.

    Pré-condition : candidate_filtering doit être à status='done'.
    Sinon : 400.
    """
    if project_id in _pm_graph_running:
        raise HTTPException(409, "Le staffing est déjà en cours d'exécution pour ce projet.")

    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}
    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    current_state: dict = dict(snapshot.values)
    staffing = current_state.get("staffing") or {}
    steps    = staffing.get("steps") or {}

    if (steps.get("candidate_filtering") or {}).get("status") != "done":
        raise HTTPException(
            400,
            "Le filtrage des candidats doit être terminé avant de relancer le matching.",
        )

    # Reset matching + velocity_feasibility uniquement
    new_steps = {
        **steps,
        "matching":             {"status": "pending", "result": None},
        "velocity_feasibility": {"status": "pending", "result": None},
    }
    new_staffing = {**staffing, "steps": new_steps}

    # Vider la matérialisation DB (idempotent)
    try:
        from agents.pm.agents.staffing.steps.matching.repository import clear_assignments
        cleared = await clear_assignments(project_id)
        if cleared:
            print(f"[rerun_matching]   ↳ {cleared} affectation(s) supprimées en DB")
    except Exception as clr_err:
        print(f"[rerun_matching] ⚠️  clear assignments échoué : {clr_err}")

    # Injecter le nouvel état + repasser en "validated" pour retourner dans node_validate
    # qui re-routera vers node_staffing (matching pending) → recalcul.
    await pm_graph.aupdate_state(
        config,
        {
            "staffing":          new_staffing,
            "current_phase":     "staffing",
            "validation_status": "validated",
            "human_feedback":    None,
            "error":             None,
        },
        as_node="node_validate",
    )

    # Repasser le pipeline_state en PENDING_VALIDATION
    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_8_STAFFING,
        status     = PipelineStatusEnum.PENDING_VALIDATION,
        ai_output  = {"staffing": new_staffing},
    )

    async def _run():
        _pm_graph_running.add(project_id)
        try:
            await pm_graph.ainvoke(None, config=config)
        except Exception as e:
            if "GraphInterrupt" not in type(e).__name__:
                print(f"[rerun_matching] erreur graph projet {project_id} : {e}")
        finally:
            _pm_graph_running.discard(project_id)

    background.add_task(_run)

    print(f"[rerun_matching] ✅ matching relancé pour projet {project_id} — exécution en arrière-plan")
    return {
        "project_id": project_id,
        "message":    "Matching relancé. L'analyse reprend en arrière-plan.",
    }


async def _sync_recruitment_needs(
    project_id:   int,
    pm_decisions: dict[str, str],
    norm_result:  dict,
) -> None:
    """
    Synchronise la table staffing_recruitment_needs selon les décisions PM :
    - "recruit" → créer ou remettre à "open"
    - "accept"  → passer à "cancelled" si un besoin ouvert existe
    """
    from app.database.models.pm.staffing_recruitment_need import StaffingRecruitmentNeed
    from sqlalchemy import select as sa_select

    # Construire un index profil → mapping pour récupérer les suggested_job_titles et reason
    mappings_index: dict[str, dict] = {
        m["required_profile"]: m
        for m in norm_result.get("profile_mappings", [])
        if isinstance(m, dict) and "required_profile" in m
    }

    async with AsyncSessionLocal() as session:
        for profile, decision in pm_decisions.items():
            row = (await session.execute(
                sa_select(StaffingRecruitmentNeed).where(
                    StaffingRecruitmentNeed.project_id       == project_id,
                    StaffingRecruitmentNeed.required_profile == profile,
                )
            )).scalar_one_or_none()

            mapping = mappings_index.get(profile, {})
            suggested = mapping.get("matched_job_titles", [])
            reason    = mapping.get("reason", "") or f"Profil '{profile}' non couvert en interne."

            if decision == "recruit":
                if row:
                    row.status               = "open"
                    row.suggested_job_titles = suggested
                    row.reason               = reason
                else:
                    session.add(StaffingRecruitmentNeed(
                        project_id           = project_id,
                        required_profile     = profile,
                        suggested_job_titles = suggested,
                        reason               = reason,
                        status               = "open",
                    ))
            elif decision == "accept" and row and row.status == "open":
                row.status = "cancelled"

        await session.commit()
    print(f"[pipeline] recruitment_needs synchronisés pour projet {project_id}")


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

    syncable = {"epics", "stories", "story_deps", "cpm", "sprints"}
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

    # ── 4b. Pour les phases epics/stories : charger depuis la DB ─
    # Les objets ajoutés manuellement sont en DB mais PAS dans le checkpoint
    # LangGraph. On remplace avec les données fraîches DB.
    if phase == "stories":
        db_stories_fresh = await get_all_stories_as_dicts(project_id)
        if db_stories_fresh:
            state_for_sync = {**state_for_sync, "stories": db_stories_fresh}
            print(f"[JIRA RESYNC] stories override: {len(db_stories_fresh)} stories depuis DB (vs {len(current_state.get('stories') or [])} dans checkpoint)")

    elif phase == "epics":
        db_epics_fresh = await get_epics(project_id)
        epics_formatted = [
            {
                "db_id":              e.id,
                "title":              e.title,
                "description":        e.description or "",
                "splitting_strategy": e.splitting_strategy or "by_feature",
            }
            for e in db_epics_fresh
        ]
        if epics_formatted:
            state_for_sync = {**state_for_sync, "epics": epics_formatted}
            print(f"[JIRA RESYNC] epics override: {len(epics_formatted)} epics depuis DB (vs {len(current_state.get('epics') or [])} dans checkpoint)")

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
# POST /pipeline/{project_id}/prioritization/rerun — Relance la priorisation
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/prioritization/rerun")
async def rerun_prioritization(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Relance l'algorithme de priorisation sans toucher au reste du pipeline.
    Utile après modification des story_points ou des dépendances.
    """
    pm_graph = get_pm_graph()
    if pm_graph is None:
        raise HTTPException(503, "Le pipeline PM n'est pas initialisé.")

    config = {"configurable": {"thread_id": f"pm_{project_id}"}}

    snapshot = await pm_graph.aget_state(config)
    if not snapshot or not snapshot.values:
        raise HTTPException(404, "Aucun état pipeline trouvé pour ce projet.")

    state: dict = dict(snapshot.values)

    # Remplacer stories par les données fraîches depuis la DB
    db_stories = await get_all_stories_as_dicts(project_id)
    if db_stories:
        state = {**state, "stories": db_stories}

    from agents.pm.agents.prioritization.algorithme import node_prioritization
    try:
        patch = await node_prioritization(state)
    except Exception as e:
        raise HTTPException(500, f"Erreur lors de la priorisation : {str(e)}")

    # Mettre à jour le checkpoint LangGraph
    await pm_graph.aupdate_state(config, patch, as_node="node_prioritization")

    # Mettre à jour la DB pipeline_state
    prio_phase = next(
        (p for p in await get_all_pipeline_states(project_id)
         if p.phase.value == PipelinePhaseEnum.PHASE_5_PRIORITIZATION.value),
        None,
    )
    current_ai_output = (prio_phase.ai_output or {}) if prio_phase else {}
    await upsert_pipeline_state(
        project_id = project_id,
        phase      = PipelinePhaseEnum.PHASE_5_PRIORITIZATION,
        status     = PipelineStatusEnum.PENDING_VALIDATION,
        ai_output  = {**current_ai_output, "priorities": patch.get("priorities", [])},
    )

    return {
        "project_id": project_id,
        "priorities": patch.get("priorities", []),
        "message":    "Priorisation recalculée avec succès.",
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
        DELETE FROM project_management.story_dependencies
        WHERE story_id IN (
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
    db:           AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_pm),
):
    """Modifie les champs éditables d'une user story et synchronise ai_output."""
    updates = body.model_dump(exclude_none=True)
    found   = await update_story(story_id, updates)
    if not found:
        raise HTTPException(404, f"Story {story_id} introuvable.")

    # Récupère project_id pour sync ai_output
    result = await db.execute(
        select(UserStory, Epic.project_id)
        .join(Epic, UserStory.epic_id == Epic.id)
        .where(UserStory.id == story_id)
    )
    row = result.first()
    if row:
        await _sync_stories_to_ai_output(row[1])

    return {"story_id": story_id, "updated": True}


# ──────────────────────────────────────────────────────────────
# DELETE /pipeline/stories/{story_id} — Supprimer une story
# ──────────────────────────────────────────────────────────────

@router.delete("/stories/{story_id}")
async def delete_story_endpoint(
    story_id:     int,
    db:           AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_pm),
):
    """Supprime définitivement une user story et synchronise ai_output."""
    # Récupère project_id AVANT suppression
    result = await db.execute(
        select(UserStory, Epic.project_id)
        .join(Epic, UserStory.epic_id == Epic.id)
        .where(UserStory.id == story_id)
    )
    row = result.first()
    if not row:
        raise HTTPException(404, f"Story {story_id} introuvable.")
    project_id = row[1]

    found = await delete_story(story_id)
    if not found:
        raise HTTPException(404, f"Story {story_id} introuvable.")

    await _sync_stories_to_ai_output(project_id)
    return {"story_id": story_id, "deleted": True}


# ──────────────────────────────────────────────────────────────
# POST /pipeline/{project_id}/stories — Ajouter une story manuellement
# ──────────────────────────────────────────────────────────────

@router.post("/{project_id}/stories")
async def create_story_endpoint(
    project_id:   int,
    body:         StoryCreateRequest,
    current_user: dict = Depends(require_pm),
):
    """Crée manuellement une user story dans un epic donné (par son index 0-based)."""
    import json as _json
    from app.database.models.pm.enums import StoryStatusEnum

    async with AsyncSessionLocal() as session:
        # Récupère l'epic cible par index 0-based
        epics_result = await session.execute(
            select(Epic)
            .where(Epic.project_id == project_id)
            .order_by(Epic.id)
        )
        db_epics = epics_result.scalars().all()
        if body.epic_idx < 0 or body.epic_idx >= len(db_epics):
            raise HTTPException(400, f"epic_idx {body.epic_idx} invalide pour ce projet.")
        target_epic = db_epics[body.epic_idx]

        ac = body.acceptance_criteria or []
        new_story = UserStory(
            epic_id             = target_epic.id,
            title               = body.title,
            description         = body.description,
            story_points        = body.story_points,
            splitting_strategy  = target_epic.splitting_strategy or "by_feature",
            acceptance_criteria = _json.dumps(ac, ensure_ascii=False),
            status              = StoryStatusEnum.GENERATED,
            ai_metadata         = {"source": "manual"},
        )
        session.add(new_story)
        await session.commit()
        await session.refresh(new_story)
        new_id = new_story.id

    await _sync_stories_to_ai_output(project_id)

    return {
        "db_id":               new_id,
        "epic_idx":            body.epic_idx,
        "title":               body.title,
        "description":         body.description,
        "story_points":        body.story_points,
        "acceptance_criteria": ac,
        "splitting_strategy":  target_epic.splitting_strategy or "by_feature",
    }


# ══════════════════════════════════════════════════════════════
# EPICS CRUD
# ══════════════════════════════════════════════════════════════

class EpicUpdateRequest(BaseModel):
    title:              Optional[str] = None
    description:        Optional[str] = None
    splitting_strategy: Optional[str] = None

class EpicCreateRequest(BaseModel):
    title:              str
    description:        str = ""
    splitting_strategy: str = "by_feature"


async def _sync_stories_to_ai_output(project_id: int) -> None:
    """
    Relit les stories DB et met à jour ai_output de la phase stories dans pipeline_state.
    Préserve les champs _review (calculés par LLM, absents de la table user_stories).
    Appelé après chaque CRUD sur les stories pour que le dashboard reste cohérent.
    """
    db_stories = await get_all_stories_as_dicts(project_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PipelineState)
            .where(PipelineState.project_id == project_id)
            .where(PipelineState.phase == PipelinePhaseEnum.PHASE_3_STORIES)
            .order_by(PipelineState.id.desc())
            .limit(1)
        )
        ps = result.scalar_one_or_none()
        if not ps:
            return

        # Préserve _review depuis l'ancien snapshot (absent de la DB)
        review_map: dict[int, dict] = {}
        for s in (ps.ai_output or {}).get("stories", []):
            if s.get("db_id") and s.get("_review"):
                review_map[int(s["db_id"])] = s["_review"]

        for s in db_stories:
            db_id = s.get("db_id")
            if db_id and db_id in review_map:
                s["_review"] = review_map[db_id]

        from sqlalchemy.orm.attributes import flag_modified
        current = dict(ps.ai_output or {})
        current["stories"] = db_stories
        ps.ai_output = current
        flag_modified(ps, "ai_output")
        await session.commit()


async def _sync_epics_to_ai_output(project_id: int, db: AsyncSession) -> None:
    """Relit les epics DB et met à jour ai_output de la phase epics en pipeline_state."""
    db_epics = await get_epics(project_id)
    epics_list = [
        {
            "db_id":              e.id,
            "title":              e.title,
            "description":        e.description or "",
            "splitting_strategy": e.splitting_strategy or "by_feature",
        }
        for e in db_epics
    ]
    result = await db.execute(
        select(PipelineState)
        .where(PipelineState.project_id == project_id)
        .where(PipelineState.phase == PipelinePhaseEnum.PHASE_2_EPICS)
        .order_by(PipelineState.id.desc())
        .limit(1)
    )
    ps = result.scalar_one_or_none()
    if ps:
        current = dict(ps.ai_output or {})
        current["epics"] = epics_list
        ps.ai_output = current
        await db.commit()


@router.get("/{project_id}/epics")
async def get_project_epics(
    project_id:   int,
    current_user: dict = Depends(require_pm),
):
    """Retourne les epics du projet avec leurs db_id."""
    db_epics = await get_epics(project_id)
    return [
        {
            "db_id":              e.id,
            "title":              e.title,
            "description":        e.description or "",
            "splitting_strategy": e.splitting_strategy or "by_feature",
        }
        for e in db_epics
    ]


@router.put("/epics/{epic_id}")
async def update_epic_endpoint(
    epic_id:      int,
    body:         EpicUpdateRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_pm),
):
    """Modifie le titre, la description ou la stratégie d'un epic."""
    found = await update_epic(epic_id, body.model_dump(exclude_none=True))
    if not found:
        raise HTTPException(404, f"Epic {epic_id} introuvable.")

    # Récupérer project_id depuis la DB pour sync ai_output
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()
    if epic:
        await _sync_epics_to_ai_output(epic.project_id, db)

    return {"epic_id": epic_id, "updated": True}


@router.delete("/epics/{epic_id}")
async def delete_epic_endpoint(
    epic_id:      int,
    db:           AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_pm),
):
    """Supprime un epic (et ses stories en cascade)."""
    result = await db.execute(select(Epic).where(Epic.id == epic_id))
    epic = result.scalar_one_or_none()
    if not epic:
        raise HTTPException(404, f"Epic {epic_id} introuvable.")
    project_id = epic.project_id

    found = await delete_epic(epic_id)
    if not found:
        raise HTTPException(404, f"Epic {epic_id} introuvable.")

    await _sync_epics_to_ai_output(project_id, db)
    return {"epic_id": epic_id, "deleted": True}


@router.post("/{project_id}/epics")
async def add_epic_endpoint(
    project_id:   int,
    body:         EpicCreateRequest,
    db:           AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_pm),
):
    """Ajoute un nouvel epic au projet."""
    orm_e = await add_epic(project_id, body.model_dump())
    await _sync_epics_to_ai_output(project_id, db)
    return {
        "epic_id":           orm_e.id,
        "title":             orm_e.title,
        "description":       orm_e.description,
        "splitting_strategy": orm_e.splitting_strategy,
    }


# ──────────────────────────────────────────────────────────────
# GET  /pipeline/{project_id}/story-dependencies — Lire les dépendances
# PUT  /pipeline/{project_id}/story-dependencies — Sauvegarder les dépendances éditées
# ──────────────────────────────────────────────────────────────

class StoryDependencyItem(BaseModel):
    from_story_id:   int
    to_story_id:     int
    dependency_type: str = "functional"
    relation_type:   str = "FS"
    is_blocking:     bool = True
    level:           str = "intra_epic"
    reason:          str = ""

class UpdateStoryDepsRequest(BaseModel):
    dependencies: list[StoryDependencyItem]


@router.get("/{project_id}/story-dependencies")
async def list_story_dependencies(
    project_id:   int,
    current_user: dict = Depends(require_pm),
):
    """Retourne toutes les dépendances entre stories du projet."""
    from agents.pm.agents.dependencies.repository import get_story_dependencies
    deps = await get_story_dependencies(project_id)
    return deps


@router.put("/{project_id}/story-dependencies")
async def update_story_dependencies(
    project_id:   int,
    body:         UpdateStoryDepsRequest,
    current_user: dict = Depends(require_pm),
):
    """
    Remplace toutes les dépendances du projet par celles envoyées.
    Appelé quand l'utilisateur valide ses modifications manuelles dans le tableau.
    Synchronise aussi pipeline_state.ai_output pour PHASE_4_STORY_DEPS.
    """
    from agents.pm.agents.dependencies.repository import save_story_dependencies
    deps_list = [d.model_dump() for d in body.dependencies]
    await save_story_dependencies(project_id, deps_list)
    await _sync_story_deps_to_ai_output(project_id)
    return {"saved": len(deps_list)}


async def _sync_story_deps_to_ai_output(project_id: int) -> None:
    """
    Relit les dépendances DB et met à jour ai_output de la phase story_deps.
    Garantit que le dashboard affiche les modifications manuelles après refresh.
    """
    from agents.pm.agents.dependencies.repository import get_story_dependencies
    db_deps = await get_story_dependencies(project_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PipelineState)
            .where(PipelineState.project_id == project_id)
            .where(PipelineState.phase == PipelinePhaseEnum.PHASE_4_STORY_DEPS)
            .order_by(PipelineState.id.desc())
            .limit(1)
        )
        ps = result.scalar_one_or_none()
        if not ps:
            return

        from sqlalchemy.orm.attributes import flag_modified
        current = dict(ps.ai_output or {})
        current["story_dependencies"] = db_deps
        ps.ai_output = current
        flag_modified(ps, "ai_output")
        await session.commit()


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
