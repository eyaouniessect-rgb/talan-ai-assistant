# Outils Calendar : create_event, get_events.
from datetime import date, datetime, timedelta
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
            "id":    e.get("id", ""),
            "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
            "end":   e.get("end",   {}).get("dateTime", e.get("end",   {}).get("date", "")),
            "title": e.get("summary", "Sans titre"),
        }
        for e in events  # conflits : on garde le format minimal actuel (pas besoin de plus)
    ]

    return {
        "success": True,
        "conflicts": busy,
        "message": "Conflits détectés" if busy else "Aucun conflit"
    }


def _trim_event(e: dict) -> dict:
    """
    Réduit un objet événement Google Calendar aux seuls champs utiles pour l'agent.
    Un événement complet peut dépasser 2000 tokens — on garde l'essentiel.
    """
    start = e.get("start", {})
    end   = e.get("end", {})
    return {
        "id":        e.get("id", ""),
        "summary":   e.get("summary", "Sans titre"),
        "start":     start.get("dateTime", start.get("date", "")),
        "end":       end.get("dateTime",   end.get("date", "")),
        "htmlLink":  e.get("htmlLink", ""),
        "hangoutLink": e.get("hangoutLink", ""),
        "location":  e.get("location", ""),
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
    trimmed = [_trim_event(e) for e in events]
    return {"success": True, "events": trimmed}


# ─────────────────────────────────────────
# ➕ CREATE EVENT
# ─────────────────────────────────────────
async def create_meeting(title: str, start: str, end: str, attendees: list[str] | None = None, add_meet: bool = False, location: str | None = None):
    # Reject past dates
    try:
        start_clean = start.split("T")[0] if "T" in start else start
        event_date = datetime.strptime(start_clean, "%Y-%m-%d").date()
        if event_date < date.today():
            return {
                "success": False,
                "error": f"Impossible de créer un événement dans le passé (date : {start_clean}). Veuillez choisir une date future."
            }
    except ValueError:
        pass  # Si on ne peut pas parser la date, on laisse le MCP valider

    payload = {
        "calendarId": "primary",
        "summary": title,
        "start": start,
        "end": end,
        "sendUpdates": "all",
    }
    if location:
        payload["location"] = location
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
    remove_meet: bool = False,
    location: str | None = None,
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
    if location:
        payload["location"] = location
    if attendees is not None:
        payload["attendees"] = [{"email": email} for email in attendees]
    if remove_meet:
        # Supprime le lien Google Meet sans recréer l'événement
        payload["conferenceData"] = None
        payload["conferenceDataVersion"] = 1
    data = await call_mcp("update-event", payload)
    return {"success": True, "event": data}


# ─────────────────────────────────────────
# ❌ DELETE EVENT
# ─────────────────────────────────────────
async def delete_meeting(event_id: str):
    try:
        data = await call_mcp(
            "delete-event",
            {
                "calendarId": "primary",
                "eventId": event_id,
                "sendUpdates": "all",
            }
        )
        print(f"[delete_meeting] MCP response: {data}")

        # Le MCP renvoie une erreur explicite dans le texte
        if isinstance(data, dict):
            text = data.get("text", "")
            if "403" in text or "forbidden" in text.lower() or "not the organizer" in text.lower():
                return {
                    "success": False,
                    "message": "Suppression impossible : vous n'êtes pas l'organisateur de cet événement. "
                               "Vous pouvez uniquement vous retirer de la réunion.",
                    "not_organizer": True,
                }
            if "404" in text or "not found" in text.lower():
                return {"success": False, "message": "Événement introuvable (déjà supprimé ?)."}

        # HTTP 204 = succès → data est {} ou None
        return {"success": True, "message": "Event supprimé"}

    except Exception as e:
        err = str(e)
        print(f"[delete_meeting] ERREUR: {err}")
        if "403" in err or "forbidden" in err.lower() or "organizer" in err.lower():
            return {
                "success": False,
                "message": "Suppression impossible : vous n'êtes pas l'organisateur de cet événement. "
                           "Vous pouvez uniquement vous retirer de la réunion.",
                "not_organizer": True,
            }
        return {"success": False, "message": f"Erreur lors de la suppression : {err}"}


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

def _keyword_match(event: dict, query: str) -> bool:
    """
    Vérifie si le mot-clé (ou un de ses tokens) est présent dans le titre ou la description.
    Comparaison insensible à la casse et aux accents.
    """
    q_norm = _strip_accents(query.lower())
    tokens = [t for t in q_norm.split() if len(t) >= 2]
    title = _strip_accents(event.get("summary", "").lower())
    desc  = _strip_accents(event.get("description", "").lower())
    haystack = title + " " + desc
    # Match si le terme complet OU au moins un token est trouvé
    return q_norm in haystack or any(tok in haystack for tok in tokens)

async def search_meetings(query: str):
    """
    Recherche en 3 tentatives :
    1. MCP search-events (terme exact)
    2. MCP search-events (variante accentuée/sans accent)
    3. Fallback local : récupère tous les événements des 60 prochains jours
       et filtre par mot-clé côté Python — garantit de trouver même les titres partiels.
    """
    # ── Tentative 1 — terme original via MCP ─────────────
    data = await call_mcp("search-events", {"query": query})
    results = data.get("events", data.get("result", []))

    # ── Tentative 2 — variante accentuée/sans accent ──────
    if not results:
        query_no_accent = _strip_accents(query)
        if query_no_accent != query:
            # Terme avec accents → essaie sans accent
            data2 = await call_mcp("search-events", {"query": query_no_accent})
            results = data2.get("events", data2.get("result", [])) or results
        else:
            # Terme sans accents → essaie variante accentuée
            ACCENT_MAP = str.maketrans({'e': 'é', 'a': 'à', 'u': 'ù', 'i': 'î', 'o': 'ô'})
            accented = query.translate(ACCENT_MAP)
            if accented != query:
                data2 = await call_mcp("search-events", {"query": accented})
                results = data2.get("events", data2.get("result", [])) or results

    # ── Tentative 3 — fallback local sur les 60 prochains jours ──
    if not results:
        today     = date.today()
        time_min  = _to_rfc3339(today.isoformat())
        time_max  = _to_rfc3339_end((today + timedelta(days=60)).isoformat())
        all_data  = await call_mcp(
            "list-events",
            {"calendarId": "primary", "timeMin": time_min, "timeMax": time_max},
        )
        all_events = all_data.get("events", all_data.get("result", []))
        results = [e for e in all_events if _keyword_match(e, query)]
        print(f"[search_meetings] fallback local : {len(all_events)} évts scannés → {len(results)} match(es) pour '{query}'")

    trimmed = [_trim_event(e) for e in results]
    return {"success": True, "results": trimmed}


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