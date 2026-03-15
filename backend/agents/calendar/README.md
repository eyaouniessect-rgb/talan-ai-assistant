# Agent Calendar
> Serveur FastAPI indépendant — Port **8005**

## Rôle
Crée et consulte des événements Google Calendar. Principalement appelé en **multi-hop** par l'Agent RH pour bloquer automatiquement les jours de congé dans l'agenda.

---

## Lancer l'agent
```bash
uvicorn agents.calendar.server:app --port 8005 --reload
```

## Agent Card A2A
```
GET http://localhost:8005/.well-known/agent.json
```

---

## Outils disponibles

| Outil | Ce qu'il fait | Paramètres |
|-------|--------------|------------|
| `create_event` | Crée un événement dans Google Calendar | `title`, `start_date`, `end_date`, `user_email` |
| `get_events` | Liste les événements d'une période | `user_email`, `start_date`, `end_date` |

---

## Source de données
**MCP Google Calendar** → API Google Calendar via OAuth2

Fichier requis :
```
credentials/google_credentials.json   ← télécharger depuis Google Cloud Console
```

---

## Appelé par
- **Agent RH** (multi-hop A2A) → après `create_leave` pour bloquer les jours dans l'agenda
- **Orchestrateur** directement → si l'utilisateur demande "mon calendrier cette semaine"

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI A2A |
| `agent.py` | Agent LangChain ReAct avec les outils Calendar |
| `tools.py` | Implémentation des 2 outils via MCP Google Calendar |
| `mcp_client.py` | Client MCP avec authentification OAuth2 Google |
| `schemas.py` | Pydantic : CreateEventRequest, EventResponse |
| `prompts.py` | Prompt système pour la gestion d'agenda |
