# agents/pm/agents/staffing/steps/matching/service.py
# ═══════════════════════════════════════════════════════════════
# Step 5 — Matching (orchestrateur).
#
# Pour chaque sprint :
#   1. Init capacity_state des candidats du sprint (par séniorité).
#   2. Pour chaque profil P du sprint, appel LLM UNIQUE qui score
#      tous les couples (story_du_sprint_qui_a_besoin_de_P, candidat_éligible).
#   3. Itère les stories dans l'ordre rang (déjà fourni par story_distribution).
#   4. Pour chaque (story, profile) : filtrage dur, sélection best-fit + tie-break,
#      consommation de capacité, fabrication d'un ProfileAssignment.
#   5. Calcule story_status, recommended_team, sprint_status.
#
# Le LLM ne fait QUE scorer les compétences. Le reste est déterministe.
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
import asyncio
import json
import re
from typing import Optional

from agents.pm.agents.staffing.schemas import (
    CandidateOption,
    GlobalMatchingSummary,
    MatchingResult,
    ProfileAssignment,
    SprintMatching,
    StoryMatching,
    TeamMemberRecommended,
)
from agents.pm.agents.staffing.steps.matching.prompt import (
    MATCHING_SYSTEM_PROMPT,
    build_matching_prompt,
)
from agents.pm.agents.staffing.steps.matching.selection import (
    CAPACITY_BY_SENIORITY,
    REASON_BY_GAP,
    REASON_BY_WARNING,
    REASON_MANUAL_DECISION,
    classify_match_level,
    compute_skill_score,
    compute_sprint_status,
    compute_story_status,
    consume_capacity,
    filter_eligible_with_degradation,
    init_capacity_state,
    pick_candidate,
    reason_seniority_downgrade,
)
from app.core.groq_client import invoke_with_fallback


_MODEL              = "openai/gpt-oss-120b"
_MAX_TOKENS         = 12000  # batch global peut contenir jusqu'à _MAX_PAIRS_PER_BATCH paires
_RETRY_ATTEMPTS     = 3
_NVIDIA_RETRY_DELAY = 7
# Limite stricte du nombre de paires (story × candidate) par appel LLM.
# Au-delà, on chunk les candidats en plusieurs appels parallèles. Empêche
# la troncature de la réponse JSON (~150 tokens par paire en sortie).
_MAX_PAIRS_PER_BATCH = 30


# ──────────────────────────────────────────────────────────────
# Appel LLM pour un batch (sprint × profile)
# ──────────────────────────────────────────────────────────────

