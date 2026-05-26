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

import os
import httpx
from agents.slack.mcp_client import call_mcp

# Token Slack pour les appels directs (le MCP officiel n'expose pas reactions.remove,
# on appelle donc Slack en direct pour cette opération).
_SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")


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

        # Normaliser les alias emoji Slack (+1 == thumbsup, -1 == thumbsdown).
        # On agrège count ET la liste des user_ids qui ont réagi pour permettre
        # au LLM de savoir QUI a posé chaque réaction.
        _EMOJI_ALIASES = {"+1": "thumbsup", "-1": "thumbsdown"}
        reactions_map: dict[str, dict] = {}
        for r in msg.get("reactions", []):
            name = r.get("name")
            if not name:
                continue
            canonical = _EMOJI_ALIASES.get(name, name)
            entry = reactions_map.setdefault(canonical, {"count": 0, "users": []})
            entry["count"] += r.get("count", 0)
            entry["users"].extend(r.get("users", []))

        # Résoudre les user_ids en noms lisibles via user_map déjà chargé
        reactions_list = []
        for emoji_name, info in reactions_map.items():
            user_names = []
            for uid in info["users"]:
                if uid in user_map:
                    user_names.append(user_map[uid]["name"])
                else:
                    user_names.append(uid)
            reactions_list.append({
                "name": emoji_name,
                "count": info["count"],
                "reacted_by": user_names,
            })

        enriched.append({
            "author_name": author_name,
            "author_type": "bot" if is_from_bot else "user",
            "text":        text,
            "ts":          ts,
            "reactions":   reactions_list,
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


async def search_messages(query: str, count: int = 10) -> dict:
    """
    Recherche des messages dans Slack par mot-clé.
    Parcourt l'historique des channels disponibles et filtre côté Python.
    """
    query_lower = query.lower()

    # Récupérer la liste des channels
    channels_data = await call_mcp("slack_list_channels", {"limit": 50})
    channels = channels_data.get("channels", [])
    if not channels:
        return {"ok": False, "error": "Impossible de récupérer les channels"}

    # Récupérer un seul appel slack_get_users pour résoudre les noms
    user_map: dict[str, str] = {}
    try:
        users_data = await call_mcp("slack_get_users", {})
        members = users_data.get("members") or users_data.get("users") or []
        for m in members:
            uid = m.get("id", "")
            profile = m.get("profile", {})
            name = (
                profile.get("real_name") or profile.get("display_name")
                or m.get("real_name") or m.get("name") or uid
            )
            user_map[uid] = name
    except Exception:
        pass

    results = []
    skipped_channels = []
    for ch in channels:
        if len(results) >= count:
            break
        ch_id = ch.get("id")
        ch_name = ch.get("name", ch_id)
        if not ch_id:
            continue
        try:
            hist = await call_mcp("slack_get_channel_history", {"channel_id": ch_id, "limit": 100})
            for msg in hist.get("messages", []):
                text = msg.get("text", "")
                if query_lower in text.lower():
                    uid      = msg.get("user", "")
                    bot_id   = msg.get("bot_id", "")
                    username = msg.get("username", "")
                    if uid and uid in user_map:
                        author = user_map[uid]
                    elif bot_id:
                        author = username or "Talan Assistant"
                    else:
                        author = uid or "Inconnu"
                    results.append({
                        "channel": ch_name,
                        "channel_id": ch_id,
                        "author": author,
                        "text": text.replace("\\n", "\n").strip(),
                        "ts": msg.get("ts", ""),
                    })
                    if len(results) >= count:
                        break
        except Exception:
            skipped_channels.append(ch_name)
            continue

    response = {"ok": True, "messages": results, "total": len(results)}
    if skipped_channels:
        response["warning"] = f"Channels inaccessibles (bot non invité) : {', '.join(skipped_channels[:5])}"
    return response


async def add_reaction(channel: str, timestamp: str, reaction: str) -> dict:
    """Ajoute un emoji réaction à un message Slack."""
    return await call_mcp("slack_add_reaction", {
        "channel_id": channel,
        "timestamp": timestamp,
        "reaction": reaction,
    })


async def _slack_api_call(method: str, payload: dict) -> dict:
    """
    Appelle directement l'API Slack (utilisé pour reactions.remove qui n'est pas
    exposé par le MCP officiel).
    """
    if not _SLACK_BOT_TOKEN:
        return {"ok": False, "error": "SLACK_BOT_TOKEN absent de l'environnement"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"https://slack.com/api/{method}",
            headers={
                "Authorization": f"Bearer {_SLACK_BOT_TOKEN}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=payload,
        )
        try:
            return r.json()
        except Exception:
            return {"ok": False, "error": f"réponse non-JSON: {r.text[:200]}"}


async def remove_reaction(channel: str, timestamp: str, reaction: str) -> dict:
    """
    Retire un emoji réaction d'un message Slack.
    Appelle directement Slack (pas via MCP) car le MCP officiel
    @modelcontextprotocol/server-slack n'expose pas reactions.remove.
    Retente avec l'alias si Slack répond 'no_reaction' (ex: 'thumbsup' ↔ '+1').
    """
    _REVERSE_ALIASES = {
        "thumbsup": "+1", "+1": "thumbsup",
        "thumbsdown": "-1", "-1": "thumbsdown",
    }

    result = await _slack_api_call("reactions.remove", {
        "channel": channel,
        "timestamp": timestamp,
        "name": reaction,
    })

    # Si la réaction n'est pas trouvée et qu'un alias existe, retente avec l'alias.
    if isinstance(result, dict) and not result.get("ok"):
        err = (result.get("error") or "").lower()
        if "no_reaction" in err and reaction in _REVERSE_ALIASES:
            alias = _REVERSE_ALIASES[reaction]
            result = await _slack_api_call("reactions.remove", {
                "channel": channel,
                "timestamp": timestamp,
                "name": alias,
            })

    return result


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
