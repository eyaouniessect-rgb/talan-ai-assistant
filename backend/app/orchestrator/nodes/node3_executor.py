# app/orchestrator/nodes/node3_executor.py

import asyncio
import json
import contextvars
from datetime import date, datetime, timezone

from app.orchestrator.state import AssistantState, PlanStep
from app.a2a.client import send_task_to_url
from app.a2a.discovery import discovery
from langsmith import traceable

MAX_HISTORY = 10
MAX_AI_RESPONSE_CHARS = 300

# Préfixes des messages d'erreur système à exclure de l'historique
_ERROR_PREFIXES = ("⚠️", "Erreur lors du traitement")

# ── ContextVar pour la queue SSE (streaming) ─────────────
_stream_queue: contextvars.ContextVar = contextvars.ContextVar('_stream_queue', default=None)


async def _emit(queue, event: dict):
    """Emit an event to the SSE queue if streaming is active."""
    if queue is not None:
        await queue.put(event)
        print(f"   📡 [STREAM] {event.get('type')} | step={event.get('step_id','')} agent={event.get('agent','')}")


# ── Réponses déterministes pour l'agent "chat" ────────────
MERCI_KEYWORDS = {
    "merci", "ok merci", "super merci", "merci beaucoup",
    "parfait", "super", "nickel", "très bien", "d'accord",
    "ok d'accord", "c'est bon", "c bon"
}

SALUTATION_KEYWORDS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou", "bonne journée"
}

_AU_REVOIR_KEYWORDS = {
    "au revoir", "aurevoir", "bonne journée", "bonne journee",
    "à bientôt", "a bientot", "bonne soirée", "bonne soiree",
    "bye", "ciao", "tchao",
}

DATE_KEYWORDS = {
    "date", "aujourd'hui", "quel jour", "quelle date",
    "c'est quoi la date", "la date aujourd'hui", "date du jour"
}

PRESENTATION = """Bonjour ! Je suis Talan Assistant chez Talan Tunisie.
Je peux vous aider avec vos congés, projets, tickets Jira, messages Slack, calendrier et recherche documentaire.
Comment puis-je vous aider ?"""

# Noms affichables pour les agents (pour les messages de fallback)
AGENT_DISPLAY_NAMES = {
    "rh":       "RH (gestion des congés)",
    "calendar": "Calendrier",
    "jira":     "Jira",
    "slack":    "Slack",
    "crm":      "CRM",
    "chat":     "Assistant",
}


class AgentUnavailableError(Exception):
    """Levée quand un agent n'est pas découvert (pas démarré / non développé)."""
    pass


def _step_start_msg(agent: str, task: str) -> str:
    """Génère un message de démarrage d'étape naturel selon l'agent et la tâche."""
    t = task.lower()
    if agent == "rh":
        if any(k in t for k in ["solde", "reste", "combien"]):
            return "🔍 Je vérifie votre solde de congés..."
        if any(k in t for k in ["poser", "créer", "creer", "pose un", "créer un", "creer un"]):
            return "📝 Je crée votre demande de congé..."
        if any(k in t for k in ["supprimer", "annuler", "retirer"]):
            return "🗑️ J'annule votre congé..."
        return "⚙️ Je traite votre demande RH..."
    if agent == "calendar":
        # Vérifier annuler/supprimer EN PREMIER pour éviter le match sur "reunion" dans "annuler cette reunion"
        if any(k in t for k in ["annuler", "supprimer", "cancel"]):
            return "🗑️ J'annule votre réunion..."
        if any(k in t for k in ["modifier", "déplacer", "decaler", "reporter"]):
            return "✏️ Je modifie votre réunion..."
        if any(k in t for k in ["rétabli", "retabli", "ancienne", "restau"]):
            return "🔄 Je rétablis votre réunion..."
        if any(k in t for k in ["disponib", "vérifi", "verifie"]):
            return "🔍 Je vérifie les disponibilités..."
        if any(k in t for k in ["créer", "creer", "planifier", "réunion", "reunion", "meeting"]):
            return "📅 Je crée votre réunion dans le calendrier..."
        return "📅 Je consulte votre calendrier..."
    if agent == "jira":
        return "🎯 Je consulte vos tickets Jira..."
    if agent == "slack":
        return "💬 J'envoie votre message Slack..."
    if agent == "crm":
        return "🏢 Je consulte les données CRM..."
    return f"⚙️ Je traite votre demande ({agent})..."


