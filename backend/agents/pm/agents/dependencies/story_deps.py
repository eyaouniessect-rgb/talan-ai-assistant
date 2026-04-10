# agents/pm/agents/dependencies/story_deps.py
# Phase 5 — Dépendances entre User Stories
# STUB — implémentation complète à venir.

from agents.pm.state import PMPipelineState


async def node_story_deps(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 5 : analyse des dépendances entre stories.

    Le LLM identifie les relations de précédence :
      story B ne peut démarrer que si story A est terminée.

    Structure : [{"story_id": int, "depends_on_id": int}]
    """
    project_id     = state.get("project_id")
    refined_stories = state.get("refined_stories", [])
    stories        = refined_stories or state.get("stories", [])
    human_feedback = state.get("human_feedback")

    print(f"[story_deps] Phase 5 | projet={project_id} | {len(stories)} stories (stub)")

    return {
        "story_dependencies": [],
        "current_phase":      "story_deps",
        "validation_status":  "pending_human",
        "human_feedback":     None,
        "error":              None,
    }
