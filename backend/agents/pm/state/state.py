# agents/pm/state/state.py
# ═══════════════════════════════════════════════════════════════
# State du pipeline PM — LangGraph TypedDict
#
# Ce fichier définit PMPipelineState, le dictionnaire d'état
# qui circule entre tous les noeuds du graph PM.
#
# Chaque noeud lit les champs dont il a besoin et écrit
# uniquement les champs qu'il produit.
#
# Organisation :
#   - Input         : données reçues au lancement du pipeline
#   - Phases 2→12   : résultats produits par chaque noeud
#   - Contrôle      : suivi de la phase courante + DB
#   - Validation    : human-in-the-loop (interrupt LangGraph)
#   - Jira sync     : mapping IDs locaux ↔ clés Jira
#   - Erreur        : message d'erreur si un noeud échoue
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
from typing import TypedDict, Optional


# ──────────────────────────────────────────────────────────────
# STATE PRINCIPAL
# ──────────────────────────────────────────────────────────────

class PMPipelineState(TypedDict):

    # ╔══════════════════════════════════════════════════════╗
    # ║  INPUT — fourni au lancement du pipeline            ║
    # ║  (depuis POST /pipeline/{id}/start)                 ║
    # ╚══════════════════════════════════════════════════════╝

    project_id: int
    user_id: int

    # ID du document CDC dans project_management.project_documents
    # node_extraction SELECT file_path FROM project_documents WHERE id = document_id
    document_id: int

    # Texte brut extrait du CDC — rempli par node_extraction
    # Utilisé par tous les nodes LLM suivants (epics, stories, etc.)
    cdc_text: str


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 2 — Epics                                    ║
    # ║  Produit par : agents/epics/agent.py                ║
    # ╚══════════════════════════════════════════════════════╝

    epics: list[dict]
    # Structure d'un epic :
    # {
    #   "title":              str,
    #   "description":        str,
    #   "splitting_strategy": str   — "by_feature" | "by_user_role"
    #                               — "by_workflow_step" | "by_component"
    # }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 3 — User Stories                             ║
    # ║  Produit par : agents/stories/agent.py              ║
    # ║  L'agent utilise epic.splitting_strategy pour       ║
    # ║  adapter la granularité du découpage                ║
    # ╚══════════════════════════════════════════════════════╝

    stories: list[dict]
    # Structure d'une story :
    # {
    #   "epic_id":              int,
    #   "title":                str,        — "En tant que X, je veux Y..."
    #   "description":          str,
    #   "story_points":         int,        — suite Fibonacci : 1,2,3,5,8,13
    #   "acceptance_criteria":  list[str],  — générés ici (PAS dans les epics)
    #   "splitting_strategy":   str         — hérité de l'epic parent
    # }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 4 — Raffinement PO ↔ Tech Lead               ║
    # ║  Produit par : agents/refinement/                   ║
    # ║  Pattern multi-agent : débat en N rounds (max 3)    ║
    # ╚══════════════════════════════════════════════════════╝

    refinement_rounds: list[dict]
    # Structure d'un round :
    # {
    #   "round":         int,
    #   "po_comment":    str,
    #   "tech_comment":  str,
    #   "stories_patch": list[dict]
    # }

    refined_stories: list[dict]
    # Stories après consensus PO ↔ Tech Lead (même structure que stories)


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 5 — Dépendances entre User Stories           ║
    # ╚══════════════════════════════════════════════════════╝

    story_dependencies: list[dict]
    # { "story_id": int, "depends_on_id": int }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 6 — Priorisation MoSCoW                      ║
    # ╚══════════════════════════════════════════════════════╝

    priorities: list[dict]
    # { "story_id": int, "moscow": str, "value_score": float, "final_rank": int }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 7 — Tasks                                    ║
    # ╚══════════════════════════════════════════════════════╝

    tasks: list[dict]
    # {
    #   "story_id": int, "title": str, "description": str,
    #   "duration_days": int,
    #   "task_type": str   — "frontend"|"backend"|"design"|"devops"|"qa"|"other"
    # }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 8 — Dépendances entre Tasks                  ║
    # ╚══════════════════════════════════════════════════════╝

    task_dependencies: list[dict]
    # { "task_id": int, "depends_on_id": int }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 9 — Critical Path Method (CPM)               ║
    # ╚══════════════════════════════════════════════════════╝

    cpm_result: dict
    # { task_idx → { "earliest_start": float, "latest_start": float,
    #                "slack": float, "is_critical": bool } }

    critical_path: list[int]
    # Index des tasks sur le chemin critique (slack == 0)


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 10 — Sprint Planning                         ║
    # ╚══════════════════════════════════════════════════════╝

    sprints: list[dict]
    # {
    #   "name": str, "goal": str, "start_date": str, "end_date": str,
    #   "story_ids": list[int], "task_ids": list[int]
    # }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 11 — Staffing                                ║
    # ╚══════════════════════════════════════════════════════╝

    staffing: dict
    # { task_idx (int) → employee_id (int) }


    # ╔══════════════════════════════════════════════════════╗
    # ║  PHASE 12 — Monitoring continu                      ║
    # ╚══════════════════════════════════════════════════════╝

    monitoring_plan: dict
    # {
    #   "kpis": list[dict], "alerts": list[dict],
    #   "review_frequency": str, "jira_webhooks": list[str]
    # }


    # ╔══════════════════════════════════════════════════════╗
    # ║  CONTRÔLE DU PIPELINE                              ║
    # ╚══════════════════════════════════════════════════════╝

    # Nom de la phase en cours
    # "extract"|"epics"|"stories"|"refinement"|"story_deps"|
    # "prioritization"|"tasks"|"task_deps"|"cpm"|"sprints"|"staffing"|"monitoring"
    current_phase: str

    pipeline_state_id: int


    # ╔══════════════════════════════════════════════════════╗
    # ║  VALIDATION HUMAINE — phases 2 → 11                 ║
    # ╚══════════════════════════════════════════════════════╝

    # "pending_ai" | "pending_human" | "validated" | "rejected"
    validation_status: str

    human_feedback: Optional[str]


    # ╔══════════════════════════════════════════════════════╗
    # ║  JIRA SYNC                                          ║
    # ╚══════════════════════════════════════════════════════╝

    jira_project_key: str
    jira_epic_map: dict       # { local_epic_idx: jira_epic_key }
    jira_story_map: dict      # { local_story_idx: jira_issue_key }
    jira_task_map: dict       # { local_task_idx: jira_subtask_key }
    jira_sprint_map: dict     # { local_sprint_idx: jira_sprint_id }
    jira_synced_phases: list[str]


    # ╔══════════════════════════════════════════════════════╗
    # ║  ERREUR                                             ║
    # ╚══════════════════════════════════════════════════════╝

    error: Optional[str]
