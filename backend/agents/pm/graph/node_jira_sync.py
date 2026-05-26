# agents/pm/graph/node_jira_sync.py
# ═══════════════════════════════════════════════════════════════
# Nœud LangGraph — Synchronisation Jira
# Appelé après chaque validation humaine approuvée.
# ═══════════════════════════════════════════════════════════════

import os
from dotenv import load_dotenv

from agents.pm.state import PMPipelineState
from agents.pm.jira  import actions
from agents.pm.agents.epics.repository   import get_epics,   update_epic_jira_key
from agents.pm.agents.stories.repository import get_stories, update_story_jira_key

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

    patch      = {}
    sync_ok    = True   # False si la sync a échoué complètement (toutes erreurs)

    try:
        if phase == "extract":
            print("[JIRA SYNC] Phase extraction → pas d'objet Jira a creer")

        elif phase == "epics":
            patch = await _sync_epics(state)

        elif phase == "stories":
            patch = await _sync_stories(state)
            # Si aucune story créée alors qu'il y en avait → ne pas marquer synced
            nb_stories = len(state.get("stories") or [])
            nb_created = len(patch.get("jira_story_map", {}))
            if nb_stories > 0 and nb_created == 0:
                sync_ok = False
                print(f"[JIRA SYNC] ⚠ Aucune story créée dans Jira ({nb_stories} attendues) — phase NON marquée comme synchronisée")

        elif phase == "cpm":
            patch = await _sync_cpm(state)

        elif phase == "story_deps":
            patch = await _sync_story_deps(state)

        elif phase == "staffing":
            # Phase staffing : crée les sprints dans Jira + add stories au sprint.
            # Les sprints sont produits par node_staffing (state["sprints"]).
            patch = await _sync_sprints(state)

        else:
            print(f"[JIRA SYNC] Phase '{phase}' → pas d'action Jira definie pour cette phase")

    except Exception as e:
        sync_ok = False
        print(f"\n[JIRA SYNC] !! ERREUR phase '{phase}' : {e}")
        print(f"[JIRA SYNC] Pipeline continue malgre l'erreur Jira\n")

    # Marquer comme synchronisé seulement si succès (évite de bloquer les retries)
    if sync_ok:
        patch["jira_synced_phases"] = already_synced + [phase]
    else:
        patch["jira_synced_phases"] = already_synced   # phase retentera au prochain appel

    print(f"\n[JIRA SYNC] Termine — jira_synced_phases = {patch['jira_synced_phases']}")
    print(f"{'#'*60}\n")
    return patch


# ──────────────────────────────────────────────────────────────
# PHASE 2 — Epics
# ──────────────────────────────────────────────────────────────

