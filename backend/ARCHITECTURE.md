
talan-assistant-backend/
│
│   # ┌─────────────────────────────────────────────────────┐
│   # │  FICHIERS RACINE — Configuration globale du projet  │
│   # └─────────────────────────────────────────────────────┘
│
├── .env.example            # Toutes les variables d'environnement à remplir (clés API, BDD, ports agents...)
├── .gitignore              # Fichiers à ne jamais commiter (.env, credentials/, __pycache__...)
├── requirements.txt        # Toutes les dépendances Python du projet
├── docker-compose.yml      # Lance PostgreSQL + ChromaDB + Ollama en un seul docker-compose up -d
├── README.md               # Guide de démarrage du projet (install, lancer, comptes démo...)
│
│
├── app/                    # ◄ APPLICATION PRINCIPALE — FastAPI + LangGraph Orchestrateur
│   │
│   ├── main.py             # Point d'entrée : crée l'app FastAPI, branche tous les routers, configure CORS
│   ├── config.py           # Charge le fichier .env et expose un objet `settings` global
│   │
│   ├── api/                # ◄ ROUTES HTTP — Ce que le frontend React appelle
│   │   ├── auth.py         # POST /auth/login → retourne JWT  |  POST /auth/refresh → renouvelle le token
│   │   ├── chat.py         # POST /chat → envoie le message à LangGraph  |  GET /chat/stream → SSE streaming
│   │   ├── users.py        # GET /users/me → profil connecté  |  PUT /users/me → mise à jour profil
│   │   ├── pipeline.py     # POST /pipeline → upload CDC (PM uniquement) → lance le pipeline LangGraph PM
│   │   └── notifications.py# GET /notifications → liste  |  PUT /notifications/{id}/read → marquer lu
│   │
│   ├── core/               # ◄ SÉCURITÉ & RÈGLES TRANSVERSALES — utilisées partout dans le projet
│   │   ├── security.py     # Crée/vérifie les JWT, hache les mots de passe (bcrypt), get_current_user()
│   │   ├── rbac.py         # Vérifie les permissions : check_permission(role, action) → True/False
│   │   ├── rate_limiter.py # Limite les requêtes : 60/min globalement, 20/min sur /chat (protège le LLM)
│   │   ├── anti_injection.py # Bloque les Prompt Injection, MCP Injection, nettoie les inputs utilisateur
│   │   └── file_validator.py # Valide les fichiers uploadés : extension .pdf/.docx, taille max, double extension
│   │
│   ├── orchestrator/       # ◄ CERVEAU DU SYSTÈME — LangGraph pilote tous les agents
│   │   │
│   │   ├── graph.py        # Assemble les 3 nodes dans un StateGraph LangGraph et compile le graphe final
│   │   ├── state.py        # Définit la mémoire court-terme (RAM) : messages[], user_id, role, intent, entities
│   │   │
│   │   ├── nodes/          # ◄ LES 3 ÉTAPES DE TRAITEMENT DE CHAQUE MESSAGE
│   │   │   ├── node1_intent.py  # Appelle le LLM → détecte l'intention + l'agent cible + les entités (dates, IDs)
│   │   │   ├── node2_rbac.py    # Vérifie en base si ce rôle a le droit de faire cette action (sans LLM)
│   │   │   └── node3_dispatch.py# Envoie la tâche au bon agent via A2A HTTP (RH/CRM/Jira/Slack/Calendar/RAG)
│   │   │
│   │   ├── memory/         # ◄ MÉMOIRE LONG TERME — persiste les conversations en base
│   │   │   └── checkpointer.py  # Configure PostgreSQL Checkpointer : sauvegarde auto l'état après chaque échange
│   │   │
│   │   └── pipeline_pm/    # ◄ PIPELINE SPÉCIAL PM — Analyse un CDC en 6 étapes
│   │       ├── graph.py    # Graphe LangGraph séquentiel : extraction → débat PO/TL → MoSCoW → CPM → allocation
│   │       └── nodes.py    # Implémentation de chacun des 6 nodes du pipeline PM
│   │
│   ├── database/           # ◄ BASE DE DONNÉES — PostgreSQL via SQLAlchemy
│   │   │
│   │   ├── connection.py   # Connexion async à PostgreSQL, expose get_db() injectable dans les routes FastAPI
│   │   │
│   │   ├── models/         # ◄ TABLES SQL — Structure de la base de données
│   │   │   ├── user.py     # Table `users` : id, name, email, password_hash, role, created_at
│   │   │   ├── chat.py     # Tables `conversations` et `messages` : historique complet des échanges
│   │   │   ├── permissions.py # Table `permissions` : rôle → liste des actions autorisées (RBAC)
│   │   │   ├── hris.py     # Tables RH : `employees`, `leaves`, `teams` (schéma hris)
│   │   │   └── crm.py      # Tables CRM : `clients`, `projects`, `reports` (schéma crm)
│   │   │
│   │   ├── schemas/        # ◄ VALIDATION — Schémas Pydantic pour les requêtes/réponses API
│   │   │   ├── user.py     # UserCreate, UserLogin, UserResponse, TokenResponse
│   │   │   └── chat.py     # MessageRequest, MessageResponse, ConversationResponse
│   │   │
│   │   └── migrations/     # ◄ ALEMBIC — Versioning de la base de données
│   │       └── env.py      # Config Alembic : détecte les changements de modèles et génère les migrations SQL
│   │
│   ├── a2a/                # ◄ PROTOCOLE A2A — Communication entre l'orchestrateur et les agents
│   │   ├── client.py       # Client HTTP réutilisable : send_task(agent_url, task, params) → résultat
│   │   ├── models.py       # Modèles Pydantic A2A : AgentCard, A2ATask, A2AResponse
│   │   └── registry.py     # Registre des agents : get_agent("rh") → retourne l'URL et les capacités de l'agent
│   │
│   └── rag/                # ◄ MODULE RAG — Recherche dans les documents internes
│       ├── retriever.py    # Pipeline complet : question → embedding → ChromaDB → chunks → LLM → réponse
│       ├── embedder.py     # Convertit les textes en vecteurs (modèle multilingue, supporte le français)
│       └── indexer.py      # Indexe les fichiers de data/documents/ dans ChromaDB (à lancer une fois)
│
│
├── agents/                 # ◄ AGENTS A2A — Chaque agent = un serveur FastAPI indépendant
│   │
│   ├── rh/                 # ◄ AGENT RH — Port 8001 | Gère congés, disponibilités, équipes
│   │   ├── README.md       # Documentation : rôle, outils disponibles, comment lancer, multi-hop Calendar+Slack
│   │   ├── server.py       # Serveur FastAPI : expose /.well-known/agent.json (A2A) + POST /tasks
│   │   ├── agent.py        # Initialise l'agent LangChain ReAct avec les outils RH
│   │   ├── tools.py        # Outils : create_leave, get_my_leaves, get_team_availability, get_team_stack
│   │   ├── mcp_client.py   # Se connecte au MCP PostgreSQL Server → schéma hris uniquement
│   │   ├── schemas.py      # Schémas Pydantic : CreateLeaveRequest, LeaveResponse, TeamAvailabilityResponse
│   │   └── prompts.py      # Prompt système de l'agent : personnalité, capacités, règles métier RH
│   │
│   ├── crm/                # ◄ AGENT CRM — Port 8002 | Gère projets, clients, rapports
│   │   ├── README.md       # Documentation : accès différencié Consultant (ses projets) vs PM (tous les projets)
│   │   ├── server.py       # Serveur FastAPI A2A (même structure que Agent RH)
│   │   ├── agent.py        # Agent LangChain ReAct avec les outils CRM
│   │   ├── tools.py        # Outils : get_my_projects, get_all_projects, generate_client_report, get_project_team
│   │   ├── mcp_client.py   # Se connecte au MCP PostgreSQL Server → schéma crm uniquement
│   │   ├── schemas.py      # Schémas Pydantic : ProjectResponse, ClientReportRequest
│   │   └── prompts.py      # Prompt système de l'agent CRM
│   │
│   ├── jira/               # ◄ AGENT JIRA — Port 8003 | Gère les tickets Atlassian
│   │   ├── README.md       # Documentation : outils disponibles, configuration du token Atlassian
│   │   ├── server.py       # Serveur FastAPI A2A
│   │   ├── agent.py        # Agent LangChain ReAct avec les outils Jira
│   │   ├── tools.py        # Outils : get_tickets, create_ticket, update_status, get_sprint
│   │   ├── mcp_client.py   # Se connecte au MCP Atlassian Server (API Jira REST via MCP)
│   │   ├── schemas.py      # Schémas Pydantic : TicketResponse, CreateTicketRequest
│   │   └── prompts.py      # Prompt système de l'agent Jira
│   │
│   ├── slack/              # ◄ AGENT SLACK — Port 8004 | Envoie des messages et notifie les équipes
│   │   ├── README.md       # Documentation : appelé en multi-hop par Agent RH après création de congé
│   │   ├── server.py       # Serveur FastAPI A2A
│   │   ├── agent.py        # Agent LangChain ReAct avec les outils Slack
│   │   ├── tools.py        # Outils : send_message, read_channel, notify_team
│   │   ├── mcp_client.py   # Se connecte au MCP Slack Server (Bot Token)
│   │   ├── schemas.py      # Schémas Pydantic : SendMessageRequest, MessageResponse
│   │   └── prompts.py      # Prompt système de l'agent Slack
│   │
│   └── calendar/           # ◄ AGENT CALENDAR — Port 8005 | Gère Google Calendar
│       ├── README.md       # Documentation : appelé en multi-hop par Agent RH pour bloquer les congés
│       ├── server.py       # Serveur FastAPI A2A
│       ├── agent.py        # Agent LangChain ReAct avec les outils Calendar
│       ├── tools.py        # Outils : create_event, get_events
│       ├── mcp_client.py   # Se connecte au MCP Google Calendar Server (OAuth2)
│       ├── schemas.py      # Schémas Pydantic : CreateEventRequest, EventResponse
│       └── prompts.py      # Prompt système de l'agent Calendar
│
│
├── scripts/                # ◄ SCRIPTS UTILITAIRES — À lancer en ligne de commande
│   ├── seed_db.py          # Peuple la BDD avec des données mock réalistes (Faker) : users, projets, congés
│   ├── seed_permissions.py # Insère les règles RBAC initiales : consultant et pm → leurs actions autorisées
│   └── index_documents.py  # Indexe les fichiers de data/documents/ dans ChromaDB pour le RAG
│
│
├── tests/                  # ◄ TESTS — Unitaires et d'intégration
│   ├── conftest.py         # Fixtures partagées : client FastAPI de test, base de données de test, mocks
│   ├── test_auth.py        # Teste login, génération JWT, refresh token, token expiré
│   ├── test_rbac.py        # Teste les permissions : consultant ne peut pas voir tous les projets, etc.
│   ├── test_orchestrator.py# Teste le graphe LangGraph complet (les 3 nodes enchaînés)
│   └── test_agents/        # Tests par agent
│       ├── test_rh.py      # Teste create_leave, multi-hop vers Calendar + Slack
│       ├── test_crm.py     # Teste get_my_projects, generate_client_report
│       ├── test_jira.py    # Teste get_tickets, create_ticket
│       └── test_rag.py     # Teste l'indexation et la qualité des réponses RAG
│
│
├── data/                   # ◄ DONNÉES LOCALES
│   ├── documents/          # Fichiers PDF/DOCX à indexer dans ChromaDB (politiques RH, chartes IT, guides)
│   └── mock/               # Fichiers JSON de données mock pour les tests
│
│
└── credentials/            # ◄ CREDENTIALS SENSIBLES — Ne jamais commiter dans Git !
    └── google_credentials.json  # Fichier OAuth2 Google pour l'Agent Calendar (à télécharger depuis GCP)
