# agents/pm/graph/graph.py
# ═══════════════════════════════════════════════════════════════
# Graph LangGraph du pipeline PM — 12 phases
#
# Flux complet :
#   extraction (pas de validation)
#       → epics → validate → jira_sync
#       → stories → validate → jira_sync
#       → refinement → validate → jira_sync
#       → story_deps → validate → jira_sync
#       → prioritization → validate → jira_sync
#       → tasks → validate → jira_sync
#       → task_deps → validate → jira_sync
#       → cpm → validate → jira_sync
#       → sprints → validate → jira_sync
#       → staffing → validate → jira_sync
#       → monitoring → END (pas de validation)
#
# Persistance :
#   AsyncPostgresSaver (même pattern que app/orchestrator/graph.py)
#   thread_id = str(project_id) → permet la reprise après interrupt()
# ═══════════════════════════════════════════════════════════════

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from dotenv import load_dotenv
import psycopg
import os

from agents.pm.state import PMPipelineState
from agents.pm.graph.node_validate import node_validate

# Agents — chaque dossier expose la fonction noeud principale
from agents.pm.agents.extraction.agent  import node_extraction
from agents.pm.agents.epics.agent       import node_epics
from agents.pm.agents.stories.agent     import node_stories
from agents.pm.agents.refinement.agent  import node_refinement
from agents.pm.agents.dependencies.story_deps import node_story_deps
from agents.pm.agents.dependencies.task_deps  import node_task_deps
from agents.pm.agents.prioritization.agent    import node_prioritization
from agents.pm.agents.tasks.agent       import node_tasks
from agents.pm.agents.cpm.agent         import node_cpm
from agents.pm.agents.sprints.agent     import node_sprints
from agents.pm.agents.staffing.agent    import node_staffing
from agents.pm.agents.monitoring.agent  import node_monitoring
from agents.pm.graph.node_jira_sync     import node_jira_sync

load_dotenv()

DB_URI = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'password')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'talan_assistant')}"
    f"?sslmode=disable"
)

# Instance globale — None jusqu'à init_pm_graph()
pm_graph = None


# ──────────────────────────────────────────────────────────────
# ROUTEURS
# ──────────────────────────────────────────────────────────────

_PHASE_ORDER = [
    "extract", "epics", "stories", "refinement",
    "story_deps", "prioritization", "tasks", "task_deps",
    "cpm", "sprints", "staffing", "monitoring",
]

_PHASE_TO_NODE: dict[str, str] = {
    "extract":        "node_extraction",
    "epics":          "node_epics",
    "stories":        "node_stories",
    "refinement":     "node_refinement",
    "story_deps":     "node_story_deps",
    "prioritization": "node_prioritization",
    "tasks":          "node_tasks",
    "task_deps":      "node_task_deps",
    "cpm":            "node_cpm",
    "sprints":        "node_sprints",
    "staffing":       "node_staffing",
    "monitoring":     "node_monitoring",
}


def _next_phase(current: str) -> str:
    try:
        idx = _PHASE_ORDER.index(current)
        if idx + 1 < len(_PHASE_ORDER):
            return _PHASE_ORDER[idx + 1]
    except ValueError:
        pass
    return END


def _route_after_validate(state: PMPipelineState) -> str:
    """
    - validated → jira_sync → phase suivante
    - rejected  → retour à la phase courante (relance avec human_feedback)
    """
    if state.get("validation_status") == "validated":
        return "jira_sync"
    phase = state.get("current_phase", "")
    return _PHASE_TO_NODE.get(phase, END)


def _route_after_jira_sync(state: PMPipelineState) -> str:
    """Passe à la phase suivante selon current_phase."""
    phase = state.get("current_phase", "")
    next_phase = _next_phase(phase)
    return _PHASE_TO_NODE.get(next_phase, END)


