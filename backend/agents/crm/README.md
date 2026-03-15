# Agent CRM
> Serveur FastAPI indépendant — Port **8002**

## Rôle
Gère les projets, clients et rapports. Accès différencié selon le rôle : un Consultant voit uniquement ses propres projets, un PM voit tous les projets de l'entreprise.

---

## Lancer l'agent
```bash
uvicorn agents.crm.server:app --port 8002 --reload
```

## Agent Card A2A
```
GET http://localhost:8002/.well-known/agent.json
```

---

## Outils disponibles

| Outil | Ce qu'il fait | Accès | Paramètres |
|-------|--------------|-------|------------|
| `get_my_projects` | Projets assignés à un consultant | Consultant + PM | `user_id` |
| `get_all_projects` | Tous les projets de l'entreprise | PM uniquement | `pm_id` |
| `generate_client_report` | Génère un rapport d'avancement client | PM uniquement | `project_id` |
| `get_project_team` | Membres de l'équipe d'un projet | Consultant + PM | `project_id` |

---

## Source de données
**MCP PostgreSQL** → schéma `crm`
- Table `clients` — clients de l'entreprise
- Table `projects` — projets en cours et terminés
- Table `reports` — rapports générés

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI A2A |
| `agent.py` | Agent LangChain ReAct avec les outils CRM |
| `tools.py` | Implémentation des 4 outils (appels MCP PostgreSQL) |
| `mcp_client.py` | Client MCP connecté au schéma `crm` uniquement |
| `schemas.py` | Pydantic : ProjectResponse, ClientReportRequest |
| `prompts.py` | Prompt système avec règles d'accès par rôle |
