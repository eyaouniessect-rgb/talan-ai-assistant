# api/events/events.py
# Schéma : hris
#
# Routes des événements et historiques de l'utilisateur connecté.
# GET /events/               → événements Google Calendar de l'utilisateur
# GET /events/all            → tous les événements (PM et RH uniquement)
# GET /events/history        → historique des actions calendar
# GET /events/leaves/history → historique des actions congé

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.hris import CalendarEvent, CalendarEventLog, Employee, LeaveLog

router = APIRouter(prefix="/events", tags=["Events"])


def _employee_subquery(user_id: int):
    """Retourne le scalar subquery de l'employee_id pour un user_id donné."""
    return select(Employee.id).where(Employee.user_id == user_id).scalar_subquery()


@router.get("/")
async def get_my_events(
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Événements Google Calendar de l'utilisateur connecté."""
    emp_id = _employee_subquery(current_user["user_id"])
    result = await db.execute(
        select(CalendarEvent).where(CalendarEvent.employee_id == emp_id)
        .order_by(desc(CalendarEvent.start_datetime)).offset(offset).limit(limit)
    )
    return [_serialize_event(e) for e in result.scalars().all()]


@router.get("/all")
async def get_all_events(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Tous les événements — PM et RH uniquement."""
    if current_user["role"] not in ("pm", "rh"):
        raise HTTPException(status_code=403, detail="Accès réservé aux PM et RH")
    result = await db.execute(
        select(CalendarEvent).order_by(desc(CalendarEvent.start_datetime)).offset(offset).limit(limit)
    )
    return [_serialize_event(e) for e in result.scalars().all()]


@router.get("/history")
async def get_my_calendar_history(
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Historique des actions calendar de l'utilisateur connecté."""
    emp_id = _employee_subquery(current_user["user_id"])
    result = await db.execute(
        select(CalendarEventLog).where(CalendarEventLog.employee_id == emp_id)
        .order_by(desc(CalendarEventLog.created_at)).offset(offset).limit(limit)
    )
    return [_serialize_calendar_log(log) for log in result.scalars().all()]


@router.get("/leaves/history")
async def get_my_leave_history(
    limit: int = Query(default=30, le=100),
    offset: int = Query(default=0),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Historique des actions congé de l'utilisateur connecté."""
    emp_id = _employee_subquery(current_user["user_id"])
    result = await db.execute(
        select(LeaveLog).where(LeaveLog.employee_id == emp_id)
        .order_by(desc(LeaveLog.created_at)).offset(offset).limit(limit)
    )
    return [_serialize_leave_log(log) for log in result.scalars().all()]


def _serialize_event(e: CalendarEvent) -> dict:
    return {
        "id": e.id, "employee_id": e.employee_id, "google_event_id": e.google_event_id,
        "title": e.title,
        "start": e.start_datetime.isoformat() if e.start_datetime else None,
        "end": e.end_datetime.isoformat() if e.end_datetime else None,
        "location": e.location,
        "attendees": e.attendees.split(", ") if e.attendees else [],
        "meet_link": e.meet_link, "html_link": e.html_link,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _serialize_calendar_log(log: CalendarEventLog) -> dict:
    icons = {"created": "➕", "updated": "✏️", "updated_schedule": "📅", "deleted": "🗑️"}
    return {
        "id": log.id, "action": log.action, "icon": icons.get(log.action, "📋"),
        "event_title": log.event_title, "description": log.description,
        "google_event_id": log.google_event_id,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


def _serialize_leave_log(log: LeaveLog) -> dict:
    icons = {"requested": "📝", "approved": "✅", "rejected": "❌", "cancelled": "🚫"}
    return {
        "id": log.id, "action": log.action, "icon": icons.get(log.action, "📋"),
        "description": log.description, "leave_id": log.leave_id,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