async def _sync_epics(state: PMPipelineState) -> dict:
    epics            = state.get("epics") or []
    project_id       = state.get("project_id")
    jira_project_key = state.get("jira_project_key", "")
    print(f"\n[JIRA SYNC] >>> EPICS : {len(epics)} epics a creer dans Jira projet '{jira_project_key}'")

    if not epics:
        print("[JIRA SYNC] SKIP — state['epics'] est vide")
        return {}

    db_epics      = await get_epics(project_id) if project_id else []
    db_id_by_pos  = [e.id for e in db_epics]
    db_jira_by_id = {e.id: e.jira_epic_key for e in db_epics if e.jira_epic_key}

    # Construire l'index des épics déjà synchronisés (depuis le state)
    existing_map_raw = state.get("jira_epic_map") or {}
    already_synced_idx: dict[int, str] = {}
    for k, v in existing_map_raw.items():
        try:
            already_synced_idx[int(k)] = v
        except (ValueError, TypeError):
            pass

    epic_map = dict(already_synced_idx)
    skipped  = 0
    errors   = 0

    for i, epic in enumerate(epics):
        # Dédup : déjà dans le state map ?
        existing_key = already_synced_idx.get(i)
        # Dédup : déjà en DB avec un jira_epic_key ?
        if not existing_key:
            db_id_for_check = epic.get("db_id") or (db_id_by_pos[i] if i < len(db_id_by_pos) else None)
            if db_id_for_check:
                existing_key = db_jira_by_id.get(int(db_id_for_check))
        if existing_key:
            epic_map[i] = existing_key
            skipped += 1
            print(f"[JIRA SYNC]   [SKIP] Epic {i+1}/{len(epics)} déjà dans Jira → {existing_key}")
            continue

        try:
            key = actions.create_epic(
                title       = epic["title"],
                description = epic.get("description", ""),
                project_key = jira_project_key,
            )
            epic_map[i] = key
            print(f"[JIRA SYNC]   [OK] Epic {i+1}/{len(epics)} '{epic['title'][:50]}' → {key}")

            # Mise à jour DB : utilise db_id direct si disponible
            db_id = epic.get("db_id")
            if db_id:
                await update_epic_jira_key(int(db_id), key)
                print(f"[JIRA SYNC]   DB: epic db_id={db_id} → jira_epic_key={key}")
            elif i < len(db_id_by_pos):
                await update_epic_jira_key(db_id_by_pos[i], key)
                print(f"[JIRA SYNC]   DB: epic pos_id={db_id_by_pos[i]} → jira_epic_key={key} (fallback positionnel)")

        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Epic {i+1} '{epic.get('title','')}' : {e}")

    # ── Second passage : epics DB sans jira_epic_key non couverts par le state ──
    # Cas : epics ajoutés manuellement, absents du checkpoint LangGraph
    state_db_ids: set[int] = set()
    for i, epic in enumerate(epics):
        db_id = epic.get("db_id") or (db_id_by_pos[i] if i < len(db_id_by_pos) else None)
        if db_id:
            state_db_ids.add(int(db_id))

    for e in db_epics:
        if e.id in state_db_ids:
            continue  # déjà traité dans le premier passage
        idx = db_id_by_pos.index(e.id) if e.id in db_id_by_pos else (max(epic_map.keys(), default=-1) + 1)
        if e.jira_epic_key:
            epic_map[idx] = e.jira_epic_key
            skipped += 1
            print(f"[JIRA SYNC]   [SKIP] Epic manuel '{e.title[:50]}' déjà dans Jira → {e.jira_epic_key}")
            continue
        try:
            key = actions.create_epic(
                title       = e.title,
                description = e.description or "",
                project_key = jira_project_key,
            )
            epic_map[idx] = key
            await update_epic_jira_key(e.id, key)
            print(f"[JIRA SYNC]   [OK] Epic manuel idx={idx} '{e.title[:50]}' → {key}")
        except Exception as e_err:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Epic manuel '{e.title}' : {e_err}")

    newly_created = len(epic_map) - len(already_synced_idx)
    print(f"\n[JIRA SYNC] Epics : {newly_created} nouveaux créés, {skipped} ignorés (déjà sync), {errors} erreurs")
    print(f"[JIRA SYNC] jira_epic_map = {epic_map}")
    return {"jira_epic_map": epic_map}


# ──────────────────────────────────────────────────────────────
# PHASE 3 — Stories
# ──────────────────────────────────────────────────────────────

