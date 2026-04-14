# agents/rh/agent.py
# ═══════════════════════════════════════════════════════════
# Agent RH — ReAct (GPT-OSS 120B) avec failover clés Groq
# ═══════════════════════════════════════════════════════════
from dotenv import load_dotenv
import asyncio
import json
import re
from datetime import date
from typing import Optional

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from agents.rh.prompts import RH_REACT_PROMPT
from agents.rh import tools as rh_tools
from app.core.groq_client import build_llm, build_llm_groq_fallback, rotate_llm_key, _is_fallback_error, _is_tpm_error, _is_context_error, FRIENDLY_QUOTA_MSG, FRIENDLY_CONTEXT_MSG  # noqa: F401
from app.core.rbac import check_tool_permission, tool_permission_denied_message
from utils.streaming import enqueue_final as _enqueue_final_shared, enqueue_working, rh_tool_to_human_text
from langsmith import trace

load_dotenv()


async def _enqueue_final(event_queue: EventQueue, text: str, task_id: str, context_id: str, status_emitted: int = 0) -> None:
    """Délègue à utils.streaming.enqueue_final — toujours TaskStatusUpdateEvent."""
    await _enqueue_final_shared(event_queue, text, task_id, context_id)


# ── Rôle utilisateur courant (injecté par execute()) ─────
_current_role = "consultant"


async def _log_leave_action(
    user_id: int,
    action: str,
    description: str,
    leave_id: "int | None" = None,
) -> None:
    """Persiste une entrée dans hris.leave_logs via employee_id."""
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.hris import Employee, LeaveLog

        async with AsyncSessionLocal() as session:
            row = await session.execute(
                select(Employee.id).where(Employee.user_id == user_id)
            )
            employee_id = row.scalar_one_or_none()
            if not employee_id:
                return

            log = LeaveLog(
                employee_id = employee_id,
                leave_id    = leave_id,
                action      = action,
                description = description,
            )
            session.add(log)
            await session.commit()
        print(f"  📋 Log congé : [{action}] (employee_id={employee_id})")
    except Exception as e:
        print(f"  ⚠️ Impossible de logger l'action congé : {e}")


def _extract_role_from_message(text: str) -> str:
    """Extrait le rôle du message enrichi envoyé par node3."""
    for line in text.split("\n"):
        if line.strip().lower().startswith("role utilisateur"):
            role = line.split(":")[-1].strip().lower()
            if role in ("consultant", "pm", "rh"):
                return role
    return "consultant"


async def _check_rbac(tool_name: str) -> str | None:
    """Vérifie RBAC. Retourne None si OK, sinon le message d'erreur."""
    if await check_tool_permission(_current_role, tool_name):
        return None
    msg = tool_permission_denied_message(tool_name)
    print(f"  🔒 RBAC refusé : {_current_role} → {tool_name}")
    return json.dumps({"error": msg, "rbac_denied": True}, ensure_ascii=False)


# ══════════════════════════════════════════════════════
# OUTILS LANGCHAIN (avec RBAC)
# ══════════════════════════════════════════════════════

@tool
async def create_leave(user_id: int, start_date: str, end_date: str) -> str:
    """Crée une demande de congé. Vérifie automatiquement les chevauchements."""
    denied = await _check_rbac("create_leave")
    if denied: return denied
    result = await rh_tools.create_leave(user_id=user_id, start_date=start_date, end_date=end_date)

    if result.get("success"):
        leave_id = result.get("leave_id")
        days     = result.get("days_count", "?")
        await _log_leave_action(
            user_id     = user_id,
            action      = "requested",
            description = f"Vous avez demandé un congé du {start_date} au {end_date} ({days} jour(s))",
            leave_id    = leave_id,
        )

    return json.dumps(result, ensure_ascii=False)