def _handle_chat(task: str, today_iso: str) -> str:
    """Gère les réponses pour l'agent 'chat'."""
    last_clean = task.lower().strip().rstrip("!?.,:;")
    last_clean = " ".join(last_clean.split())

    if last_clean in MERCI_KEYWORDS:
        return "De rien ! N'hésitez pas si vous avez besoin d'autre chose."
    if last_clean in SALUTATION_KEYWORDS:
        return PRESENTATION
    if last_clean in _AU_REVOIR_KEYWORDS:
        return "Au revoir ! Bonne continuation."
    if any(kw in last_clean for kw in DATE_KEYWORDS):
        date_part = today_iso.split()[0]
        return f"Aujourd'hui c'est le {date_part}."
    return (
        "Je n'ai pas compris votre demande. Voici ce que je peux faire :\n\n"
        "- **Congés** : créer, supprimer, consulter, vérifier le solde\n"
        "- **Calendrier** : créer, modifier, supprimer des réunions\n"
        "- **Jira** : consulter vos tickets\n"
        "- **Slack** : envoyer un message\n\n"
        "Pouvez-vous reformuler votre demande ?"
    )


def _extract_clean_text(content: str) -> str:
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed.get("response", content)
        return content
    except (json.JSONDecodeError, TypeError):
        return content


def _strip_markdown_tables(text: str) -> str:
    """Supprime les lignes de tableau Markdown (| ... |) pour réduire les tokens."""
    result = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Ignorer les lignes de tableau et les séparateurs (|---|)
        if stripped.startswith("|"):
            continue
        result.append(line)
    return "\n".join(result).strip()


def _build_history(trimmed_messages: list) -> str:
    lines = []
    for msg in trimmed_messages[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        clean = _extract_clean_text(msg.content)
        # Exclure les messages d'erreur système (quota, contexte trop long...)
        if msg.type != "human" and any(clean.startswith(p) for p in _ERROR_PREFIXES):
            continue
        # Supprimer les tableaux Markdown pour économiser des tokens
        if msg.type != "human":
            clean = _strip_markdown_tables(clean)
        if msg.type != "human" and len(clean) > MAX_AI_RESPONSE_CHARS:
            clean = clean[:MAX_AI_RESPONSE_CHARS] + "... [tronqué]"
        lines.append(f"{role}: {clean}")
    return "\n".join(lines)


def _get_step_status(plan: list, step_id: str) -> str:
    """Retourne le statut d'une étape par son ID."""
    for s in plan:
        if s["step_id"] == step_id:
            return s["status"]
    return "unknown"


_CONDITION_KEYWORDS = ["si ", "if ", "seulement si", "only if", "lorsque ", "dans le cas où"]

async def _check_condition(task: str, context: str) -> bool:
    """
    Évalue si la condition d'un step conditionnel est remplie.
    Retourne True → exécuter le step | False → ignorer le step.
    Utilisé uniquement si la tâche contient un mot-clé conditionnel ET un contexte.
    """
    task_lower = task.lower()
    if not any(kw in task_lower for kw in _CONDITION_KEYWORDS):
        return True  # Pas de condition → toujours exécuter
    if not context.strip():
        return True  # Pas de contexte → on ne peut pas évaluer → exécuter

    from langchain_core.messages import HumanMessage
    from app.core.groq_client import invoke_with_fallback

    prompt = (
        f"Résultat de l'étape précédente :\n{context}\n\n"
        f"Tâche conditionnelle : {task}\n\n"
        f"D'après le résultat ci-dessus, la condition dans la tâche est-elle remplie ?\n"
        f"Réponds UNIQUEMENT par OUI ou NON."
    )
    try:
        response = await invoke_with_fallback(
            model="openai/gpt-oss-120b",
            messages=[HumanMessage(content=prompt)],
            max_tokens=5,
            temperature=0,
        )
        result = response.strip().lower()
        print(f"   🔍 Évaluation condition → '{result}' pour : {task[:80]}")
        return "oui" in result
    except Exception as e:
        print(f"   ⚠️ Évaluation condition échouée ({e}) → exécution par défaut")
        return True  # En cas d'erreur → exécuter par défaut


async def _check_google_token(user_id: int) -> tuple[bool, str]:
    """
    Vérifie que l'utilisateur a un token Google Calendar valide en base.
    Retourne (ok: bool, raison: str).
      - ok=True  → le token existe et le refresh_token est présent
      - ok=False → token absent ou refresh_token manquant (accès révoqué)
    """
    try:
        from sqlalchemy import select
        from app.database.connection import AsyncSessionLocal
        from app.database.models.user import GoogleOAuthToken

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(GoogleOAuthToken).where(GoogleOAuthToken.user_id == user_id)
            )
            token = result.scalar_one_or_none()

        if token is None:
            return False, "not_connected"
        if not token.refresh_token:
            return False, "no_refresh_token"
        # Si expires_at est défini et dépassé, le refresh_token reste valable
        # (Google invalide le refresh_token seulement si l'accès est révoqué)
        return True, "ok"
    except Exception as e:
        print(f"  ⚠️ _check_google_token erreur : {e}")
        # En cas d'erreur DB, on laisse passer (l'agent renverra son propre message)
        return True, "db_error"


