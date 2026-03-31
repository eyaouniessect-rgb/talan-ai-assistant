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
    

async def delete_leave(
    user_id: int,
    leave_id: int = None,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """
    Annule une demande de congé existante.

    Modes supportés :
    - leave_id : annule un congé précis
    - start_date seule : annule le congé qui couvre cette date
    - start_date + end_date : annule tous les congés qui chevauchent la période

    Seuls les congés avec statut 'pending' ou 'approved' peuvent être annulés.
    """
    async with AsyncSessionLocal() as db:
        today = date.today()

        # ── 1. Trouve l'employee ───────────────────────
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()
        if not employee:
            return {"error": "Employé introuvable"}

        # ── 2. Trouve le congé / les congés ────────────
        if leave_id:
            result = await db.execute(
                select(Leave).where(
                    and_(
                        Leave.id == leave_id,
                        Leave.employee_id == employee.id,
                    )
                )
            )
            leave = result.scalar_one_or_none()

            if not leave:
                return {
                    "error": "not_found",
                    "message": "Aucun congé trouvé correspondant à ces critères.",
                }

            if leave.status not in ("pending", "approved"):
                return {
                    "error": "invalid_status",
                    "message": f"Impossible d'annuler un congé avec le statut '{leave.status}'.",
                }

            if leave.start_date <= today:
                return {
                    "error": "past_leave_locked",
                    "message": (
                        "Impossible d'annuler un congé déjà commencé ou passé "
                        f"(du {leave.start_date} au {leave.end_date})."
                    ),
                }

            old_status = leave.status
            leave.status = "cancelled"
            recovered_days = leave.days_count or 0
            await db.commit()

            return {
                "success": True,
                "mode": "single",
                "count": 1,
                "leave_id": leave.id,
                "start_date": str(leave.start_date),
                "end_date": str(leave.end_date),
                "days_count": leave.days_count,
                "total_days_recovered": recovered_days,
                "old_status": old_status,
                "new_status": "cancelled",
                "message": (
                    f"Congé du {leave.start_date} au {leave.end_date} "
                    f"({recovered_days} jour(s)) annulé avec succès. "
                    f"Jours récupérés : {recovered_days}."
                ),
            }
        elif start_date:
            target_start = date.fromisoformat(start_date)
            target_end = date.fromisoformat(end_date) if end_date else target_start

            if target_end < target_start:
                return {
                    "error": "invalid_range",
                    "message": "La date de fin doit être après la date de début.",
                }

            # Si une période est fournie, annule TOUS les congés qui chevauchent la période.
            # Cela évite d'annuler arbitrairement le premier congé trouvé.
            result = await db.execute(
                select(Leave).where(
                    and_(
                        Leave.employee_id == employee.id,
                        Leave.status.in_(["pending", "approved"]),
                        Leave.start_date <= target_end,
                        Leave.end_date >= target_start,
                    )
                ).order_by(Leave.start_date.asc(), Leave.id.asc())
            )
            leaves = result.scalars().all()

            if not leaves:
                return {
                    "error": "not_found",
                    "message": (
                        "Aucun congé actif trouvé correspondant à cette date"
                        if not end_date
                        else f"Aucun congé actif trouvé sur la période du {target_start} au {target_end}."
                    ),
                }

            eligible_leaves = [l for l in leaves if l.start_date > today]
            blocked_leaves = [l for l in leaves if l.start_date <= today]

            if not eligible_leaves:
                return {
                    "error": "past_leave_locked",
                    "message": (
                        "Aucun congé annulable sur cette période : "
                        "les congés déjà commencés ou passés ne peuvent pas être annulés."
                    ),
                    "blocked_count": len(blocked_leaves),
                    "blocked_leaves": [
                        {
                            "leave_id": l.id,
                            "start_date": str(l.start_date),
                            "end_date": str(l.end_date),
                            "status": l.status,
                        }
                        for l in blocked_leaves
                    ],
                }

            cancelled = []
            total_days = 0
            for leave in eligible_leaves:
                old_status = leave.status
                leave.status = "cancelled"
                days = leave.days_count or 0
                total_days += days
                cancelled.append({
                    "leave_id": leave.id,
                    "start_date": str(leave.start_date),
                    "end_date": str(leave.end_date),
                    "days_count": days,
                    "old_status": old_status,
                    "new_status": "cancelled",
                })

            await db.commit()

            if len(cancelled) == 1:
                c = cancelled[0]
                return {
                    "success": True,
                    "mode": "single",
                    "count": 1,
                    "leave_id": c["leave_id"],
                    "start_date": c["start_date"],
                    "end_date": c["end_date"],
                    "days_count": c["days_count"],
                    "total_days_recovered": c["days_count"],
                    "old_status": c["old_status"],
                    "new_status": "cancelled",
                    "message": (
                        f"Congé du {c['start_date']} au {c['end_date']} "
                        f"({c['days_count']} jour(s)) annulé avec succès. "
                        f"Jours récupérés : {c['days_count']}."
                    ),
                }

            return {
                "success": True,
                "mode": "range",
                "count": len(cancelled),
                "total_days_recovered": total_days,
                "cancelled_leaves": cancelled,
                "blocked_count": len(blocked_leaves),
                "blocked_leaves": [
                    {
                        "leave_id": l.id,
                        "start_date": str(l.start_date),
                        "end_date": str(l.end_date),
                        "status": l.status,
                    }
                    for l in blocked_leaves
                ],
                "message": (
                    f"{len(cancelled)} congés annulés avec succès "
                    f"sur la période du {target_start} au {target_end}. "
                    f"Jours récupérés : {total_days}."
                ),
            }
        else:
            return {"error": "Veuillez préciser l'identifiant du congé ou la date."}


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