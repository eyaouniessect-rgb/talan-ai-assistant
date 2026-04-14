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
from sqlalchemy import select, and_, or_
from sqlalchemy.orm import selectinload
from app.database.connection import AsyncSessionLocal
from app.database.models.hris import Leave, Employee, Team, Department, LeaveLog, SeniorityEnum, EmployeeSkill, Skill
from app.database.models.public.user import User
from agents.rh.schemas import (
    CreateLeaveRequest,
    LeaveResponse,
    TeamAvailabilityResponse,
    TeamMemberAvailability,
    TeamStackResponse,
)



async def create_leave(user_id: int, start_date: str, end_date: str) -> dict:
    """
    Crée une demande de congé. Vérifie le solde, les chevauchements et les jours ouvrés.
    Retourne manager_email + employee_name pour la notification automatique.
    """
    async with AsyncSessionLocal() as db:

        # ── 1. Trouve l'employee + son user ───────────────────────
        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(Employee.user_id == user_id)
        )
        row = result.first()
        if not row:
            return {"error": f"Employé introuvable pour user_id={user_id}"}
        employee, emp_user = row

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

        # ── 4. Vérifie le solde ────────────────────────
        balance_check = await check_leave_balance(user_id=user_id, requested_days=days)
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
        existing = overlap_result.scalars().first()
        if existing:
            return {
                "error": "overlap",
                "message": (
                    f"Chevauchement avec un congé existant du "
                    f"{existing.start_date} au {existing.end_date} "
                    f"(statut: {existing.status})."
                ),
            }

        # ── 6. Sauvegarde les valeurs avant commit (expire après commit) ──
        employee_id_val = employee.id
        manager_id_val  = employee.manager_id
        employee_name   = emp_user.name

        # ── 7. Crée le congé ───────────────────────────
        leave = Leave(
            employee_id=employee_id_val,
            start_date=start,
            end_date=end,
            days_count=days,
            status="pending",
        )
        db.add(leave)
        await db.commit()
        await db.refresh(leave)

        # ── 8. Récupère le manager pour la notification ─
        manager_email = None
        manager_name  = None
        if manager_id_val:
            mgr_result = await db.execute(
                select(Employee, User)
                .join(User, Employee.user_id == User.id)
                .where(Employee.id == manager_id_val)
            )
            mgr_row = mgr_result.first()
            if mgr_row:
                manager_email = mgr_row[1].email
                manager_name  = mgr_row[1].name

        return {
            "success": True,
            "leave_id": leave.id,
            "start_date": start_date,
            "end_date": end_date,
            "days_count": days,
            "status": "pending",
            "solde_restant": balance_check["solde_effectif"] - days,
            "employee_name": employee_name,
            "manager_email": manager_email,
            "manager_name": manager_name,
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
                    "start_date": str(l.start_date),
                    "end_date": str(l.end_date),
                    "days_count": l.days_count,
                    "status": l.status,
                }
                for l in leaves
            ],
        }