async def _call_agent(
    agent_name: str,
    task: str,
    user_id: int,
    role: str,
    today_iso: str,
    history: str = "",
    step_id: str = None,
    queue=None,
):
    discovered = await discovery.find_agent_by_name(agent_name)
    if not discovered:
        raise AgentUnavailableError(f"Agent '{agent_name}' non trouvé")

    history_section = f"Historique de la conversation :\n{history}\n---\n" if history else ""
    message = (
        f"Date du jour : {today_iso}\n---\n"
        f"{history_section}"
        f"INSTRUCTION À EXÉCUTER :\n{task}\n---\n"
        f"Role utilisateur : {role}\nUser ID : {user_id}"
    )

    print(f"      [A2A] Appel agent='{agent_name}' streaming={discovered.supports_streaming}")

    if discovered.supports_streaming and queue is not None:
        from app.a2a.client import send_task_to_url_streaming
        final_text = ""
        async for evt_type, evt_text in send_task_to_url_streaming(discovered.url, message):
            if evt_type == "status" and step_id is not None:
                print(f"      [A2A STREAM] status: {evt_text[:80]}")
                # Skip final JSON responses (they are the agent's result, not progress text)
                _is_json_response = False
                try:
                    _parsed = json.loads(evt_text)
                    if isinstance(_parsed, dict) and "response" in _parsed:
                        _is_json_response = True
                except (json.JSONDecodeError, TypeError):
                    pass
                if not _is_json_response:
                    await _emit(queue, {
                        "type": "step_progress",
                        "step_id": step_id,
                        "agent": agent_name,
                        "text": evt_text,
                    })
            final_text = evt_text  # la dernière valeur = texte final
        response = final_text or "L'agent n'a pas retourné de réponse."
    else:
        response = await send_task_to_url(discovered.url, message)

    try:
        parsed = json.loads(response)
        if parsed.get("needs_input"):
            return response, True
    except Exception:
        pass
    return response, False


