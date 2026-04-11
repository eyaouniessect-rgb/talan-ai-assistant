# app/orchestrator/nodes/node3_executor.py
# ═══════════════════════════════════════════════════════════
# Node 3 — Executor
#
# Responsabilités :
#   - Exécute chaque step du plan généré par node1 en appelant les agents A2A
#   - Gère le streaming SSE via ContextVar (_stream_queue)
#   - Traite les réponses "needs_input" (human-in-the-loop)
#   - Gère les dépendances entre steps (depends_on)
#   - Évalue les conditions (steps conditionnels : "si X, fais Y")
#   - Guard Google Calendar : vérifie le token avant d'appeler l'agent
#   - Assemble la réponse finale depuis les résultats de tous les steps
#
# Utilitaires importés depuis orchestrator/utils/ :
#   - _extract_clean_text   : extrait le texte d'une réponse JSON agent
#   - _build_history        : formate l'historique pour le contexte A2A
#   - AGENT_DISPLAY_NAMES   : noms affichables dans les messages de fallback
#   - _check_google_token   : vérifie le token Google Calendar avant appel
# ═══════════════════════════════════════════════════════════

import asyncio
import json
import contextvars
from datetime import date

from app.orchestrator.state import AssistantState, PlanStep
from app.a2a.client import send_task_to_url
from app.a2a.discovery import discovery
from langsmith import traceable

from app.orchestrator.utils import (
    _extract_clean_text,
    _build_history,
    AGENT_DISPLAY_NAMES,
    _check_google_token,
)

# ─────────────────────────────────────────────
# Paramètres de l'historique
# ─────────────────────────────────────────────

MAX_HISTORY = 10   # Nombre de messages conservés pour le contexte A2A


# ─────────────────────────────────────────────
# ContextVar pour la queue SSE (streaming)
# ─────────────────────────────────────────────
# Permet de récupérer la queue sans la passer en paramètre dans tout l'arbre d'appel.
# Initialisée dans le endpoint /chat/stream avant l'invocation du graph.

_stream_queue: contextvars.ContextVar = contextvars.ContextVar('_stream_queue', default=None)


# ─────────────────────────────────────────────
# Émission d'événements SSE
# ─────────────────────────────────────────────

async def _emit(queue, event: dict):
    """Envoie un événement dans la queue SSE si le streaming est actif."""
    if queue is not None:
        await queue.put(event)
        print(f"   [STREAM] {event.get('type')} | step={event.get('step_id','')} agent={event.get('agent','')}")


# ─────────────────────────────────────────────
# Réponses déterministes pour l'agent "chat"
# ─────────────────────────────────────────────
# Traitement local sans appel LLM pour les messages de salutation/politesse.

_MERCI_KEYWORDS = {
    "merci", "ok merci", "super merci", "merci beaucoup",
    "parfait", "super", "nickel", "très bien", "d'accord",
    "ok d'accord", "c'est bon", "c bon",
}

_SALUTATION_KEYWORDS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou", "bonne journée",
}

_AU_REVOIR_KEYWORDS = {
    "au revoir", "aurevoir", "bonne journée", "bonne journee",
    "à bientôt", "a bientot", "bonne soirée", "bonne soiree",
    "bye", "ciao", "tchao",
}

_DATE_KEYWORDS = {
    "date", "aujourd'hui", "quel jour", "quelle date",
    "c'est quoi la date", "la date aujourd'hui", "date du jour",
}

_PRESENTATION = (
    "Bonjour ! Je suis Talan Assistant chez Talan Tunisie.\n"
    "Je peux vous aider avec vos congés, projets, tickets Jira, "
    "messages Slack, calendrier et recherche documentaire.\n"
    "Comment puis-je vous aider ?"
)

# Mots-clés pour générer des messages de démarrage d'étape contextuels
_CONDITION_KEYWORDS = ["si ", "if ", "seulement si", "only if", "lorsque ", "dans le cas où"]


# ─────────────────────────────────────────────
# Erreur agent non disponible
# ─────────────────────────────────────────────