async def get_team_availability(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Retourne la disponibilité des membres de l'équipe de l'utilisateur.
    start_date / end_date : période à vérifier (YYYY-MM-DD). Par défaut : aujourd'hui.
    """
    from datetime import date as date_type
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

        # Période à vérifier
        try:
            check_start = date_type.fromisoformat(start_date) if start_date else date.today()
            check_end   = date_type.fromisoformat(end_date)   if end_date   else date.today()
        except ValueError:
            check_start = check_end = date.today()

        availability = []
        for emp, user in members:
            if emp.user_id == user_id:
                continue
            if emp.seniority == SeniorityEnum.PRINCIPAL:
                continue
            # Congé approuvé qui chevauche la période demandée
            result = await db.execute(
                select(Leave).where(
                    and_(
                        Leave.employee_id == emp.id,
                        Leave.start_date <= check_end,
                        Leave.end_date   >= check_start,
                        Leave.status == "approved",
                    )
                )
            )
            active_leave = result.scalar_one_or_none()

            availability.append({
                "name":           user.name,
                "email":          user.email,
                "available":      active_leave is None,
                "on_leave":       active_leave is not None,
                "leave_start_date": str(active_leave.start_date) if active_leave else None,
                "leave_end_date": str(active_leave.end_date)     if active_leave else None,
            })

        return {
            "success":    True,
            "team_id":    employee.team_id,
            "period":     {"start": str(check_start), "end": str(check_end)},
            "members":    availability,
        }


async def get_team_availability_by_name(
    team_name: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Retourne la disponibilité des membres d'une équipe par son nom (ou département).
    start_date / end_date : période à vérifier (YYYY-MM-DD). Par défaut : aujourd'hui.
    """
    from datetime import date as date_type
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Team))
        all_teams = result.scalars().all()

        matched_team = None
        search = team_name.lower().strip()
        for t in all_teams:
            if search in t.name.lower():
                matched_team = t
                break

        if not matched_team:
            return {"error": f"Équipe '{team_name}' introuvable", "available_teams": [t.name for t in all_teams]}

        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(Employee.team_id == matched_team.id)
        )
        members = result.all()

        # Période à vérifier
        try:
            check_start = date_type.fromisoformat(start_date) if start_date else date.today()
            check_end   = date_type.fromisoformat(end_date)   if end_date   else date.today()
        except ValueError:
            check_start = check_end = date.today()

        availability = []
        for emp, user in members:
            if emp.seniority == SeniorityEnum.PRINCIPAL:
                continue
            result = await db.execute(
                select(Leave).where(
                    and_(
                        Leave.employee_id == emp.id,
                        Leave.start_date <= check_end,
                        Leave.end_date   >= check_start,
                        Leave.status == "approved",
                    )
                )
            )
            active_leave = result.scalar_one_or_none()
            availability.append({
                "name":           user.name,
                "email":          user.email,
                "available":      active_leave is None,
                "on_leave":       active_leave is not None,
                "leave_start_date": str(active_leave.start_date) if active_leave else None,
                "leave_end_date": str(active_leave.end_date)     if active_leave else None,
            })

        return {
            "success":   True,
            "team_name": matched_team.name,
            "team_id":   matched_team.id,
            "period":    {"start": str(check_start), "end": str(check_end)},
            "members":   availability,
        }


async def get_team_stack(
    user_id: int,
    caller_role: str = "consultant",
    skill_filter: str = None,
    my_team_only: bool = False,
    team_filter: str = None,
    dept_filter: str = None,
) -> dict:
    """
    Retourne les compétences techniques des membres selon le rôle de l'appelant.

    Scopes :
      - consultant             → uniquement sa propre équipe (toujours)
      - pm/rh + my_team_only  → uniquement sa propre équipe
      - pm/rh                 → toute l'entreprise (team_filter/dept_filter optionnels)
    """
    async with AsyncSessionLocal() as db:
        # ── 1. Récupère l'employé appelant ────────────────────────────────
        result = await db.execute(
            select(Employee).where(Employee.user_id == user_id)
        )
        employee = result.scalar_one_or_none()

        # RH/PM sans profil employé → autorisé en mode entreprise uniquement
        if not employee and caller_role not in ("rh", "pm"):
            return {"error": "Employé introuvable"}
        if not employee and (caller_role in ("rh", "pm")) and my_team_only:
            return {"error": "Profil employé requis pour filtrer par 'mon équipe'."}

        # ── 2. Construit la requête selon le scope ────────────────────────
        query = (
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .options(
                selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
                selectinload(Employee.team).selectinload(Team.department),
            )
        )

        if (caller_role == "consultant" or my_team_only is True) and employee:
            # Scope restreint : son équipe uniquement
            query = query.where(Employee.team_id == employee.team_id)
        else:
            # Scope élargi : toute l'entreprise (pm / rh)
            if team_filter:
                query = (
                    query
                    .join(Team, Employee.team_id == Team.id)
                    .where(Team.name.ilike(f"%{team_filter}%"))
                )
            if dept_filter:
                if team_filter:
                    # Team déjà jointe
                    query = query.join(Department, Team.department_id == Department.id)
                else:
                    query = (
                        query
                        .join(Team, Employee.team_id == Team.id)
                        .join(Department, Team.department_id == Department.id)
                    )
                query = query.where(Department.name.ilike(f"%{dept_filter}%"))

        members = (await db.execute(query)).all()

        # ── 3. Construit la liste filtrée par skill ───────────────────────
        stack = []
        for emp, user in members:
            if emp.user_id == user_id:
                continue  # Exclut l'appelant lui-même
            if emp.seniority == SeniorityEnum.PRINCIPAL:
                continue  # Exclut le directeur (unique, hors équipe opérationnelle)

            skills = [
                {"name": es.skill.name, "level": es.level}
                for es in emp.employee_skills
            ]

            team_name = emp.team.name if emp.team else None
            dept_name = emp.team.department.name if emp.team and emp.team.department else None

            member_info = {
                "name": user.name,
                "email": user.email,
                "team": team_name,
                "department": dept_name,
            }

            if skill_filter:
                keyword = skill_filter.strip().lower()
                matched = [s for s in skills if keyword in s["name"].lower()]
                if not matched:
                    continue
                stack.append({**member_info, "skills": matched})
            else:
                stack.append({**member_info, "skills": skills if skills else "Non renseigné"})

        # ── 4. Message clair si aucun résultat ───────────────────────────
        if not stack:
            scope_label = "l'équipe" if caller_role == "consultant" else "l'entreprise"
            msg = (
                f"Aucun membre de {scope_label} ne possède de compétence en '{skill_filter}'."
                if skill_filter
                else f"Aucun membre trouvé dans le périmètre demandé."
            )
            return {"success": True, "team_stack": [], "message": msg}

        return {
            "success": True,
            "scope": "team" if caller_role == "consultant" else "company",
            "skill_filter": skill_filter,
            "team_filter": team_filter,
            "dept_filter": dept_filter,
            "team_stack": stack,
        }
    

