# Guide de Routage — Talan Assistant

De la réception d'un message jusqu'à la délégation à un agent spécialisé.

---

## Vue d'ensemble

```
Utilisateur
    │
    ▼
[POST /chat/]           ← API FastAPI (app/api/chat.py)
    │
    ▼
[LangGraph Pipeline]    ← Graphe d'orchestration (app/orchestrator/graph.py)
    │
    ├─► Node 1 — Routeur LLM      → détecte quel(s) agent(s) traite(nt) la demande
    │
    ├─► Node 3 — Dispatch A2A     → envoie la tâche à l'agent via HTTP
    │
    └─► Node 4 — Sauvegarde       → persiste l'AIMessage dans l'état LangGraph
    │
    ▼
Réponse JSON → Frontend React
```

---

## Étape 1 — Réception du message (`app/api/chat.py`)

L'utilisateur envoie un message via le frontend. L'API FastAPI :

1. Vérifie le JWT (`get_current_user`) → récupère `user_id` et `role`
2. Trouve ou crée une `Conversation` en base
3. Construit l'état initial LangGraph et appelle `graph.ainvoke()`

```python
initial_state = {
    "messages":     [HumanMessage(content="vérifie mon solde de congés")],
    "user_id":      42,
    "role":         "consultant",
    "target_agent": None,
    "final_response": None,
}
config = {"configurable": {"thread_id": str(conversation.id)}}
result = await graph.ainvoke(initial_state, config)
```

> **`thread_id`** = `conversation.id` → LangGraph utilise ce thread pour persister
> l'historique de la conversation dans PostgreSQL (checkpointer).

---

## Étape 2 — Node 1 : Routeur LLM (`app/orchestrator/nodes/node1_intent.py`)

C'est le cerveau du routage. Il détermine **quel(s) agent(s)** doit(vent) traiter la demande.

### Architecture en cascade (fast paths + LLM)

```
Message reçu
    │
    ├─► FAST PATH 1 : chat-only ?        → "bonjour", "merci"   → target_agent = "chat"
    │
    ├─► FAST PATH 2 : gibberish ?        → "azerty123!!!"        → target_agent = "chat"
    │
    ├─► FAST PATH 3 : context continuation ?
    │       L'agent précédent a posé une question
    │       + réponse courte sans verbe d'action
    │       → garde le même agent (ex: réponse à "quelle date ?" → "lundi prochain")
    │
    └─► PRIMARY : LLM Router
            • Lit le manifest de routage (Agent Cards A2A)
            • Prompt système avec descriptions des agents + few-shots
            • Modèle : openai/gpt-oss-20b  (température 0)
            • Fallback : keyword match si LLM indisponible
```

### Sortie possible du Node 1

**Agent unique :**
```json
{ "target_agent": "rh" }
```

**Multi-agent (2+ agents, exécution parallèle) :**
```json
{
  "targets": [
    { "agent": "rh",       "sub_task": "vérifie mon solde de congés" },
    { "agent": "calendar", "sub_task": "montre mon agenda de la semaine prochaine" }
  ]
}
```

### Exemples de routage

| Message utilisateur | Agent(s) détecté(s) |
|---|---|
| `"combien de jours de congé il me reste ?"` | `rh` |
| `"crée une réunion demain à 10h"` | `calendar` |
| `"qui est disponible dans mon équipe lundi ?"` | `rh` |
| `"bonjour"` | `chat` (fast path) |
| `"14h"` *(réponse à une question en cours)* | `calendar` (fast path context) |
| `"vérifie mon solde puis montre mon agenda"` | `rh` + `calendar` (multi) |
| `"pose un congé lundi, crée une réunion mardi et mets à jour mon ticket jira"` | `rh` + `calendar` + `jira` (multi) |

### Manifest de routage (auto-généré)

Le routeur ne repose pas sur un mapping figé. Il interroge les **Agent Cards A2A** en temps réel :

```
GET http://localhost:8001/.well-known/agent.json  → description + skills + examples du RH agent
GET http://localhost:8002/.well-known/agent.json  → description + skills + examples du Calendar agent
...
```

Ce manifest est mis en cache 5 minutes (`DISCOVERY_CACHE_TTL`). Si un agent est hors ligne, il est simplement absent du prompt.

---

## Étape 3 — Node 3 : Dispatch A2A (`app/orchestrator/nodes/node3_dispatch.py`)

Reçoit le résultat du Node 1 et délègue aux agents.

### Cas 1 : `target_agent = "chat"` (réponses déterministes)

Pas de LLM, pas d'agent externe. Réponses directes :

```
"bonjour"        → "Bonjour ! Je suis Talan Assistant..."
"merci"          → "De rien ! N'hésitez pas si besoin."
"quelle date ?"  → "Aujourd'hui c'est le 30/03/2026."
```

### Cas 2 : Agent unique