class AgentUnavailableError(Exception):
    """Levée quand un agent n'est pas découvert (pas démarré / pas encore développé)."""
    pass


# ──────────────────────────────────────────────────────────
# MESSAGE DE DÉMARRAGE D'ÉTAPE (contextualisé par agent)
# ──────────────────────────────────────────────────────────

def _step_start_msg(agent: str, task: str) -> str:
    """
    Génère un message de progression naturel pour l'UI selon l'agent et la tâche.
    Affiché dans le frontend pendant que l'agent traite la demande (streaming).
    """
    t = task.lower()

    # ── Agent RH ──────────────────────────────────────────
    if agent == "rh":
        if any(k in t for k in ["solde", "reste", "combien"]):
            return "Je verifie votre solde de conges..."
        if any(k in t for k in ["poser", "créer", "creer", "pose un", "créer un", "creer un"]):
            return "Je cree votre demande de conge..."
        if any(k in t for k in ["supprimer", "annuler", "retirer"]):
            return "J'annule votre conge..."
        return "Je traite votre demande RH..."

    # ── Agent Calendar ────────────────────────────────────
    if agent == "calendar":
        # Vérifier annuler/supprimer EN PREMIER (évite le match sur "réunion" dans "annuler cette réunion")
        if any(k in t for k in ["annuler", "supprimer", "cancel"]):
            return "J'annule votre reunion..."
        if any(k in t for k in ["modifier", "déplacer", "decaler", "reporter"]):
            return "Je modifie votre reunion..."
        if any(k in t for k in ["rétabli", "retabli", "ancienne", "restau"]):
            return "Je retablis votre reunion..."
        if any(k in t for k in ["disponib", "vérifi", "verifie"]):
            return "Je verifie les disponibilites..."
        if any(k in t for k in ["créer", "creer", "planifier", "réunion", "reunion", "meeting"]):
            return "Je cree votre reunion dans le calendrier..."
        return "Je consulte votre calendrier..."

    # ── Autres agents ─────────────────────────────────────
    if agent == "jira":
        return "Je consulte vos tickets Jira..."
    if agent == "slack":
        return "J'envoie votre message Slack..."
    if agent == "crm":
        return "Je consulte les donnees CRM..."
    return f"Je traite votre demande ({agent})..."


# ──────────────────────────────────────────────────────────
# RÉPONSES LOCALES POUR L'AGENT "CHAT"
# ──────────────────────────────────────────────────────────

def _handle_chat(task: str, today_iso: str) -> str:
    """
    Gère les réponses déterministes pour l'agent 'chat' sans appel LLM.
    Couvre : remerciements, salutations, au revoir, question de date, inconnu.
    """
    last_clean = task.lower().strip().rstrip("!?.,:;")
    last_clean = " ".join(last_clean.split())

    if last_clean in _MERCI_KEYWORDS:
        return "De rien ! N'hesitez pas si vous avez besoin d'autre chose."
    if last_clean in _SALUTATION_KEYWORDS:
        return _PRESENTATION
    if last_clean in _AU_REVOIR_KEYWORDS:
        return "Au revoir ! Bonne continuation."
    if any(kw in last_clean for kw in _DATE_KEYWORDS):
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


# ──────────────────────────────────────────────────────────
# UTILITAIRES DE PLAN
# ──────────────────────────────────────────────────────────

def _get_step_status(plan: list, step_id: str) -> str:
    """Retourne le statut d'une étape par son ID, ou 'unknown' si introuvable."""
    for s in plan:
        if s["step_id"] == step_id:
            return s["status"]
    return "unknown"


# ──────────────────────────────────────────────────────────
# ÉVALUATION DE CONDITIONS (steps conditionnels)
# ──────────────────────────────────────────────────────────