async def _sync_stories(state: PMPipelineState) -> dict:
    import json as _json

    stories          = state.get("stories") or []
    epic_map         = state.get("jira_epic_map") or {}
    project_id       = state.get("project_id")
    jira_project_key = state.get("jira_project_key", "")
    from agents.pm.jira import client as _jira_client
    sp_fields = _jira_client.get_story_points_field_ids()
    print(f"\n[JIRA SYNC] >>> STORIES : {len(stories)} stories à créer dans Jira projet '{jira_project_key}'")
    print(f"[JIRA SYNC]   story_points fields détectés : {sp_fields}")
    print(f"[JIRA SYNC]   jira_epic_map = {epic_map}")

    if not stories:
        print("[JIRA SYNC] SKIP — state['stories'] est vide")
        return {}

    if not epic_map:
        print("[JIRA SYNC] ⚠ jira_epic_map vide — stories créées sans lien epic")

    # Fallback positionnel : si les stories n'ont pas encore de db_id (ancienne exécution)
    db_stories   = await get_stories(project_id) if project_id else []
    db_id_by_pos = [s.id for s in db_stories]

    # ── Construire un index des clés Jira déjà existantes ─────
    # Source 1 : jira_story_map déjà dans le state (clés str ou int)
    existing_map_raw = state.get("jira_story_map") or {}
    already_synced_idx: dict[int, str] = {}
    for k, v in existing_map_raw.items():
        try:
            already_synced_idx[int(k)] = v
        except (ValueError, TypeError):
            pass

    # Source 2 : jira_issue_key en DB (si la story a un db_id)
    db_jira_by_id = {s.id: s.jira_issue_key for s in db_stories if s.jira_issue_key}

    story_map = dict(already_synced_idx)   # partir de l'existant → merge
    skipped   = 0
    errors    = 0

    for i, story in enumerate(stories):
        # Déjà synchronisée ? (via state map ou via DB)
        existing_key = already_synced_idx.get(i)
        if not existing_key:
            db_id_for_check = story.get("db_id") or (db_id_by_pos[i] if i < len(db_id_by_pos) else None)
            if db_id_for_check:
                existing_key = db_jira_by_id.get(int(db_id_for_check))
        if existing_key:
            story_map[i] = existing_key
            skipped += 1
            sp = story.get("story_points")
            if sp:
                try:
                    actions.update_story_points(existing_key, sp)
                    print(f"[JIRA SYNC]   [UPDATE SP] {existing_key} → story_points={sp}")
                except Exception as sp_err:
                    errors += 1
                    print(f"[JIRA SYNC]   [ERREUR SP] {existing_key} story_points={sp} : {sp_err}")
            else:
                print(f"[JIRA SYNC]   [SKIP] Story {i+1}/{len(stories)} {existing_key} (story_points absent en DB)")
            continue

        try:
            epic_idx = story.get("epic_id")
            # jira_epic_map peut avoir des clés str ou int selon la sérialisation JSON
            epic_key = epic_map.get(str(epic_idx)) or epic_map.get(epic_idx)

            # Normaliser acceptance_criteria (JSON string ou liste)
            ac = story.get("acceptance_criteria", [])
            if isinstance(ac, str):
                try:
                    ac = _json.loads(ac)
                except Exception:
                    ac = [ac] if ac else []

            key = actions.create_story(
                title               = story["title"],
                description         = story.get("description", ""),
                acceptance_criteria = ac,
                project_key         = jira_project_key,
                epic_key            = epic_key,
                story_points        = story.get("story_points"),
            )
            story_map[i] = key
            print(f"[JIRA SYNC]   [OK] Story {i+1}/{len(stories)} → {key} (epic={epic_key})")

            # ── Mise à jour DB : utilise db_id direct si disponible (priorité) ──
            db_id = story.get("db_id")
            if db_id:
                await update_story_jira_key(int(db_id), key)
                print(f"[JIRA SYNC]   DB: story db_id={db_id} → jira_issue_key={key}")
            elif i < len(db_id_by_pos):
                await update_story_jira_key(db_id_by_pos[i], key)
                print(f"[JIRA SYNC]   DB: story pos_id={db_id_by_pos[i]} → jira_issue_key={key} (fallback positionnel)")
            else:
                print(f"[JIRA SYNC]   ⚠ Story {i} : impossible de trouver l'id DB pour mise à jour jira_issue_key")

        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Story {i+1} '{story.get('title','')[:60]}' : {e}")

    newly_created = len(story_map) - len(already_synced_idx)
    print(f"\n[JIRA SYNC] Stories : {newly_created} nouvelles créées, {skipped} ignorées (déjà sync), {errors} erreurs")
    print(f"[JIRA SYNC] jira_story_map = {story_map}")
    return {"jira_story_map": story_map}


# ──────────────────────────────────────────────────────────────
# PHASE CPM — Label "critical-path" sur les stories critiques
# ──────────────────────────────────────────────────────────────

async def _sync_cpm(state: PMPipelineState) -> dict:
    critical_path = state.get("critical_path") or []
    project_id    = state.get("project_id")
    print(f"\n[JIRA SYNC] >>> CPM : {len(critical_path)} stories sur le chemin critique")

    if not critical_path:
        print("[JIRA SYNC] SKIP — critical_path vide")
        return {}

    # Résoudre db_id → jira_issue_key depuis la DB
    db_stories   = await get_stories(project_id) if project_id else []
    jira_by_dbid = {s.id: s.jira_issue_key for s in db_stories if s.jira_issue_key}

    if not jira_by_dbid:
        print("[JIRA SYNC] SKIP — aucune story n'a de clé Jira (phase stories non synchronisée ?)")
        return {}

    labeled  = 0
    skipped  = 0
    errors   = 0
    for story_id in critical_path:
        jira_key = jira_by_dbid.get(story_id)
        if not jira_key:
            skipped += 1
            print(f"[JIRA SYNC]   [SKIP] story_id={story_id} : clé Jira introuvable")
            continue
        try:
            actions.add_label(jira_key, "critical-path")
            labeled += 1
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] {jira_key} : {e}")

    print(f"\n[JIRA SYNC] CPM : {labeled} labels ajoutés, {skipped} ignorés, {errors} erreurs")
    return {}