async def send_email(
    to_email: str,
    subject: str,
    body: str,
    cc_emails: list = None,
) -> dict:
    """
    Envoie un email générique via le compte Talan Assistant.
    Le contenu (subject, body) est généré par le LLM selon le contexte.
    """
    from utils.email import send_generic_email
    try:
        send_generic_email(
            to_email=to_email,
            subject=subject,
            body=body,
            cc_emails=cc_emails or [],
        )
        return {
            "success": True,
            "to": to_email,
            "cc": cc_emails or [],
            "subject": subject,
        }
    except Exception as e:
        return {"error": f"Échec envoi email : {str(e)}"}


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


# ═══════════════════════════════════════════════════════════
# OUTILS RH MANAGER — réservés au rôle "rh"
# ═══════════════════════════════════════════════════════════

async def approve_leave_request(employee_name: str) -> dict:
    """
    Approuve la (les) demande(s) de congé en attente d'un employé identifié par son nom.
    Si plusieurs employés correspondent, retourne la liste pour que le RH choisisse.
    """
    async with AsyncSessionLocal() as db:
        search = f"%{employee_name.lower()}%"
        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(User.name.ilike(search))
        )
        matches = result.all()

        if not matches:
            return {"error": f"Aucun employé trouvé pour '{employee_name}'"}

        if len(matches) > 1:
            return {
                "multiple_matches": True,
                "message": f"{len(matches)} employés correspondent à '{employee_name}'. Précisez lequel.",
                "employees": [
                    {"name": user.name, "email": user.email}
                    for emp, user in matches
                ],
            }

        emp, user = matches[0]

        result = await db.execute(
            select(Leave).where(
                and_(Leave.employee_id == emp.id, Leave.status == "pending")
            )
        )
        pending = result.scalars().all()

        if not pending:
            return {"error": f"Aucune demande de congé en attente pour {user.name}"}

        # Récupère le manager de l'employé
        manager_email = None
        manager_name  = None
        if emp.manager_id:
            mgr_result = await db.execute(
                select(Employee, User)
                .join(User, Employee.user_id == User.id)
                .where(Employee.id == emp.manager_id)
            )
            mgr_row = mgr_result.first()
            if mgr_row:
                _, mgr_user = mgr_row
                manager_email = mgr_user.email
                manager_name  = mgr_user.name

        approved = []
        for lv in pending:
            lv.status = "approved"
            db.add(LeaveLog(
                employee_id=emp.id,
                leave_id=lv.id,
                action="approved",
                description="Congé approuvé par le responsable RH",
            ))
            approved.append({
                "start_date": str(lv.start_date),
                "end_date":   str(lv.end_date),
                "days_count": lv.days_count,
            })

        await db.commit()

        # Envoie un email de notification à l'employé
        try:
            from utils.email import send_leave_approved_email
            cc = [manager_email] if manager_email else []
            for lv_info in approved:
                send_leave_approved_email(
                    to_email=user.email,
                    employee_name=user.name,
                    start_date=lv_info["start_date"],
                    end_date=lv_info["end_date"],
                    days_count=lv_info["days_count"],
                    manager_name=manager_name,
                    cc_emails=cc,
                )
        except Exception as e:
            print(f"  ⚠️ Email notification échec : {e}")

        return {
            "success": True,
            "employee_name": user.name,
            "approved_leaves": approved,
            "count": len(approved),
            "email_sent_to": user.email,
            "manager_notified": manager_name,
        }


