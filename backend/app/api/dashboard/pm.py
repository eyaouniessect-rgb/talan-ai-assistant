# app/api/dashboard/pm.py
# ═══════════════════════════════════════════════════════════════
# Dashboard PM — statistiques temps réel
#
# team_members_count   : membres de la même équipe que le PM (team_id)
# assigned_members     : membres assignés aux projets du PM (Assignment)
#
# Disponibilité (basée sur team_members) :
#   Congé approuvé couvrant aujourd'hui → indisponible (dot rouge)
#   Sinon → disponible (dot vert)
#
# Colonnes projets (champ progress) :
#   progress == 0      → "À faire"
#   0 < progress < 100 → "En cours"
#   progress == 100    → "Terminé"
# ═══════════════════════════════════════════════════════════════

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.crm.project         import Project
from app.database.models.crm.assignment      import Assignment
from app.database.models.hris.employee       import Employee
from app.database.models.hris.employee_skill import EmployeeSkill
from app.database.models.hris.leave          import Leave
from app.database.models.hris.calendar_event import CalendarEvent
from app.database.models.hris.enums          import LeaveStatusEnum
from app.database.models.hris.team           import Team
from app.database.models.hris.department     import Department
from app.database.models.pm.sprint           import Sprint
from app.database.models.pm.staffing_assignment import StaffingAssignment
from app.database.models.pm.user_story        import UserStory
from app.services import pm_delivery_metrics as pdm
from agents.pm.db import get_employee_id_by_user

router = APIRouter(prefix="/dashboard/pm", tags=["Dashboard PM"])


