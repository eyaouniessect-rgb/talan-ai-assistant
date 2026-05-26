# agents/pm/agents/staffing/steps/matching/crm_repository.py
# ═══════════════════════════════════════════════════════════════
# Dérive crm.assignments depuis project_management.staffing_assignments.
#
# crm.assignments      = vue macro RH (1 ligne = 1 employé × 1 projet)
# staffing_assignments = vue micro PM (1 ligne = 1 story × 1 profil × 1 employé)
#
# allocation_percent = moyenne sur les sprints de (sum_sp_sprint / capacity_seniority × 100)
#   Ex: Firas (MID, 2.33 SP/sprint) → 2.33/8×100 = 29%
#
# Appelé dans node_jira_sync._sync_sprints, après persist_assignments.
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations
from datetime import date
from collections import defaultdict

from sqlalchemy import select

from app.database.connection import AsyncSessionLocal
from app.database.models.crm.assignment import Assignment
from app.database.models.pm.staffing_assignment import StaffingAssignment

# Même constante que selection.py (JUNIOR=6 / MID=8 / SENIOR=10 SP par sprint)
_CAPACITY_BY_SENIORITY: dict[str, int] = {
    "JUNIOR": 6,
    "MID":    8,
    "SENIOR": 10,
}
_DEFAULT_CAPACITY = 8  # fallback MID


def _compute_allocation_percent(
    rows: list,   # liste de StaffingAssignment rows pour 1 employé
) -> int:
    """
    allocation_percent = moyenne sur les sprints de (sum_sp / capacity × 100).
    Arrondi à l'entier le plus proche, borné [1, 100].
    """
    # Capacité de l'employé (constante par projet, on prend la première valeur)
    seniority = (rows[0].employee_seniority or "MID").upper()
    capacity  = _CAPACITY_BY_SENIORITY.get(seniority, _DEFAULT_CAPACITY)

    # Somme des SP par sprint
    sp_by_sprint: dict[int, float] = defaultdict(float)
    for r in rows:
        sp_by_sprint[r.sprint_number] += (r.allocated_sp or 0.0)

    if not sp_by_sprint:
        return 100

    # Allocation% par sprint, puis moyenne
    sprint_allocs = [
        (sp / capacity) * 100
        for sp in sp_by_sprint.values()
    ]
    avg = sum(sprint_allocs) / len(sprint_allocs)
    return max(1, min(100, round(avg)))


async def upsert_crm_assignments(
    project_id: int,
    sprint_start: date | None,
    sprint_end: date | None,
) -> int:
    """
    Upsert (select-then-insert-or-update) dans crm.assignments pour chaque
    employé réellement affecté au projet (status assigned ou assigned_with_warning).

    allocation_percent calculé depuis les SP réels :
        moyenne sur les sprints de (sum_allocated_sp / capacity_seniority × 100)

    Idempotent : plusieurs appels ne créent pas de doublons.
    Retourne le nombre de lignes créées ou mises à jour.
    """
    async with AsyncSessionLocal() as db:
        # ── 1. Toutes les lignes affectées pour ce projet ─────────
        sa_rows = (await db.execute(
            select(
                StaffingAssignment.employee_id,
                StaffingAssignment.employee_seniority,
                StaffingAssignment.job_title,
                StaffingAssignment.required_profile,
                StaffingAssignment.sprint_number,
                StaffingAssignment.allocated_sp,
            )
            .where(
                StaffingAssignment.project_id == project_id,
                StaffingAssignment.employee_id.isnot(None),
                StaffingAssignment.status.in_(["assigned", "assigned_with_warning"]),
            )
        )).all()

        if not sa_rows:
            return 0

        # ── 2. Grouper par employee_id ────────────────────────────
        by_emp: dict[int, list] = defaultdict(list)
        for r in sa_rows:
            by_emp[r.employee_id].append(r)

        # ── 3. Calcul role + allocation% par employé ──────────────
        employee_data: dict[int, dict] = {}
        for emp_id, rows in by_emp.items():
            employee_data[emp_id] = {
                "role":       rows[0].job_title or rows[0].required_profile or "",
                "allocation": _compute_allocation_percent(rows),
            }

        # ── 4. Assignments CRM existants pour ce projet ───────────
        existing_rows = (await db.execute(
            select(Assignment).where(Assignment.project_id == project_id)
        )).scalars().all()
        existing_by_emp: dict[int, Assignment] = {a.employee_id: a for a in existing_rows}

        # ── 5. Upsert ─────────────────────────────────────────────
        count = 0
        for emp_id, data in employee_data.items():
            if emp_id in existing_by_emp:
                a = existing_by_emp[emp_id]
                if data["role"]:
                    a.role_in_project    = data["role"]
                a.allocation_percent     = data["allocation"]
                if sprint_start and not a.start_date:
                    a.start_date = sprint_start
                if sprint_end:
                    a.end_date = sprint_end
            else:
                db.add(Assignment(
                    project_id         = project_id,
                    employee_id        = emp_id,
                    role_in_project    = data["role"] or None,
                    allocation_percent = data["allocation"],
                    start_date         = sprint_start,
                    end_date           = sprint_end,
                ))
            count += 1

        await db.commit()
    return count
