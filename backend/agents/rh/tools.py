# Outils de l'Agent RH (appelés pendant le cycle ReAct) :
# - create_leave_tool       : INSERT dans hris.leaves via MCP PostgreSQL
# - get_my_leaves_tool      : SELECT depuis hris.leaves via MCP PostgreSQL
# - get_team_availability_tool : calcule les disponibilités depuis hris.employees + leaves
# - get_team_stack_tool     : SELECT depuis hris.employees (champ skills)
# agents/rh/tools.py
# Fonctions métier de l'Agent RH.
# Appelées par RHAgentExecutor pendant le cycle ReAct.
# Accèdent directement à PostgreSQL via SQLAlchemy (sans MCP pour l'instant).

from datetime import date, datetime
from sqlalchemy import select, and_
from app.database.connection import AsyncSessionLocal
from app.database.models.hris import Leave, Employee, Team
from app.database.models.user import User
from agents.rh.schemas import (
    CreateLeaveRequest,
    LeaveResponse,
    TeamAvailabilityResponse,
    TeamMemberAvailability,
    TeamStackResponse,
)


async def create_leave(user_id: int, start_date: str, end_date: str) -> dict:
    """
    Crée une demande de congé pour un employé.
    Vérifie :
    1. Que l'employé existe
    2. Qu'il n'y a pas de chevauchement avec un congé existant (pending ou approved)
    3. Calcule automatiquement les jours ouvrés
    """
    async with AsyncSessionLocal() as db:

        # ── 1. Trouve l'employee ───────────────────────
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return {"error": f"Employé introuvable pour user_id={user_id}"}

        # ── 2. Parse les dates ─────────────────────────
        start = date.fromisoformat(start_date)
        end   = date.fromisoformat(end_date)

        if end < start:
            return {"error": "La date de fin doit être après la date de début."}

        # ── 3. Vérification d'overlap ──────────────────
        # Cherche un congé existant (pending ou approved) qui chevauche
        overlap_result = await db.execute(
            select(Leave).where(
                and_(
                    Leave.employee_id == employee.id,
                    Leave.status.in_(["pending", "approved"]),
                    Leave.start_date <= end,    # congé existant commence avant la fin
                    Leave.end_date >= start,    # congé existant finit après le début
                )
            )
        )
        existing_leave = overlap_result.scalars().first()

        if existing_leave:
            return {
                "error": "overlap",
                "message": (
                    f"Vous avez déjà une demande de congé du "
                    f"{existing_leave.start_date} au {existing_leave.end_date} "
                    f"avec le statut '{existing_leave.status}'. "
                    f"Impossible de créer un congé qui se chevauche."
                ),
                "existing_leave": {
                    "id": existing_leave.id,
                    "start_date": str(existing_leave.start_date),
                    "end_date": str(existing_leave.end_date),
                    "status": existing_leave.status,
                }
            }

        # ── 4. Calcule les jours ouvrés ────────────────
        days = sum(
            1 for i in range((end - start).days + 1)
            if (start.toordinal() + i) % 7 not in (6, 0)
        )

        if days == 0:
            return {"error": "La période sélectionnée ne contient aucun jour ouvré (week-end)."}

        # ── 5. Crée le congé ───────────────────────────
        leave = Leave(
            employee_id=employee.id,
            start_date=start,
            end_date=end,
            days_count=days,
            status="pending",
        )
        db.add(leave)
        await db.commit()
        await db.refresh(leave)

        return {
            "success": True,
            "leave_id": leave.id,
            "start_date": start_date,
            "end_date": end_date,
            "days_count": days,
            "status": "pending",
            "message": f"Congé créé avec succès ({days} jours ouvrés). Statut : en attente d'approbation.",
        }


async def get_my_leaves(user_id: int) -> dict:
    """
    Retourne tous les congés d'un employé.
    """
    async with AsyncSessionLocal() as db:
        # Trouve l'employee
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return {"error": f"Employé introuvable pour user_id={user_id}"}

        # Récupère les congés
        result = await db.execute(
            select(Leave).where(Leave.employee_id == employee.id)
            .order_by(Leave.created_at.desc())
        )
        leaves = result.scalars().all()

        if not leaves:
            return {
                "success": True,
                "leaves": [],
                "message": "Vous n'avez aucun congé enregistré.",
            }

        leaves_list = [
            {
                "id": l.id,
                "start_date": str(l.start_date),
                "end_date": str(l.end_date),
                "days_count": l.days_count,
                "status": l.status,
            }
            for l in leaves
        ]

        return {
            "success": True,
            "total": len(leaves_list),
            "leaves": leaves_list,
        }


async def get_team_availability(user_id: int) -> dict:
    """
    Retourne la disponibilité des membres de l'équipe de l'utilisateur.
    """
    async with AsyncSessionLocal() as db:
        # Trouve l'équipe de l'employé
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return {"error": "Employé introuvable"}

        # Trouve tous les membres de la même équipe
        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(Employee.team_id == employee.team_id)
        )
        members = result.all()

        today = date.today()

        # Vérifie si chaque membre a un congé en cours
        availability = []
        for emp, user in members:
            result = await db.execute(
                select(Leave).where(
                    and_(
                        Leave.employee_id == emp.id,
                        Leave.start_date <= today,
                        Leave.end_date >= today,
                        Leave.status == "approved",
                    )
                )
            )
            active_leave = result.scalar_one_or_none()

            availability.append({
                "name": user.name,
                "available": active_leave is None,
                "on_leave": active_leave is not None,
            })

        return {
            "success": True,
            "team_id": employee.team_id,
            "members": availability,
        }


async def get_team_stack(user_id: int) -> dict:
    """
    Retourne les compétences techniques des membres de l'équipe.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return {"error": "Employé introuvable"}

        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(Employee.team_id == employee.team_id)
        )
        members = result.all()

        stack = [
            {
                "name": user.name,
                "skills": emp.skills or "Non renseigné",
            }
            for emp, user in members
        ]

        return {
            "success": True,
            "team_stack": stack,
        }