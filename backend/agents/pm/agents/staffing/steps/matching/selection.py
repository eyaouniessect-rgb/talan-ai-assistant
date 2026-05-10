# agents/pm/agents/staffing/steps/matching/selection.py
# ═══════════════════════════════════════════════════════════════
# Step 5 — Matching : logique PURE et DÉTERMINISTE.
#
# Aucune I/O ici (DB, LLM, HTTP). Tout est testable en unit-tests.
# Le LLM est invoqué dans service.py et son retour est passé en argument
# à pick_candidate(...) sous forme de map {(story_id, employee_id): score_dict}.
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
from typing import Iterable, Optional

# ── Capacités par séniorité (constantes, override possible plus tard) ──
CAPACITY_BY_SENIORITY: dict[str, int] = {
    "JUNIOR": 6,
    "MID":    8,
    "SENIOR": 10,
}

SENIORITY_RANK: dict[str, int] = {
    "JUNIOR": 1,
    "MID":    2,
    "SENIOR": 3,
}

# ── Seuils de match_level (déterministes) ──────────────────────
MATCH_LEVEL_THRESHOLDS = [
    (0.85, "excellent"),
    (0.65, "good"),
    (0.40, "medium"),
    (0.0,  "weak"),
]

# ── Précision du score pour le tie-break (anti-jitter LLM) ─────
SKILL_SCORE_PRECISION = 2

# Tolérance numérique pour les comparaisons de capacité (float arithmetic).
EPS = 1e-9


# ──────────────────────────────────────────────────────────────
# Score & match_level
# ──────────────────────────────────────────────────────────────

def compute_skill_score(
    matched_skills:   list[str],
    inferred_matches: list[str],
    missing_skills:   list[str],
) -> float:
    """
    Score = (matched + inferred) / (matched + inferred + missing)
    Arrondi à SKILL_SCORE_PRECISION décimales.

    Le dénominateur est la somme des skills SCOPÉES au profil par le LLM
    (sous-ensemble des required_skills de la story relevant de ce profil
    précis). Empêche un Backend d'être pénalisé pour des skills Frontend
    de la même story.

    matched = compétence directement présente chez le candidat.
    inferred = compétence déduite via une compétence proche
               (ex : candidat a "React JS" → infère "JavaScript").
    missing = compétence relevant du profil mais absente du candidat.

    Si le scope est vide (matched + inferred + missing = 0) → 1.0 :
      aucune skill du profil n'était requise pour cette story, donc le
      candidat n'a rien à prouver.
    """
    relevant = len(matched_skills) + len(inferred_matches) + len(missing_skills)
    if relevant == 0:
        return 1.0
    score = (len(matched_skills) + len(inferred_matches)) / relevant
    score = max(0.0, min(1.0, score))
    return round(score, SKILL_SCORE_PRECISION)


def classify_match_level(skill_score: float) -> str:
    """skill_score → 'excellent' | 'good' | 'medium' | 'weak'."""
    for threshold, level in MATCH_LEVEL_THRESHOLDS:
        if skill_score >= threshold:
            return level
    return "weak"


def warning_for_match_level(level: str) -> Optional[str]:
    """Renvoie le warning_type associé si le niveau impose un avertissement."""
    if level == "medium":
        return "medium_skill_match"
    if level == "weak":
        return "weak_skill_match"
    return None


# ──────────────────────────────────────────────────────────────
# Filtrage déterministe (séniorité + capacité)
# ──────────────────────────────────────────────────────────────