async def _call_llm_skill_scoring(
    profile:         str,
    stories_payload: list[dict],
    candidates_payload: list[dict],
    sprint_number:   int,
    nvidia_key_index: int,
) -> dict:
    """
    Retourne dict {(story_id, employee_id) : {matched, inferred, missing, reason}}.
    En cas d'échec total LLM, retourne {} → fallback caller (medium par défaut).
    """
    if not stories_payload or not candidates_payload:
        return {}

    user_prompt = build_matching_prompt(profile, stories_payload, candidates_payload)

    raw: Optional[str] = None
    for attempt in range(1, _RETRY_ATTEMPTS + 1):
        try:
            raw = await invoke_with_fallback(
                model            = _MODEL,
                messages         = [
                    {"role": "system", "content": MATCHING_SYSTEM_PROMPT},
                    {"role": "user",   "content": user_prompt},
                ],
                max_tokens       = _MAX_TOKENS,
                temperature      = 0,
                nvidia_key_index = nvidia_key_index,
                nvidia_max_keys  = 1,
                skip_groq        = True,
            )
            if raw and raw.strip():
                print(
                    f"[matching] ✅ Sprint {sprint_number} / {profile} — "
                    f"LLM OK (tentative {attempt}, "
                    f"{len(stories_payload)} stories × {len(candidates_payload)} candidats)"
                )
                break
            raise ValueError("Réponse LLM vide")
        except Exception as e:
            print(
                f"[matching] ⚠️  Sprint {sprint_number} / {profile} — "
                f"LLM tentative {attempt}/{_RETRY_ATTEMPTS} échouée : "
                f"{type(e).__name__}: {str(e)[:80]}"
            )
            if attempt < _RETRY_ATTEMPTS:
                await asyncio.sleep(_NVIDIA_RETRY_DELAY)

    if not raw:
        print(f"[matching] ❌ Sprint {sprint_number} / {profile} — LLM KO après {_RETRY_ATTEMPTS} tentatives")
        return {}

    try:
        parsed = _parse_llm_response(raw, stories_payload)
        expected = len(stories_payload) * len(candidates_payload)
        if len(parsed) < expected:
            # Réponse incomplète : probablement troncature (max_tokens insuffisant
            # ou JSON malformé en queue). On log mais on retourne ce qui a été parsé.
            print(
                f"[matching] ⚠️  Profil '{profile}' — {len(parsed)}/{expected} paires "
                f"parsées (réponse possiblement tronquée, longueur raw={len(raw)} chars)"
            )
        return parsed
    except Exception as e:
        # Log une portion du raw pour diagnostic
        head = (raw or "")[:200].replace("\n", " ")
        tail = (raw or "")[-200:].replace("\n", " ")
        print(
            f"[matching] ⚠️  Profil '{profile}' — parsing KO ({type(e).__name__}: {e}) | "
            f"raw_len={len(raw or '')} | head={head!r} | tail={tail!r}"
        )
        return {}


def _parse_llm_response(raw: str, stories_payload: list[dict]) -> dict:
    """
    Retourne {(story_id, employee_id): {matched, inferred, missing, reason}}.

    - Filtre les skills hallucinés : ne garde que ce qui est dans required_skills
      de la story.
    - Garantit la disjonction matched / inferred / missing.
    - N'AJOUTE PLUS automatiquement les skills non classifiées comme "missing".
      Le LLM scope volontairement les skills au profil ; les omises sont
      considérées comme NON-RELEVANT pour ce profil (ex : un Backend ne doit
      pas être pénalisé pour les skills Frontend de la même story).
    """
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
    data  = json.loads(clean)

    raw_scores = data.get("scores", [])
    if not isinstance(raw_scores, list):
        raise ValueError("Le champ 'scores' doit être une liste.")

    # Map des required_skills par story (pour filtrer/valider)
    required_by_story: dict[int, list[str]] = {
        int(s["story_id"]): list(s.get("required_skills", []))
        for s in stories_payload
    }

    out: dict = {}
    for entry in raw_scores:
        if not isinstance(entry, dict):
            continue
        try:
            sid = int(entry.get("story_id"))
            eid = int(entry.get("employee_id"))
        except (TypeError, ValueError):
            continue

        required = required_by_story.get(sid, [])
        required_lower = {r.lower(): r for r in required}  # normalisation casse

        def _filter(seq) -> list[str]:
            if not isinstance(seq, list):
                return []
            seen, result = set(), []
            for item in seq:
                key = str(item).strip().lower()
                canonical = required_lower.get(key)
                if canonical and canonical not in seen:
                    seen.add(canonical)
                    result.append(canonical)
            return result

        matched  = _filter(entry.get("matched_skills",   []))
        inferred = _filter(entry.get("inferred_matches", []))
        missing  = _filter(entry.get("missing_skills",   []))

        # Disjonction stricte : matched > inferred > missing
        inferred = [s for s in inferred if s not in matched]
        positive = set(matched) | set(inferred)
        missing  = [s for s in missing if s not in positive]

        # IMPORTANT : on N'AJOUTE PAS les required_skills manquantes du retour.
        # Le LLM scope volontairement par profil — les skills omises sont
        # supposées relever d'un AUTRE profil de la story, pas manquantes
        # pour le candidat scoré.

        out[(sid, eid)] = {
            "matched_skills":   matched,
            "inferred_matches": inferred,
            "missing_skills":   missing,
            "reason":           str(entry.get("reason", "")).strip(),
        }
    return out