async def _require_pm(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "pm":
        raise HTTPException(403, "Accès réservé aux Project Managers.")
    return current_user


@router.get("")
async def get_pm_dashboard(
    current_user: dict         = Depends(_require_pm),
    db:           AsyncSession = Depends(get_db),
):
    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(404, "Profil employé introuvable.")

    today = date.today()

    # ── 1. Récupérer le profil du PM (pour obtenir son team_id) ─
    pm_employee = (await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.team))
    )).scalar_one_or_none()
    if not pm_employee:
        raise HTTPException(404, "Employé introuvable.")

    pm_team_id = pm_employee.team_id

    # ── 2. Projets gérés par ce PM ────────────────────────────
    projects_rows = (await db.execute(
        select(Project)
        .where(Project.project_manager_id == employee_id)
        .options(selectinload(Project.client))
        .order_by(Project.created_at.desc())
    )).scalars().all()

    project_ids     = [p.id for p in projects_rows]
    proj_name_by_id = {p.id: p.name for p in projects_rows}

    # ── 3. Membres de l'équipe du PM (même team_id) ──────────
    team_rows = (await db.execute(
        select(Employee)
        .where(
            Employee.team_id   == pm_team_id,
            Employee.id        != employee_id,   # exclure le PM lui-même
            Employee.leave_date.is_(None),        # exclure les partis
        )
        .options(
            selectinload(Employee.user),
            selectinload(Employee.team),
            selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
        )
    )).scalars().all()

    team_member_ids = {e.id for e in team_rows}
    total_team      = len(team_rows)

    # ── 4. Membres assignés aux projets (distinct) ────────────
    assigned_count = 0
    assigned_ids: set[int] = set()
    if project_ids:
        asgn_emp_ids = (await db.execute(
            select(Assignment.employee_id)
            .where(Assignment.project_id.in_(project_ids))
            .distinct()
        )).scalars().all()
        assigned_ids  = set(asgn_emp_ids)
        assigned_count = len(assigned_ids)

    # ── 5. Disponibilité du jour (sur les membres de l'équipe) ─
    on_leave_today: set[int] = set()
    if team_member_ids:
        leave_rows = (await db.execute(
            select(Leave.employee_id).where(
                Leave.employee_id.in_(team_member_ids),
                Leave.status     == LeaveStatusEnum.APPROVED,
                Leave.start_date <= today,
                Leave.end_date   >= today,
            )
        )).scalars().all()
        on_leave_today = set(leave_rows)

    available_count  = total_team - len(on_leave_today)
    availability_pct = round(available_count / total_team * 100) if total_team > 0 else 100

    # ── 6. Vue d'ensemble équipe (membres de l'équipe) ────────
    # Projets de chaque membre via Assignment
    member_projects: dict[int, list[str]] = {}
    if project_ids and team_member_ids:
        team_asgn = (await db.execute(
            select(Assignment)
            .where(
                Assignment.project_id.in_(project_ids),
                Assignment.employee_id.in_(team_member_ids),
            )
        )).scalars().all()
        for a in team_asgn:
            pname = proj_name_by_id.get(a.project_id, "")
            member_projects.setdefault(a.employee_id, [])
            if pname and pname not in member_projects[a.employee_id]:
                member_projects[a.employee_id].append(pname)

    team_overview = []
    for emp in team_rows:
        name     = emp.user.name if emp.user else f"Employé {emp.id}"
        initials = "".join(w[0].upper() for w in name.split()[:2])
        skills   = [
            {"name": es.skill.name, "level": es.level.value if es.level else "beginner"}
            for es in (emp.employee_skills or [])
            if es.skill
        ]
        team_overview.append({
            "id":               emp.id,
            "name":             name,
            "initials":         initials,
            "job_title":        emp.job_title or "—",
            "team_name":        emp.team.name if emp.team else "—",
            "is_available":     emp.id not in on_leave_today,
            "skills":           skills,
            "current_projects": member_projects.get(emp.id, []),
        })

    # ── 7. Détail des membres assignés (pour le tooltip de la carte KPI) ────
    # Pour chaque employé assigné à un projet du PM, on expose :
    #   name, job_title, team, department, project_name, sprint courant actif.
    # Source : StaffingAssignment (sprint_number + employee_name dénormalisé)
    #          + Employee → Team → Department pour équipe/département.
    assigned_members_detail: list[dict] = []
    # Compteurs de tickets (= staffing_assignments) du sprint actif, par statut.
    # Unité = assignment (une story split front/back = 2 tickets, c'est voulu :
    # chacun a son propre progress_status).
    tickets_counts   = {"to_do": 0, "in_progress": 0, "done": 0}
    # Répartition par projet+sprint actif (pour la section "par projet")
    tickets_by_proj: dict[tuple[int, int], dict] = {}
    # Tâches critiques (assignments dont la story.is_critical = True)
    critical_total          = 0
    critical_by_proj: dict[tuple[int, int], int] = {}
    if project_ids:
        # Sprints actifs par projet
        active_sprint_by_proj: dict[int, int] = {}
        active_sprint_rows = (await db.execute(
            select(Sprint.project_id, Sprint.sprint_number)
            .where(
                Sprint.project_id.in_(project_ids),
                Sprint.status == "active",
            )
        )).all()
        for row in active_sprint_rows:
            active_sprint_by_proj[row.project_id] = row.sprint_number

        if active_sprint_by_proj:
            # StaffingAssignments sur les sprints actifs
            sa_active = (await db.execute(
                select(StaffingAssignment)
                .where(
                    tuple_(StaffingAssignment.project_id, StaffingAssignment.sprint_number)
                    .in_(list(active_sprint_by_proj.items())),
                    StaffingAssignment.employee_id.isnot(None),
                    StaffingAssignment.status.in_(["assigned", "assigned_with_warning"]),
                )
            )).scalars().all()

            # Charger les UserStory pour identifier celles flagguées is_critical
            story_ids = {a.story_id for a in sa_active if a.story_id}
            critical_story_ids: set[int] = set()
            if story_ids:
                crit_rows = (await db.execute(
                    select(UserStory.id).where(
                        UserStory.id.in_(story_ids),
                        UserStory.is_critical.is_(True),
                    )
                )).scalars().all()
                critical_story_ids = set(crit_rows)

            # Compteurs : global, par projet+sprint, et tâches critiques
            for a in sa_active:
                key = a.progress_status or "to_do"
                if key in tickets_counts:
                    tickets_counts[key] += 1

                proj_key = (a.project_id, a.sprint_number)
                slot = tickets_by_proj.setdefault(proj_key, {
                    "project_id":    a.project_id,
                    "project_name":  proj_name_by_id.get(a.project_id, "—"),
                    "sprint_number": a.sprint_number,
                    "to_do":         0,
                    "in_progress":   0,
                    "done":          0,
                    "critical":      0,
                })
                if key in ("to_do", "in_progress", "done"):
                    slot[key] += 1

                if a.story_id and a.story_id in critical_story_ids:
                    slot["critical"]            += 1
                    critical_total              += 1
                    critical_by_proj[proj_key]   = critical_by_proj.get(proj_key, 0) + 1

            # Team + département par employee_id
            emp_ids_active = list({a.employee_id for a in sa_active})
            emp_td: dict[int, dict] = {}
            if emp_ids_active:
                emp_rows2 = (await db.execute(
                    select(Employee, Team, Department)
                    .outerjoin(Team, Employee.team_id == Team.id)
                    .outerjoin(Department, Team.department_id == Department.id)
                    .where(Employee.id.in_(emp_ids_active))
                )).all()
                for emp, team, dept in emp_rows2:
                    emp_td[emp.id] = {
                        "team":       team.name       if team else None,
                        "department": dept.name.value if dept and dept.name else None,
                    }

            # Déduplique par (project_id, employee_id)
            seen_asgn: set[tuple] = set()
            for a in sa_active:
                key = (a.project_id, a.employee_id)
                if key in seen_asgn:
                    continue
                seen_asgn.add(key)
                td = emp_td.get(a.employee_id, {})
                assigned_members_detail.append({
                    "name":           a.employee_name or "—",
                    "job_title":      a.job_title or "—",
                    "team":           td.get("team"),
                    "department":     td.get("department"),
                    "project_name":   proj_name_by_id.get(a.project_id, "—"),
                    "sprint_number":  a.sprint_number,
                })

    # ── 8. Colonnes projets ───────────────────────────────────
    todo_col, in_progress_col, done_col = [], [], []
    for p in projects_rows:
        prog  = p.progress or 0.0
        entry = {
            "id":          p.id,
            "name":        p.name,
            "client_name": p.client.name if p.client else "—",
            "progress":    prog,
            "status":      p.status,
        }
        if prog <= 0:
            todo_col.append(entry)
        elif prog >= 100:
            done_col.append(entry)
        else:
            in_progress_col.append(entry)

    return {
        "stats": {
            "projects_count":         len(projects_rows),
            "team_members_count":     total_team,
            "team_name":              pm_employee.team.name if pm_employee.team else "—",
            "assigned_members_count": assigned_count,
            "tickets": {
                "to_do":       tickets_counts["to_do"],
                "in_progress": tickets_counts["in_progress"],
                "done":        tickets_counts["done"],
                "total":       sum(tickets_counts.values()),
                # Répartition par projet+sprint actif (triée par volume desc)
                "by_project":  sorted(
                    list(tickets_by_proj.values()),
                    key=lambda x: -(x["to_do"] + x["in_progress"] + x["done"]),
                ),
            },
            "critical_tickets": {
                "total":      critical_total,
                "by_project": sorted(
                    [
                        {
                            "project_id":    pid,
                            "project_name":  proj_name_by_id.get(pid, "—"),
                            "sprint_number": snum,
                            "count":         count,
                        }
                        for (pid, snum), count in critical_by_proj.items()
                    ],
                    key=lambda x: -x["count"],
                ),
            },
            "availability": {
                "percentage":      availability_pct,
                "available_count": available_count,
                "total_count":     total_team,
            },
        },
        "team_overview":             team_overview,
        "assigned_members_detail":   assigned_members_detail,
        "projects_columns": {
            "todo":        todo_col,
            "in_progress": in_progress_col,
            "done":        done_col,
        },
    }