```
1. Discovery → find_agent_by_name("rh")
             → GET http://localhost:8001/.well-known/agent.json (cache 5min)

2. Construit le message enrichi :
   ┌──────────────────────────────────────────────┐
   │ Date du jour : 2026-03-30 (lundi)            │
   │ Historique récent (LECTURE SEULE) :          │
   │   Utilisateur: combien de jours...           │
   │ ---                                          │
   │ INSTRUCTION À EXÉCUTER MAINTENANT :          │
   │   vérifie mon solde de congés                │
   │ ---                                          │
   │ Role utilisateur : consultant                │
   │ User ID : 42                                 │
   └──────────────────────────────────────────────┘

3. send_task_to_url(agent_url, message)
   → POST http://localhost:8001/  (protocole A2A)
   → Headers: Authorization: Bearer <A2A_SECRET_TOKEN>

4. Réponse de l'agent → final_response
```

### Cas 3 : Multi-agent (exécution parallèle)

```
targets = [
  { "agent": "rh",       "sub_task": "vérifie mon solde de congés" },
  { "agent": "calendar", "sub_task": "montre mon agenda" }
]

1. Pré-résolution parallèle des URLs :
   asyncio.gather(
     discovery.find_agent_by_name("rh"),
     discovery.find_agent_by_name("calendar"),
   )

2. Dispatch parallèle :
   asyncio.gather(
     send_task_to_url("http://localhost:8001", "vérifie mon solde..."),
     send_task_to_url("http://localhost:8002", "montre mon agenda..."),
   )

3. Fusion des réponses :
   **RH** :
   Il vous reste 18 jours de congé annuel.

   ---

   **CALENDAR** :
   Voici votre agenda de la semaine prochaine :
   • Lundi 06/04 — Réunion d'équipe 10h-11h
   ...
```

---

## Étape 4 — Node 4 : Sauvegarde

Persiste la réponse finale dans `state["messages"]` en tant qu'`AIMessage`.
LangGraph checkpoint → PostgreSQL.

---

## Cycle complet — Exemple réel

```
POST /chat/
Body: { "message": "vérifie mon solde de congés puis montre mon agenda de la semaine" }

Node 1 ──────────────────────────────────────────────────────
  LLM Router reçoit le message + manifest des agents
  "puis" → connecteur multi-domaine détecté
  "solde de congés" → domaine RH
  "agenda de la semaine" → domaine Calendar
  ✅ Résultat : targets = [rh, calendar]

Node 3 ──────────────────────────────────────────────────────
  Discovery pré-résout rh (localhost:8001) et calendar (localhost:8002)
  Dispatch parallèle des deux sous-tâches
  Attente asyncio.gather → ~2 secondes
  Fusion → réponse combinée

Node 4 ──────────────────────────────────────────────────────
  AIMessage sauvegardé dans LangGraph state

API ─────────────────────────────────────────────────────────
  Sauvegarde user message + assistant message en base
  Retourne ChatResponse au frontend
```

---

## Discovery A2A (`app/a2a/discovery.py`)

Chaque agent expose une **Agent Card** à `/.well-known/agent.json` :

```json
{
  "name": "RH Agent",
  "description": "Gestion des congés, absences et données RH",
  "version": "1.0.0",
  "skills": [
    {
      "id": "create_leave",
      "name": "Créer un congé",
      "description": "Pose une demande de congé pour l'employé",
      "tags": ["congé", "absence", "annuel", "maternité"],
      "examples": ["pose un congé du 5 au 10 avril", "je veux prendre des vacances"]
    }
  ]
}
```

Le système scan ces URLs au démarrage et toutes les 5 minutes. Si un agent est **down**, il est automatiquement retiré du prompt du routeur.

---

## RBAC — Où se fait le contrôle des permissions ?

Le contrôle se fait **dans chaque agent**, au niveau de chaque tool.
Avant d'exécuter une action (ex: `create_leave`), l'agent vérifie en base :

```sql
SELECT * FROM permissions
WHERE role = 'consultant' AND action = 'create_leave' AND allowed = true;
```

| Rôle | Exemples de permissions |
|---|---|
| `consultant` | create_leave, get_my_leaves, create_meeting |
| `pm` | + get_all_leaves (vision équipe) |
| `rh` | + approve_leave, reject_leave, create_user_account |

---

## Fichiers clés

| Fichier | Rôle |
|---|---|
| `app/api/chat.py` | Point d'entrée HTTP, gestion conversation |
| `app/orchestrator/graph.py` | Définition du graphe LangGraph |
| `app/orchestrator/nodes/node1_intent.py` | Routeur LLM + fast paths |
| `app/orchestrator/nodes/node3_dispatch.py` | Dispatch mono et multi-agent |
| `app/a2a/discovery.py` | Scan des Agent Cards + cache |
| `app/a2a/client.py` | Client HTTP A2A (envoi des tâches) |
| `app/orchestrator/state.py` | Définition du state LangGraph |