def filter_eligible_with_degradation(
    candidates:       list[dict],
    required_level:   str,
    allocated_sp:     float,
    capacity_state:   dict[int, dict],
) -> tuple[list[dict], str, str | None]:
    """
    Filtrage avec DÉGRADATION GRACIEUSE de la séniorité.

    Pour chaque rang en partant du required_level vers JUNIOR :
      - On collecte les candidats de rang ≥ try_rank ayant assez de capacité.
      - Dès qu'on trouve un groupe non vide, on retourne ce groupe.

    Politique : si aucun SENIOR n'est disponible pour une story SENIOR, on
    affecte un MID (puis un JUNIOR si nécessaire) pour ne pas bloquer le
    matching. Le PM garde l'information via `downgrade_from`.

    Retourne (eligibles, gap_reason, downgrade_from) :
      - eligibles      : candidats retenus (vide si pas trouvé)
      - gap_reason     : "" si trouvé, sinon "no_available_candidate" | "capacity_gap"
      - downgrade_from : required_level si on a dû descendre le niveau, sinon None

    Note : "seniority_gap" n'est plus émis — la dégradation gracieuse le
    supplante. Si vraiment AUCUN candidat n'est disponible, on retourne
    "no_available_candidate" → l'UI propose un envoi RH.
    """
    if not candidates:
        return [], "no_available_candidate", None

    required_rank = SENIORITY_RANK.get(required_level, SENIORITY_RANK["MID"])

    # Cascade : essayer required_rank, puis required_rank - 1, …, jusqu'à 1
    for try_rank in range(required_rank, 0, -1):
        level_candidates = [
            c for c in candidates
            if SENIORITY_RANK.get(c.get("seniority", "MID"), SENIORITY_RANK["MID"]) >= try_rank
        ]
        with_capacity = [
            c for c in level_candidates
            if (state := capacity_state.get(c["employee_id"])) is not None
            and state["remaining_capacity_sp"] + EPS >= allocated_sp
        ]
        if with_capacity:
            downgrade_from = required_level if try_rank < required_rank else None
            return with_capacity, "", downgrade_from

    # Aucun candidat disponible à AUCUN niveau (avec capacité).
    # → soit aucun candidat n'a de capacité (capacity_gap), soit la liste est
    # vide à la base (déjà géré au début).
    return [], "capacity_gap", None


# Alias rétro-compatibilité — ancien nom, ancienne signature 2-tuple.
def filter_eligible_candidates(
    candidates:     list[dict],
    required_level: str,
    allocated_sp:   float,
    capacity_state: dict[int, dict],
) -> tuple[list[dict], str]:
    """Wrapper sans dégradation pour compat — préfère filter_eligible_with_degradation."""
    eligibles, gap, _ = filter_eligible_with_degradation(
        candidates, required_level, allocated_sp, capacity_state,
    )
    return eligibles, gap


# ──────────────────────────────────────────────────────────────
# Sélection du meilleur candidat (best-fit waste + tie-break)
# ──────────────────────────────────────────────────────────────

def _group_by_match_level(scored: list[dict]) -> dict[str, list[dict]]:
    """Regroupe les candidats par match_level."""
    groups: dict[str, list[dict]] = {}
    for c in scored:
        groups.setdefault(c["match_level"], []).append(c)
    return groups


def pick_best_match_group(scored: list[dict]) -> tuple[list[dict], str]:
    """
    Choisit le meilleur groupe disponible :
      excellent+good > medium > weak

    Retourne (group, level_label) où level_label ∈ {"excellent_or_good", "medium", "weak"}.
    """
    groups = _group_by_match_level(scored)
    eg = groups.get("excellent", []) + groups.get("good", [])
    if eg:
        return eg, "excellent_or_good"
    if groups.get("medium"):
        return groups["medium"], "medium"
    if groups.get("weak"):
        return groups["weak"], "weak"
    return [], "weak"


def _seniority_distance(c_seniority: str, required_level: str) -> int:
    """Distance de séniorité (préfère le candidat le plus proche du niveau requis)."""
    return abs(
        SENIORITY_RANK.get(c_seniority,    SENIORITY_RANK["MID"])
        - SENIORITY_RANK.get(required_level, SENIORITY_RANK["MID"])
    )


