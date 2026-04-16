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
from sqlalchemy import select
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
from agents.pm.db import get_employee_id_by_user

router = APIRouter(prefix="/dashboard/pm", tags=["Dashboard PM"])

_TICKETS_MOCK = 23


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

    # ── 7. Colonnes projets ───────────────────────────────────
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
            "tickets_in_progress":    _TICKETS_MOCK,
            "availability": {
                "percentage":      availability_pct,
                "available_count": available_count,
                "total_count":     total_team,
            },
        },
        "team_overview":    team_overview,
        "projects_columns": {
            "todo":        todo_col,
            "in_progress": in_progress_col,
            "done":        done_col,
        },
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