# ──────────────────────────────────────────────────────────────
# Helpers pour fabriquer un ProfileAssignment
# ──────────────────────────────────────────────────────────────

def _make_unassigned(
    profile:        str,
    required_level: str,
    allocated_sp:   float,
    status:         str,
    reason:         Optional[str] = None,
) -> ProfileAssignment:
    return ProfileAssignment(
        required_profile = profile,
        required_level   = required_level,
        allocated_sp     = allocated_sp,
        status           = status,
        reason           = reason or REASON_BY_GAP.get(status, ""),
    )


def _compose_reason(
    score_reason:        str,
    decision:            str,
    warning_type:        Optional[str],
    seniority_downgrade: Optional[str],
    actual_seniority:    Optional[str],
) -> str:
    """Compose le reason final en concaténant les warnings actifs (skill + séniorité)."""
    parts: list[str] = []
    if seniority_downgrade and actual_seniority:
        parts.append(reason_seniority_downgrade(seniority_downgrade, actual_seniority))
    if warning_type:
        parts.append(REASON_BY_WARNING.get(warning_type, ""))
    if not parts:
        return score_reason or "Bon alignement des compétences avec les besoins de la story."
    # On ajoute toujours le commentaire LLM en complément si présent.
    if score_reason:
        parts.append(f"Note IA : {score_reason}")
    return " ".join(p for p in parts if p)


def _build_alternatives(scored: list[dict], allocated_sp: float) -> list[CandidateOption]:
    """
    Construit la liste des candidats alternatifs (avec leurs scores LLM)
    à partir des candidats déjà scorés pour un (story × profile).
    Le PM peut changer l'affectation vers n'importe lequel d'eux.
    """
    return [
        CandidateOption(
            employee_id           = c["employee_id"],
            name                  = c.get("name", ""),
            job_title             = c.get("job_title", ""),
            seniority             = c.get("seniority", "MID"),
            skill_score           = c.get("skill_score", 0.0),
            match_level           = c.get("match_level", "weak"),
            matched_skills        = c.get("matched_skills",   []),
            inferred_matches      = c.get("inferred_matches", []),
            missing_skills        = c.get("missing_skills",   []),
            remaining_capacity_sp = c.get("remaining_capacity_sp", 0.0),
            waste                 = round(c.get("remaining_capacity_sp", 0.0) - allocated_sp, 4),
            reason                = c.get("reason", ""),
        )
        for c in scored
    ]


def _make_assigned(
    profile:             str,
    required_level:      str,
    allocated_sp:        float,
    chosen:              dict,
    score_data:          dict,
    skill_score:         float,
    match_level:         str,
    decision:            str,
    warning_type:        Optional[str],
    seniority_downgrade: Optional[str] = None,
    alternatives:        Optional[list[dict]] = None,
) -> ProfileAssignment:
    actual_seniority = chosen.get("seniority")
    reason = _compose_reason(
        score_reason        = score_data.get("reason", ""),
        decision            = decision,
        warning_type        = warning_type,
        seniority_downgrade = seniority_downgrade,
        actual_seniority    = actual_seniority,
    )
    # Si dégradation détectée, on bascule en assigned_with_warning même
    # si le skill match est bon (pour que le PM voie clairement l'alerte).
    final_status = decision
    if seniority_downgrade and decision == "assigned":
        final_status = "assigned_with_warning"
    return ProfileAssignment(
        required_profile         = profile,
        required_level           = required_level,
        employee_id              = chosen["employee_id"],
        employee_name            = chosen.get("name"),
        employee_seniority       = actual_seniority,
        job_title                = chosen.get("job_title"),
        allocated_sp             = allocated_sp,
        skill_score              = skill_score,
        match_level              = match_level,
        matched_skills           = score_data.get("matched_skills",   []),
        inferred_matches         = score_data.get("inferred_matches", []),
        missing_skills           = score_data.get("missing_skills",   []),
        status                   = final_status,
        warning_type             = warning_type,
        seniority_downgrade_from = seniority_downgrade,
        alternative_candidates   = _build_alternatives(alternatives or [], allocated_sp),
        reason                   = reason,
    )


