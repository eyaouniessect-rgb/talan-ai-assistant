# Agent Jira
> Serveur FastAPI indépendant — Port **8003**

## Rôle
Interface avec Atlassian Jira : consulte, crée et met à jour des tickets, accède aux informations de sprint.

---

## Lancer l'agent
```bash
uvicorn agents.jira.server:app --port 8003 --reload
```

## Agent Card A2A
```
GET http://localhost:8003/.well-known/agent.json
```

---

## Outils disponibles

| Outil | Ce qu'il fait | Paramètres |
|-------|--------------|------------|
| `get_tickets` | Liste les tickets d'un utilisateur | `user_id`, `status_filter` |
| `create_ticket` | Crée un nouveau ticket Jira | `title`, `description`, `priority`, `project_key` |
| `update_status` | Change le statut d'un ticket | `ticket_id`, `new_status` |
| `get_sprint` | Infos sur le sprint actif | `project_key` |

---

## Source de données
**MCP Atlassian** → API Jira REST via MCP Server Atlassian

Variables d'environnement requises :
```
MCP_JIRA_URL=https://your-domain.atlassian.net
MCP_JIRA_EMAIL=your@email.com
MCP_JIRA_API_TOKEN=your-token
```

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI A2A |
| `agent.py` | Agent LangChain ReAct avec les outils Jira |
| `tools.py` | Implémentation des 4 outils via MCP Atlassian |
| `mcp_client.py` | Client MCP connecté à l'API Jira Atlassian |
| `schemas.py` | Pydantic : TicketResponse, CreateTicketRequest |
| `prompts.py` | Prompt système avec vocabulaire Jira |