async def _check_condition(task: str, context: str) -> bool:
    """
    Évalue si la condition d'un step conditionnel est remplie d'après le contexte.
    Retourne True → exécuter le step | False → ignorer.

    N'appelle le LLM que si :
      - La tâche contient un mot-clé conditionnel ("si ", "seulement si", etc.)
      - ET un contexte est disponible (résultat d'une étape précédente)
    Sinon retourne True par défaut (pas de condition → toujours exécuter).
    """
    task_lower = task.lower()
    if not any(kw in task_lower for kw in _CONDITION_KEYWORDS):
        return True  # Pas de condition → toujours exécuter
    if not context.strip():
        return True  # Pas de contexte → impossible d'évaluer → exécuter

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
        print(f"   Evaluation condition → '{result}' pour : {task[:80]}")
        return "oui" in result
    except Exception as e:
        print(f"   Evaluation condition echouee ({e}) → execution par defaut")
        return True  # En cas d'erreur → exécuter par défaut (fail-open)


# ──────────────────────────────────────────────────────────
# APPEL D'UN AGENT A2A
# ──────────────────────────────────────────────────────────

async def _call_agent(
    agent_name: str,
    task: str,
    user_id: int,
    role: str,
    today_iso: str,
    history: str = "",
    step_id: str = None,
    queue=None,
) -> tuple[str, bool]:
    """
    Appelle un agent via le protocole A2A (HTTP).
    Retourne (response_text, needs_input).

    Modes :
      - Streaming (SSE) : si l'agent le supporte ET que queue est actif
        → émet des événements step_progress pendant l'exécution
      - Classique (HTTP) : sinon → attend la réponse complète

    Lève AgentUnavailableError si l'agent n'est pas découvert (pas démarré).
    """
    discovered = await discovery.find_agent_by_name(agent_name)
    if not discovered:
        raise AgentUnavailableError(f"Agent '{agent_name}' non trouvé")

    # ── Construction du message A2A ───────────────────────
    history_section = f"Historique de la conversation :\n{history}\n---\n" if history else ""
    message = (
        f"Date du jour : {today_iso}\n---\n"
        f"{history_section}"
        f"INSTRUCTION À EXÉCUTER :\n{task}\n---\n"
        f"Role utilisateur : {role}\nUser ID : {user_id}"
    )

    print(f"      [A2A] Appel agent='{agent_name}' streaming={discovered.supports_streaming}")

    # ── Mode streaming ────────────────────────────────────
    if discovered.supports_streaming and queue is not None:
        from app.a2a.client import send_task_to_url_streaming
        final_text = ""
        async for evt_type, evt_text in send_task_to_url_streaming(discovered.url, message):
            if evt_type == "status" and step_id is not None:
                # Ignorer les réponses JSON finales (ce sont les résultats, pas la progression)
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
            final_text = evt_text  # La dernière valeur = texte final de l'agent
        response = final_text or "L'agent n'a pas retourné de réponse."

    # ── Mode classique ────────────────────────────────────
    else:
        response = await send_task_to_url(discovered.url, message)

    # ── Détection needs_input ─────────────────────────────
    try:
        parsed = json.loads(response)
        if parsed.get("needs_input"):
            return response, True
    except Exception:
        pass
    return response, False


# ══════════════════════════════════════════════════════════
# NODE 3 — FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════