def _make_manual(
    profile:        str,
    required_level: str,
    allocated_sp:   float,
    options:        list[dict],
    seniority_downgrade: Optional[str] = None,
) -> ProfileAssignment:
    """Construit un ProfileAssignment status=manual_decision_required."""
    reason = REASON_MANUAL_DECISION
    if seniority_downgrade and options:
        actual = options[0].get("seniority", "MID")
        reason = (
            reason_seniority_downgrade(seniority_downgrade, actual)
            + " Plusieurs candidats équivalents — le PM doit trancher."
        )
    return ProfileAssignment(
        required_profile         = profile,
        required_level           = required_level,
        allocated_sp             = allocated_sp,
        status                   = "manual_decision_required",
        seniority_downgrade_from = seniority_downgrade,
        reason                   = reason,
        candidate_options        = [
            CandidateOption(
                employee_id           = o["employee_id"],
                name                  = o["name"],
                job_title             = o.get("job_title", ""),
                seniority             = o.get("seniority", "MID"),
                skill_score           = o["skill_score"],
                match_level           = o["match_level"],
                matched_skills        = o.get("matched_skills",   []),
                inferred_matches      = o.get("inferred_matches", []),
                missing_skills        = o.get("missing_skills",   []),
                remaining_capacity_sp = o["remaining_capacity_sp"],
                waste                 = o["waste"],
                reason                = o.get("reason", ""),
            )
            for o in options
        ],
    )


# ──────────────────────────────────────────────────────────────
# Traitement d'un sprint complet
# ──────────────────────────────────────────────────────────────

