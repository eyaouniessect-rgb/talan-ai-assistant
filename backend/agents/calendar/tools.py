# Outils Calendar : create_event, get_events.
from agents.calendar.mcp_client import call_mcp

# ─────────────────────────────────────────
# 🛠️ HELPERS — Format RFC 3339 (Google Calendar API)
# ─────────────────────────────────────────
TUNIS_TZ = "+01:00"  # Africa/Tunis = UTC+1

def _to_rfc3339(date_str: str) -> str:
    """'YYYY-MM-DD' → 'YYYY-MM-DDT00:00:00+01:00' (début de journée)"""
    if "T" in date_str:
        if "+" not in date_str and "Z" not in date_str:
            return date_str + TUNIS_TZ
        return date_str
    return f"{date_str}T00:00:00{TUNIS_TZ}"

def _to_rfc3339_end(date_str: str) -> str:
    """'YYYY-MM-DD' → 'YYYY-MM-DDT23:59:59+01:00' (fin de journée)"""
    if "T" in date_str:
        if "+" not in date_str and "Z" not in date_str:
            return date_str + TUNIS_TZ
        return date_str
    return f"{date_str}T23:59:59{TUNIS_TZ}"


# ─────────────────────────────────────────
# 🔥 CHECK CONFLICTS (get-freebusy)
# ─────────────────────────────────────────
async def check_calendar_conflicts(start_date: str, end_date: str):
    """
    Vérifie les conflits via list-events (plus fiable que get-freebusy).
    Si des événements existent sur le créneau → conflits détectés.
    """
    data = await call_mcp(
        "list-events",
        {
            "calendarId": "primary",
            "timeMin": _to_rfc3339(start_date),
            "timeMax": _to_rfc3339_end(end_date),
        }
    )
    print(f"[check_conflicts] raw MCP response: {data}")

    events = data.get("events", data.get("result", []))

    busy = [
        {
            "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
            "end":   e.get("end",   {}).get("dateTime", e.get("end",   {}).get("date", "")),
            "title": e.get("summary", "Sans titre"),
        }
        for e in events
    ]

    return {
        "success": True,
        "conflicts": busy,
        "message": "Conflits détectés" if busy else "Aucun conflit"
    }


# ─────────────────────────────────────────
# 📅 LIST EVENTS
# ─────────────────────────────────────────
async def get_calendar_events(start_date: str, end_date: str):
    data = await call_mcp(
        "list-events",
        {
            "calendarId": "primary",
            "timeMin": _to_rfc3339(start_date),
            "timeMax": _to_rfc3339_end(end_date),
        }
    )
    events = data.get("events", data.get("result", []))
    return {"success": True, "events": events}


# ─────────────────────────────────────────
# ➕ CREATE EVENT
# ─────────────────────────────────────────
async def create_meeting(title: str, start: str, end: str, attendees: list[str] | None = None, add_meet: bool = False):
    payload = {
        "calendarId": "primary",
        "summary": title,
        "start": start,
        "end": end,
        "sendUpdates": "all",
    }
    if attendees:
        payload["attendees"] = [{"email": email} for email in attendees]
    if add_meet:
        payload["conferenceData"] = {
            "createRequest": {
                "requestId": f"meet-{title[:20].replace(' ', '-')}-{start[:10]}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        }
    print(f"[create_meeting] payload → MCP: {payload}")
    data = await call_mcp("create-event", payload)
    print(f"[create_meeting] MCP response: {data}")
    return {"success": True, "event": data}


# ─────────────────────────────────────────
# ✏️ UPDATE EVENT
# ─────────────────────────────────────────
async def update_meeting(
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    end: str | None = None,
    attendees: list[str] | None = None,
):
    payload: dict = {
        "calendarId": "primary",
        "eventId": event_id,
        "sendUpdates": "all",
    }
    if title:
        payload["summary"] = title
    if start:
        payload["start"] = start
    if end:
        payload["end"] = end
    if attendees is not None:
        # Liste complète des participants souhaités (remplace l'existante)
        payload["attendees"] = [{"email": email} for email in attendees]
    data = await call_mcp("update-event", payload)
    return {"success": True, "event": data}


# ─────────────────────────────────────────
# ❌ DELETE EVENT
# ─────────────────────────────────────────
async def delete_meeting(event_id: str):
    data = await call_mcp(
        "delete-event",
        {
            "calendarId": "primary",
            "eventId": event_id,
            "sendUpdates": "all",
        }
    )
    print(f"[delete_meeting] MCP response: {data}")
    return {"success": True, "message": "Event supprimé"}


# ─────────────────────────────────────────
# 🔍 SEARCH EVENTS
# ─────────────────────────────────────────
import unicodedata

def _strip_accents(text: str) -> str:
    """Supprime les accents pour une comparaison normalisée."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

async def search_meetings(query: str):
    """
    Recherche avec le terme original, puis avec accents normalisés si vide.
    """
    # Tentative 1 — terme exact
    data = await call_mcp("search-events", {"query": query})
    results = data.get("events", data.get("result", []))

    # Tentative 2 — si vide et le terme n'a pas d'accents, essaie les variantes accentuées françaises
    if not results:
        query_no_accent = _strip_accents(query)
        if query_no_accent != query:
            # La requête avait des accents mais rien trouvé → rien à faire de plus
            pass
        else:
            # La requête n'a PAS d'accents → essaie avec accents communs
            ACCENT_MAP = str.maketrans({
                'e': 'é', 'a': 'à', 'u': 'û', 'i': 'î', 'o': 'ô',
            })
            accented = query.translate(ACCENT_MAP)
            if accented != query:
                data2 = await call_mcp("search-events", {"query": accented})
                results = data2.get("events", data2.get("result", [])) or results

    return {"success": True, "results": results}


# ─────────────────────────────────────────
# 📄 EVENT DETAILS
# ─────────────────────────────────────────
async def get_event_details(event_id: str):
    data = await call_mcp(
        "get-event",
        {"eventId": event_id}
    )
    return {"success": True, "event": data}


# ─────────────────────────────────────────
# 👍 RESPOND EVENT
# ─────────────────────────────────────────
async def respond_to_event(event_id: str, response: str):
    data = await call_mcp(
        "respond-to-event",
        {
            "eventId": event_id,
            "response": response
        }
    )
    return {"success": True, "status": data}