@tool
async def delete_leave(
    user_id: int,
    leave_id: int = None,
    start_date: str = None,
    end_date: str = None,
) -> str:
    """
    Annule une demande de congé existante.
    - leave_id : annule un congé précis
    - start_date seule : annule le congé couvrant cette date
    - start_date + end_date : annule les congés de la période
    """
    denied = await _check_rbac("delete_leave")
    if denied: return denied
    result = await rh_tools.delete_leave(
        user_id=user_id,
        leave_id=leave_id,
        start_date=start_date,
        end_date=end_date,
    )

    if result.get("success"):
        cancelled = result.get("cancelled_leaves") or []
        if cancelled:
            for item in cancelled:
                await _log_leave_action(
                    user_id     = user_id,
                    action      = "cancelled",
                    description = (
                        f"Congé #{item.get('leave_id')} du {item.get('start_date')} "
                        f"au {item.get('end_date')} annulé"
                    ),
                    leave_id    = item.get("leave_id"),
                )
        else:
            await _log_leave_action(
                user_id     = user_id,
                action      = "cancelled",
                description = (
                    f"Congé #{result.get('leave_id')} du {result.get('start_date')} "
                    f"au {result.get('end_date')} annulé"
                ),
                leave_id    = result.get("leave_id"),
            )

    return json.dumps(result, ensure_ascii=False)