# ──────────────────────────────────────────────────────────────
# PHASE 4 — Dépendances (Issue Links)
# ──────────────────────────────────────────────────────────────

async def _sync_story_deps(state: PMPipelineState) -> dict:
    deps       = state.get("story_dependencies") or []
    project_id = state.get("project_id")
    print(f"\n[JIRA SYNC] >>> STORY DEPS : {len(deps)} dépendances à créer comme Issue Links")

    if not deps:
        print("[JIRA SYNC] SKIP — state['story_dependencies'] est vide")
        return {}

    # Construire db_id → jira_issue_key depuis la DB (source de vérité)
    db_stories   = await get_stories(project_id) if project_id else []
    jira_by_dbid = {s.id: s.jira_issue_key for s in db_stories if s.jira_issue_key}

    if not jira_by_dbid:
        print("[JIRA SYNC] SKIP — aucune story n'a encore de clé Jira (phase stories non synchronisée ?)")
        return {}

    created = 0
    skipped = 0
    errors  = 0

    for dep in deps:
        from_id = dep.get("from_story_id")
        to_id   = dep.get("to_story_id")
        rel     = dep.get("relation_type", "FS")

        from_key = jira_by_dbid.get(from_id)
        to_key   = jira_by_dbid.get(to_id)

        if not from_key or not to_key:
            skipped += 1
            print(f"[JIRA SYNC]   [SKIP] dep {from_id}→{to_id} : clé Jira manquante (from={from_key}, to={to_key})")
            continue

        try:
            actions.create_issue_link(from_key, to_key, rel)
            created += 1
            print(f"[JIRA SYNC]   [OK] {from_key} --{rel}--> {to_key}")
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] {from_key}→{to_key} : {e}")

    print(f"\n[JIRA SYNC] Issue Links : {created} créés, {skipped} ignorés, {errors} erreurs")
    return {}


# ──────────────────────────────────────────────────────────────
# PHASE STAFFING — Sprints (créés en Jira après matching validé)
# ──────────────────────────────────────────────────────────────

