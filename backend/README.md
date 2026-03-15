# Talan Assistant — Backend

Assistant d'entreprise intelligent & unifié basé sur FastAPI + LangGraph + A2A + MCP.

## Stack technique
- **FastAPI** — API principale (auth, routing, SSE streaming)
- **LangGraph** — Orchestrateur multi-agents (3 nodes : intention, RBAC, dispatch)
- **A2A Protocol** — Communication inter-agents (chaque agent = serveur FastAPI indépendant)
- **MCP** — Connexion aux outils externes (PostgreSQL, Jira, Slack, Google Calendar)
- **ChromaDB** — Base vectorielle pour le module RAG
- **PostgreSQL** — Base relationnelle (hris, crm, chat_history, permissions)
- **LangSmith** — Monitoring et traçabilité du pipeline LangGraph
- **Ollama + LLaMA 3** — Modèles LLM locaux pour les données sensibles

## Lancer le projet

```bash
# 1. Créer l'environnement virtuel
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer les variables d'environnement
cp .env.example .env
# Remplir les valeurs dans .env

# 4. Lancer la base de données
docker-compose up -d postgres chromadb

# 5. Appliquer les migrations
alembic upgrade head

# 6. Peupler la base avec les données mock
python scripts/seed_db.py

# 7. Lancer l'orchestrateur principal
uvicorn app.main:app --reload --port 8000

# 8. Lancer les agents (dans des terminaux séparés)
uvicorn agents.rh.server:app --port 8001
uvicorn agents.crm.server:app --port 8002
uvicorn agents.jira.server:app --port 8003
uvicorn agents.slack.server:app --port 8004
uvicorn agents.calendar.server:app --port 8005
```

## Architecture
Voir `docs/architecture.md` pour le schéma complet.
