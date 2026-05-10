# agents/pm/agents/staffing/steps/candidate_filtering/service.py
# Step 4 — Candidate Filtering (par sprint)
#
# Logique :
#   Pour chaque sprint (dates exactes issues de story_distribution) :
#     Pour chaque profil avec décision PM = "accept" :
#       - Chercher les employés dont le job_title est dans matched_job_titles
#       - Exclure ceux qui ont un congé (PENDING ou APPROVED) qui chevauche le sprint
#       - Exclure ceux qui ont une affectation à un autre projet qui chevauche le sprint
#       → Ne retenir que les candidats 100% disponibles sur cette fenêtre
#
# Condition de chevauchement (dates) :
#   existing_start <= sprint_end AND existing_end >= sprint_start

from __future__ import annotations

from datetime import date

from agents.pm.agents.staffing.schemas import (
    AvailabilityPeriod,
    CandidateEmployee,
    CandidateFilteringResult,
    SprintCandidates,
)


async def _get_candidates_with_availability(
    job_titles:    list[str],
    sprint_start:  date,
    sprint_end:    date,
    project_id:    int,
) -> tuple[list[CandidateEmployee], list[CandidateEmployee]]:
    """
    Retourne (available, unavailable) pour les employés dont le job_title
    est dans job_titles, sur la fenêtre [sprint_start, sprint_end].

    Chaque employé indisponible est accompagné du détail de ses blocages :
      - Congés PENDING/APPROVED chevauchant le sprint → reason_type = "leave"
      - Affectations sur un autre projet chevauchant le sprint → reason_type = "assignment"
    """
    from sqlalchemy import select, and_, or_
    from sqlalchemy.orm import selectinload
    from app.database.connection import AsyncSessionLocal
    from app.database.models.hris.employee       import Employee
    from app.database.models.hris.employee_skill import EmployeeSkill
    from app.database.models.hris.leave          import Leave
    from app.database.models.crm.assignment      import Assignment
    from app.database.models.crm.project         import Project as CrmProject
    from app.database.models.hris.enums          import LeaveStatusEnum

    fmt = lambda d: d.isoformat() if d else "?"

    async with AsyncSessionLocal() as db:

        # 1. Tous les employés avec le bon job_title
        emp_rows = (
            await db.execute(
                select(Employee)
                .options(
                    selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
                    selectinload(Employee.user),
                )
                .where(Employee.job_title.in_(job_titles))
            )
        ).scalars().all()

        if not emp_rows:
            return [], []

        emp_ids = [e.id for e in emp_rows]

        # 2. Congés PENDING/APPROVED chevauchant le sprint
        leave_rows = (
            await db.execute(
                select(Leave).where(
                    and_(
                        Leave.employee_id.in_(emp_ids),
                        Leave.status.in_([LeaveStatusEnum.PENDING, LeaveStatusEnum.APPROVED]),
                        Leave.start_date <= sprint_end,
                        Leave.end_date   >= sprint_start,
                    )
                )
            )
        ).scalars().all()

        # leave_type peut être un enum ou une string selon la config de la colonne
        def _leave_label(leave) -> str:
            ltype = leave.leave_type
            raw   = ltype.value if hasattr(ltype, "value") else str(ltype)
            labels = {
                "annual":       "Congé annuel",
                "sick":         "Congé maladie",
                "maternity":    "Congé maternité",
                "paternity":    "Congé paternité",
                "unpaid":       "Congé sans solde",
                "remote":       "Télétravail",
                "other":        "Congé",
            }
            return labels.get(raw.lower(), f"Congé ({raw})")

        # emp_id → liste de AvailabilityPeriod (leave)
        leave_periods: dict[int, list] = {}
        for lv in leave_rows:
            leave_periods.setdefault(lv.employee_id, []).append(
                AvailabilityPeriod(
                    start_date  = fmt(lv.start_date),
                    end_date    = fmt(lv.end_date),
                    reason      = f"{_leave_label(lv)} du {fmt(lv.start_date)} au {fmt(lv.end_date)}",
                    reason_type = "leave",
                )
            )

        # 3. Affectations sur un AUTRE projet chevauchant le sprint
        assign_rows = (
            await db.execute(
                select(Assignment, CrmProject.name.label("project_name")).join(
                    CrmProject, Assignment.project_id == CrmProject.id
                ).where(
                    and_(
                        Assignment.employee_id.in_(emp_ids),
                        Assignment.project_id  != project_id,
                        Assignment.start_date  <= sprint_end,
                        or_(
                            Assignment.end_date >= sprint_start,
                            Assignment.end_date == None,   # noqa: E711
                        ),
                    )
                )
            )
        ).all()

        # emp_id → liste de AvailabilityPeriod (assignment)
        assign_periods: dict[int, list] = {}
        for row in assign_rows:
            asgn         = row[0]
            project_name = row[1] or f"Projet #{asgn.project_id}"
            end_label    = fmt(asgn.end_date) if asgn.end_date else "en cours"
            assign_periods.setdefault(asgn.employee_id, []).append(
                AvailabilityPeriod(
                    start_date  = fmt(asgn.start_date),
                    end_date    = fmt(asgn.end_date) if asgn.end_date else "",
                    reason      = f"Affecté au projet « {project_name} » du {fmt(asgn.start_date)} au {end_label}",
                    reason_type = "assignment",
                )
            )

    # 4. Construire les deux listes
    available:   list[CandidateEmployee] = []
    unavailable: list[CandidateEmployee] = []

    for emp in emp_rows:
        skills      = [es.skill.name for es in emp.employee_skills if es.skill]
        name        = (emp.user.name if emp.user else None) or f"Employé {emp.id}"
        job_title   = emp.job_title or ""
        seniority   = (emp.seniority.value if emp.seniority else "mid").upper()
        match_type  = "exact" if job_title in job_titles else "close"

        blocking = (
            leave_periods.get(emp.id, []) +
            assign_periods.get(emp.id, [])
        )

        if not blocking:
            available.append(CandidateEmployee(
                employee_id         = emp.id,
                name                = name,
                job_title           = job_title,
                seniority           = seniority,
                skills              = skills,
                availability_status = "Available",
                unavailable_periods = [],
                profile_match       = match_type,
                matched_profile     = job_title,
            ))
        else:
            unavailable.append(CandidateEmployee(
                employee_id         = emp.id,
                name                = name,
                job_title           = job_title,
                seniority           = seniority,
                skills              = skills,
                availability_status = "Unavailable",
                unavailable_periods = blocking,
                profile_match       = match_type,
                matched_profile     = job_title,
            ))

    return available, unavailable