# ──────────────────────────────────────────────────────────────
# GET /dashboard/pm/delivery — Indicateurs de livraison (sprints + retards)
#
# Cet endpoint alimente la section "Pilotage des livraisons" du dashboard
# PM (composant PMDashboard côté React). Il NE retourne PAS le détail
# sprint par sprint — pour ça, on a l'endpoint dédié
# GET /pipeline/{project_id}/monitoring/delivery, consommé par l'onglet
# Monitoring de chaque projet.
#
# Toute la logique de calcul (offsets, retard cumulé, insight texte,
# distribution, vélocité) vit dans app/services/pm_delivery_metrics.py.
# ──────────────────────────────────────────────────────────────

@router.get("/delivery")
async def get_pm_delivery(
    current_user: dict         = Depends(_require_pm),
    db:           AsyncSession = Depends(get_db),
):
    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(404, "Profil employé introuvable.")

    today = date.today()

    # 1) Projets non archivés gérés par ce PM
    projects = (await db.execute(
        select(Project)
        .where(
            Project.project_manager_id == employee_id,
            Project.archived.is_(False),
        )
        .options(selectinload(Project.client))
        .order_by(Project.created_at.desc())
    )).scalars().all()

    project_ids = [p.id for p in projects]

    # 2) Tous les sprints des projets — un seul SELECT
    sprint_rows: list[Sprint] = []
    if project_ids:
        sprint_rows = (await db.execute(
            select(Sprint)
            .where(Sprint.project_id.in_(project_ids))
            .order_by(Sprint.project_id, Sprint.sprint_number)
        )).scalars().all()

    sprints_by_project: dict[int, list[Sprint]] = {pid: [] for pid in project_ids}
    for s in sprint_rows:
        sprints_by_project.setdefault(s.project_id, []).append(s)

    # 3) Résumé par projet (utilise pdm.build_project_summary qui produit
    #    également l'insight texte affiché sous chaque carte)
    project_summaries = [
        pdm.build_project_summary(p, sprints_by_project.get(p.id, []), today)
        for p in projects
    ]

    # 4) Personnes affectées au sprint courant de chaque projet
    #    → StaffingAssignment (assigned/assigned_with_warning, employee_id non null)
    #    → join Employee → Team → Department pour équipe et département
    #
    #    Utilisé uniquement dans la carte "En développement" du dashboard PM
    #    pour afficher "3 personnes · Équipe Alpha · Ingénierie".
    asgn_by_proj_sprint: dict[tuple, dict] = {}

    if project_ids:
        sa_rows = (await db.execute(
            select(StaffingAssignment)
            .where(
                StaffingAssignment.project_id.in_(project_ids),
                StaffingAssignment.employee_id.isnot(None),
                StaffingAssignment.status.in_(["assigned", "assigned_with_warning"]),
            )
        )).scalars().all()

        # Récupère team + département pour chaque employé distinct
        emp_ids = list({a.employee_id for a in sa_rows})
        emp_info: dict[int, dict] = {}
        if emp_ids:
            emp_rows = (await db.execute(
                select(Employee, Team, Department)
                .outerjoin(Team, Employee.team_id == Team.id)
                .outerjoin(Department, Team.department_id == Department.id)
                .where(Employee.id.in_(emp_ids))
            )).all()
            for emp, team, dept in emp_rows:
                emp_info[emp.id] = {
                    "team":       team.name if team else None,
                    "department": dept.name.value if dept and dept.name else None,
                }

        # Groupe par (project_id, sprint_number), déduplique par employee_id
        for a in sa_rows:
            key = (a.project_id, a.sprint_number)
            if key not in asgn_by_proj_sprint:
                asgn_by_proj_sprint[key] = {}
            if a.employee_id not in asgn_by_proj_sprint[key]:
                td = emp_info.get(a.employee_id, {})
                asgn_by_proj_sprint[key][a.employee_id] = {
                    "name":       a.employee_name,
                    "job_title":  a.job_title,
                    "team":       td.get("team"),
                    "department": td.get("department"),
                }

    # Fusionne les assignees dans chaque résumé de projet
    for summary in project_summaries:
        snum = summary["current_sprint_number"]
        if snum is not None:
            emp_dict = asgn_by_proj_sprint.get((summary["id"], snum), {})
            employees = list(emp_dict.values())
        else:
            employees = []

        summary["current_sprint_assignee_count"] = len(employees)
        summary["current_sprint_assignees"] = employees  # liste individuelle pour le tooltip

    # 5) Tous les résumés de projets — le frontend filtre côté client
    #    selon le statut sélectionné dans le dropdown (défaut : in_development)
    all_projects = project_summaries

    # 5) Ranking "Projets à risque" : retard cumulé strictement positif,
    #    statut in_development uniquement (déjà livrés ou en pré-prod = hors scope)
    at_risk_projects = sorted(
        [
            s for s in project_summaries
            if s["cumulative_delay_days"] > 0 and s["status"] == "in_development"
        ],
        key=lambda x: x["cumulative_delay_days"],
        reverse=True,
    )

    # 6) Agrégats portefeuille
    in_development_count = sum(1 for p in projects if p.status == "in_development")
    delivered_count      = sum(1 for p in projects if p.status == "delivered")

    return {
        "kpis": {
            "total_projects":       len(projects),
            "in_development_count": in_development_count,
            "delivered_count":      delivered_count,
            "at_risk_count":        len(at_risk_projects),
            "avg_sprint_delay_days": pdm.avg_sprint_delay_days(sprint_rows),
            "velocity_30d":         pdm.count_velocity_30d(sprint_rows, today),
        },
        "all_projects":              all_projects,
        "at_risk_projects":          at_risk_projects,
        "status_distribution":       pdm.status_distribution(projects),
        "sprint_delay_distribution": pdm.sprint_delay_distribution(sprint_rows),
        "active_overdue_sprint_count": sum(
            1 for s in sprint_rows
            if s.status == "active" and today > s.end_date
        ),
        "velocity_weekly":           pdm.velocity_weekly(
            sprint_rows, weeks=8, today=today,
            project_names={p.id: p.name for p in projects},
        ),
    }


