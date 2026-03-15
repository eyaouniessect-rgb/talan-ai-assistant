#!/usr/bin/env python3
"""
Script de génération de l'architecture backend Talan Assistant.
Lance ce script pour créer tous les dossiers et fichiers vides.
  python3 generate_structure.py
"""

import os

# ─────────────────────────────────────────────────────────────
# STRUCTURE COMPLÈTE DU BACKEND
# Chaque tuple : (chemin, contenu du fichier)
# ─────────────────────────────────────────────────────────────

FILES = {

# ═══════════════════════════════════════════════════════════
# RACINE DU PROJET
# ═══════════════════════════════════════════════════════════

"README.md": """# Talan Assistant — Backend

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
source venv/bin/activate  # Windows: venv\\Scripts\\activate

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
""",

".env.example": """# ── APPLICATION ──────────────────────────────────────────
APP_NAME=TalanAssistant
APP_ENV=development
APP_PORT=8000
SECRET_KEY=your-super-secret-key-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ── BASE DE DONNÉES ───────────────────────────────────────
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=talan
POSTGRES_PASSWORD=talan_password
POSTGRES_DB=talan_assistant

# ── CHROMADB (RAG) ────────────────────────────────────────
CHROMA_HOST=localhost
CHROMA_PORT=8010
CHROMA_COLLECTION_RH=politiques_rh
CHROMA_COLLECTION_IT=chartes_it

# ── LLM — MODÈLES ─────────────────────────────────────────
# Modèle principal (cloud)
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o

# Modèle local pour données sensibles (Ollama)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3

# Choisir le mode : cloud | local | hybrid
LLM_MODE=hybrid

# ── LANGSMITH (monitoring) ────────────────────────────────
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls__...
LANGCHAIN_PROJECT=talan-assistant

# ── MCP SERVERS ───────────────────────────────────────────
MCP_POSTGRES_URL=postgresql://talan:talan_password@localhost:5432/talan_assistant
MCP_JIRA_URL=https://your-domain.atlassian.net
MCP_JIRA_EMAIL=your@email.com
MCP_JIRA_API_TOKEN=your-jira-token
MCP_SLACK_BOT_TOKEN=xoxb-...
MCP_SLACK_CHANNEL_ID=C0XXXXXXXXX
MCP_GOOGLE_CREDENTIALS_FILE=credentials/google_credentials.json

# ── AGENTS A2A ────────────────────────────────────────────
AGENT_RH_URL=http://localhost:8001
AGENT_CRM_URL=http://localhost:8002
AGENT_JIRA_URL=http://localhost:8003
AGENT_SLACK_URL=http://localhost:8004
AGENT_CALENDAR_URL=http://localhost:8005

# ── CORS ──────────────────────────────────────────────────
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
""",

"requirements.txt": """# ── FRAMEWORK ────────────────────────────────────────────
fastapi==0.111.0
uvicorn[standard]==0.29.0
python-multipart==0.0.9
python-dotenv==1.0.1

# ── ORCHESTRATION IA ──────────────────────────────────────
langchain==0.2.0
langchain-openai==0.1.7
langchain-community==0.2.0
langgraph==0.1.5
langsmith==0.1.63

# ── LLM LOCAL ─────────────────────────────────────────────
ollama==0.2.1

# ── BASE DE DONNÉES ───────────────────────────────────────
sqlalchemy==2.0.30
alembic==1.13.1
asyncpg==0.29.0
psycopg2-binary==2.9.9

# ── AUTHENTIFICATION ──────────────────────────────────────
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# ── RAG / VECTORDB ────────────────────────────────────────
chromadb==0.5.0
sentence-transformers==3.0.0

# ── MCP ───────────────────────────────────────────────────
mcp==1.0.0
httpx==0.27.0
httpx-sse==0.4.0

# ── SÉCURITÉ ──────────────────────────────────────────────
slowapi==0.1.9          # rate limiting
pydantic==2.7.1
pydantic-settings==2.2.1
bleach==6.1.0           # sanitisation anti-injection

# ── UTILITAIRES ───────────────────────────────────────────
python-dateutil==2.9.0
faker==25.0.0           # génération données mock
pytest==8.2.0
pytest-asyncio==0.23.6
""",

"docker-compose.yml": """version: '3.9'
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: talan
      POSTGRES_PASSWORD: talan_password
      POSTGRES_DB: talan_assistant
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  chromadb:
    image: chromadb/chroma:latest
    ports:
      - "8010:8000"
    volumes:
      - chroma_data:/chroma/chroma

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

volumes:
  postgres_data:
  chroma_data:
  ollama_data:
""",

# ═══════════════════════════════════════════════════════════
# APP — ORCHESTRATEUR PRINCIPAL (FastAPI + LangGraph)
# ═══════════════════════════════════════════════════════════

"app/__init__.py": "# Package principal de l'application FastAPI",

"app/main.py": """# Point d'entrée FastAPI.
# Initialise l'app, enregistre les routers, configure CORS,
# rate limiting, middleware de sécurité et LangSmith.
""",

"app/config.py": """# Chargement de toutes les variables d'environnement via pydantic-settings.
# Expose un objet `settings` importable dans tout le projet.
""",

# ── API ROUTES ──────────────────────────────────────────────

"app/api/__init__.py": "# Package des routes API",

"app/api/auth.py": """# Routes d'authentification.
# POST /auth/login     → vérifie email+password → retourne JWT access + refresh token
# POST /auth/refresh   → renouvelle l'access token depuis le refresh token
# POST /auth/logout    → invalide le token côté serveur
""",

"app/api/chat.py": """# Route principale du chat.
# POST /chat           → reçoit message + user_id + role → envoie à l'orchestrateur LangGraph
# GET  /chat/stream    → SSE endpoint → streame la réponse token par token vers le frontend React
""",

"app/api/users.py": """# Routes de gestion des utilisateurs.
# GET  /users/me       → retourne le profil de l'utilisateur connecté
# PUT  /users/me       → met à jour le profil
""",

"app/api/pipeline.py": """# Route dédiée au pipeline PM (analyse de CDC).
# POST /pipeline       → reçoit un fichier PDF/DOCX (CDC) → lance le pipeline LangGraph PM
#                        (extraction → MoSCoW → CPM → allocation ressources)
# Accessible uniquement aux utilisateurs avec role=pm (vérifié par middleware RBAC).
""",

"app/api/notifications.py": """# Routes des notifications.
# GET  /notifications          → liste les notifications de l'utilisateur connecté
# PUT  /notifications/{id}/read → marque une notification comme lue
""",

# ── CORE — LOGIQUE MÉTIER ────────────────────────────────────

"app/core/__init__.py": "# Package core — logique transversale",

"app/core/security.py": """# Tout ce qui concerne la sécurité :
# - Création et vérification des JWT (access + refresh tokens)
# - Hachage des mots de passe (bcrypt via passlib)
# - Dépendance FastAPI `get_current_user` injectable dans toutes les routes
""",

"app/core/rbac.py": """# Contrôle d'accès basé sur les rôles (Role-Based Access Control).
# Contient la table PERMISSIONS en base + la logique de vérification :
#   check_permission(role, action) → True / False
# Utilisé par le Node 2 de l'orchestrateur LangGraph.
# Exemple : consultant peut créer des congés, mais pas voir tous les projets.
""",

"app/core/rate_limiter.py": """# Configuration du rate limiting avec slowapi.
# Limite par défaut : 60 requêtes / minute / utilisateur.
# Limite sur /chat : 20 requêtes / minute (évite l'abus du LLM).
""",

"app/core/anti_injection.py": """# Protection contre les attaques d'injection :
# - Prompt Injection : sanitise et valide le contenu des messages avant d'envoyer au LLM
# - MCP Injection    : vérifie que les paramètres envoyés aux MCP servers sont propres
# - SQL Injection    : toujours utiliser SQLAlchemy ORM (jamais de requêtes brutes)
# - File Check       : vérifie l'extension et le contenu MIME des fichiers uploadés
#   → Double extension check : rapport.pdf.exe → rejeté
#   → Liste blanche : seulement .pdf et .docx acceptés pour le CDC
""",

"app/core/file_validator.py": """# Validation des fichiers uploadés par le PM (CDC).
# - Vérifie l'extension (liste blanche : .pdf, .docx)
# - Vérifie le type MIME réel (pas juste l'extension déclarée)
# - Double extension check : bloque les fichiers comme "rapport.pdf.exe"
# - Limite la taille : max 10 MB
""",

# ── ORCHESTRATEUR LANGGRAPH ──────────────────────────────────

"app/orchestrator/__init__.py": "# Package de l'orchestrateur LangGraph",

"app/orchestrator/graph.py": """# Définition du graphe LangGraph principal.
# Assemble les 3 nodes dans un StateGraph et compile le graphe.
# Configure aussi le PostgreSQL Checkpointer pour la long-term memory.
# 
# Flux : Node1 (intention) → Node2 (RBAC) → Node3 (dispatch A2A)
#                                          ↘ blocked (si non autorisé)
""",

"app/orchestrator/state.py": """# Définition du LangGraph State (short-term memory en RAM).
# TypedDict contenant :
#   - messages       : list[BaseMessage] — historique de la conversation en cours
#   - user_id        : str
#   - role           : str (consultant | pm)
#   - intent         : str — intention détectée par Node 1
#   - target_agent   : str — agent cible détecté par Node 1
#   - entities       : dict — entités extraites (dates, IDs, etc.)
#   - is_authorized  : bool — résultat du Node 2 RBAC
#   - final_response : str — réponse finale à streamer
""",

"app/orchestrator/nodes/__init__.py": "# Package des nodes LangGraph",

"app/orchestrator/nodes/node1_intent.py": """# Node 1 — Détection d'intention.
# Appelle le LLM avec le message utilisateur.
# Extrait :
#   - L'intention (create_leave, get_projects, get_tickets, search_docs, etc.)
#   - L'agent cible (agent_rh, agent_crm, agent_jira, agent_slack, agent_calendar, rag)
#   - Les entités nommées (dates, IDs de tickets, noms de projets)
# Charge aussi l'historique depuis PostgreSQL (long-term memory via Checkpointer).
""",

"app/orchestrator/nodes/node2_rbac.py": """# Node 2 — Vérification des permissions (déterministe, sans LLM).
# Interroge la table PERMISSIONS en base avec (role, intention).
# Si autorisé  → passe à Node 3
# Si refusé    → retourne immédiatement une réponse "bloqué" au frontend
# C'est la couche de sécurité métier principale de l'architecture.
""",

"app/orchestrator/nodes/node3_dispatch.py": """# Node 3 — Dispatch via le protocole A2A.
# Selon l'agent cible détecté en Node 1, envoie une requête HTTP A2A
# au bon serveur d'agent (agent_rh:8001, agent_crm:8002, etc.)
# Gère aussi :
#   - L'exécution parallèle si plusieurs agents sont indépendants
#   - Le timeout et la gestion d'erreur par agent
#   - Le routing vers le Module RAG si l'intention est "search_docs"
""",

"app/orchestrator/memory/__init__.py": "# Package memory",

"app/orchestrator/memory/checkpointer.py": """# Configuration du LangGraph PostgreSQL Checkpointer (long-term memory).
# Sauvegarde automatiquement l'état complet de chaque conversation
# dans la table chat_history de PostgreSQL après chaque échange.
# Permet de reprendre une conversation après fermeture du navigateur.
""",

"app/orchestrator/pipeline_pm/__init__.py": "# Package pipeline PM",

"app/orchestrator/pipeline_pm/graph.py": """# Graphe LangGraph dédié au pipeline PM d'analyse de CDC.
# 6 nodes séquentiels :
#   Node 1 : Extraction du contenu du CDC (PDF/DOCX → texte)
#   Node 2 : Débat PO vs TL (simulation de priorisation contradictoire)
#   Node 3 : Priorisation MoSCoW (Must/Should/Could/Won't Have)
#   Node 4 : Graphe de dépendances entre les tâches
#   Node 5 : Calcul du chemin critique (CPM — Critical Path Method)
#   Node 6 : Allocation des ressources humaines recommandée
""",

"app/orchestrator/pipeline_pm/nodes.py": """# Implémentation des 6 nodes du pipeline PM.
# Chaque node reçoit l'état du pipeline et retourne l'état mis à jour.
# Chaque node appelle le LLM avec un prompt spécialisé.
""",

# ── DATABASE ─────────────────────────────────────────────────

"app/database/__init__.py": "# Package base de données",

"app/database/connection.py": """# Connexion async à PostgreSQL via SQLAlchemy (asyncpg).
# Expose : engine, AsyncSessionLocal, get_db (dépendance FastAPI injectable)
""",

"app/database/models/__init__.py": "# Package des modèles SQLAlchemy",

"app/database/models/user.py": """# Modèle SQLAlchemy pour la table `users`.
# Champs : id, name, email, hashed_password, role (consultant|pm), created_at, is_active
""",

"app/database/models/chat.py": """# Modèles SQLAlchemy pour les tables de chat :
# - `conversations` : id, user_id, title, created_at, updated_at
# - `messages`      : id, conversation_id, role (user|assistant), content, timestamp
#   → Utilisé par le LangGraph Checkpointer pour la long-term memory
""",

"app/database/models/permissions.py": """# Modèle SQLAlchemy pour la table `permissions`.
# Champs : id, role (consultant|pm), action (create_leave, get_all_projects, etc.), allowed (bool)
# Peuplée au démarrage via les migrations Alembic (données initiales dans seed_permissions.py).
""",

"app/database/models/hris.py": """# Modèles SQLAlchemy pour le schéma RH (schema hris) :
# - `employees`    : id, name, email, role, team_id, manager_id
# - `leaves`       : id, employee_id, start_date, end_date, status, days_count
# - `teams`        : id, name, manager_id
""",

"app/database/models/crm.py": """# Modèles SQLAlchemy pour le schéma CRM (schema crm) :
# - `clients`      : id, name, industry, contact_email
# - `projects`     : id, name, client_id, status, progress, deadline, team_ids
# - `reports`      : id, project_id, content, generated_at
""",

"app/database/schemas/__init__.py": "# Package des schémas Pydantic",

"app/database/schemas/user.py": """# Schémas Pydantic pour la validation des données utilisateur :
# UserCreate, UserLogin, UserResponse, TokenResponse
""",

"app/database/schemas/chat.py": """# Schémas Pydantic pour les messages et conversations :
# MessageRequest, MessageResponse, ConversationResponse
""",

"app/database/migrations/env.py": """# Configuration Alembic pour les migrations de base de données.
# Alembic détecte automatiquement les changements dans les modèles SQLAlchemy.
# Commandes utiles :
#   alembic revision --autogenerate -m "description"
#   alembic upgrade head
""",

# ── A2A PROTOCOL ─────────────────────────────────────────────

"app/a2a/__init__.py": "# Package du protocole A2A (Agent-to-Agent)",

"app/a2a/client.py": """# Client A2A réutilisable pour appeler n'importe quel agent.
# Méthode principale : send_task(agent_url, task, params) → résultat
# Gère :
#   - L'authentification Bearer entre agents
#   - Le timeout (default: 30s)
#   - Les retries en cas d'erreur réseau (max 3 tentatives)
#   - La désérialisation de la réponse A2A standard
""",

"app/a2a/models.py": """# Modèles Pydantic pour le protocole A2A :
# - AgentCard    : description de l'agent (name, url, capabilities, authentication)
# - A2ATask      : requête envoyée à un agent (task, params, context)
# - A2AResponse  : réponse standard d'un agent (status, result, error)
""",

"app/a2a/registry.py": """# Registre des agents disponibles.
# Charge les URLs des agents depuis les variables d'environnement.
# Méthode : get_agent(name) → AgentCard
# Utilisé par Node 3 pour résoudre l'URL de l'agent cible.
""",

# ── RAG MODULE ───────────────────────────────────────────────

"app/rag/__init__.py": "# Package du module RAG (Retrieval-Augmented Generation)",

"app/rag/retriever.py": """# Module RAG principal.
# Flux complet : question → embedding → recherche ChromaDB → chunks → LLM → réponse
# Collections ChromaDB :
#   - politiques_rh    : politiques de congés, règlement intérieur
#   - chartes_it       : charte informatique, procédures sécurité
#   - guides_onboarding : guides d'intégration, FAQ employés
""",

"app/rag/embedder.py": """# Gestion des embeddings pour ChromaDB.
# Utilise sentence-transformers pour convertir les textes en vecteurs.
# Modèle par défaut : paraphrase-multilingual-MiniLM-L12-v2 (supporte le français)
""",

"app/rag/indexer.py": """# Script d'indexation des documents internes dans ChromaDB.
# À lancer une fois au démarrage ou quand les documents changent :
#   python -m app.rag.indexer
# Lit les fichiers depuis data/documents/ et les indexe dans ChromaDB.
""",

# ═══════════════════════════════════════════════════════════
# AGENTS — SERVEURS A2A INDÉPENDANTS
# ═══════════════════════════════════════════════════════════

"agents/__init__.py": "# Package des agents A2A — chaque agent est un serveur FastAPI indépendant",

# ── AGENT RH ────────────────────────────────────────────────

"agents/rh/__init__.py": "# Agent RH — Port 8001",

"agents/rh/README.md": """# Agent RH — Gestionnaire des Ressources Humaines

## Rôle
Gère tout ce qui concerne les ressources humaines : congés, disponibilités, équipes.

## Port
`8001` — accessible sur `http://localhost:8001`

## Agent Card A2A
```
GET http://localhost:8001/.well-known/agent.json
```

## Outils disponibles (Tools)
| Outil | Description | Paramètres |
|-------|-------------|------------|
| `create_leave` | Créer une demande de congé | user_id, start_date, end_date |
| `get_my_leaves` | Lister les congés d'un employé | user_id |
| `get_team_availability` | Disponibilité de l'équipe | team_id, date_range |
| `get_team_stack` | Compétences techniques de l'équipe | team_id |

## Sources de données
- **MCP PostgreSQL** → schéma `hris` (tables employees, leaves, teams)

## Agents appelés (multi-hop A2A)
Après `create_leave`, l'Agent RH appelle automatiquement :
- **Agent Calendar** → bloquer les jours dans Google Calendar
- **Agent Slack** → notifier le Project Manager

## Lancer l'agent
```bash
uvicorn agents.rh.server:app --port 8001 --reload
```
""",

"agents/rh/server.py": """# Serveur FastAPI de l'Agent RH.
# Expose :
#   GET  /.well-known/agent.json  → Agent Card A2A
#   POST /tasks                   → Reçoit et exécute les tâches A2A
#   GET  /health                  → Health check
""",

"agents/rh/agent.py": """# Logique principale de l'Agent RH.
# Initialise l'agent LangChain ReAct avec les outils RH.
# Le cycle ReAct : Reason → Act (appel MCP ou A2A) → Observe → Reason → ...
""",

"agents/rh/tools.py": """# Outils de l'Agent RH (appelés pendant le cycle ReAct) :
# - create_leave_tool       : INSERT dans hris.leaves via MCP PostgreSQL
# - get_my_leaves_tool      : SELECT depuis hris.leaves via MCP PostgreSQL
# - get_team_availability_tool : calcule les disponibilités depuis hris.employees + leaves
# - get_team_stack_tool     : SELECT depuis hris.employees (champ skills)
""",

"agents/rh/mcp_client.py": """# Client MCP PostgreSQL spécifique à l'Agent RH.
# Se connecte au MCP Server PostgreSQL et exécute les requêtes
# sur le schéma `hris` uniquement (isolation des données).
""",

"agents/rh/schemas.py": """# Schémas Pydantic pour les entrées/sorties de l'Agent RH :
# CreateLeaveRequest, LeaveResponse, TeamAvailabilityResponse
""",

"agents/rh/prompts.py": """# Prompts système de l'Agent RH.
# Définit la personnalité, les capacités et les limites de l'agent.
# Contient aussi les instructions pour les appels multi-hop vers Calendar et Slack.
""",

# ── AGENT CRM ───────────────────────────────────────────────

"agents/crm/__init__.py": "# Agent CRM — Port 8002",

"agents/crm/README.md": """# Agent CRM — Gestionnaire de la Relation Client

## Rôle
Gère les projets, clients et rapports. Permet aux consultants de suivre leurs projets
et aux PMs d'avoir une vue globale de tous les projets de l'entreprise.

## Port
`8002` — accessible sur `http://localhost:8002`

## Agent Card A2A
```
GET http://localhost:8002/.well-known/agent.json
```

## Outils disponibles (Tools)
| Outil | Description | Paramètres |
|-------|-------------|------------|
| `get_my_projects` | Projets assignés à un consultant | user_id |
| `get_all_projects` | Tous les projets (PM uniquement) | pm_id |
| `generate_client_report` | Génère un rapport client | project_id |
| `get_project_team` | Membres de l'équipe d'un projet | project_id |

## Sources de données
- **MCP PostgreSQL** → schéma `crm` (tables clients, projects, reports)

## Accès différencié par rôle
- Consultant : voit uniquement ses projets (`get_my_projects`)
- PM : voit tous les projets (`get_all_projects`)

## Lancer l'agent
```bash
uvicorn agents.crm.server:app --port 8002 --reload
```
""",

"agents/crm/server.py": "# Serveur FastAPI de l'Agent CRM (même structure que Agent RH).",
"agents/crm/agent.py": "# Logique ReAct de l'Agent CRM.",
"agents/crm/tools.py": "# Outils CRM : get_my_projects, get_all_projects, generate_client_report, get_project_team.",
"agents/crm/mcp_client.py": "# Client MCP PostgreSQL pour le schéma `crm`.",
"agents/crm/schemas.py": "# Schémas Pydantic CRM : ProjectResponse, ClientReportRequest.",
"agents/crm/prompts.py": "# Prompts système de l'Agent CRM.",

# ── AGENT JIRA ──────────────────────────────────────────────

"agents/jira/__init__.py": "# Agent Jira — Port 8003",

"agents/jira/README.md": """# Agent Jira — Gestionnaire de Tickets Atlassian

## Rôle
Interface avec Jira pour créer, consulter et mettre à jour des tickets et sprints.

## Port
`8003` — accessible sur `http://localhost:8003`

## Agent Card A2A
```
GET http://localhost:8003/.well-known/agent.json
```

## Outils disponibles (Tools)
| Outil | Description | Paramètres |
|-------|-------------|------------|
| `get_tickets` | Liste les tickets assignés | user_id, status_filter |
| `create_ticket` | Créer un nouveau ticket Jira | title, description, priority, project_key |
| `update_status` | Changer le statut d'un ticket | ticket_id, new_status |
| `get_sprint` | Infos sur le sprint actif | project_key |

## Sources de données
- **MCP Atlassian** → API Jira REST via MCP Server Atlassian

## Lancer l'agent
```bash
uvicorn agents.jira.server:app --port 8003 --reload
```
""",

"agents/jira/server.py": "# Serveur FastAPI de l'Agent Jira.",
"agents/jira/agent.py": "# Logique ReAct de l'Agent Jira.",
"agents/jira/tools.py": "# Outils Jira : get_tickets, create_ticket, update_status, get_sprint.",
"agents/jira/mcp_client.py": "# Client MCP Atlassian pour l'API Jira.",
"agents/jira/schemas.py": "# Schémas Pydantic Jira : TicketResponse, CreateTicketRequest.",
"agents/jira/prompts.py": "# Prompts système de l'Agent Jira.",

# ── AGENT SLACK ─────────────────────────────────────────────

"agents/slack/__init__.py": "# Agent Slack — Port 8004",

"agents/slack/README.md": """# Agent Slack — Gestionnaire de Communication

## Rôle
Envoie des messages, lit les canaux et notifie les équipes via Slack.
Principalement appelé en mode multi-hop par l'Agent RH après création de congé.

## Port
`8004` — accessible sur `http://localhost:8004`

## Agent Card A2A
```
GET http://localhost:8004/.well-known/agent.json
```

## Outils disponibles (Tools)
| Outil | Description | Paramètres |
|-------|-------------|------------|
| `send_message` | Envoyer un message dans un canal | channel_id, message |
| `read_channel` | Lire les derniers messages | channel_id, limit |
| `notify_team` | Notifier toute une équipe | team_id, message |

## Sources de données
- **MCP Slack** → API Slack via MCP Server Slack (Bot Token)

## Lancer l'agent
```bash
uvicorn agents.slack.server:app --port 8004 --reload
```
""",

"agents/slack/server.py": "# Serveur FastAPI de l'Agent Slack.",
"agents/slack/agent.py": "# Logique ReAct de l'Agent Slack.",
"agents/slack/tools.py": "# Outils Slack : send_message, read_channel, notify_team.",
"agents/slack/mcp_client.py": "# Client MCP Slack (Bot Token via MCP Server).",
"agents/slack/schemas.py": "# Schémas Pydantic Slack : SendMessageRequest, MessageResponse.",
"agents/slack/prompts.py": "# Prompts système de l'Agent Slack.",

# ── AGENT CALENDAR ──────────────────────────────────────────

"agents/calendar/__init__.py": "# Agent Calendar — Port 8005",

"agents/calendar/README.md": """# Agent Calendar — Gestionnaire de Google Calendar

## Rôle
Crée et consulte des événements Google Calendar.
Appelé en mode multi-hop par l'Agent RH pour bloquer les jours de congé.

## Port
`8005` — accessible sur `http://localhost:8005`

## Agent Card A2A
```
GET http://localhost:8005/.well-known/agent.json
```

## Outils disponibles (Tools)
| Outil | Description | Paramètres |
|-------|-------------|------------|
| `create_event` | Créer un événement dans Google Calendar | title, start_date, end_date, user_email |
| `get_events` | Lister les événements d'une période | user_email, start_date, end_date |

## Sources de données
- **MCP Google Calendar** → API Google Calendar via MCP Server Google

## Credentials
Fichier de credentials Google OAuth2 dans `credentials/google_credentials.json`.

## Lancer l'agent
```bash
uvicorn agents.calendar.server:app --port 8005 --reload
```
""",

"agents/calendar/server.py": "# Serveur FastAPI de l'Agent Calendar.",
"agents/calendar/agent.py": "# Logique ReAct de l'Agent Calendar.",
"agents/calendar/tools.py": "# Outils Calendar : create_event, get_events.",
"agents/calendar/mcp_client.py": "# Client MCP Google Calendar.",
"agents/calendar/schemas.py": "# Schémas Pydantic Calendar : CreateEventRequest, EventResponse.",
"agents/calendar/prompts.py": "# Prompts système de l'Agent Calendar.",

# ═══════════════════════════════════════════════════════════
# SCRIPTS UTILITAIRES
# ═══════════════════════════════════════════════════════════

"scripts/__init__.py": "# Package scripts utilitaires",

"scripts/seed_db.py": """# Peuple la base de données avec des données mock réalistes (Faker).
# Crée : utilisateurs (consultant + PM), projets, tickets, congés, permissions.
# À lancer UNE FOIS après alembic upgrade head.
# Commande : python scripts/seed_db.py
""",

"scripts/seed_permissions.py": """# Insère les règles RBAC initiales dans la table `permissions`.
# Définit qui peut faire quoi :
#   consultant : create_leave, get_my_leaves, get_my_projects, get_tickets...
#   pm         : get_all_projects, get_team_availability, create_ticket, upload_cdc...
""",

"scripts/index_documents.py": """# Indexe les documents internes dans ChromaDB pour le module RAG.
# Lit les fichiers depuis data/documents/ (PDF, DOCX, TXT).
# Découpe en chunks, génère les embeddings, stocke dans ChromaDB.
# Commande : python scripts/index_documents.py
""",

# ═══════════════════════════════════════════════════════════
# TESTS
# ═══════════════════════════════════════════════════════════

"tests/__init__.py": "# Package des tests",
"tests/conftest.py": """# Configuration pytest : fixtures partagées (client FastAPI de test, BDD de test, utilisateurs mock).
""",

"tests/test_auth.py": "# Tests unitaires pour l'authentification (login, JWT, refresh token).",
"tests/test_rbac.py": "# Tests unitaires pour le RBAC (permissions par rôle).",
"tests/test_orchestrator.py": "# Tests d'intégration pour l'orchestrateur LangGraph (les 3 nodes).",
"tests/test_agents/__init__.py": "# Tests par agent",
"tests/test_agents/test_rh.py": "# Tests de l'Agent RH (create_leave, get_leaves, multi-hop vers Calendar+Slack).",
"tests/test_agents/test_crm.py": "# Tests de l'Agent CRM (get_my_projects, generate_report).",
"tests/test_agents/test_jira.py": "# Tests de l'Agent Jira (get_tickets, create_ticket).",
"tests/test_agents/test_rag.py": "# Tests du module RAG (indexation, recherche, qualité des réponses).",

# ═══════════════════════════════════════════════════════════
# DONNÉES
# ═══════════════════════════════════════════════════════════

"data/documents/.gitkeep": "# Placer ici les documents internes à indexer dans ChromaDB (PDF, DOCX, TXT)",
"data/mock/.gitkeep": "# Fichiers JSON de données mock pour les tests",
"credentials/.gitkeep": "# google_credentials.json — NE PAS COMMITER (ajouté dans .gitignore)",

".gitignore": """.env
credentials/
__pycache__/
*.pyc
.pytest_cache/
venv/
.venv/
*.egg-info/
dist/
.DS_Store
""",
}

def generate():
    for path, content in FILES.items():
        dirpath = os.path.dirname(path)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  ✓ {path}")
    print(f"\n✅ {len(FILES)} fichiers créés avec succès !")
    print("\nProchaines étapes :")
    print("  1. python -m venv venv && source venv/bin/activate")
    print("  2. pip install -r requirements.txt")
    print("  3. cp .env.example .env  →  remplir les valeurs")
    print("  4. docker-compose up -d")
    print("  5. alembic upgrade head")
    print("  6. python scripts/seed_db.py")
    print("  7. uvicorn app.main:app --reload")

if __name__ == "__main__":
    generate()
