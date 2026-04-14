# agents/pm/graph/node_jira_sync.py
# ═══════════════════════════════════════════════════════════════
# Nœud LangGraph — Synchronisation Jira
# Appelé après chaque validation humaine approuvée.
# ═══════════════════════════════════════════════════════════════

import os
from dotenv import load_dotenv

from agents.pm.state import PMPipelineState
from agents.pm.jira  import actions

load_dotenv()
_JIRA_ENABLED = bool(os.getenv("JIRA_BASE_URL") and os.getenv("JIRA_API_TOKEN"))


async def node_jira_sync(state: PMPipelineState) -> dict:
    phase            = state.get("current_phase", "")
    jira_project_key = (state.get("jira_project_key") or "").strip()

    print(f"\n{'#'*60}")
    print(f"# JIRA SYNC — Phase '{phase}'")
    print(f"#   jira_project_key = '{jira_project_key}'")
    print(f"#   JIRA_ENABLED     = {_JIRA_ENABLED}")
    print(f"#   JIRA_BASE_URL    = {os.getenv('JIRA_BASE_URL', 'NON DEFINI')}")
    print(f"{'#'*60}")

    if not _JIRA_ENABLED:
        print("[JIRA SYNC] SKIP — JIRA_BASE_URL ou JIRA_API_TOKEN manquant dans .env")
        return {}

    # La clé projet est obligatoire — pas de fallback .env
    if not jira_project_key:
        print("[JIRA SYNC] SKIP — jira_project_key absent du state (non renseigné dans le wizard)")
        return {}

    # Déjà synchronisé
    already_synced = list(state.get("jira_synced_phases") or [])
    if phase in already_synced:
        print(f"[JIRA SYNC] SKIP — Phase '{phase}' deja synchronisee")
        return {}

    patch = {}

    try:
        if phase == "extract":
            print("[JIRA SYNC] Phase extraction → pas d'objet Jira a creer")

        elif phase == "epics":
            patch = await _sync_epics(state)

        elif phase == "stories":
            patch = await _sync_stories(state)

        elif phase == "tasks":
            patch = await _sync_tasks(state)

        elif phase == "sprints":
            patch = await _sync_sprints(state)

        else:
            print(f"[JIRA SYNC] Phase '{phase}' → pas d'action Jira definie pour cette phase")

    except Exception as e:
        print(f"\n[JIRA SYNC] !! ERREUR phase '{phase}' : {e}")
        print(f"[JIRA SYNC] Pipeline continue malgre l'erreur Jira\n")

    patch["jira_synced_phases"] = already_synced + [phase]

    print(f"\n[JIRA SYNC] Termine — jira_synced_phases = {patch['jira_synced_phases']}")
    print(f"{'#'*60}\n")
    return patch


# ──────────────────────────────────────────────────────────────
# PHASE 2 — Epics
# ──────────────────────────────────────────────────────────────

async def _sync_epics(state: PMPipelineState) -> dict:
    epics            = state.get("epics") or []
    jira_project_key = state.get("jira_project_key", "")
    print(f"\n[JIRA SYNC] >>> EPICS : {len(epics)} epics a creer dans Jira projet '{jira_project_key}'")

    if not epics:
        print("[JIRA SYNC] SKIP — state['epics'] est vide")
        return {}

    epic_map = {}
    errors   = 0
    for i, epic in enumerate(epics):
        try:
            key = actions.create_epic(
                title       = epic["title"],
                description = epic.get("description", ""),
                project_key = jira_project_key,
            )
            epic_map[i] = key
            print(f"[JIRA SYNC]   [OK] Epic {i+1}/{len(epics)} '{epic['title'][:50]}' → {key}")
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Epic {i+1} '{epic.get('title','')}' : {e}")

    print(f"\n[JIRA SYNC] Epics : {len(epic_map)} crees, {errors} erreurs")
    print(f"[JIRA SYNC] jira_epic_map = {epic_map}")
    return {"jira_epic_map": epic_map}


# ──────────────────────────────────────────────────────────────
# PHASE 3 — Stories
# ──────────────────────────────────────────────────────────────