def pick_candidate(
    scored:          list[dict],
    allocated_sp:    float,
    required_level:  str,
    capacity_state:  dict[int, dict],
) -> dict:
    """
    Sélection finale parmi les candidats déjà scorés par le LLM.

    scored : list[dict] avec :
        employee_id, seniority, skill_score, match_level,
        matched_skills, inferred_matches, missing_skills, reason

    Algorithme (déterministe) :
      1. Garder le meilleur groupe (excellent+good > medium > weak).
      2. Best-fit waste = remaining - allocated, minimum.
      3. Si égalité → meilleur skill_score (arrondi).
      4. Si égalité → séniorité la plus proche du required_level.
      5. Si égalité → employee_id le plus petit (déterministe). Le PM peut
         changer le choix après coup via "Changer l'affectation".

    Retourne un dict :
      {
        "decision": "assigned" | "assigned_with_warning",
        "warning_type": str | None,
        "chosen": dict,                  # le candidat retenu
        "candidate_options": list[dict]  # toujours vide (plus de manual auto)
      }
    """
    if not scored:
        return {
            "decision":          "no_available_candidate",
            "warning_type":      None,
            "chosen":            None,
            "candidate_options": [],
        }

    group, level_label = pick_best_match_group(scored)
    if not group:
        return {
            "decision":          "no_available_candidate",
            "warning_type":      None,
            "chosen":            None,
            "candidate_options": [],
        }

    # 2. Calcul du waste
    enriched = []
    for c in group:
        remaining = capacity_state[c["employee_id"]]["remaining_capacity_sp"]
        waste     = round(remaining - allocated_sp, 4)
        enriched.append({**c, "waste": waste, "remaining_capacity_sp": remaining})

    # 3. Best-fit : minimum de waste
    min_waste = min(c["waste"] for c in enriched)
    pool      = [c for c in enriched if c["waste"] == min_waste]

    if len(pool) == 1:
        return _decide(pool[0], level_label, [])

    # 4. Tie-break : meilleur skill_score arrondi
    max_score = max(round(c["skill_score"], SKILL_SCORE_PRECISION) for c in pool)
    pool      = [
        c for c in pool
        if round(c["skill_score"], SKILL_SCORE_PRECISION) == max_score
    ]
    if len(pool) == 1:
        return _decide(pool[0], level_label, [])

    # 5. Tie-break : séniorité la plus proche du required_level
    min_dist = min(_seniority_distance(c["seniority"], required_level) for c in pool)
    pool     = [
        c for c in pool
        if _seniority_distance(c["seniority"], required_level) == min_dist
    ]
    if len(pool) == 1:
        return _decide(pool[0], level_label, [])

    # 6. Tie-break final : employee_id le plus petit (totalement déterministe).
    # Le PM peut changer ce choix après-coup via "Changer l'affectation" ;
    # plus de manual_decision_required sur égalités.
    pool.sort(key=lambda c: c["employee_id"])
    return _decide(pool[0], level_label, [])


def _decide(chosen: dict, level_label: str, candidate_options: list[dict]) -> dict:
    """Construit la sortie selon le groupe retenu."""
    if level_label == "medium":
        return {
            "decision":          "assigned_with_warning",
            "warning_type":      "medium_skill_match",
            "chosen":            chosen,
            "candidate_options": candidate_options,
        }
    if level_label == "weak":
        return {
            "decision":          "assigned_with_warning",
            "warning_type":      "weak_skill_match",
            "chosen":            chosen,
            "candidate_options": candidate_options,
        }
    return {
        "decision":          "assigned",
        "warning_type":      None,
        "chosen":            chosen,
        "candidate_options": candidate_options,
    }


# ──────────────────────────────────────────────────────────────
# Statuts agrégés story → sprint
# ──────────────────────────────────────────────────────────────

_PROFILE_OK_STATUSES = {"assigned", "assigned_with_warning"}
_PROFILE_ERROR_STATUSES = {
    "missing_profile",
    "capacity_gap",
    "seniority_gap",
    "no_available_candidate",
}


def compute_story_status(profile_statuses: list[str]) -> str:
    """
    Calcule le statut d'une user story à partir des statuts de ses profils :
      - manual si au moins un profil est manual_decision_required
      - fully_assigned si tous OK (assigned ou assigned_with_warning)
      - not_assigned si aucun n'est OK
      - partially_assigned sinon (mix OK + erreurs)
    """
    if not profile_statuses:
        return "not_assigned"

    if any(s == "manual_decision_required" for s in profile_statuses):
        return "manual_decision_required"

    ok_count = sum(1 for s in profile_statuses if s in _PROFILE_OK_STATUSES)

    if ok_count == len(profile_statuses):
        return "fully_assigned"
    if ok_count == 0:
        return "not_assigned"
    return "partially_assigned"