async def filter_candidates(
    norm_result:    dict,
    distrib_result: dict,
    project_id:     int,
) -> CandidateFilteringResult:
    """
    norm_result    : dict issu de ProfileNormalizationResult.model_dump()
    distrib_result : dict issu de StoryDistributionResult.model_dump()
    project_id     : ID du projet en cours (pour exclure ses propres affectations)
    """
    print("[candidate_filtering] ▶ Step 4 — Candidate Filtering (par sprint)")

    mappings     = norm_result.get("profile_mappings", [])
    pm_decisions = norm_result.get("pm_decisions",     {})
    sprints      = distrib_result.get("sprints",       [])

    # Profils marqués "recruit" → pas de recherche interne
    missing_profiles = [
        m.get("required_profile", "")
        for m in mappings
        if isinstance(m, dict)
        and pm_decisions.get(m.get("required_profile", ""), "accept") == "recruit"
    ]

    candidates_by_sprint: dict[str, SprintCandidates] = {}

    for sprint in sprints:
        if not isinstance(sprint, dict):
            continue

        sprint_num  = sprint.get("sprint_number", 0)
        start_str   = sprint.get("start_date", "")
        end_str     = sprint.get("end_date",   "")
        key         = f"sprint_{sprint_num}"

        try:
            sprint_start = date.fromisoformat(start_str)
            sprint_end   = date.fromisoformat(end_str)
        except ValueError:
            print(f"[candidate_filtering] ⚠️  Sprint {sprint_num} — dates invalides ({start_str}/{end_str}), ignoré")
            continue

        print(f"[candidate_filtering]   Sprint {sprint_num} ({start_str} → {end_str})")
        candidates_by_profile:            dict[str, list[CandidateEmployee]] = {}
        unavailable_candidates_by_profile: dict[str, list[CandidateEmployee]] = {}

        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue

            profile  = mapping.get("required_profile", "")
            titles   = mapping.get("matched_job_titles", [])
            decision = pm_decisions.get(profile, "accept")

            if decision == "recruit":
                continue   # profil à recruter en externe → on skip

            if not titles:
                candidates_by_profile[profile] = []
                continue

            available, unavailable = await _get_candidates_with_availability(
                job_titles   = titles,
                sprint_start = sprint_start,
                sprint_end   = sprint_end,
                project_id   = project_id,
            )
            candidates_by_profile[profile]            = available
            unavailable_candidates_by_profile[profile] = unavailable
            print(
                f"[candidate_filtering]     '{profile}' → "
                f"{len(available)} disponible(s), {len(unavailable)} indisponible(s)"
            )

        total = sum(len(v) for v in candidates_by_profile.values())
        candidates_by_sprint[key] = SprintCandidates(
            sprint_number                     = sprint_num,
            start_date                        = start_str,
            end_date                          = end_str,
            candidates_by_profile             = candidates_by_profile,
            unavailable_candidates_by_profile = unavailable_candidates_by_profile,
            total_available                   = total,
        )
        print(f"[candidate_filtering]   → Sprint {sprint_num} : {total} candidat(s) total")

    print(
        f"[candidate_filtering] ✅ terminé — "
        f"{len(candidates_by_sprint)} sprint(s) | "
        f"{len(missing_profiles)} profil(s) à recruter"
    )

    return CandidateFilteringResult(
        candidates_by_sprint = candidates_by_sprint,
        missing_profiles     = missing_profiles,
    )