async def reject_leave_request(employee_name: str, reason: str = "") -> dict:
    """
    Rejette la (les) demande(s) de congé en attente d'un employé identifié par son nom.
    Si plusieurs employés correspondent, retourne la liste pour que le RH choisisse.
    """
    async with AsyncSessionLocal() as db:
        search = f"%{employee_name.lower()}%"
        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(User.name.ilike(search))
        )
        matches = result.all()

        if not matches:
            return {"error": f"Aucun employé trouvé pour '{employee_name}'"}

        if len(matches) > 1:
            return {
                "multiple_matches": True,
                "message": f"{len(matches)} employés correspondent à '{employee_name}'. Précisez lequel.",
                "employees": [
                    {"name": user.name, "email": user.email}
                    for emp, user in matches
                ],
            }

        emp, user = matches[0]

        result = await db.execute(
            select(Leave).where(
                and_(Leave.employee_id == emp.id, Leave.status == "pending")
            )
        )
        pending = result.scalars().all()

        if not pending:
            return {"error": f"Aucune demande de congé en attente pour {user.name}"}

        # Récupère le manager de l'employé
        manager_email = None
        manager_name  = None
        if emp.manager_id:
            mgr_result = await db.execute(
                select(Employee, User)
                .join(User, Employee.user_id == User.id)
                .where(Employee.id == emp.manager_id)
            )
            mgr_row = mgr_result.first()
            if mgr_row:
                _, mgr_user = mgr_row
                manager_email = mgr_user.email
                manager_name  = mgr_user.name

        rejected = []
        reason_text = reason or "Aucune raison précisée"
        for lv in pending:
            lv.status = "rejected"
            db.add(LeaveLog(
                employee_id=emp.id,
                leave_id=lv.id,
                action="rejected",
                description=f"Congé rejeté : {reason_text}",
            ))
            rejected.append({
                "start_date": str(lv.start_date),
                "end_date":   str(lv.end_date),
                "days_count": lv.days_count,
            })

        await db.commit()

        # Envoie un email de notification à l'employé
        try:
            from utils.email import send_leave_rejected_email
            cc = [manager_email] if manager_email else []
            for lv_info in rejected:
                send_leave_rejected_email(
                    to_email=user.email,
                    employee_name=user.name,
                    start_date=lv_info["start_date"],
                    end_date=lv_info["end_date"],
                    days_count=lv_info["days_count"],
                    reason=reason_text,
                    manager_name=manager_name,
                    cc_emails=cc,
                )
        except Exception as e:
            print(f"  ⚠️ Email notification échec : {e}")

        return {
            "success": True,
            "employee_name": user.name,
            "rejected_leaves": rejected,
            "count": len(rejected),
            "reason": reason_text,
            "email_sent_to": user.email,
            "manager_notified": manager_name,
        }