# ──────────────────────────────────────────────────────────────
# GET /dashboard/pm/events — Événements aujourd'hui et demain
# ──────────────────────────────────────────────────────────────

@router.get("/events")
async def get_pm_events(
    current_user: dict         = Depends(_require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne les événements du calendrier du PM pour aujourd'hui et demain,
    groupés par jour, triés par heure de début.
    """
    from datetime import timedelta, datetime as dt

    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(404, "Profil employé introuvable.")

    today    = date.today()
    tomorrow = today + timedelta(days=1)

    # Fenêtre : 00:00:00 aujourd'hui → 23:59:59 demain
    start_window = dt.combine(today,    dt.min.time())
    end_window   = dt.combine(tomorrow, dt.max.time())

    events_rows = (await db.execute(
        select(CalendarEvent)
        .where(
            CalendarEvent.employee_id    == employee_id,
            CalendarEvent.start_datetime >= start_window,
            CalendarEvent.start_datetime <= end_window,
        )
        .order_by(CalendarEvent.start_datetime)
    )).scalars().all()

    def _fmt_event(ev: CalendarEvent) -> dict:
        start = ev.start_datetime
        end   = ev.end_datetime
        # Durée en minutes
        duration_min = int((end - start).total_seconds() / 60) if end and start else None
        return {
            "id":             ev.id,
            "title":          ev.title,
            "date":           start.date().isoformat(),
            "start_time":     start.strftime("%H:%M"),
            "end_time":       end.strftime("%H:%M") if end else None,
            "duration_min":   duration_min,
            "location":       ev.location,
            "attendees":      [a.strip() for a in (ev.attendees or "").split(",") if a.strip()],
            "meet_link":      ev.meet_link,
            "html_link":      ev.html_link,
            "google_event_id": ev.google_event_id,
        }

    today_events    = [_fmt_event(e) for e in events_rows if e.start_datetime.date() == today]
    tomorrow_events = [_fmt_event(e) for e in events_rows if e.start_datetime.date() == tomorrow]

    return {
        "today": {
            "label":  "Aujourd'hui",
            "date":   today.isoformat(),
            "events": today_events,
        },
        "tomorrow": {
            "label":  "Demain",
            "date":   tomorrow.isoformat(),
            "events": tomorrow_events,
        },
    }
