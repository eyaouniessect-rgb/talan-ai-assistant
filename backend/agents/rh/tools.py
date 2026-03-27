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

        # ── 3. Calcule les jours ouvrés ────────────────
        days = sum(
            1 for i in range((end - start).days + 1)
            if (start.toordinal() + i) % 7 not in (6, 0)
        )

        if days == 0:
            return {"error": "La période ne contient aucun jour ouvré."}

        # ── 4. Vérifie le solde AVANT l'overlap ────────
        balance_check = await check_leave_balance(
            user_id=user_id,
            requested_days=days
        )

        if not balance_check.get("can_create", True):
            return {
                "error": "solde_insuffisant",
                "message": balance_check["message"],
                "solde_effectif": balance_check["solde_effectif"],
                "jours_demandes": days,
            }

        # ── 5. Vérifie l'overlap ───────────────────────
        overlap_result = await db.execute(
            select(Leave).where(
                and_(
                    Leave.employee_id == employee.id,
                    Leave.status.in_(["pending", "approved"]),
                    Leave.start_date <= end,
                    Leave.end_date >= start,
                )
            )
        )
        existing_leave = overlap_result.scalars().first()

        if existing_leave:
            return {
                "error": "overlap",
                "message": (
                    f"Chevauchement avec un congé existant du "
                    f"{existing_leave.start_date} au {existing_leave.end_date} "
                    f"(statut: {existing_leave.status})."
                ),
            }

        # ── 6. Crée le congé ───────────────────────────
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
            "solde_restant": balance_check["solde_effectif"] - days,
        }
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


async def get_my_leaves(user_id: int, status_filter: str = None) -> dict:
    """
    Retourne les congés d'un employé.
    status_filter : "pending" | "approved" | "rejected" | None (tous)
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            return {"error": "Employé introuvable"}

        # ← filtre par status si spécifié
        query = select(Leave).where(Leave.employee_id == employee.id)
        if status_filter:
            query = query.where(Leave.status == status_filter)
        query = query.order_by(Leave.created_at.desc())

        result = await db.execute(query)
        leaves = result.scalars().all()

        if not leaves:
            msg = f"Aucun congé{' en attente' if status_filter == 'pending' else ''} trouvé."
            return {"success": True, "leaves": [], "message": msg}

        return {
            "success": True,
            "total": len(leaves),
            "leaves": [
                {
                    "id": l.id,
                    "start_date": str(l.start_date),
                    "end_date": str(l.end_date),
                    "days_count": l.days_count,
                    "status": l.status,
                }
                for l in leaves
            ],
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

        # Vérifie si chaque membre a un congé en cours (exclut l'utilisateur demandeur)
        availability = []
        for emp, user in members:
            if emp.user_id == user_id:
                continue  # Ne pas inclure soi-même dans la liste d'équipe
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
            if emp.user_id != user_id  # Exclut l'utilisateur demandeur
        ]

        return {
            "success": True,
            "team_stack": stack,
        }
    

async def check_leave_balance(user_id: int, requested_days: int = 0) -> dict:
    """
    Vérifie le solde de congés disponible.
    
    Calcul :
    solde_effectif = leave_balance - jours_pending
    
    Si requested_days > 0 : vérifie si la demande est possible.
    """
    async with AsyncSessionLocal() as db:

        # ── 1. Trouve l'employee ───────────────────────
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()

        if not employee:
            return {"error": "Employé introuvable"}

        # ── 2. Calcule les jours déjà en pending ───────
        result = await db.execute(
            select(Leave).where(
                and_(
                    Leave.employee_id == employee.id,
                    Leave.status == "pending",
                )
            )
        )
        pending_leaves = result.scalars().all()

        jours_pending = sum(l.days_count or 0 for l in pending_leaves)

        # ── 3. Solde effectif ──────────────────────────
        solde_total    = employee.leave_balance or 26
        solde_effectif = solde_total - jours_pending

        response = {
            "success": True,
            "solde_total": solde_total,
            "jours_pending": jours_pending,
            "solde_effectif": solde_effectif,
            "pending_details": [
                {
                    "id": l.id,
                    "start_date": str(l.start_date),
                    "end_date": str(l.end_date),
                    "days_count": l.days_count,
                }
                for l in pending_leaves
            ]
        }

        # ── 4. Vérifie si la demande est possible ──────
        if requested_days > 0:
            if requested_days > solde_effectif:
                response["can_create"] = False
                response["message"] = (
                    f"Solde insuffisant. Vous avez {solde_effectif} jours disponibles "
                    f"({solde_total} jours - {jours_pending} jours en attente). "
                    f"Votre demande de {requested_days} jours dépasse ce solde."
                )
            else:
                response["can_create"] = True
                response["message"] = (
                    f"Solde suffisant. Vous avez {solde_effectif} jours disponibles. "
                    f"Après cette demande il vous restera "
                    f"{solde_effectif - requested_days} jours."
                )

        return response    