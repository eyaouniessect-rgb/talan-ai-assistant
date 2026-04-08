# utils/streaming.py
# ═══════════════════════════════════════════════════════════
# Utilitaires partagés pour le streaming A2A entre agents.
# Centralise : _enqueue_final, tool_to_human_text (rh + calendar)
# ═══════════════════════════════════════════════════════════

from a2a.server.events import EventQueue
from a2a.types import TaskStatusUpdateEvent, TaskStatus, TaskState
from a2a.utils import new_agent_text_message


# ══════════════════════════════════════════════════════
# Envoi de l'événement final A2A
# ══════════════════════════════════════════════════════

async def enqueue_final(
    event_queue: EventQueue,
    text: str,
    task_id: str,
    context_id: str,
) -> None:
    """
    Envoie toujours un TaskStatusUpdateEvent(final=True).
    Le protocole A2A streaming exige ce format pour clore le flux,
    qu'un outil ait été appelé ou non.
    """
    msg = new_agent_text_message(text, context_id=context_id, task_id=task_id)
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.completed, message=msg),
        final=True,
    ))


async def enqueue_working(
    event_queue: EventQueue,
    text: str,
    task_id: str,
    context_id: str,
) -> None:
    """Envoie un événement de progression (tool call en cours)."""
    msg = new_agent_text_message(text, context_id=context_id, task_id=task_id)
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=TaskStatus(state=TaskState.working, message=msg),
        final=False,
    ))


# ══════════════════════════════════════════════════════
# Conversion outil → texte lisible (RH agent)
# ══════════════════════════════════════════════════════

def rh_tool_to_human_text(tool_name: str, args: dict) -> str:
    """Convertit un appel d'outil RH en texte lisible pour l'utilisateur."""
    mapping = {
        "check_leave_balance":          "💰 Vérification du solde de congés...",
        "get_my_leaves":                "📋 Récupération de vos congés...",
        "create_leave":                 f"📝 Création du congé du {args.get('start_date')} au {args.get('end_date')}...",
        "delete_leave":                 f"🗑️ Annulation du congé{' du ' + args.get('start_date') if args.get('start_date') else ''}...",
        "notify_manager":               "📢 Notification du manager...",
        "get_team_availability":        "👥 Vérification de la disponibilité de l'équipe...",
        "get_team_availability_by_name": f"👥 Vérification de la disponibilité de l'équipe « {args.get('team_name', '')} »...",
        "get_team_stack":               "💼 Récupération des compétences de l'équipe...",
        "check_calendar_conflicts":     f"🔍 Vérification du calendrier du {args.get('start_date')} au {args.get('end_date')}...",
        # Outils manager RH
        "get_leaves_by_filter":         "🔎 Recherche des demandes de congé selon les filtres...",
        "approve_leave_request":        f"✅ Approbation du congé de « {args.get('employee_name', '')} »...",
        "reject_leave_request":         f"❌ Refus du congé de « {args.get('employee_name', '')} »...",
        "update_employee_info":         f"✏️ Mise à jour du profil de « {args.get('employee_name', '')} »...",
        "get_all_leaves":               "📋 Récupération de tous les congés...",
        "create_user_account":          f"👤 Création du compte de « {args.get('name', '')} »...",
        "deactivate_user":              f"🚫 Désactivation du compte de « {args.get('employee_name', '')} »...",
    }
    return mapping.get(tool_name, f"⚙️ {tool_name}...")


# ══════════════════════════════════════════════════════
# Conversion outil → texte lisible (Calendar agent)
# ══════════════════════════════════════════════════════

def calendar_tool_to_human_text(tool_name: str, args: dict) -> str:
    """Convertit un appel d'outil Calendar en texte lisible pour l'utilisateur."""
    match tool_name:
        case "get_calendar_events":
            start = args.get("start_date", "")[:10]
            end   = args.get("end_date", "")[:10]
            if start == end:
                return f"📅 Consultation des événements du {start}..."
            return f"📅 Consultation des événements du {start} au {end}..."
        case "check_calendar_conflicts":
            start = args.get("start_date", "")[:10]
            end   = args.get("end_date", "")[:10]
            return f"🔍 Vérification des disponibilités du {start} au {end}..."
        case "search_meetings":
            return f"🔎 Recherche d'événements : « {args.get('query', '')} »..."
        case "create_meeting":
            title   = args.get("title", "Sans titre")
            date    = args.get("start_date", "")
            start_t = args.get("start_time", "")
            return f"➕ Création de l'événement « {title} » le {date} à {start_t}..."
        case "update_meeting":
            parts = []
            if args.get("title"):
                parts.append(f"titre → « {args['title']} »")
            if args.get("start_time"):
                parts.append(f"heure → {args.get('start_time')}–{args.get('end_time', '?')}")
            detail = ", ".join(parts) if parts else "événement"
            return f"✏️ Modification de l'événement ({detail})..."
        case "delete_meeting":
            return f"🗑️ Suppression de l'événement « {args.get('title', '')} »..."
        case "lookup_user_by_name":
            return f"🔍 Recherche de l'email de « {args.get('name', '')} »..."
        case _:
            return f"⚙️ {tool_name}..."