async def _compute_global_scores(
    sprints:                list[dict],
    candidates_by_sprint:   dict[str, dict],
    profile_extraction_idx: dict[int, dict],
    pm_decisions:           dict[str, str],
    missing_global:         set[str],
) -> dict[str, dict]:
    """
    Fait UN SEUL appel LLM par profil en regroupant toutes les stories
    de TOUS les sprints. Réduit de S×P appels à P appels.

    Retourne global_score_maps[profile][(story_id, employee_id)] = score_data.
    """
    # Étape 1 : collecter toutes les stories + candidats par profil (cross-sprint)
    global_needs: dict[str, dict] = {}   # profile → {stories: {sid: {...}}, candidates: {eid: {...}}}

    for sprint in sprints:
        sn  = sprint.get("sprint_number")
        key = f"sprint_{sn}"
        sc  = candidates_by_sprint.get(key, {}) or {}
        cands_by_profile = sc.get("candidates_by_profile", {})

        for story in sprint.get("assigned_stories", []):
            sid  = story["story_id"]
            spec = profile_extraction_idx.get(sid)
            if not spec:
                continue
            for profile in spec["required_profiles"]:
                if profile in missing_global or pm_decisions.get(profile, "accept") == "recruit":
                    continue
                if profile not in global_needs:
                    global_needs[profile] = {"stories": {}, "candidates": {}}

                global_needs[profile]["stories"][sid] = {
                    "story_id":              sid,
                    "title":                 story.get("title", ""),
                    "story_points":          story.get("story_points", 0),
                    "required_skills":       spec.get("required_skills", []),
                    "required_level":        spec.get("required_level",  "MID"),
                    "all_required_profiles": spec.get("required_profiles", []),
                }
                # Candidats du sprint pour ce profil (dédup par employee_id)
                for c in cands_by_profile.get(profile, []):
                    eid = c["employee_id"]
                    if eid not in global_needs[profile]["candidates"]:
                        global_needs[profile]["candidates"][eid] = {
                            "employee_id": eid,
                            "name":        c.get("name", ""),
                            "job_title":   c.get("job_title", ""),
                            "seniority":   c.get("seniority", "MID"),
                            "skills":      c.get("skills", []),
                        }

    # Étape 2 : pour chaque profil, on chunk les candidats si la batch est trop grosse
    # afin que la réponse JSON LLM tienne dans _MAX_TOKENS sans troncature.
    # Chaque chunk = 1 appel LLM contenant TOUTES les stories du profil mais
    # uniquement N candidats, où N est calculé pour rester ≤ _MAX_PAIRS_PER_BATCH.
    global_score_maps: dict[str, dict] = {p: {} for p in global_needs}

    # Préparer la liste des batches (profile, stories_payload, candidates_chunk)
    batches: list[tuple[str, list[dict], list[dict]]] = []
    for profile, need in global_needs.items():
        stories_payload    = list(need["stories"].values())
        candidates_payload = list(need["candidates"].values())
        if not stories_payload or not candidates_payload:
            continue
        # Combien de candidats par appel pour rester ≤ _MAX_PAIRS_PER_BATCH ?
        n_stories = len(stories_payload)
        cands_per_call = max(1, _MAX_PAIRS_PER_BATCH // n_stories)
        for i in range(0, len(candidates_payload), cands_per_call):
            chunk = candidates_payload[i : i + cands_per_call]
            batches.append((profile, stories_payload, chunk))

    async def _score_batch(batch_idx: int, profile: str,
                           stories_payload: list[dict],
                           candidates_chunk: list[dict]) -> None:
        scores = await _call_llm_skill_scoring(
            profile            = profile,
            stories_payload    = stories_payload,
            candidates_payload = candidates_chunk,
            sprint_number      = 0,
            nvidia_key_index   = batch_idx % 2,
        )
        global_score_maps[profile].update(scores)
        print(
            f"[matching] ✅ Profil '{profile}' chunk {batch_idx + 1} — "
            f"{len(stories_payload)} stories × {len(candidates_chunk)} candidats "
            f"({len(scores)}/{len(stories_payload) * len(candidates_chunk)} paires scorées)"
        )

    if batches:
        print(
            f"[matching] 🚀 {len(global_needs)} profil(s) → {len(batches)} appel(s) LLM "
            f"(chunké pour éviter troncature JSON)"
        )
        await asyncio.gather(*[
            _score_batch(idx, profile, stories_payload, chunk)
            for idx, (profile, stories_payload, chunk) in enumerate(batches)
        ])

    return global_score_maps


async def _match_sprint(
    sprint:                 dict,
    sprint_candidates:      dict,
    profile_extraction_idx: dict[int, dict],
    pm_decisions:           dict[str, str],
    missing_global:         set[str],
    nvidia_key_index:       int,
    precomputed_scores:     dict[str, dict],   # global score map, pré-calculé
) -> SprintMatching:
    sprint_number = sprint["sprint_number"]
    start_date    = sprint.get("start_date", "")
    end_date      = sprint.get("end_date",   "")
    assigned_stories_in_sprint = sprint.get("assigned_stories", [])

    print(
        f"[matching] ▶ Sprint {sprint_number} ({start_date} → {end_date}) — "
        f"{len(assigned_stories_in_sprint)} stories"
    )

    # 1. Init capacity state à partir de tous les candidats du sprint (déduplifiés)
    candidates_by_profile: dict[str, list[dict]] = sprint_candidates.get("candidates_by_profile", {})
    all_candidates: dict[int, dict] = {}
    for profile, c_list in candidates_by_profile.items():
        for c in c_list:
            all_candidates.setdefault(c["employee_id"], c)
    capacity_state = init_capacity_state(all_candidates.values())

    # Les scores LLM sont fournis via precomputed_scores (calculés une fois globalement).

    # 4. Itérer les stories dans l'ordre fourni et fabriquer les assignments
    story_matchings: list[StoryMatching] = []
    issues:          list[ProfileAssignment] = []
    manual:          list[ProfileAssignment] = []

    for story in assigned_stories_in_sprint:
        sid          = story["story_id"]
        spec         = profile_extraction_idx.get(sid, {})
        required_profiles = spec.get("required_profiles", [])
        required_skills   = spec.get("required_skills",   [])
        required_level    = spec.get("required_level",    "MID")
        story_points      = story.get("story_points", 0)
        story_title       = story.get("title", "")

        n_profiles   = max(1, len(required_profiles))
        allocated_sp = round(float(story_points) / n_profiles, 4)

        per_profile_assignments: list[ProfileAssignment] = []

        for profile in required_profiles:
            # 4.a Profil à recruter ou non normalisé → missing_profile
            if profile in missing_global or pm_decisions.get(profile, "accept") == "recruit":
                pa = _make_unassigned(profile, required_level, allocated_sp, "missing_profile")
                per_profile_assignments.append(pa)
                issues.append(pa)
                continue

            # 4.b Filtrage dur AVEC dégradation gracieuse (SENIOR→MID→JUNIOR)
            cand_list = candidates_by_profile.get(profile, [])
            eligible, gap, seniority_downgrade = filter_eligible_with_degradation(
                candidates     = cand_list,
                required_level = required_level,
                allocated_sp   = allocated_sp,
                capacity_state = capacity_state,
            )
            if not eligible:
                pa = _make_unassigned(
                    profile, required_level, allocated_sp,
                    gap or "no_available_candidate",
                )
                per_profile_assignments.append(pa)
                issues.append(pa)
                continue

            # 4.c Récupérer les scores LLM pour les candidats éligibles
            scored: list[dict] = []
            scores_for_profile = precomputed_scores.get(profile, {})
            for c in eligible:
                key = (sid, c["employee_id"])
                score_data = scores_for_profile.get(key) or {
                    # Fallback : LLM KO ou couple absent → considérer medium au pire
                    "matched_skills":   [],
                    "inferred_matches": [],
                    "missing_skills":   list(required_skills),
                    "reason":           "Score LLM indisponible — évaluation par défaut.",
                }
                skill_score = compute_skill_score(
                    matched_skills   = score_data["matched_skills"],
                    inferred_matches = score_data["inferred_matches"],
                    missing_skills   = score_data["missing_skills"],
                )
                # En cas de fallback total, donner 0.5 pour ne pas bloquer le sprint.
                if not score_data["matched_skills"] and not score_data["inferred_matches"] \
                        and "indisponible" in score_data["reason"]:
                    skill_score = 0.5
                level = classify_match_level(skill_score)
                # Capacité restante au moment de cette story (à jour avec les
                # affectations précédentes du sprint). Sert au bouton "Changer
                # l'affectation" côté PM.
                remaining = capacity_state.get(c["employee_id"], {}).get("remaining_capacity_sp", 0.0)
                scored.append({
                    "employee_id":           c["employee_id"],
                    "name":                  c.get("name", ""),
                    "job_title":             c.get("job_title", ""),
                    "seniority":             c.get("seniority", "MID"),
                    "skills":                c.get("skills", []),
                    "skill_score":           skill_score,
                    "match_level":           level,
                    "matched_skills":        score_data["matched_skills"],
                    "inferred_matches":      score_data["inferred_matches"],
                    "missing_skills":        score_data["missing_skills"],
                    "reason":                score_data["reason"],
                    "remaining_capacity_sp": remaining,
                })

            # 4.d Sélection finale (déterministe)
            decision = pick_candidate(
                scored          = scored,
                allocated_sp    = allocated_sp,
                required_level  = required_level,
                capacity_state  = capacity_state,
            )

            if decision["decision"] == "manual_decision_required":
                pa = _make_manual(
                    profile, required_level, allocated_sp,
                    decision["candidate_options"],
                    seniority_downgrade=seniority_downgrade,
                )
                per_profile_assignments.append(pa)
                manual.append(pa)
                continue

            if decision["decision"] == "no_available_candidate" or decision["chosen"] is None:
                pa = _make_unassigned(profile, required_level, allocated_sp, "no_available_candidate")
                per_profile_assignments.append(pa)
                issues.append(pa)
                continue

            chosen = decision["chosen"]
            pa = _make_assigned(
                profile             = profile,
                required_level      = required_level,
                allocated_sp        = allocated_sp,
                chosen              = chosen,
                score_data          = chosen,
                skill_score         = chosen["skill_score"],
                match_level         = chosen["match_level"],
                decision            = decision["decision"],
                warning_type        = decision["warning_type"],
                seniority_downgrade = seniority_downgrade,
                alternatives        = scored,   # pour le bouton "Changer l'affectation"
            )
            per_profile_assignments.append(pa)
            consume_capacity(capacity_state, chosen["employee_id"], allocated_sp)

        # Calcul du story_status
        story_status = compute_story_status([a.status for a in per_profile_assignments])

        story_matchings.append(StoryMatching(
            story_id        = sid,
            story_title     = story_title,
            story_points    = story_points,
            required_level  = required_level,
            required_skills = required_skills,
            story_status    = story_status,
            assignments     = per_profile_assignments,
        ))

    # 5. recommended_team du sprint (candidats avec assigned_sp > 0)
    recommended_team: list[TeamMemberRecommended] = []
    for emp_id, state in capacity_state.items():
        if state["assigned_sp"] <= 0:
            continue
        recommended_team.append(TeamMemberRecommended(
            employee_id           = emp_id,
            name                  = state.get("name", ""),
            job_title             = state.get("job_title", ""),
            seniority             = state.get("seniority", "MID"),
            capacity_sp           = state["capacity_sp"],
            assigned_sp           = state["assigned_sp"],
            remaining_capacity_sp = state["remaining_capacity_sp"],
            stories_handled       = state.get("stories_handled", 0),
        ))

    # 6. sprint_status
    sprint_status = compute_sprint_status([s.story_status for s in story_matchings])

    planned_sp = sum(s.story_points for s in story_matchings)

    return SprintMatching(
        sprint_number        = sprint_number,
        start_date           = start_date,
        end_date             = end_date,
        sprint_status        = sprint_status,
        planned_story_points = planned_sp,
        recommended_team     = recommended_team,
        story_assignments    = story_matchings,
        issues               = issues,
        manual_decisions     = manual,
    )


# ──────────────────────────────────────────────────────────────
# Point d'entrée public
# ──────────────────────────────────────────────────────────────

async def match_assignments(
    profile_extraction_result: dict,
    norm_result:               dict,
    distrib_result:            dict,
    filter_result:             dict,
) -> MatchingResult:
    """
    Step 5 — Matching complet.

    Inputs (tous des dicts model_dump() des étapes précédentes) :
      profile_extraction_result : { stories_profiles: [{story_id, required_profiles, required_skills, required_level}] }
      norm_result               : { profile_mappings, available_job_titles, pm_decisions }
      distrib_result            : { sprints: [{sprint_number, start_date, end_date, assigned_stories: [...]}, ...] }
      filter_result             : { candidates_by_sprint: { "sprint_N": {candidates_by_profile, ...} }, missing_profiles }

    Sortie : MatchingResult.
    """
    print("[matching] ▶ Step 5 — Matching")

    # Index story_id → spec d'extraction
    profile_extraction_idx: dict[int, dict] = {
        int(s["story_id"]): {
            "required_profiles": list(s.get("required_profiles", [])),
            "required_skills":   list(s.get("required_skills",   [])),
            "required_level":    s.get("required_level", "MID"),
        }
        for s in profile_extraction_result.get("stories_profiles", [])
    }

    pm_decisions   = norm_result.get("pm_decisions", {})
    missing_global = set(filter_result.get("missing_profiles", []))
    sprints        = distrib_result.get("sprints", [])
    candidates_by_sprint = filter_result.get("candidates_by_sprint", {})

    # Étape A : UN appel LLM par profil (cross-sprint) — avant de traiter les sprints.
    # Réduit drastiquement le nombre d'appels (P au lieu de S×P).
    global_scores = await _compute_global_scores(
        sprints                = sprints,
        candidates_by_sprint   = candidates_by_sprint,
        profile_extraction_idx = profile_extraction_idx,
        pm_decisions           = pm_decisions,
        missing_global         = missing_global,
    )

    # Étape B : traitement séquentiel sprint par sprint avec les scores pré-calculés.
    # Les capacités sont indépendantes entre sprints (réinitialisées à chaque sprint).
    matching_by_sprint: dict[str, SprintMatching] = {}
    for i, sprint in enumerate(sprints):
        if not isinstance(sprint, dict):
            continue
        sn  = sprint.get("sprint_number")
        key = f"sprint_{sn}"
        sc  = candidates_by_sprint.get(key, {}) or {}
        sm  = await _match_sprint(
            sprint                 = sprint,
            sprint_candidates      = sc,
            profile_extraction_idx = profile_extraction_idx,
            pm_decisions           = pm_decisions,
            missing_global         = missing_global,
            nvidia_key_index       = i % 2,
            precomputed_scores     = global_scores,
        )
        matching_by_sprint[key] = sm

    # ── Résumé global ─────────────────────────────────────────
    total_sprints              = len(matching_by_sprint)
    fully_staffed_sprints      = sum(1 for s in matching_by_sprint.values() if s.sprint_status == "fully_staffed")
    partially_staffed_sprints  = sum(1 for s in matching_by_sprint.values() if s.sprint_status == "partially_staffed")
    manual_decision_sprints    = sum(1 for s in matching_by_sprint.values() if s.sprint_status == "manual_decision_required")
    not_staffed_sprints        = sum(1 for s in matching_by_sprint.values() if s.sprint_status == "not_staffed")

    # Membres uniques de l'équipe recommandée (cross-sprint)
    unique_member_ids: set[int] = set()
    total_assignments = 0
    assignments_with_warning = 0
    total_issues = 0
    for s in matching_by_sprint.values():
        for tm in s.recommended_team:
            unique_member_ids.add(tm.employee_id)
        for st in s.story_assignments:
            for a in st.assignments:
                total_assignments += 1
                if a.status == "assigned_with_warning":
                    assignments_with_warning += 1
        total_issues += len(s.issues)

    summary = GlobalMatchingSummary(
        total_sprints                  = total_sprints,
        fully_staffed_sprints          = fully_staffed_sprints,
        partially_staffed_sprints      = partially_staffed_sprints,
        manual_decision_sprints        = manual_decision_sprints,
        not_staffed_sprints            = not_staffed_sprints,
        total_recommended_team_members = len(unique_member_ids),
        missing_profiles               = sorted(missing_global),
        total_issues                   = total_issues,
        assignments_with_warning       = assignments_with_warning,
        total_assignments              = total_assignments,
    )

    print(
        f"[matching] ✅ Step 5 terminé — "
        f"{fully_staffed_sprints}/{total_sprints} fully | "
        f"{partially_staffed_sprints} partial | "
        f"{manual_decision_sprints} manual | "
        f"{not_staffed_sprints} not | "
        f"{assignments_with_warning} warning(s)"
    )

    return MatchingResult(
        matching_by_sprint = matching_by_sprint,
        global_summary     = summary,
    )
