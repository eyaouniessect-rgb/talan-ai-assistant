# agents/pm/agents/staffing/schemas.py
# ═══════════════════════════════════════════════════════════════
# Pydantic models partagés par tous les steps de la phase Staffing.
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# STEP 1 — Profile Extraction
# ──────────────────────────────────────────────────────────────

class StoryProfileRequirement(BaseModel):
    story_id:          int
    required_profiles: list[str] = Field(description="Ex: ['Backend Developer', 'AI Engineer']")
    required_skills:   list[str] = Field(description="Ex: ['FastAPI', 'NLP', 'PostgreSQL']")
    required_level:    Literal["JUNIOR", "MID", "SENIOR"] = Field(default="MID")


class ProfileExtractionResult(BaseModel):
    stories_profiles: list[StoryProfileRequirement]


# ──────────────────────────────────────────────────────────────
# STEP 2 — Profile Normalization
# ──────────────────────────────────────────────────────────────

class ProfileMapping(BaseModel):
    required_profile:   str
    matched_job_titles: list[str]
    match_type:         Literal["exact", "close", "none"]
    confidence:         float = Field(ge=0.0, le=1.0)
    reason:             str = ""


class ProfileNormalizationResult(BaseModel):
    profile_mappings:     list[ProfileMapping]
    available_job_titles: list[str]
    pm_decisions: dict[str, str] = Field(
        default_factory=dict,
        description='{"Frontend Developer": "accept", "ETL Engineer": "recruit"}'
    )


# ──────────────────────────────────────────────────────────────
# STEP 3 — Story Distribution (Répartition initiale des stories)
# ──────────────────────────────────────────────────────────────

class SprintStory(BaseModel):
    story_id:     int
    title:        str
    story_points: int
    rank:         int


class SprintWindow(BaseModel):
    sprint_number:      int
    start_date:         str   # "YYYY-MM-DD"
    end_date:           str   # "YYYY-MM-DD" (10e jour ouvrable)
    target_capacity_sp: int
    assigned_stories:   list[SprintStory]
    actual_sp:          int
    delta_sp:           int   # actual - target (>0 = dépassement, <0 = sous-chargé)


class StoryDistributionResult(BaseModel):
    number_of_sprints:         int
    sprint_duration_days:      int   # toujours 10 jours ouvrables
    total_story_points:        int
    target_capacity_per_sprint: int
    sprints:                   list[SprintWindow]


# ──────────────────────────────────────────────────────────────
# STEP 4 — Candidate Filtering (par sprint)
# ──────────────────────────────────────────────────────────────

class AvailabilityPeriod(BaseModel):
    start_date:  str
    end_date:    str
    reason:      str                                           # message lisible (ex: "Congé annuel")
    reason_type: Literal["leave", "assignment"] = "leave"     # type de blocage


class CandidateEmployee(BaseModel):
    employee_id:         int
    name:                str
    job_title:           str
    seniority:           Literal["JUNIOR", "MID", "SENIOR"]
    skills:              list[str]
    availability_status: Literal["Available", "Partially Available", "Unavailable"]
    unavailable_periods: list[AvailabilityPeriod] = []
    profile_match:       Literal["exact", "close"]
    matched_profile:     str


class SprintCandidates(BaseModel):
    sprint_number:                    int
    start_date:                       str
    end_date:                         str
    candidates_by_profile:            dict[str, list[CandidateEmployee]]
    unavailable_candidates_by_profile: dict[str, list[CandidateEmployee]] = {}
    total_available:                  int


class CandidateFilteringResult(BaseModel):
    candidates_by_sprint: dict[str, SprintCandidates]   # clé = "sprint_1", "sprint_2" …
    missing_profiles:     list[str] = []                # profils marqués "recruit"


# ──────────────────────────────────────────────────────────────
# STEP 5 — Matching
# ──────────────────────────────────────────────────────────────
#
# 3 niveaux de statut :
#   - profil dans une story  → ProfileAssignmentStatus
#   - story complète         → StoryStatus
#   - sprint complet         → SprintStatus
#
# Score de compétences : déterministe, calculé à partir du retour LLM
#   skill_score = (matched + inferred) / max(1, total_required)
#   match_level :
#     ≥ 0.85 → excellent | ≥ 0.65 → good | ≥ 0.40 → medium | < 0.40 → weak
# ──────────────────────────────────────────────────────────────

ProfileAssignmentStatus = Literal[
    "assigned",
    "assigned_with_warning",
    "missing_profile",
    "capacity_gap",
    "seniority_gap",
    "no_available_candidate",
    "manual_decision_required",
]

StoryStatus = Literal[
    "fully_assigned",
    "partially_assigned",
    "not_assigned",
    "manual_decision_required",
]

SprintStatus = Literal[
    "fully_staffed",
    "partially_staffed",
    "manual_decision_required",
    "not_staffed",
]

MatchLevel = Literal["excellent", "good", "medium", "weak"]
WarningType = Literal["medium_skill_match", "weak_skill_match"]


class CandidateOption(BaseModel):
    """Option proposée au PM en cas de manual_decision_required."""
    employee_id:           int
    name:                  str
    job_title:             str
    seniority:             Literal["JUNIOR", "MID", "SENIOR"]
    skill_score:           float = Field(ge=0.0, le=1.0)
    match_level:           MatchLevel
    matched_skills:        list[str] = []
    inferred_matches:      list[str] = []
    missing_skills:        list[str] = []
    remaining_capacity_sp: float
    waste:                 float
    reason:                str = ""


