# agents/pm/agents/stories/service.py
# ═══════════════════════════════════════════════════════════════
# Délègue au ReAct agent — interface inchangée pour agent.py
# ═══════════════════════════════════════════════════════════════

from agents.pm.agents.stories.react_agent import run_stories_react_agent


async def generate_stories(
    epics: list[dict],
    human_feedback: str | None = None,
    architecture_details: dict | None = None,
    project_id: int | None = None,
    business_actors: list[str] | None = None,
) -> list[dict]:
    """
    Génère les User Stories via l'orchestrateur ReAct (4 tools × N epics).
    project_id : si fourni, stream les événements vers GET /pipeline/{id}/stories/stream
    business_actors : acteurs métier identifiés en phase 2, passés au LLM pour forcer
                      des stories orientées rôle humain (pas "système" ou "application").
    """
    return await run_stories_react_agent(
        epics                = epics,
        human_feedback       = human_feedback,
        architecture_details = architecture_details,
        project_id           = project_id,
        business_actors      = business_actors or [],
    )