async def _sync_stories(state: PMPipelineState) -> dict:
    stories          = state.get("stories") or []
    epic_map         = state.get("jira_epic_map") or {}
    jira_project_key = state.get("jira_project_key", "")
    print(f"\n[JIRA SYNC] >>> STORIES : {len(stories)} stories a creer dans Jira projet '{jira_project_key}'")
    print(f"[JIRA SYNC]   jira_epic_map disponible = {epic_map}")

    if not stories:
        print("[JIRA SYNC] SKIP — state['stories'] est vide")
        return {}

    if not epic_map:
        print("[JIRA SYNC] AVERTISSEMENT — jira_epic_map vide, les stories ne seront pas liees a un Epic")

    story_map = {}
    errors    = 0
    for i, story in enumerate(stories):
        try:
            epic_idx = story.get("epic_id")
            epic_key = epic_map.get(str(epic_idx)) or epic_map.get(epic_idx)

            key = actions.create_story(
                title               = story["title"],
                description         = story.get("description", ""),
                acceptance_criteria = story.get("acceptance_criteria", []),
                project_key         = jira_project_key,
                epic_key            = epic_key,
                story_points        = story.get("story_points"),
            )
            story_map[i] = key
            print(f"[JIRA SYNC]   [OK] Story {i+1}/{len(stories)} → {key} (epic_key={epic_key})")
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Story {i+1} '{story.get('title','')[:50]}' : {e}")

    print(f"\n[JIRA SYNC] Stories : {len(story_map)} creees, {errors} erreurs")
    print(f"[JIRA SYNC] jira_story_map = {story_map}")
    return {"jira_story_map": story_map}


# ──────────────────────────────────────────────────────────────
# PHASE 7 — Tasks
# ──────────────────────────────────────────────────────────────

async def _sync_tasks(state: PMPipelineState) -> dict:
    tasks            = state.get("tasks") or []
    story_map        = state.get("jira_story_map") or {}
    jira_project_key = state.get("jira_project_key", "")
    print(f"\n[JIRA SYNC] >>> TASKS : {len(tasks)} tasks a creer dans Jira projet '{jira_project_key}'")

    if not tasks:
        print("[JIRA SYNC] SKIP — state['tasks'] est vide")
        return {}

    task_map = {}
    errors   = 0
    for i, task in enumerate(tasks):
        try:
            story_idx  = task.get("story_id")
            parent_key = story_map.get(str(story_idx)) or story_map.get(story_idx)

            key = actions.create_task(
                title       = task["title"],
                description = task.get("description", ""),
                project_key = jira_project_key,
                parent_key  = parent_key,
            )
            task_map[i] = key
            print(f"[JIRA SYNC]   [OK] Task {i+1}/{len(tasks)} → {key} (parent={parent_key})")
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Task {i+1} '{task.get('title','')[:50]}' : {e}")

    print(f"\n[JIRA SYNC] Tasks : {len(task_map)} creees, {errors} erreurs")
    return {"jira_task_map": task_map}


# ──────────────────────────────────────────────────────────────
# PHASE 10 — Sprints
# ──────────────────────────────────────────────────────────────

async def _sync_sprints(state: PMPipelineState) -> dict:
    sprints   = state.get("sprints") or []
    story_map = state.get("jira_story_map") or {}
    print(f"\n[JIRA SYNC] >>> SPRINTS : {len(sprints)} sprints a creer dans Jira")

    if not sprints:
        print("[JIRA SYNC] SKIP — state['sprints'] est vide")
        return {}

    jira_project_key = state.get("jira_project_key", "")
    board_id = actions.get_board_id(jira_project_key)
    print(f"[JIRA SYNC]   board_id = {board_id} (projet '{jira_project_key}')")
    if not board_id:
        print("[JIRA SYNC] ERREUR — Board Jira introuvable pour le projet")
        return {}

    sprint_map = {}
    errors     = 0
    for i, sprint in enumerate(sprints):
        try:
            sprint_id = actions.create_sprint(
                board_id   = board_id,
                name       = sprint["name"],
                start_date = sprint.get("start_date", ""),
                end_date   = sprint.get("end_date", ""),
            )
            if sprint_id:
                sprint_map[i] = sprint_id
                story_ids  = sprint.get("story_ids") or []
                issue_keys = [
                    story_map.get(str(sid)) or story_map.get(sid)
                    for sid in story_ids
                    if story_map.get(str(sid)) or story_map.get(sid)
                ]
                if issue_keys:
                    actions.add_issues_to_sprint(sprint_id, issue_keys)
                print(f"[JIRA SYNC]   [OK] Sprint {i+1} '{sprint['name']}' → id={sprint_id} ({len(issue_keys)} stories)")
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Sprint {i+1} : {e}")

    print(f"\n[JIRA SYNC] Sprints : {len(sprint_map)} crees, {errors} erreurs")
    return {"jira_sprint_map": sprint_map}
