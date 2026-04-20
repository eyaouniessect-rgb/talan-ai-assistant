# agents/slack/tools.py
# ═══════════════════════════════════════════════════════════
# Outils Slack — appellent le MCP Server local (@modelcontextprotocol/server-slack)
#
# Noms d'outils exacts du package :
#   slack_post_message       → envoyer un message
#   slack_reply_to_thread    → répondre dans un thread
#   slack_get_channel_history → lire les messages d'un channel
#   slack_get_thread_replies  → lire les réponses d'un thread
#   slack_list_channels      → lister les channels
#   slack_get_users          → lister tous les utilisateurs
#   slack_get_user_profile   → profil d'un utilisateur par son ID
# ═══════════════════════════════════════════════════════════

from agents.slack.mcp_client import call_mcp


async def send_message(channel: str, text: str) -> dict:
    """Envoie un message dans un channel ou DM (channel = ID channel ou user_id)."""
    return await call_mcp("slack_post_message", {
        "channel_id": channel,
        "text": text,
    })


async def reply_to_thread(channel: str, thread_ts: str, text: str) -> dict:
    """Répond dans un thread Slack existant."""
    return await call_mcp("slack_reply_to_thread", {
        "channel_id": channel,
        "thread_ts": thread_ts,
        "text": text,
    })


async def read_channel(channel: str, limit: int = 20) -> dict:
    """
    Récupère les N derniers messages d'un channel.
    - Résout les IDs en noms via UN seul appel slack_get_users.
    - Stocke le flag is_bot pour distinguer humains et bots.
    - Filtre seulement les événements système des HUMAINS (channel_join/leave).
    - Conserve tous les messages de bots/apps.
    """
    data = await call_mcp("slack_get_channel_history", {
        "channel_id": channel,
        "limit": limit,
    })

    messages = data.get("messages", [])
    if not messages:
        return {"ok": True, "messages": []}

    # ── Construire la map user_id → {name, is_bot} ────────
    # UN seul appel pour tous les utilisateurs
    user_map: dict[str, dict] = {}
    try:
        users_data = await call_mcp("slack_get_users", {})
        members = users_data.get("members") or users_data.get("users") or []
        for m in members:
            uid = m.get("id", "")
            if not uid:
                continue
            profile = m.get("profile", {})
            name = (
                profile.get("real_name")
                or profile.get("display_name")
                or m.get("real_name")
                or m.get("name")
                or uid
            )
            is_bot = bool(m.get("is_bot") or m.get("is_app_user"))
            user_map[uid] = {"name": name, "is_bot": is_bot}
    except Exception:
        pass  # Fallback : IDs bruts affichés

    # ── Enrichir les messages ─────────────────────────────
    enriched = []
    for msg in messages:
        subtype  = msg.get("subtype", "")
        uid      = msg.get("user", "")
        bot_id   = msg.get("bot_id", "")
        bot_name = msg.get("username", "")
        text     = msg.get("text", "").strip()
        ts       = msg.get("ts", "")

        # ── Détecter si c'est un bot/app ──────────────────
        is_from_bot = bool(bot_id) or subtype == "bot_message"
        if uid and uid in user_map:
            is_from_bot = is_from_bot or user_map[uid]["is_bot"]

        # ── Filtrer UNIQUEMENT les événements système humains
        # (channel_join/leave d'une personne, pas d'un bot)
        if subtype in ("channel_join", "channel_leave", "channel_purpose", "channel_topic") and not is_from_bot:
            continue

        # ── Résoudre le nom de l'auteur ───────────────────
        if uid and uid in user_map:
            author_name = user_map[uid]["name"]
        elif bot_id:
            author_name = bot_name or "Talan Assistant"
        else:
            author_name = uid or "Inconnu"

        enriched.append({
            "author_name": author_name,
            "author_type": "bot" if is_from_bot else "user",
            "text":        text,
            "ts":          ts,
        })

    return {"ok": True, "messages": enriched, "total": len(enriched)}


async def get_thread_replies(channel: str, thread_ts: str) -> dict:
    """Récupère toutes les réponses d'un thread."""
    return await call_mcp("slack_get_thread_replies", {
        "channel_id": channel,
        "thread_ts": thread_ts,
    })


async def get_channel_list() -> dict:
    """Liste les channels Slack disponibles."""
    return await call_mcp("slack_list_channels", {})


async def get_all_users() -> dict:
    """Récupère la liste complète des utilisateurs du workspace."""
    return await call_mcp("slack_get_users", {})


async def get_user_profile(user_id: str) -> dict:
    """Retourne le profil d'un utilisateur par son ID Slack (U...)."""
    return await call_mcp("slack_get_user_profile", {
        "user_id": user_id,
    })


async def find_user_by_name(name: str) -> dict:
    """
    Cherche un utilisateur par son nom (prénom, nom complet).
    Appelle slack_get_users puis filtre côté Python.
    """
    data = await get_all_users()

    # Le MCP retourne soit {"members": [...]} soit {"users": [...]}
    members = data.get("members") or data.get("users") or []
    name_lower = name.lower()

    matches = []
    for m in members:
        profile = m.get("profile", {})
        real_name    = (profile.get("real_name") or m.get("real_name") or "").lower()
        display_name = (profile.get("display_name") or "").lower()
        email        = (profile.get("email") or "").lower()

        if (name_lower in real_name or
            name_lower in display_name or
            name_lower in email):
            matches.append({
                "id":           m.get("id"),
                "name":         profile.get("real_name") or m.get("real_name"),
                "display_name": profile.get("display_name"),
                "email":        profile.get("email"),
                "is_bot":       m.get("is_bot", False),
            })

    # Exclure les bots
    matches = [m for m in matches if not m.get("is_bot")]

    if not matches:
        return {"ok": False, "error": f"Aucun utilisateur trouvé pour '{name}'"}
    return {"ok": True, "users": matches}
