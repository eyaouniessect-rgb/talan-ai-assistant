# Agent RH
> Serveur FastAPI indépendant — Port **8001**

## Rôle
Gère tout ce qui concerne les ressources humaines : création de congés, consultation des disponibilités d'équipe, compétences des membres.

---

## Lancer l'agent
```bash
uvicorn agents.rh.server:app --port 8001 --reload
```

## Agent Card A2A
```
GET http://localhost:8001/.well-known/agent.json
```

---

## Outils disponibles

| Outil | Ce qu'il fait | Paramètres |
|-------|--------------|------------|
| `create_leave` | Crée une demande de congé en base | `user_id`, `start_date`, `end_date` |
| `get_my_leaves` | Liste tous les congés d'un employé | `user_id` |
| `get_team_availability` | Calcule qui est disponible sur une période | `team_id`, `date_range` |
| `get_team_stack` | Retourne les compétences techniques de l'équipe | `team_id` |

---

## Source de données
**MCP PostgreSQL** → schéma `hris`
- Table `employees` — profils des employés
- Table `leaves` — demandes de congés
- Table `teams` — composition des équipes

---

## Multi-hop A2A
Après un `create_leave` réussi, cet agent appelle automatiquement :
- **Agent Calendar** (port 8005) → bloque les jours dans Google Calendar
- **Agent Slack** (port 8004) → notifie le Project Manager

```
Agent RH → create_leave ✅
         → A2A → Agent Calendar → create_event()
         → A2A → Agent Slack    → send_message()
```

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI : routes `/.well-known/agent.json` et `POST /tasks` |
| `agent.py` | Initialise l'agent LangChain ReAct avec les outils |
| `tools.py` | Implémentation des 4 outils (appels MCP PostgreSQL) |
| `mcp_client.py` | Client MCP connecté au schéma `hris` uniquement |
| `schemas.py` | Modèles Pydantic pour les requêtes et réponses |
| `prompts.py` | Prompt système : personnalité, règles métier RH |