class ProfileAssignment(BaseModel):
    """Résultat du matching pour UN profil requis dans UNE user story."""
    required_profile:  str
    required_level:    Optional[Literal["JUNIOR", "MID", "SENIOR"]] = None
    employee_id:       Optional[int] = None
    employee_name:     Optional[str] = None
    employee_seniority: Optional[Literal["JUNIOR", "MID", "SENIOR"]] = None
    job_title:         Optional[str] = None
    allocated_sp:      float
    skill_score:       Optional[float] = Field(default=None, ge=0.0, le=1.0)
    match_level:       Optional[MatchLevel] = None
    matched_skills:    list[str] = []
    inferred_matches:  list[str] = []
    missing_skills:    list[str] = []
    status:            ProfileAssignmentStatus
    warning_type:      Optional[WarningType] = None
    # Si la séniorité a été dégradée (ex : story requiert SENIOR mais on a affecté MID),
    # on indique ici le niveau initialement requis. None sinon.
    seniority_downgrade_from: Optional[Literal["JUNIOR", "MID", "SENIOR"]] = None
    candidate_options: list[CandidateOption] = []   # rempli ssi status=manual_decision_required
    # Tous les candidats éligibles scorés par le LLM pour ce (story × profile),
    # peu importe celui qui a été retenu. Permet au PM de changer l'affectation
    # via le bouton "Changer l'affectation" côté frontend.
    alternative_candidates: list[CandidateOption] = []
    reason:            str = ""


class StoryMatching(BaseModel):
    story_id:        int
    story_title:     str
    story_points:    int
    required_level:  Literal["JUNIOR", "MID", "SENIOR"]
    required_skills: list[str] = []
    story_status:    StoryStatus
    assignments:     list[ProfileAssignment]


class TeamMemberRecommended(BaseModel):
    employee_id:           int
    name:                  str
    job_title:             str
    seniority:             Literal["JUNIOR", "MID", "SENIOR"]
    capacity_sp:           int
    assigned_sp:           float
    remaining_capacity_sp: float
    stories_handled:       int = 0


class SprintMatching(BaseModel):
    sprint_number:        int
    start_date:           str
    end_date:             str
    sprint_status:        SprintStatus
    planned_story_points: int
    recommended_team:     list[TeamMemberRecommended] = []
    story_assignments:    list[StoryMatching]         = []
    issues:               list[ProfileAssignment]     = []  # vue filtrée des erreurs profils
    manual_decisions:     list[ProfileAssignment]     = []  # vue filtrée des manual


class GlobalMatchingSummary(BaseModel):
    total_sprints:                 int
    fully_staffed_sprints:         int = 0
    partially_staffed_sprints:     int = 0
    manual_decision_sprints:       int = 0
    not_staffed_sprints:           int = 0
    total_recommended_team_members: int = 0
    missing_profiles:              list[str] = []
    total_issues:                  int = 0
    assignments_with_warning:      int = 0
    total_assignments:             int = 0


class MatchingResult(BaseModel):
    matching_by_sprint: dict[str, SprintMatching]   # clé = "sprint_1", "sprint_2"…
    global_summary:     GlobalMatchingSummary


# ──────────────────────────────────────────────────────────────
# STEP 6 — Velocity & Feasibility
# ──────────────────────────────────────────────────────────────

class SprintCapacity(BaseModel):
    sprint:   int
    capacity: int


class TeamMember(BaseModel):
    employee_id:           int
    name:                  str
    job_title:             str
    seniority:             Literal["JUNIOR", "MID", "SENIOR"]
    capacity_per_sprint:   int
    assigned_story_points: int
    availability_status:   Literal["Available", "Partially Available"]


class VelocityFeasibilityResult(BaseModel):
    number_of_sprints:          int
    sprint_duration_days:       int
    estimated_velocity_average: float
    required_velocity:          float
    velocity_by_sprint:         list[SprintCapacity]
    feasibility:                Literal["Feasible", "Risky", "Not Feasible"]
    message:                    str
    recommendations:            list[str]


# ──────────────────────────────────────────────────────────────
# SORTIE FINALE — phase Staffing complète
# ──────────────────────────────────────────────────────────────

class StaffingStepStatus(BaseModel):
    status: Literal["pending", "running", "done", "error"]
    result: Optional[dict] = None
    error:  Optional[str]  = None


class StaffingOutput(BaseModel):
    project_id:          int
    total_story_points:  int
    project_start_date:  str
    project_end_date:    str

    steps: dict[str, StaffingStepStatus] = Field(
        default_factory=lambda: {
            "profile_extraction":    StaffingStepStatus(status="pending"),
            "profile_normalization": StaffingStepStatus(status="pending"),
            "story_distribution":    StaffingStepStatus(status="pending"),
            "candidate_filtering":   StaffingStepStatus(status="pending"),
            "matching":              StaffingStepStatus(status="pending"),
            "velocity_feasibility":  StaffingStepStatus(status="pending"),
        }
    )

    required_profiles:  list[dict] = []
    recommended_team:   list[dict] = []
    assignments:        list[dict] = []
    velocity:           dict       = {}
    recommendations:    list[str]  = []