@traceable(name="node3_executor", tags=["orchestrator"])
async def node3_executor(state: AssistantState) -> AssistantState:
    """
    Exécuteur de plan :
      1. Reprend après question si waiting_step est défini
      2. Exécute chaque step en respectant les dépendances
      3. Gère les guards (Google token), conditions, unavailability
      4. Assemble la réponse finale depuis les résultats des steps
    """
    plan = state.get("plan")
    if not plan:
        return {**state, "final_response": "Aucun plan généré. Veuillez reformuler."}

    # ── Queue SSE depuis le ContextVar ────────────────────
    queue = _stream_queue.get()

    plan_results = state.get("plan_results") or {}
    waiting_step = state.get("waiting_step")

    # ── Reprise après question de l'agent ─────────────────
    if waiting_step:
        last_user_msg = state["messages"][-1].content
        for step in plan:
            if step["step_id"] == waiting_step:
                step["task"] = f"{step['task']}\nRéponse utilisateur : {last_user_msg}"
                step["status"] = "pending"
                break
        waiting_step = None

    # ── Contexte commun pour tous les appels A2A ──────────
    user_id = state["user_id"]
    role = state["role"]
    _today = date.today()
    _JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    today_iso = f"{_today.strftime('%Y-%m-%d')} ({_JOURS[_today.weekday()]})"

    all_messages = state["messages"]
    trimmed = all_messages[-MAX_HISTORY:] if len(all_messages) > MAX_HISTORY else all_messages
    history = _build_history(trimmed)

    print(f"\n{'='*60}")
    print(f"NODE 3 — EXECUTOR ({len(plan)} etape(s)) | streaming={'oui' if queue else 'non'}")
    print(f"{'='*60}")

    # ══════════════════════════════════════════════════════
    # BOUCLE D'EXÉCUTION DES STEPS
    # ══════════════════════════════════════════════════════
    for step in plan:
        step_id = step["step_id"]
        agent   = step["agent"]
        task    = step["task"]
        deps    = step.get("depends_on", [])

        # ── Skip les steps déjà traités ───────────────────
        if step["status"] in ("done", "failed", "unavailable", "skipped"):
            continue
        if step["status"] == "waiting_input":
            continue

        # ╔══════════════════════════════════════════════╗
        # ║  VÉRIFICATION DES DÉPENDANCES               ║
        # ╚══════════════════════════════════════════════╝
        if deps:
            blocked_deps = [
                d for d in deps
                if _get_step_status(plan, d) in ("failed", "unavailable", "skipped")
            ]
            if blocked_deps:
                # Dépendance bloquée → ignorer ce step proprement
                agent_display = AGENT_DISPLAY_NAMES.get(agent, agent.upper())
                print(f"   {step_id} ({agent}) — ignore (dependance bloquee : {blocked_deps})")
                step["status"] = "skipped"
                plan_results[step_id] = json.dumps({
                    "response": f"L'étape **{agent_display}** a été ignorée car une étape précédente n'est pas disponible.",
                    "react_steps": []
                }, ensure_ascii=False)
                await _emit(queue, {"type": "step_skipped", "step_id": step_id, "agent": agent})
                continue

            if any(_get_step_status(plan, d) not in ("done",) for d in deps):
                # Dépendances pas encore terminées → attendre
                continue

        # ╔══════════════════════════════════════════════╗
        # ║  CONTEXTE DES ÉTAPES PRÉCÉDENTES            ║
        # ╚══════════════════════════════════════════════╝
        context = ""
        for dep_id in deps:
            if dep_id in plan_results:
                if _get_step_status(plan, dep_id) == "done":
                    dep_text = _extract_clean_text(plan_results[dep_id])
                    context += f"Résultat de l'étape {dep_id} : {dep_text}\n"

        full_task = f"{context}{task}"

        # ╔══════════════════════════════════════════════╗
        # ║  ÉVALUATION DE CONDITION (steps conditionnels)║
        # ╚══════════════════════════════════════════════╝
        if deps and context:
            condition_met = await _check_condition(task, context)
            if not condition_met:
                print(f"   {step_id} ({agent}) — condition non remplie → ignore")
                step["status"] = "skipped"
                plan_results[step_id] = json.dumps({"response": "", "react_steps": []}, ensure_ascii=False)
                await _emit(queue, {"type": "step_skipped", "step_id": step_id, "agent": agent})
                continue

        # ╔══════════════════════════════════════════════╗
        # ║  GUARD GOOGLE CALENDAR                      ║
        # ║  Vérifie le token avant d'appeler l'agent   ║
        # ╚══════════════════════════════════════════════╝
        if agent == "calendar":
            token_ok, reason = await _check_google_token(user_id)
            if not token_ok:
                if reason == "not_connected":
                    friendly = (
                        "Votre compte Google Calendar n'est pas encore connecté.\n\n"
                        "Rendez-vous dans **Paramètres → Google Calendar** et cliquez sur "
                        "**Connecter Google Calendar** pour autoriser l'assistant à accéder à votre agenda."
                    )
                else:
                    friendly = (
                        "La connexion Google Calendar a expiré ou a été révoquée.\n\n"
                        "Rendez-vous dans **Paramètres → Google Calendar** et cliquez sur "
                        "**Reconnecter** pour renouveler l'accès."
                    )
                print(f"   {step_id} (calendar) — token Google absent ({reason})")
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

        # ╔══════════════════════════════════════════════╗
        # ║  AGENT "CHAT" — Traitement local            ║
        # ║  (sans appel A2A — réponses déterministes)  ║
        # ╚══════════════════════════════════════════════╝
        if agent == "chat":
            print(f"   {step_id} (chat) — traitement local")
            await _emit(queue, {
                "type": "step_start",
                "step_id": step_id,
                "agent": agent,
                "text": "Je formule une reponse...",
            })
            response = _handle_chat(full_task, today_iso)
            plan_results[step_id] = json.dumps(
                {"response": response, "react_steps": []}, ensure_ascii=False
            )
            step["status"] = "done"
            await _emit(queue, {
                "type": "step_done",
                "step_id": step_id,
                "agent": agent,
                "result": response,
            })
            continue

        # ╔══════════════════════════════════════════════╗
        # ║  APPEL AGENT A2A                            ║
        # ╚══════════════════════════════════════════════╝
        print(f"   {step_id} ({agent}) — appel agent...")
        await _emit(queue, {
            "type": "step_start",
            "step_id": step_id,
            "agent": agent,
            "text": _step_start_msg(agent, full_task),
        })

        try:
            response, needs_input = await _call_agent(
                agent, full_task, user_id, role, today_iso, history,
                step_id=step_id, queue=queue,
            )

            # ── Human-in-the-loop : l'agent pose une question ─
            if needs_input:
                print(f"   {step_id} ({agent}) — input requis")
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
                    "final_response": response,
                }

            # ── Succès ────────────────────────────────────────
            print(f"   {step_id} ({agent}) — succes")
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
            # Agent non démarré / pas encore développé → message de fallback, on continue
            agent_display = AGENT_DISPLAY_NAMES.get(agent, agent.upper())
            friendly = f"La fonctionnalité **{agent_display}** n'est pas encore disponible dans notre système."
            print(f"   {step_id} ({agent}) — non disponible (fallback)")
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
            # On continue les autres étapes indépendantes

        except Exception as e:
            # Erreur technique inattendue → on continue quand même
            error_msg = f"Une erreur est survenue lors de l'étape {step_id} ({agent}) : {str(e)}"
            print(f"   {step_id} ({agent}) — erreur : {e}")
            await _emit(queue, {
                "type": "step_done",
                "step_id": step_id,
                "agent": agent,
                "result": error_msg,
            })
            step["status"] = "failed"
            plan_results[step_id] = json.dumps(
                {"response": error_msg, "react_steps": []}, ensure_ascii=False
            )

    print(f"{'='*60}\n")

    # ══════════════════════════════════════════════════════
    # ASSEMBLAGE DE LA RÉPONSE FINALE
    # ══════════════════════════════════════════════════════
    # Concatène les résultats de tous les steps terminés (done, unavailable, failed).
    # Les steps ignorés (skipped) ne sont pas inclus pour ne pas polluer la réponse.

    final_parts = []
    for step in plan:
        step_id     = step["step_id"]
        step_status = step["status"]
        result_raw  = plan_results.get(step_id, "")
        result_text = _extract_clean_text(result_raw)

        if step_status in ("done", "unavailable", "failed") and result_text:
            final_parts.append(result_text)
        # step_status == "skipped" → pas ajouté (étape conditionnelle non exécutée)

    final_response = "\n\n".join(final_parts) if final_parts else "Je n'ai pas pu traiter votre demande."
    last_agent = plan[-1]["agent"] if plan else None

    return {
        **state,
        "final_response": final_response,
        "plan": None,
        "plan_results": None,
        "waiting_step": None,
        "last_agent": last_agent,
    }