async def get_leaves_by_filter(
    status: str | None = None,
    department: str | None = None,
    team: str | None = None,
    employee_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """
    Récupère les demandes de congé selon des filtres combinables :
    statut, département, équipe, nom d'employé, période (start_date/end_date).
    """
    from datetime import date as date_type

    # Conversion des dates string → date Python pour éviter l'erreur de type PostgreSQL
    parsed_start: date_type | None = None
    parsed_end: date_type | None = None
    try:
        if start_date:
            parsed_start = date_type.fromisoformat(start_date)
        if end_date:
            parsed_end = date_type.fromisoformat(end_date)
    except ValueError as e:
        return {"success": False, "error": f"Format de date invalide : {e}. Utilisez le format AAAA-MM-JJ."}

    try:
        async with AsyncSessionLocal() as db:
            query = (
                select(Leave, Employee, User, Team, Department)
                .join(Employee, Leave.employee_id == Employee.id)
                .join(User, Employee.user_id == User.id)
                .join(Team, Employee.team_id == Team.id)
                .outerjoin(Department, Team.department_id == Department.id)
            )

            if status:
                query = query.where(Leave.status == status)
            if team:
                query = query.where(Team.name.ilike(f"%{team}%"))
            if department:
                query = query.where(Department.name.ilike(f"%{department}%"))
            if employee_name:
                query = query.where(User.name.ilike(f"%{employee_name}%"))
            if parsed_start:
                query = query.where(Leave.end_date >= parsed_start)
            if parsed_end:
                query = query.where(Leave.start_date <= parsed_end)

            query = query.order_by(Leave.created_at.desc())
            result = await db.execute(query)
            rows = result.all()

            leaves = []
            for lv, emp, user, team_obj, dept in rows:
                leaves.append({
                    "employee_name": user.name,
                    "team": team_obj.name if team_obj else None,
                    "department": dept.name if dept else None,
                    "leave_type": lv.leave_type.value if hasattr(lv.leave_type, "value") else lv.leave_type,
                    "start_date": str(lv.start_date),
                    "end_date": str(lv.end_date),
                    "days_count": lv.days_count,
                    "status": lv.status.value if hasattr(lv.status, "value") else lv.status,
                    "created_at": str(lv.created_at)[:10] if lv.created_at else None,
                })

            return {
                "success": True,
                "count": len(leaves),
                "filters_applied": {
                    k: v for k, v in {
                        "status": status, "department": department,
                        "team": team, "employee_name": employee_name,
                        "start_date": start_date, "end_date": end_date,
                    }.items() if v
                },
                "leaves": leaves,
            }

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"get_leaves_by_filter error: {e}")
        return {"success": False, "error": "Impossible de récupérer les congés. Vérifiez les filtres et réessayez."}


async def update_employee_info(
    employee_name: str,
    job_title: str | None = None,
    seniority: str | None = None,
    manager_name: str | None = None,
    team_name: str | None = None,
) -> dict:
    """
    Met à jour les informations d'un employé (poste, séniorité, manager, équipe).
    Recherche l'employé par son nom.
    """
    async with AsyncSessionLocal() as db:
        search = f"%{employee_name.lower()}%"
        result = await db.execute(
            select(Employee, User)
            .join(User, Employee.user_id == User.id)
            .where(User.name.ilike(search))
        )
        matches = result.all()

        if not matches:
            return {"error": f"Aucun employé trouvé pour '{employee_name}'"}
        if len(matches) > 1:
            return {
                "multiple_matches": True,
                "message": f"{len(matches)} employés correspondent. Précisez le nom complet.",
                "employees": [{"name": u.name, "email": u.email} for _, u in matches],
            }

        emp, user = matches[0]
        changes = {}

        if job_title is not None:
            emp.job_title = job_title
            changes["job_title"] = job_title

        if seniority is not None:
            try:
                emp.seniority = SeniorityEnum(seniority)
                changes["seniority"] = seniority
            except ValueError:
                return {"error": f"Seniority invalide : {seniority}. Valeurs acceptées : junior, mid, senior, lead, principal"}

        if team_name is not None:
            team_result = await db.execute(select(Team).where(Team.name.ilike(f"%{team_name}%")))
            team = team_result.scalar_one_or_none()
            if not team:
                return {"error": f"Équipe '{team_name}' introuvable"}
            emp.team_id = team.id
            changes["team"] = team.name

        if manager_name is not None:
            mgr_result = await db.execute(
                select(Employee, User)
                .join(User, Employee.user_id == User.id)
                .where(User.name.ilike(f"%{manager_name}%"))
            )
            mgr_matches = mgr_result.all()
            if not mgr_matches:
                return {"error": f"Manager '{manager_name}' introuvable"}
            if len(mgr_matches) > 1:
                return {
                    "multiple_matches": True,
                    "message": f"Plusieurs managers correspondent à '{manager_name}'.",
                    "employees": [{"name": u.name, "email": u.email} for _, u in mgr_matches],
                }
            mgr_emp, mgr_user = mgr_matches[0]
            emp.manager_id = mgr_emp.id
            changes["manager"] = mgr_user.name

        if not changes:
            return {"error": "Aucune modification fournie (job_title, seniority, manager_name, team_name)"}

        db.add(emp)
        await db.commit()

        return {
            "success": True,
            "employee_name": user.name,
            "changes": changes,
        }