async def _sync_sprints(state: PMPipelineState) -> dict:
    """
    Après validation PM du staffing :
      1. Persiste les affectations en `staffing_assignments` (DB)
      2. Persiste les sprints en `sprints` (DB) → récupère leurs db_ids
      3. Crée les sprints dans Jira et ajoute les stories
      4. Met à jour pm.sprints.jira_sprint_id

    La persistance DB est faite ici (et non dans node_staffing) pour que le
    PM puisse modifier les affectations avant que les tables ne soient
    écrites. node_jira_sync ne tourne que sur validation approuvée.
    """
    from agents.pm.agents.staffing.steps.matching.repository import persist_assignments
    from agents.pm.agents.staffing.steps.story_distribution.repository import (
        persist_sprints, update_sprint_jira_id,
    )

    sprints    = state.get("sprints") or []
    project_id = state.get("project_id")
    print(f"\n[JIRA SYNC] >>> STAFFING : persistance DB + {len(sprints)} sprints Jira")

    # ── 1. Persistance staffing_assignments ────────────────────
    staffing       = state.get("staffing") or {}
    steps          = staffing.get("steps") or {}
    matching_dump  = (steps.get("matching") or {}).get("result")
    distrib_result = (steps.get("story_distribution") or {}).get("result")

    if project_id and matching_dump:
        try:
            n = await persist_assignments(project_id, matching_dump)
            print(f"[JIRA SYNC]   ↳ {n} affectation(s) persistées en DB")
        except Exception as e:
            print(f"[JIRA SYNC]   ⚠ persistance staffing_assignments échouée : {e}")

    # ── 1b. Dériver crm.assignments depuis les affectations persistées ──
    if project_id and matching_dump:
        try:
            from datetime import date as _date
            from agents.pm.agents.staffing.steps.matching.crm_repository import upsert_crm_assignments
            _sprint_start: _date | None = None
            _sprint_end:   _date | None = None
            if sprints:
                _starts = [s["start_date"] for s in sprints if s.get("start_date")]
                _ends   = [s["end_date"]   for s in sprints if s.get("end_date")]
                if _starts:
                    _sprint_start = _date.fromisoformat(min(_starts))
                if _ends:
                    _sprint_end = _date.fromisoformat(max(_ends))
            m = await upsert_crm_assignments(project_id, _sprint_start, _sprint_end)
            print(f"[JIRA SYNC]   ↳ {m} crm.assignment(s) upsertés (allocation% calculé)")
        except Exception as e:
            print(f"[JIRA SYNC]   ⚠ upsert crm.assignments échoué : {e}")

    # ── 2. Persistance sprints (récupère les db_ids + jira_sprint_id préservés) ──
    db_id_by_sn:   dict[int, int]      = {}
    jira_id_by_sn: dict[int, int | None] = {}
    if project_id and distrib_result:
        try:
            persisted = await persist_sprints(project_id, distrib_result)
            db_id_by_sn   = {s["sprint_number"]: s["db_id"]          for s in persisted}
            jira_id_by_sn = {s["sprint_number"]: s.get("jira_sprint_id") for s in persisted}
            print(f"[JIRA SYNC]   ↳ {len(persisted)} sprint(s) persistés en DB")
        except Exception as e:
            print(f"[JIRA SYNC]   ⚠ persistance sprints échouée : {e}")

    if not sprints:
        print("[JIRA SYNC] SKIP Jira sprints — state['sprints'] est vide")
        return {}

    jira_project_key = state.get("jira_project_key", "")
    board_id = actions.get_board_id(jira_project_key)
    print(f"[JIRA SYNC]   board_id = {board_id} (projet '{jira_project_key}')")
    if not board_id:
        print("[JIRA SYNC] ERREUR — Board Jira introuvable pour le projet")
        return {}

    # ── 3. Résolution db_story_id → jira_issue_key via DB ──────
    db_stories   = await get_stories(project_id) if project_id else []
    jira_by_dbid = {s.id: s.jira_issue_key for s in db_stories if s.jira_issue_key}
    if not jira_by_dbid:
        print("[JIRA SYNC] ⚠ aucune story n'a de clé Jira — sprints créés sans stories")

    sprint_map = {}
    skipped    = 0
    errors     = 0
    for sprint in sprints:
        sn = sprint.get("sprint_number")
        try:
            # ── Dédup : sprint Jira déjà créé pour ce sprint_number ? ──
            # Si oui, on saute le create_sprint (évite les doublons type
            # "Sprint 1" + "IS Sprint 1" dans Jira) et on add juste les
            # stories restantes (idempotent côté Jira API).
            existing_jira_id = jira_id_by_sn.get(sn)
            if existing_jira_id:
                sprint_id = existing_jira_id
                sprint_map[sn] = sprint_id
                skipped += 1
                story_ids = sprint.get("story_ids") or []
                issue_keys = [
                    jira_by_dbid[sid]
                    for sid in story_ids
                    if sid in jira_by_dbid
                ]
                if issue_keys:
                    actions.add_issues_to_sprint(sprint_id, issue_keys)
                print(
                    f"[JIRA SYNC]   [SKIP] Sprint {sn} déjà dans Jira "
                    f"(jira_id={sprint_id}) — {len(issue_keys)} stories (re)addées"
                )
                continue

            # ── Création neuve dans Jira ───────────────────────
            sprint_id = actions.create_sprint(
                board_id   = board_id,
                name       = sprint["name"],
                start_date = sprint.get("start_date", ""),
                end_date   = sprint.get("end_date", ""),
            )
            if not sprint_id:
                continue

            sprint_map[sn] = sprint_id

            # Add stories au sprint Jira via db_story_id → jira_key
            story_ids = sprint.get("story_ids") or []
            issue_keys = [
                jira_by_dbid[sid]
                for sid in story_ids
                if sid in jira_by_dbid
            ]
            if issue_keys:
                actions.add_issues_to_sprint(sprint_id, issue_keys)

            # ── 4. Bouclage : update pm.sprints.jira_sprint_id ──
            db_id = db_id_by_sn.get(sn)
            if db_id:
                try:
                    await update_sprint_jira_id(db_id, sprint_id)
                except Exception as upd_err:
                    print(f"[JIRA SYNC]   ⚠ update pm.sprints jira_sprint_id échec sprint {sn}: {upd_err}")

            print(
                f"[JIRA SYNC]   [OK] Sprint {sn} '{sprint['name']}' "
                f"→ jira_id={sprint_id} ({len(issue_keys)}/{len(story_ids)} stories addées)"
            )
        except Exception as e:
            errors += 1
            print(f"[JIRA SYNC]   [ERREUR] Sprint {sn} : {e}")

    created_count = len(sprint_map) - skipped
    print(f"\n[JIRA SYNC] Sprints : {created_count} créés, {skipped} déjà existants, {errors} erreurs")
    return {"jira_sprint_map": sprint_map}
