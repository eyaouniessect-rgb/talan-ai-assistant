# agents/pm/agents/staffing/agent.py
# ═══════════════════════════════════════════════════════════════
# Phase 8 — Staffing (affectation des stories aux collaborateurs)
#
# Pipeline en 5 sous-étapes :
#   Step 1 — Profile Extraction      (LLM batch)       ← implémenté
#   Step 2 — Profile Normalization   (LLM + DB)        ← implémenté
#   Step 3 — Story Distribution      (déterministe)    ← implémenté
#   Step 4 — Candidate Filtering     (DB, par sprint)  ← implémenté
#   Step 5 — Matching                (LLM batch)       ← implémenté
#
# Après Step 5 (matching réussi) :
#   - persist_assignments() → matérialise staffing_assignments en DB
#   - persist_sprints()     → matérialise project_management.sprints en DB
#   - state["sprints"]      → peuplé depuis distrib_result pour la sync Jira
#
# Flux de validation :
#   node_staffing → node_validate (interrupt) → humain valide/rejette
#   Si rejeté avec feedback → node_staffing relancé avec human_feedback
#   Si validé et steps non finis → re-route vers node_staffing (step suivant)
#   Si validé et tous done → jira_sync (crée sprints Jira + add stories) → END
# ═══════════════════════════════════════════════════════════════

from agents.pm.state import PMPipelineState
from agents.pm.agents.staffing.steps.profile_extraction.service    import extract_profiles
from agents.pm.agents.staffing.steps.profile_normalization.service import normalize_profiles
from agents.pm.agents.staffing.steps.story_distribution.service    import distribute_stories
from agents.pm.agents.staffing.steps.candidate_filtering.service   import filter_candidates
from agents.pm.agents.staffing.steps.matching.service              import match_assignments

_EMPTY_STEPS = {
    "profile_extraction":    {"status": "pending", "result": None},
    "profile_normalization": {"status": "pending", "result": None},
    "story_distribution":    {"status": "pending", "result": None},
    "candidate_filtering":   {"status": "pending", "result": None},
    "matching":              {"status": "pending", "result": None},
}

_STEP_ORDER = [
    "profile_extraction",
    "profile_normalization",
    "story_distribution",
    "candidate_filtering",
    "matching",
]


