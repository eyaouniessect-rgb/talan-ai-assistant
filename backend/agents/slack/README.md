# Agent Slack
> Serveur FastAPI indépendant — Port **8004**

## Rôle
Envoie des messages, lit des canaux et notifie des équipes via Slack. Principalement appelé en **multi-hop** par l'Agent RH après la création d'un congé.

---

## Lancer l'agent
```bash
uvicorn agents.slack.server:app --port 8004 --reload
```

## Agent Card A2A
```
GET http://localhost:8004/.well-known/agent.json
```

---

## Outils disponibles

| Outil | Ce qu'il fait | Paramètres |
|-------|--------------|------------|
| `send_message` | Envoie un message dans un canal | `channel_id`, `message` |
| `read_channel` | Lit les derniers messages d'un canal | `channel_id`, `limit` |
| `notify_team` | Notifie tous les membres d'une équipe | `team_id`, `message` |

---

## Source de données
**MCP Slack** → API Slack via Bot Token

Variable d'environnement requise :
```
MCP_SLACK_BOT_TOKEN=xoxb-...
```

---

## Appelé par
L'Agent Slack est rarement appelé directement par l'orchestrateur. Il est principalement déclenché en **multi-hop A2A** par :
- **Agent RH** → après `create_leave` pour notifier le manager
- Potentiellement par l'orchestrateur directement si l'utilisateur demande explicitement d'envoyer un message

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI A2A |
| `agent.py` | Agent LangChain ReAct avec les outils Slack |
| `tools.py` | Implémentation des 3 outils via MCP Slack |
| `mcp_client.py` | Client MCP connecté à l'API Slack (Bot Token) |
| `schemas.py` | Pydantic : SendMessageRequest, MessageResponse |
| `prompts.py` | Prompt système avec règles de communication |