# ──────────────────────────────────────────────────────────────
# CONSTRUCTION DU GRAPH
# ──────────────────────────────────────────────────────────────

def build_pm_graph(checkpointer=None):
    """
    Construit et compile le graph LangGraph du pipeline PM.
    checkpointer : AsyncPostgresSaver en prod, MemorySaver en dev.
    """
    graph = StateGraph(PMPipelineState)

    # ── Enregistrement des noeuds ──────────────────────────────
    graph.add_node("node_extraction",    node_extraction)
    graph.add_node("node_epics",         node_epics)
    graph.add_node("node_stories",       node_stories)
    graph.add_node("node_refinement",    node_refinement)
    graph.add_node("node_story_deps",    node_story_deps)
    graph.add_node("node_prioritization",node_prioritization)
    graph.add_node("node_tasks",         node_tasks)
    graph.add_node("node_task_deps",     node_task_deps)
    graph.add_node("node_cpm",           node_cpm)
    graph.add_node("node_sprints",       node_sprints)
    graph.add_node("node_staffing",      node_staffing)
    graph.add_node("node_monitoring",    node_monitoring)
    graph.add_node("node_validate",      node_validate)
    graph.add_node("jira_sync",          node_jira_sync)

    # ── Point d'entrée ────────────────────────────────────────
    graph.set_entry_point("node_extraction")

    # ── Phases 1→11 : chaque phase → node_validate ────────────
    for phase_node in [
        "node_extraction",
        "node_epics", "node_stories", "node_refinement",
        "node_story_deps", "node_prioritization", "node_tasks",
        "node_task_deps", "node_cpm", "node_sprints", "node_staffing",
    ]:
        graph.add_edge(phase_node, "node_validate")

    # ── node_validate → jira_sync (validé) ou retour phase (rejeté) ─
    graph.add_conditional_edges(
        "node_validate",
        _route_after_validate,
        {
            "jira_sync":           "jira_sync",
            "node_extraction":     "node_extraction",   # rejet extraction
            "node_epics":          "node_epics",
            "node_stories":        "node_stories",
            "node_refinement":     "node_refinement",
            "node_story_deps":     "node_story_deps",
            "node_prioritization": "node_prioritization",
            "node_tasks":          "node_tasks",
            "node_task_deps":      "node_task_deps",
            "node_cpm":            "node_cpm",
            "node_sprints":        "node_sprints",
            "node_staffing":       "node_staffing",
        }
    )

    # ── jira_sync → phase suivante ────────────────────────────
    graph.add_conditional_edges(
        "jira_sync",
        _route_after_jira_sync,
        {
            "node_epics":          "node_epics",        # après validation extraction
            "node_stories":        "node_stories",
            "node_refinement":     "node_refinement",
            "node_story_deps":     "node_story_deps",
            "node_prioritization": "node_prioritization",
            "node_tasks":          "node_tasks",
            "node_task_deps":      "node_task_deps",
            "node_cpm":            "node_cpm",
            "node_sprints":        "node_sprints",
            "node_staffing":       "node_staffing",
            "node_monitoring":     "node_monitoring",
        }
    )

    # ── Phase 12 → END (pas de validation ni sync Jira) ───────
    graph.add_edge("node_monitoring", END)

    return graph.compile(checkpointer=checkpointer)


# ──────────────────────────────────────────────────────────────
# INITIALISATION
# ──────────────────────────────────────────────────────────────

async def init_pm_graph():
    """
    Initialise le graph PM avec AsyncPostgresSaver.
    Appelée au démarrage du serveur FastAPI (lifespan).
    """
    global pm_graph
    print("Initialisation du graph PM (pipeline project management)...")
    conn = await psycopg.AsyncConnection.connect(DB_URI, autocommit=True)
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()
    pm_graph = build_pm_graph(checkpointer)
    print("Graph PM pret.")


def get_pm_graph():
    """Retourne l'instance compilée du graph PM."""
    return pm_graph