@tool
async def get_my_leaves(user_id: int, status_filter: Optional[str] = None) -> str:
    """Retourne les congés d'un employé."""
    denied = await _check_rbac("get_my_leaves")
    if denied: return denied
    result = await rh_tools.get_my_leaves(user_id=user_id, status_filter=status_filter)
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_availability(
    user_id: int,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Retourne la disponibilité de l'équipe de l'utilisateur connecté pour une période donnée.
    start_date / end_date : période YYYY-MM-DD. Si absents, vérifie aujourd'hui.
    Toujours passer start_date et end_date quand l'utilisateur mentionne une période ('semaine prochaine', 'lundi', etc.)."""
    denied = await _check_rbac("get_team_availability")
    if denied: return denied
    result = await rh_tools.get_team_availability(
        user_id=user_id, start_date=start_date, end_date=end_date
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_availability_by_name(
    team_name: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """Retourne la liste des membres d'une équipe et leur disponibilité pour une période donnée.
    Utiliser pour : 'membres de l'équipe X', 'qui est dans X', 'composition de X',
    'qui est disponible dans X', 'effectif de l'équipe X'.
    Le nom peut être partiel : 'Innovation' trouvera 'Innovation Factory'.
    start_date / end_date : période YYYY-MM-DD. Si absents, vérifie aujourd'hui."""
    denied = await _check_rbac("get_team_availability")
    if denied: return denied
    result = await rh_tools.get_team_availability_by_name(
        team_name=team_name, start_date=start_date, end_date=end_date
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_team_stack(
    user_id: int,
    skill_filter: str = None,
    my_team_only: Optional[bool] = False,
    team_filter: Optional[str] = None,
    dept_filter: Optional[str] = None,
) -> str:
    """Retourne les COMPÉTENCES TECHNIQUES (skills, stack) des employés.
    Utiliser UNIQUEMENT pour : 'compétences de l'équipe', 'qui sait faire X',
    'stack technique', 'qui maîtrise React/Java/Python', 'skills de l'équipe'.
    ⛔ NE PAS utiliser pour lister les membres d'une équipe — utiliser get_team_availability_by_name.
    ⛔ NE PAS utiliser si l'utilisateur demande 'membres', 'composition', 'effectif'.

    Scope automatique :
      - consultant          → toujours son équipe uniquement
      - pm/rh               → toute l'entreprise par défaut

    Filtres optionnels (pm/rh) :
      - skill_filter : technologie précise (ex: 'Java', 'React')
      - team_filter  : nom d'équipe explicite (ex: 'Data Ops')
      - dept_filter  : département (ex: 'cloud', 'data')"""
    denied = await _check_rbac("get_team_stack")
    if denied: return denied
    result = await rh_tools.get_team_stack(
        user_id=user_id,
        caller_role=_current_role,
        skill_filter=skill_filter,
        my_team_only=my_team_only,
        team_filter=team_filter,
        dept_filter=dept_filter,
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def check_calendar_conflicts(user_id: int, start_date: str, end_date: str) -> str:
    """Vérifie les conflits réels dans Google Calendar pour la période de congé donnée."""
    denied = await _check_rbac("check_calendar_conflicts")
    if denied: return denied

    # ── Vérifier si l'utilisateur a connecté Google Calendar ──
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.public.google_oauth_token import GoogleOAuthToken
        async with AsyncSessionLocal() as db:
            token_row = (await db.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )).scalar_one_or_none()
    except Exception:
        token_row = None

    if not token_row:
        print(f"  📅 [check_calendar_conflicts] user_id={user_id} → Google Calendar non connecté")
        return json.dumps({
            "success": True,
            "conflicts": [],
            "calendar_connected": False,
            "warning": (
                f"Google Calendar non connecté — impossible de vérifier les réunions "
                f"prévues du {start_date} au {end_date}. "
                f"L'utilisateur doit être averti de connecter son agenda."
            ),
        }, ensure_ascii=False)

    # ── Appel MCP ──────────────────────────────────────────────
    try:
        from agents.calendar.tools import check_calendar_conflicts as cal_check
        account_id = str(user_id)
        print(f"  📅 [check_calendar_conflicts] user_id={user_id} → account_id='{account_id}' | période={start_date} → {end_date}")
        result = await cal_check(start_date, end_date, account_id=account_id)
        result["calendar_connected"] = True
        print(f"  📅 [check_calendar_conflicts] résultat MCP : {result}")
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Calendar MCP indisponible : {e}")
        return json.dumps({
            "success": True,
            "conflicts": [],
            "calendar_connected": False,
            "message": "Impossible de vérifier le calendrier (service indisponible).",
            "mcp_error": True,
        }, ensure_ascii=False)


@tool
async def reschedule_meeting(
    event_id: str,
    event_title: str,
    current_start: str,
    current_end: str,
    new_date: str,
) -> str:
    """
    Replanifie une réunion via l'agent Calendar (A2A).
    Passe l'event_id directement pour éviter toute recherche par titre.

    event_id      : ID Google Calendar de l'événement (champ 'id' des conflicts).
    event_title   : titre de la réunion (pour le message de confirmation).
    current_start : début ISO actuel (ex: '2026-03-26T09:00:00+01:00').
    current_end   : fin ISO actuelle  (ex: '2026-03-26T10:00:00+01:00').
    new_date      : nouvelle date YYYY-MM-DD.
    """
    denied = await _check_rbac("reschedule_meeting")
    if denied: return denied
    from app.a2a.client import send_task
    today = date.today().strftime("%Y-%m-%d")
    # Reconstruit les heures de début/fin sur la nouvelle date
    new_start = new_date + current_start[10:]
    new_end   = new_date + current_end[10:]
    message = (
        f"Date du jour : {today}\n"
        f"Déplace l'événement avec l'event_id '{event_id}' (titre : '{event_title}') "
        f"au {new_date}, nouvelle heure de début : {new_start}, nouvelle heure de fin : {new_end}. "
        f"Utilise directement update_meeting avec cet event_id sans faire de recherche."
    )
    try:
        response = await send_task("calendar", message)
        return json.dumps({"success": True, "response": response}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Impossible de replanifier '{event_title}' : {str(e)}"}, ensure_ascii=False)


@tool
async def remove_meeting_attendee(
    event_id: str,
    event_title: str,
    email_to_remove: str,
) -> str:
    """
    Retire un participant d'une réunion existante via l'agent Calendar.
    Récupère automatiquement la liste des participants puis met à jour l'événement.

    event_id        : ID Google Calendar de l'événement (champ 'id' des conflicts).
    event_title     : titre de la réunion (pour la confirmation).
    email_to_remove : adresse email du participant à retirer.
    """
    denied = await _check_rbac("reschedule_meeting")
    if denied: return denied
    from app.a2a.client import send_task
    today = date.today().strftime("%Y-%m-%d")
    print(f"  🗑️ [remove_meeting_attendee] event_id={event_id} | retirer={email_to_remove}")
    message = (
        f"Date du jour : {today}\n"
        f"Retire le participant '{email_to_remove}' de la réunion avec l'event_id '{event_id}' "
        f"(titre : '{event_title}'). "
        f"Utilise get_event avec cet event_id pour récupérer la liste actuelle des participants, "
        f"puis appelle update_meeting avec la liste mise à jour sans '{email_to_remove}'. "
        f"Ne fais aucune recherche par titre."
    )
    try:
        response = await send_task("calendar", message)
        print(f"  🗑️ [remove_meeting_attendee] réponse Calendar : {str(response)[:200]}")
        return json.dumps({"success": True, "response": response}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Impossible de retirer '{email_to_remove}' de '{event_title}' : {str(e)}"}, ensure_ascii=False)


@tool
async def notify_manager(
    manager_email: str,
    employee_name: str,
    start_date: str,
    end_date: str,
    days_count: int,
) -> str:
    """Notifie le manager par email qu'une demande de congé a été déposée.
    Utiliser les valeurs retournées par create_leave : manager_email, employee_name, start_date, end_date, days_count."""
    denied = await _check_rbac("notify_manager")
    if denied: return denied
    try:
        from utils.email import send_leave_request_email
        send_leave_request_email(
            to_email=manager_email,
            employee_name=employee_name,
            start_date=start_date,
            end_date=end_date,
            days_count=days_count,
        )
        return json.dumps({"success": True, "to": manager_email}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Échec envoi email manager : {str(e)}"}, ensure_ascii=False)


@tool
async def send_email(
    to_email: str,
    subject: str,
    body: str,
    cc_emails: list = None,
) -> str:
    """[RH UNIQUEMENT] Envoie un email générique au nom de Talan.
    Le LLM génère subject et body selon la demande de l'utilisateur.
    Exemples : demander un justificatif, informer un employé, contacter une équipe.
    cc_emails : liste optionnelle d'emails en copie."""
    denied = await _check_rbac("send_email")
    if denied: return denied
    result = await rh_tools.send_email(
        to_email=to_email,
        subject=subject,
        body=body,
        cc_emails=cc_emails or [],
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def check_leave_balance(user_id: int, requested_days: int = 0) -> str:
    """Vérifie le solde de congés disponible d'un employé."""
    denied = await _check_rbac("check_leave_balance")
    if denied: return denied
    result = await rh_tools.check_leave_balance(user_id=user_id, requested_days=requested_days)
    return json.dumps(result, ensure_ascii=False)


# ── OUTILS RÉSERVÉS AU RÔLE RH ────────────────────────

@tool
async def approve_leave_request(employee_name: str) -> str:
    """
    [RH UNIQUEMENT] Approuve la demande de congé en attente d'un employé.
    Si plusieurs employés correspondent au nom, retourne la liste pour choisir.
    """
    denied = await _check_rbac("approve_leave_request")
    if denied: return denied
    result = await rh_tools.approve_leave_request(employee_name=employee_name)
    return json.dumps(result, ensure_ascii=False)


@tool
async def reject_leave_request(employee_name: str, reason: str = "") -> str:
    """
    [RH UNIQUEMENT] Rejette la demande de congé en attente d'un employé.
    Si plusieurs employés correspondent, retourne la liste pour choisir.
    """
    denied = await _check_rbac("reject_leave_request")
    if denied: return denied
    result = await rh_tools.reject_leave_request(employee_name=employee_name, reason=reason)
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_leaves_by_filter(
    status: str = None,
    department: str = None,
    team: str = None,
    employee_name: str = None,
    start_date: str = None,
    end_date: str = None,
) -> str:
    """
    [RH UNIQUEMENT] Récupère les demandes de congé filtrées.
    Filtres combinables : status (pending/approved/rejected/cancelled),
    department, team, employee_name, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD).
    """
    denied = await _check_rbac("get_leaves_by_filter")
    if denied: return denied
    result = await rh_tools.get_leaves_by_filter(
        status=status, department=department, team=team,
        employee_name=employee_name, start_date=start_date, end_date=end_date,
    )
    return json.dumps(result, ensure_ascii=False)


@tool
async def get_my_profile(user_id: int) -> str:
    """Retourne le profil complet de l'utilisateur connecté : nom, poste, séniorité, équipe, département et nom du manager."""
    denied = await _check_rbac("get_my_profile")
    if denied: return denied
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.public.user import User
        from app.database.models.hris.employee import Employee
        from app.database.models.hris.team import Team

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Employee, User)
                .join(User, Employee.user_id == User.id)
                .where(Employee.user_id == user_id)
            )
            row = result.first()
            if not row:
                return json.dumps({"error": "Profil employé introuvable."}, ensure_ascii=False)

            emp, user = row

            # Récupère le nom du manager
            manager_name = None
            if emp.manager_id:
                mgr_result = await db.execute(
                    select(User).join(Employee, Employee.user_id == User.id)
                    .where(Employee.id == emp.manager_id)
                )
                mgr_user = mgr_result.scalar_one_or_none()
                if mgr_user:
                    manager_name = mgr_user.name

            # Récupère le nom de l'équipe
            team_name = None
            if emp.team_id:
                team_result = await db.execute(select(Team).where(Team.id == emp.team_id))
                team = team_result.scalar_one_or_none()
                if team:
                    team_name = team.name

            return json.dumps({
                "name":       user.name,
                "email":      user.email,
                "role":       user.role,
                "job_title":  emp.job_title,
                "seniority":  emp.seniority,
                "team":       team_name,
                "department": emp.department,
                "manager":    manager_name or "Aucun manager configuré",
            }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
async def update_employee_info(
    employee_name: str,
    job_title: str = None,
    seniority: str = None,
    manager_name: str = None,
    team_name: str = None,
) -> str:
    """
    [RH UNIQUEMENT] Met à jour les informations d'un employé :
    job_title, seniority (junior/mid/senior/lead/principal), manager_name, team_name.
    """
    denied = await _check_rbac("update_employee_info")
    if denied: return denied
    result = await rh_tools.update_employee_info(
        employee_name=employee_name,
        job_title=job_title,
        seniority=seniority,
        manager_name=manager_name,
        team_name=team_name,
    )
    return json.dumps(result, ensure_ascii=False)


# ══════════════════════════════════════════════════════
# LISTE DES OUTILS
# ══════════════════════════════════════════════════════

TOOLS = [
    check_leave_balance,
    create_leave,
    delete_leave,
    get_my_leaves,
    get_my_profile,
    get_team_availability,
    get_team_availability_by_name,
    get_team_stack,
    check_calendar_conflicts,
    reschedule_meeting,
    remove_meeting_attendee,
    notify_manager,
    send_email,
    # Outils RH manager
    approve_leave_request,
    reject_leave_request,
    get_leaves_by_filter,
    update_employee_info,
]


# ══════════════════════════════════════════════════════
# A2A EXECUTOR avec failover
# ══════════════════════════════════════════════════════

class RHAgentExecutor(AgentExecutor):
    """
    Pont entre le protocole A2A et le ReAct agent RH.
    Failover : si la clé Groq tombe, reconstruit le ReAct agent
    avec la clé suivante et retente.
    """

    def __init__(self) -> None:
        self._build_react_agent()

    def _build_react_agent(self, use_groq_fallback: bool = False) -> None:
        """Construit le ReAct agent.
        use_groq_fallback=True → force Groq (quand NVIDIA a échoué).
        """
        llm = (build_llm_groq_fallback if use_groq_fallback else build_llm)(
            model="openai/gpt-oss-120b",
            temperature=0,
            max_tokens=1500,
        )
        self.react_agent = create_react_agent(
            model=llm,
            tools=TOOLS,
            prompt=RH_REACT_PROMPT,
        )

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        global _current_role

        user_input = context.get_user_input()
        _current_role = _extract_role_from_message(user_input)

        task_id = context.task_id or "task"
        context_id = context.context_id or "ctx"

        print(f"\n{'='*50}")
        print(f"🤖 RHAgent ReAct (Groq 120B) — Message reçu : {user_input[:200]}")
        print(f"🔐 Rôle utilisateur : {_current_role}")
        print(f"{'='*50}")

        max_retries = 3

        with trace(
            name="rh_agent.execute",
            run_type="chain",
            inputs={"user_input": user_input[:1000], "role": _current_role},
            tags=["agent", "rh"],
        ) as ls_run:

            for attempt in range(max_retries):
                result_messages = None
                status_events_emitted = 0

                try:
                    async for event in self.react_agent.astream_events(
                        {"messages": [HumanMessage(content=user_input)]},
                        version="v2",
                        config={"recursion_limit": 12},
                    ):
                        etype = event["event"]

                        if etype == "on_tool_start":
                            tool_name = event["name"]
                            tool_args = event["data"].get("input") or {}
                            if not isinstance(tool_args, dict):
                                tool_args = {}
                            step_text = rh_tool_to_human_text(tool_name, tool_args)
                            print(f"  🔧 [STREAM] Tool start: {tool_name}({tool_args})")
                            await enqueue_working(event_queue, step_text, task_id, context_id)
                            status_events_emitted += 1

                        elif etype == "on_chain_end":
                            output = event["data"].get("output", {})
                            if isinstance(output, dict) and "messages" in output:
                                result_messages = output["messages"]

                    break

                except Exception as e:
                    # ⚠️ context_error AVANT tpm_error : "request too large" matche
                    # aussi "tokens per minute" → il faut court-circuiter en premier.
                    if _is_context_error(e):
                        print(f"⚠️ Contexte trop long (RH) : {str(e)[:120]}")
                        final_response = FRIENDLY_CONTEXT_MSG
                        ls_run.end(outputs={"response": final_response, "error": "context"})
                        await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                        return
                    elif _is_tpm_error(e) and rotate_llm_key():
                        print(f"⚠️ TPM dépassé (RH tentative {attempt+1}/{max_retries}), rotation clé Groq + attente 3s")
                        self._build_react_agent(use_groq_fallback=True)
                        await asyncio.sleep(3)
                        continue
                    elif _is_tpm_error(e):
                        print(f"⚠️ TPM dépassé (RH) — toutes les clés Groq épuisées ({max_retries} tentatives)")
                        final_response = FRIENDLY_QUOTA_MSG
                        ls_run.end(outputs={"response": final_response, "error": "quota"})
                        await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                        return
                    elif _is_fallback_error(e) and rotate_llm_key() and status_events_emitted == 0:
                        print(f"⚠️ [Groq RH] Clé invalide (tentative {attempt+1}/{max_retries}) → rotation")
                        self._build_react_agent(use_groq_fallback=True)
                        continue
                    else:
                        print(f"❌ Erreur ReAct : {str(e)}")
                        final_response = "Une erreur inattendue s'est produite. Veuillez réessayer ou reformuler votre demande."
                        ls_run.end(outputs={"response": final_response, "error": str(e)})
                        await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                        return
            else:
                final_response = "Toutes les clés API sont temporairement indisponibles. Veuillez réessayer."
                ls_run.end(outputs={"response": final_response, "error": "all_keys_exhausted"})
                await _enqueue_final(event_queue, json.dumps({"response": final_response, "react_steps": []}, ensure_ascii=False), task_id, context_id, status_events_emitted)
                return

            react_steps = []
            tool_calls_map = {}
            final_response = "L'agent n'a pas retourné de réponse."

            if result_messages:
                print(f"\n{'─'*50}")
                print("🧠 CYCLE ReAct — RHAgent :")

                for msg in result_messages:
                    msg_type = type(msg).__name__
                    if msg_type == "AIMessage":
                        if msg.content:
                            print(f"  🤔 Think  : {msg.content[:300]}")
                        if msg.tool_calls:
                            for tc in msg.tool_calls:
                                step_text = rh_tool_to_human_text(tc['name'], tc['args'])
                                react_steps.append(step_text)
                                tool_calls_map[tc['id']] = len(react_steps) - 1
                                print(f"  🔧 Act    : {tc['name']}({tc['args']})")
                    elif msg_type == "ToolMessage":
                        print(f"  👁️  Observe: {msg.content[:200]}")
                        obs = _format_observation(msg.content)
                        tc_id = getattr(msg, 'tool_call_id', None)
                        if tc_id and tc_id in tool_calls_map and obs:
                            idx = tool_calls_map[tc_id]
                            react_steps[idx] += f"\n   → {obs}"
                    elif msg_type == "HumanMessage":
                        print(f"  👤 Human  : {msg.content[:200]}")

                print(f"{'─'*50}\n")
                final_response = result_messages[-1].content

            ui_hint = _detect_ui_hint(final_response)
            print(f"  🎨 UI Hint détecté : {ui_hint}")

            ls_run.end(outputs={
                "response": final_response[:500] if final_response else "",
                "react_steps": react_steps,
                "steps_count": len(react_steps),
                "ui_hint": ui_hint,
            })

            response_data = {"response": final_response, "react_steps": react_steps}
            if ui_hint:
                response_data["ui_hint"] = ui_hint

            await _enqueue_final(event_queue, json.dumps(response_data, ensure_ascii=False), task_id, context_id, status_events_emitted)

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        pass


# ══════════════════════════════════════════════════════
# FONCTIONS UTILITAIRES
# ══════════════════════════════════════════════════════

def _normalize(text: str) -> str:
    """Normalise les caractères Unicode exotiques produits par le LLM."""
    return (
        text.lower()
        .replace("\u2011", "-")
        .replace("\u2010", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
        .replace("\u00ab", '"')
        .replace("\u00bb", '"')
    )


def _detect_ui_hint(text: str) -> "dict | None":
    """Analyse la réponse pour suggérer un composant UI interactif au frontend."""
    t = _normalize(text)

    is_oui_non = (
        "souhaitez-vous" in t or
        "voulez-vous" in t or
        "confirmez-vous" in t or
        bool(re.search(r"oui\s*/\s*non", t)) or
        bool(re.search(r"r.pondez.*oui", t)) or
        ("oui" in t and "non" in t and "?" in t)
    )
    is_time_or_title = bool(re.search(r"quelle heure|quel titre|quel jour", t))
    if is_oui_non and not is_time_or_title:
        return {"type": "confirm", "options": ["Oui", "Non"]}

    if re.search(r"dates de (d.but|fin)|p.riode souhait.e|date de debut.*date de fin", t):
        return {"type": "date_range"}

    if re.search(r"quelle date|a quelle date|precisez la date|choisissez une date|quel jour|nouvelle date", t):
        return {"type": "date_picker"}

    return None

def _format_observation(content: str) -> str:
    try:
        data = json.loads(content)
        if data.get("success"):
            if "solde_effectif" in data:
                solde = data['solde_effectif']
                total = data['solde_total']
                pending = data['jours_pending']
                can = data.get('can_create')
                base = f"Solde effectif : {solde} jours ({total} total - {pending} en attente)"
                if can is True:
                    return f"{base} ✅"
                elif can is False:
                    return f"{base} ❌ Solde insuffisant"
                return f"{base} ✅"
            if "conflicts" in data:
                conflicts = data.get("conflicts", [])
                return "Aucun conflit trouvé ✅" if not conflicts else f"{len(conflicts)} conflit(s) ⚠️"
            if "new_status" in data and data["new_status"] == "cancelled":
                return f"Congé #{data.get('leave_id')} annulé ✅"
            if "leave_id" in data and "new_status" not in data:
                return f"Congé créé (ID: {data['leave_id']}) ✅"
            if "message" in data:
                return f"{data['message']} ✅"
        elif "error" in data:
            return f"❌ {data['error']}"
    except Exception:
        pass
    return ""