async def node_staffing(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 8 : Staffing.

    À chaque appel, détermine quelle sous-étape exécuter selon l'avancement
    stocké dans state['staffing']['steps'].

    Retourne toujours validation_status='pending_human' pour suspendre
    le graph et attendre la validation humaine via node_validate.
    """
    project_id     = state.get("project_id")
    stories        = state.get("stories",    []) or []
    priorities     = state.get("priorities", []) or []
    human_feedback = state.get("human_feedback")

    # ── État courant du staffing ───────────────────────────────
    staffing = state.get("staffing") or {}
    if not isinstance(staffing, dict):
        staffing = {}

    steps = staffing.get("steps") or {}
    if not isinstance(steps, dict):
        steps = {}

    for key, default in _EMPTY_STEPS.items():
        if key not in steps:
            steps[key] = default.copy()

    # Strip any unknown/legacy step keys (e.g. velocity_feasibility removed in
    # the post-matching refactor) so they can't block the validation routing.
    steps = {k: v for k, v in steps.items() if k in _EMPTY_STEPS}

    print(f"[staffing] ▶ projet={project_id} | {len(stories)} stories | feedback={bool(human_feedback)}")
    print(f"[staffing]   statuts : " + " | ".join(
        f"{k}={v.get('status', 'pending')}" for k, v in steps.items()
    ))

    # ── Rejection feedback → reset the last completed step ─────
    # When the PM rejects, find the last "done" step (just before the first
    # non-done step) and reset it to "pending" so it re-runs with the feedback.
    if human_feedback:
        last_done_key = None
        for key in _STEP_ORDER:
            if steps.get(key, {}).get("status") == "done":
                last_done_key = key
            else:
                break
        if last_done_key:
            steps = {**steps, last_done_key: {"status": "pending", "result": None}}
            print(f"[staffing] 🔄 Feedback PM → reset '{last_done_key}' à pending pour re-run")

    # ── Préparer les stories pour l'extraction ─────────────────
    priority_map = {
        p["story_id"]: p.get("final_rank", 999)
        for p in priorities
        if isinstance(p, dict) and "story_id" in p
    }

    stories_input = sorted(
        [
            {
                "story_id":     s.get("db_id") or s.get("id"),
                "db_id":        s.get("db_id"),
                "title":        s.get("title", ""),
                "description":  s.get("description", ""),
                "story_points": s.get("story_points", 3),
            }
            for s in stories
            if (s.get("db_id") or s.get("id")) is not None
        ],
        key=lambda s: priority_map.get(s["story_id"], 999),
    )

    # ── STEP 1 — Profile Extraction ────────────────────────────
    # Re-lance uniquement si le step n'est pas encore done.
    # human_feedback seul ne suffit pas à re-lancer un step déjà done.
    profile_step = steps.get("profile_extraction", {})

    if profile_step.get("status") not in ("done",):
        print(f"[staffing] → Step 1 : Profile Extraction ({len(stories_input)} stories)")
        try:
            result = await extract_profiles(stories_input, feedback=human_feedback)
            steps = {
                **steps,
                "profile_extraction":    {"status": "done",    "result": result.model_dump()},
                "profile_normalization": {"status": "pending", "result": None},
                "story_distribution":    {"status": "pending", "result": None},
                "candidate_filtering":   {"status": "pending", "result": None},
                "matching":              {"status": "pending", "result": None},
            }
            print(f"[staffing] ✅ Step 1 terminé — {len(result.stories_profiles)} profils extraits")
        except Exception as e:
            print(f"[staffing] ❌ Step 1 échoué : {e}")
            steps = {**steps, "profile_extraction": {"status": "error", "error": str(e), "result": None}}
            return _return(staffing, steps)

        return _return(staffing, steps)

    # ── STEP 2 — Profile Normalization ─────────────────────────
    norm_step    = steps.get("profile_normalization", {})
    step1_result = steps.get("profile_extraction", {}).get("result")

    if (
        steps.get("profile_extraction", {}).get("status") == "done"
        and step1_result
        and norm_step.get("status") not in ("done",)
    ):
        print("[staffing] → Step 2 : Profile Normalization")
        try:
            norm_result = await normalize_profiles(step1_result)
            steps = {
                **steps,
                "profile_normalization": {"status": "done", "result": norm_result.model_dump()},
                "story_distribution":    {"status": "pending", "result": None},
                "candidate_filtering":   {"status": "pending", "result": None},
                "matching":              {"status": "pending", "result": None},
            }
            total    = len(norm_result.profile_mappings)
            matched  = sum(1 for m in norm_result.profile_mappings if m.match_type != "no_match")
            recruits = sum(1 for m in norm_result.profile_mappings if m.match_type == "no_match")
            print(
                f"[staffing] ✅ Step 2 terminé — {total} profils : "
                f"{matched} matchés, {recruits} à recruter"
            )
        except Exception as e:
            print(f"[staffing] ❌ Step 2 échoué : {e}")
            steps = {**steps, "profile_normalization": {"status": "error", "error": str(e), "result": None}}
            return _return(staffing, steps)

        return _return(staffing, steps)

    # ── STEP 3 — Story Distribution ────────────────────────────
    distrib_step = steps.get("story_distribution", {})
    norm_result  = steps.get("profile_normalization", {}).get("result")

    if (
        steps.get("profile_normalization", {}).get("status") == "done"
        and norm_result
        and distrib_step.get("status") not in ("done",)
    ):
        print("[staffing] → Step 3 : Story Distribution")
        try:
            distrib_result = await distribute_stories(project_id, stories_input, priorities)
            steps = {
                **steps,
                "story_distribution":  {"status": "done", "result": distrib_result.model_dump()},
                "candidate_filtering": {"status": "pending", "result": None},
                "matching":            {"status": "pending", "result": None},
            }
            print(
                f"[staffing] ✅ Step 3 terminé — "
                f"{distrib_result.number_of_sprints} sprints | "
                f"{distrib_result.total_story_points} SP total"
            )
        except Exception as e:
            print(f"[staffing] ❌ Step 3 échoué : {e}")
            steps = {**steps, "story_distribution": {"status": "error", "error": str(e), "result": None}}
            return _return(staffing, steps)

        return _return(staffing, steps)

    # ── STEP 4 — Candidate Filtering (par sprint) ──────────────
    filter_step    = steps.get("candidate_filtering", {})
    distrib_result = steps.get("story_distribution", {}).get("result")

    if (
        steps.get("story_distribution", {}).get("status") == "done"
        and distrib_result
        and norm_result
        and filter_step.get("status") not in ("done",)
    ):
        print("[staffing] → Step 4 : Candidate Filtering (par sprint)")
        try:
            filter_result = await filter_candidates(norm_result, distrib_result, project_id)
            steps = {
                **steps,
                "candidate_filtering": {"status": "done", "result": filter_result.model_dump()},
                "matching":            {"status": "pending", "result": None},
            }
            total_candidates = sum(
                sc["total_available"]
                for sc in filter_result.model_dump().get("candidates_by_sprint", {}).values()
                if isinstance(sc, dict)
            )
            print(
                f"[staffing] ✅ Step 4 terminé — "
                f"{len(filter_result.candidates_by_sprint)} sprint(s) filtrés | "
                f"{len(filter_result.missing_profiles)} profil(s) à recruter"
            )
        except Exception as e:
            print(f"[staffing] ❌ Step 4 échoué : {e}")
            steps = {**steps, "candidate_filtering": {"status": "error", "error": str(e), "result": None}}
            return _return(staffing, steps)

        return _return(staffing, steps)

    # ── STEP 5 — Matching (LLM batch par sprint × profil) ──────
    matching_step    = steps.get("matching", {})
    extraction_res   = steps.get("profile_extraction", {}).get("result")
    filter_result    = steps.get("candidate_filtering", {}).get("result")

    if (
        steps.get("candidate_filtering", {}).get("status") == "done"
        and filter_result and norm_result and distrib_result and extraction_res
        and matching_step.get("status") not in ("done",)
    ):
        print("[staffing] → Step 5 : Matching")
        try:
            m_res = await match_assignments(
                profile_extraction_result = extraction_res,
                norm_result               = norm_result,
                distrib_result            = distrib_result,
                filter_result             = filter_result,
            )
            matching_dump = m_res.model_dump()
            steps = {
                **steps,
                "matching": {"status": "done", "result": matching_dump},
            }
            gs = m_res.global_summary
            print(
                f"[staffing] ✅ Step 5 terminé — "
                f"{gs.fully_staffed_sprints}/{gs.total_sprints} fully | "
                f"{gs.partially_staffed_sprints} partial | "
                f"{gs.assignments_with_warning} warning(s) | "
                f"{gs.total_recommended_team_members} membres recommandés"
            )
        except Exception as e:
            print(f"[staffing] ❌ Step 5 échoué : {e}")
            steps = {**steps, "matching": {"status": "error", "error": str(e), "result": None}}
            return _return(staffing, steps)

        sprints_state = _build_sprints_state(distrib_result)
        return _return(staffing, steps, sprints=sprints_state)

    # ── Tous les steps sont done → en attente de la validation PM ─
    # La persistance DB est repoussée à node_jira_sync (après validation PM),
    # pour permettre au PM de modifier les affectations avant que les
    # tables staffing_assignments / sprints soient écrites.
    print("[staffing] ⏳ tous les steps terminés — en attente de la validation PM")
    sprints_state = _build_sprints_state(distrib_result)
    return _return(staffing, steps, sprints=sprints_state)


def _build_sprints_state(distrib_result: dict | None) -> list[dict] | None:
    """
    Construit state["sprints"] depuis distrib_result.
    Format consommé par node_jira_sync._sync_sprints. Pas de db_id ici —
    il sera connu seulement après que jira_sync ait persisté les sprints
    (la sync utilise sprint_number pour relier le db_id).
    """
    if not distrib_result:
        return None

    sprint_to_story_dbids: dict[int, list[int]] = {}
    for sprint_win in (distrib_result or {}).get("sprints", []):
        sn = sprint_win.get("sprint_number")
        if sn is None:
            continue
        sprint_to_story_dbids[sn] = [
            st.get("story_id")
            for st in sprint_win.get("assigned_stories", [])
            if st.get("story_id") is not None
        ]

    sprints_state: list[dict] = []
    for sprint_win in (distrib_result or {}).get("sprints", []):
        sn = sprint_win.get("sprint_number")
        if sn is None:
            continue
        sprints_state.append({
            "sprint_number":      sn,
            "name":               f"Sprint {sn}",
            "start_date":         sprint_win.get("start_date"),
            "end_date":           sprint_win.get("end_date"),
            "target_capacity_sp": sprint_win.get("target_capacity_sp"),
            "actual_sp":          sprint_win.get("actual_sp"),
            "story_ids":          sprint_to_story_dbids.get(sn, []),
        })

    return sprints_state


def _return(staffing: dict, steps: dict, sprints: list[dict] | None = None) -> dict:
    out = {
        "staffing":          {**staffing, "steps": steps},
        "current_phase":     "staffing",
        "validation_status": "pending_human",
        "human_feedback":    None,
        "error":             None,
    }
    if sprints is not None:
        out["sprints"] = sprints
    return out