@traceable(name="node3_executor", tags=["orchestrator"])
async def node3_executor(state: AssistantState) -> AssistantState:
    plan = state.get("plan")
    if not plan:
        return {**state, "final_response": "Aucun plan généré. Veuillez reformuler."}

    # ── Récupère la queue SSE depuis le ContextVar ────────
    queue = _stream_queue.get()

    plan_results = state.get("plan_results") or {}
    waiting_step = state.get("waiting_step")

    # Reprise après question
    if waiting_step:
        last_user_msg = state["messages"][-1].content
        for step in plan:
            if step["step_id"] == waiting_step:
                step["task"] = f"{step['task']}\nRéponse utilisateur : {last_user_msg}"
                step["status"] = "pending"
                break
        waiting_step = None

    user_id = state["user_id"]
    role = state["role"]
    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_iso = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY:] if len(all_messages) > MAX_HISTORY else all_messages
    history = _build_history(trimmed)

    print(f"\n{'='*60}")
    print(f"⚙️  NODE 3 — EXECUTOR ({len(plan)} étape(s)) | streaming={'oui' if queue else 'non'}")
    print(f"{'='*60}")

    for step in plan:
        step_id = step["step_id"]
        agent   = step["agent"]
        task    = step["task"]
        deps    = step.get("depends_on", [])

        if step["status"] in ("done", "failed", "unavailable", "skipped"):
            continue
        if step["status"] == "waiting_input":
            continue

        # ── Vérification des dépendances ──────────────────────
        if deps:
            blocked_deps = [d for d in deps if _get_step_status(plan, d) in ("failed", "unavailable", "skipped")]

            if blocked_deps:
                # Une dépendance est bloquée → on saute cette étape proprement
                agent_display = AGENT_DISPLAY_NAMES.get(agent, agent.upper())
                print(f"   ⏭️  {step_id} ({agent}) — ignoré (dépendance bloquée : {blocked_deps})")
                step["status"] = "skipped"
                plan_results[step_id] = json.dumps({
                    "response": f"L'étape **{agent_display}** a été ignorée car une étape précédente n'est pas disponible.",
                    "react_steps": []
                }, ensure_ascii=False)
                await _emit(queue, {
                    "type": "step_skipped",
                    "step_id": step_id,
                    "agent": agent,
                })
                continue

            if any(_get_step_status(plan, d) not in ("done",) for d in deps):
                # Dépendances pas encore terminées → on attend
                continue

        # ── Contexte des étapes précédentes ───────────────────
        context = ""
        for dep_id in deps:
            if dep_id in plan_results:
                dep_status = _get_step_status(plan, dep_id)
                if dep_status == "done":
                    dep_text = _extract_clean_text(plan_results[dep_id])
                    context += f"Résultat de l'étape {dep_id} : {dep_text}\n"

        full_task = f"{context}{task}"

        # ── Évaluation de la condition (steps conditionnels) ──
        if deps and context:
            condition_met = await _check_condition(task, context)
            if not condition_met:
                print(f"   ⏭️  {step_id} ({agent}) — condition non remplie → ignoré")
                step["status"] = "skipped"
                plan_results[step_id] = json.dumps({
                    "response": "",
                    "react_steps": []
                }, ensure_ascii=False)
                await _emit(queue, {
                    "type": "step_skipped",
                    "step_id": step_id,
                    "agent": agent,
                })
                continue

        # ── Guard Google Calendar : token requis ─────────────
        if agent == "calendar":
            token_ok, reason = await _check_google_token(user_id)
            if not token_ok:
                if reason == "not_connected":
                    friendly = (
                        "⚠️ Votre compte Google Calendar n'est pas encore connecté.\n\n"
                        "Rendez-vous dans **Paramètres → Google Calendar** et cliquez sur "
                        "**Connecter Google Calendar** pour autoriser l'assistant à accéder à votre agenda."
                    )
                else:
                    friendly = (
                        "⚠️ La connexion Google Calendar a expiré ou a été révoquée.\n\n"
                        "Rendez-vous dans **Paramètres → Google Calendar** et cliquez sur "
                        "**Reconnecter** pour renouveler l'accès."
                    )
                print(f"   🔒 {step_id} (calendar) — token Google absent ({reason}), step ignoré")
                await _emit(queue, {
                    "type": "step_unavailable",
                    "step_id": step_id,
                    "agent": agent,
                    "text": friendly,
                })
                step["status"] = "unavailable"
                plan_results[step_id] = json.dumps(
                    {"response": friendly, "react_steps": []}, ensure_ascii=False
                )
                continue

        # ── Agent "chat" (traitement local) ───────────────────
        if agent == "chat":
            print(f"   💬 {step_id} (chat) — traitement local")
            await _emit(queue, {
                "type": "step_start",
                "step_id": step_id,
                "agent": agent,
                "text": "💬 Je formule une réponse...",
            })
            response = _handle_chat(full_task, today_iso)
            plan_results[step_id] = json.dumps({"response": response, "react_steps": []}, ensure_ascii=False)
            step["status"] = "done"
            await _emit(queue, {
                "type": "step_done",
                "step_id": step_id,
                "agent": agent,
                "result": response,
            })
            continue

        # ── Emit step_start ───────────────────────────────────
        print(f"   🚀 {step_id} ({agent}) — appel agent...")
        await _emit(queue, {
            "type": "step_start",
            "step_id": step_id,
            "agent": agent,
            "text": _step_start_msg(agent, full_task),
        })

        # ── Appel de l'agent A2A ───────────────────────────────
        try:
            response, needs_input = await _call_agent(
                agent, full_task, user_id, role, today_iso, history,
                step_id=step_id, queue=queue,
            )

            if needs_input:
                print(f"   ❓ {step_id} ({agent}) — input requis")
                result_text = _extract_clean_text(response)
                ui_hint_data = None
                try:
                    parsed = json.loads(response)
                    ui_hint_data = parsed.get("ui_hint")
                except Exception:
                    pass
                await _emit(queue, {
                    "type": "needs_input",
                    "step_id": step_id,
                    "agent": agent,
                    "text": result_text,
                    "ui_hint": ui_hint_data,
                })
                step["status"] = "waiting_input"
                return {
                    **state,
                    "plan": plan,
                    "plan_results": plan_results,
                    "waiting_step": step_id,
                    "final_response": response
                }

            print(f"   ✅ {step_id} ({agent}) — succès")
            result_text = _extract_clean_text(response)
            await _emit(queue, {
                "type": "step_done",
                "step_id": step_id,
                "agent": agent,
                "result": result_text,
            })
            plan_results[step_id] = response
            step["status"] = "done"

        except AgentUnavailableError:
            # Agent non disponible → message de fallback, on continue les autres étapes
            agent_display = AGENT_DISPLAY_NAMES.get(agent, agent.upper())
            friendly = f"La fonctionnalité **{agent_display}** n'est pas encore disponible dans notre système."
            print(f"   ⚠️  {step_id} ({agent}) — non disponible (fallback)")
            await _emit(queue, {
                "type": "step_unavailable",
                "step_id": step_id,
                "agent": agent,
                "text": friendly,
            })
            step["status"] = "unavailable"
            plan_results[step_id] = json.dumps({
                "response": friendly,
                "react_steps": []
            }, ensure_ascii=False)
            # On NE fait PAS return → on continue les étapes suivantes indépendantes

        except Exception as e:
            # Vraie erreur technique → on continue quand même
            error_msg = f"Une erreur est survenue lors de l'étape {step_id} ({agent}) : {str(e)}"
            print(f"   ❌ {step_id} ({agent}) — erreur : {e}")
            await _emit(queue, {
                "type": "step_done",  # still done but with error
                "step_id": step_id,
                "agent": agent,
                "result": error_msg,
            })
            step["status"] = "failed"
            plan_results[step_id] = json.dumps({
                "response": error_msg,
                "react_steps": []
            }, ensure_ascii=False)

    print(f"{'='*60}\n")

    # ── Assemblage de la réponse finale ───────────────────────
    final_parts = []
    for step in plan:
        step_id     = step["step_id"]
        step_status = step["status"]
        result_raw  = plan_results.get(step_id, "")

        # Extraire le texte lisible
        result_text = _extract_clean_text(result_raw)

        if step_status == "done" and result_text:
            final_parts.append(result_text)
        elif step_status == "unavailable" and result_text:
            final_parts.append(result_text)
        elif step_status == "failed" and result_text:
            final_parts.append(result_text)
        elif step_status == "skipped":
            # On n'affiche pas les étapes ignorées pour ne pas polluer la réponse
            pass

    final_response = "\n\n".join(final_parts) if final_parts else "Je n'ai pas pu traiter votre demande."
    last_agent = plan[-1]["agent"] if plan else None

    return {
        **state,
        "final_response": final_response,
        "plan": None,
        "plan_results": None,
        "waiting_step": None,
        "last_agent": last_agent
    }