def compute_sprint_status(story_statuses: list[str]) -> str:
    """
    Calcule le statut d'un sprint à partir des statuts de ses stories :
      - manual si au moins une story est manual_decision_required
      - fully_staffed si toutes fully_assigned
      - not_staffed si toutes not_assigned (ou aucune story du tout)
      - partially_staffed sinon
    """
    if not story_statuses:
        return "not_staffed"

    if any(s == "manual_decision_required" for s in story_statuses):
        return "manual_decision_required"

    if all(s == "fully_assigned" for s in story_statuses):
        return "fully_staffed"

    if all(s == "not_assigned" for s in story_statuses):
        return "not_staffed"

    return "partially_staffed"


# ──────────────────────────────────────────────────────────────
# Init capacity_state
# ──────────────────────────────────────────────────────────────

def init_capacity_state(candidates_flat: Iterable[dict]) -> dict[int, dict]:
    """
    candidates_flat : ensemble de dicts candidats (déjà déduplifiés sur employee_id)
        dict requis : {employee_id, seniority}

    Retourne :
        { employee_id: {capacity_sp, assigned_sp, remaining_capacity_sp,
                        seniority, ...passthrough} }
    """
    state: dict[int, dict] = {}
    for c in candidates_flat:
        emp_id = c["employee_id"]
        if emp_id in state:
            continue
        capacity = CAPACITY_BY_SENIORITY.get(c.get("seniority", "MID"), 8)
        state[emp_id] = {
            **c,
            "capacity_sp":           capacity,
            "assigned_sp":           0.0,
            "remaining_capacity_sp": float(capacity),
            "stories_handled":       0,
        }
    return state


def consume_capacity(
    capacity_state: dict[int, dict],
    employee_id:    int,
    allocated_sp:   float,
) -> None:
    """Met à jour la capacité d'un candidat après affectation."""
    state = capacity_state[employee_id]
    state["assigned_sp"]           = round(state["assigned_sp"] + allocated_sp,           4)
    state["remaining_capacity_sp"] = round(state["remaining_capacity_sp"] - allocated_sp, 4)
    state["stories_handled"]      += 1


# ──────────────────────────────────────────────────────────────
# Reasons humains (FR) — utilisés par le service
# ──────────────────────────────────────────────────────────────

REASON_BY_GAP = {
    "no_available_candidate": "Aucun candidat disponible pour ce profil sur ce sprint.",
    "seniority_gap":          "Aucun candidat n'a la séniorité requise pour cette story.",
    "capacity_gap":           "Aucun candidat n'a assez de capacité restante sur ce sprint.",
    "missing_profile":        "Profil marqué à recruter par le Project Manager.",
}

REASON_BY_WARNING = {
    "medium_skill_match": (
        "Aucun candidat avec un bon niveau de compatibilité des compétences n'a été trouvé. "
        "Le candidat sélectionné présente une compatibilité moyenne."
    ),
    "weak_skill_match": (
        "Aucun candidat avec une compatibilité suffisante n'a été trouvé. "
        "Le candidat sélectionné présente une compatibilité faible et nécessite "
        "une validation ou un accompagnement par le PM."
    ),
}

REASON_MANUAL_DECISION = (
    "Plusieurs candidats sont strictement équivalents (même niveau de match, "
    "même waste, même score, même proximité de séniorité). Le PM doit trancher."
)


def reason_seniority_downgrade(required: str, actual: str) -> str:
    """Compose un message FR expliquant la dégradation de séniorité."""
    return (
        f"La user story requiert un profil {required} — aucun candidat {required} disponible. "
        f"Un profil {actual} a été affecté pour ne pas bloquer le matching. "
        f"Une vigilance ou un accompagnement par le PM est recommandé."
    )
