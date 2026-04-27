# agents/pm/agents/dependencies/story_deps.py
# Phase 5 — Nœud LangGraph : détection des dépendances entre User Stories

from agents.pm.state import PMPipelineState
from agents.pm.agents.dependencies.service    import run_story_deps
from agents.pm.agents.dependencies.repository import save_story_dependencies
from agents.pm.agents.stories.repository      import get_all_stories_as_dicts


async def node_story_deps(state: PMPipelineState) -> dict:
    """
    Nœud LangGraph — Phase 5 : analyse des dépendances entre stories.

    Méthodologie :
      Pass 1 — Intra-epic  : 1 appel LLM / epic, en parallèle
                             titres + descriptions, analyse fine
      Pass 2 — Inter-epic  : 1 appel LLM global
                             titres uniquement groupés par epic

    Structure de sortie par dépendance :
      from_story_id, to_story_id, dependency_type (SAFe),
      relation_type (PMBOK), is_blocking, level, reason
    """
    project_id = state.get("project_id")
    stories    = state.get("stories", [])

    # Les stories en state n'ont pas de db_id (générées par LLM avant sauvegarde).
    # On recharge depuis la DB pour avoir les vrais IDs nécessaires à la détection.
    if project_id:
        try:
            db_stories = await get_all_stories_as_dicts(project_id)
            if db_stories:
                stories = db_stories
                print(f"[story_deps] Stories rechargées depuis DB : {len(stories)} (avec db_id)")
        except Exception as e:
            print(f"[story_deps] Avertissement rechargement DB : {e} — utilisation du state")

    print(f"[story_deps] Phase 5 | projet={project_id} | {len(stories)} stories")

    if not stories:
        return {
            "story_dependencies": [],
            "current_phase":      "story_deps",
            "validation_status":  "pending_human",
            "human_feedback":     None,
            "error":              "Aucune story disponible pour analyser les dépendances.",
        }

    try:
        deps = await run_story_deps(stories)
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        print(f"[story_deps] ERREUR : {error_msg}")
        return {
            "story_dependencies": [],
            "current_phase":      "story_deps",
            "validation_status":  "pending_human",
            "human_feedback":     None,
            "error":              error_msg,
        }

    if project_id:
        await save_story_dependencies(project_id, deps)

    intra = [d for d in deps if d.get("level") == "intra_epic"]
    inter = [d for d in deps if d.get("level") == "inter_epic"]
    print(f"[story_deps] {len(deps)} dépendances persistées : {len(intra)} intra / {len(inter)} inter-epic")
    if inter:
        for d in inter:
            print(f"  ↳ inter: {d['from_story_id']}→{d['to_story_id']} | {d.get('dependency_type')} | {d.get('relation_type')}")

    return {
        "story_dependencies": deps,
        "current_phase":      "story_deps",
        "validation_status":  "pending_human",
        "human_feedback":     None,
        "error":              None,
    }
