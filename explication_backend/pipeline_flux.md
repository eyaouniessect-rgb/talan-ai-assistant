# Flux Pipeline Complet — Du Message Utilisateur à la Réponse

> Ce document décrit **chaque étape** que traverse un message, depuis le moment où l'utilisateur clique sur "Envoyer" jusqu'à ce que la réponse s'affiche. Chaque fonction, chaque fichier, chaque input et output sont détaillés.

---

## Vue d'ensemble (le grand dessin)

```
Navigateur (React)
      │
      │  POST /chat/  { message, conversation_id }
      ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI  —  backend/app/api/chat.py                        │
│  Authentifie l'user, trouve/crée la conversation            │
└──────────────────┬──────────────────────────────────────────┘
                   │  graph.ainvoke(initial_state, config)
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  LangGraph  —  backend/app/orchestrator/graph.py            │
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │  Node 1  │ →  │  Node 3  │ →  │  Node 4  │ → END        │
│  │ Routeur  │    │ Dispatch │    │  Save    │              │
│  └──────────┘    └──────────┘    └──────────┘              │
└──────────────────┬──────────────────────────────────────────┘
                   │  (uniquement si agent spécialisé)
                   │  HTTP POST via protocole A2A
                   ▼
         ┌─────────────────────┐    ┌──────────────────────┐
         │  Agent RH           │    │  Agent Calendar      │
         │  port 8001          │    │  port 8002           │
         │  agents/rh/agent.py │    │  agents/calendar/    │
         └─────────────────────┘    └──────────────────────┘
```

---

## ÉTAPE 0 — Le Frontend envoie le message

**Fichier :** `client/src/pages/Chat.jsx`

Le composant React appelle l'API backend :

```js
POST http://localhost:8000/chat/
Headers: { Authorization: "Bearer <jwt_token>" }
Body:   { "message": "pose un congé lundi", "conversation_id": 42 }
```

- `message` : ce que l'utilisateur a tapé
- `conversation_id` : l'ID de la conversation courante (permet la mémoire de contexte). Si c'est une nouvelle conversation, ce champ est absent ou temporaire (>1 000 000 000 000).

---

## ÉTAPE 1 — FastAPI reçoit la requête

**Fichier :** `backend/app/api/chat.py`
**Fonction :** `async def chat(request, current_user, db)`
**Route :** `POST /chat/`

### 1a. Authentification

```python
current_user = Depends(get_current_user)
# → lit le JWT dans le header Authorization
# → retourne { "user_id": 12, "role": "consultant", "email": "..." }
```

**Fichier de la dépendance :** `backend/app/core/security.py`

### 1b. Trouve ou crée la conversation

```python
if is_real_id:              # conversation_id < 1_000_000_000_000
    # Cherche dans la table "conversations" WHERE id=? AND user_id=?
    conversation = await db.execute(select(Conversation).where(...))
else:
    conversation = None     # ID temporaire → nouvelle conversation
```

Si aucune conversation trouvée :
```python
conversation = Conversation(user_id=user_id, title=request.message[:40])
db.add(conversation)
await db.flush()   # génère conversation.id sans encore committer
```

**Tables :** `public.conversations`, `public.messages`

### 1c. Construit l'état initial pour LangGraph

```python
initial_state = {
    "messages":       [HumanMessage(content="pose un congé lundi")],
    "user_id":        12,
    "role":           "consultant",
    # ⚠️ target_agent est ABSENT intentionnellement :
    # LangGraph va chercher la valeur dans le checkpoint (mémoire)
    # → si l'agent posait une question, l'user répond et ça continue
    "target_agents":  None,   # reset du multi-agent précédent
    "final_response": None,
}

config = {
    "configurable": {"thread_id": "42"},   # = conversation_id (string)
    "run_name": "chat:user_12",
    "metadata": { "user_id": 12, "role": "consultant", ... }
}
```

**Concept clé — thread_id :**
LangGraph utilise `thread_id` comme clé pour stocker et restaurer la mémoire de la conversation dans PostgreSQL. Chaque `conversation_id` = un `thread_id` = une mémoire séparée.

### 1d. Invoque LangGraph

```python
result = await graph.ainvoke(initial_state, config)
```

`result` est le state final après que les 3 nœuds ont été exécutés.

---

## ÉTAPE 2 — LangGraph : initialisation du graphe

**Fichier :** `backend/app/orchestrator/graph.py`
**Fonction :** `build_base_graph()` + `init_graph()` (exécutée au démarrage du serveur)

### Structure du graphe

```python
graph = StateGraph(AssistantState)

graph.add_node("node1_router",      node1_detect_intent)
graph.add_node("node3_dispatch",    node3_dispatch)
graph.add_node("node4_save_ai_msg", node4_save_ai_message)

graph.set_entry_point("node1_router")
graph.add_edge("node1_router",      "node3_dispatch")
graph.add_edge("node3_dispatch",    "node4_save_ai_msg")
graph.add_edge("node4_save_ai_msg", END)
```

Le graphe est **compilé avec un checkpointer PostgreSQL** (`AsyncPostgresSaver`). Cela signifie que LangGraph **sauvegarde automatiquement le state** après chaque nœud dans la table `checkpoints` de PostgreSQL.

### Le State partagé entre tous les nœuds

**Fichier :** `backend/app/orchestrator/state.py`

```python
class AssistantState(TypedDict):
    messages:       Annotated[list[BaseMessage], add_messages]
    #                ↑ spécial : les messages s'ACCUMULENT (add_messages)
    #                  au lieu d'être remplacés comme les autres champs

    user_id:        int           # ID de l'utilisateur connecté
    role:           str           # "consultant", "pm", "rh"
    target_agent:   Optional[str] # "rh", "calendar", "chat", ...
    target_agents:  Optional[list[dict]]  # multi-agent: [{"agent":"rh","sub_task":"..."}]
    final_response: Optional[str] # la réponse finale à renvoyer
```

**Comportement de `messages` :** Si le state actuel a `[HumanMessage("bonjour")]` et qu'un nœud retourne `messages=[AIMessage("hello")]`, le résultat sera `[HumanMessage("bonjour"), AIMessage("hello")]`. Les deux coexistent.

---

## ÉTAPE 3 — Node 1 : Détection d'intention (Routeur)

**Fichier :** `backend/app/orchestrator/nodes/node1_intent.py`
**Fonction :** `async def node1_detect_intent(state: AssistantState) -> AssistantState`
**Tracé LangSmith :** `node1_detect_intent`

**Input :** Le state complet
**Output :** State avec `target_agent` et `target_agents` remplis

### Algorithme en 4 chemins

```
Message reçu : "pose un congé lundi"
      │
      ├─ FAST PATH 1 : Est-ce une salutation ? ("bonjour", "merci"...)
      │                → target_agent = "chat"  [sans LLM]
      │
      ├─ FAST PATH 2 : Est-ce du gibberish ? ("azertqsdf"...)
      │                → target_agent = "chat"  [sans LLM]
      │
      ├─ FAST PATH 3 : L'agent précédent posait une question ET
      │                le message est court SANS verbe d'action ?
      │                (ex: l'agent RH a demandé "quelle date ?" et
      │                     l'user répond "lundi prochain")
      │                → target_agent = last_active_agent  [sans LLM]
      │
      └─ PRIMARY : Appel LLM (Groq) avec le prompt routeur
                   → retourne JSON {"target_agent": "rh"}
                      ou        {"targets": [{"agent":"rh","sub_task":"..."},
                                             {"agent":"calendar","sub_task":"..."}]}
```

#### FAST PATH 3 — Context Continuation (détail)

```python
last_active_agent = state.get("target_agent")
# ← vient du CHECKPOINT (mémoire de la conv)
# si l'agent RH a été utilisé au tour précédent → "rh"

if last_active_agent and last_active_agent not in ("chat", "rag"):
    # Trouve le dernier message de l'assistant
    last_ai_msg = ... # ex: "Pour quelle date souhaitez-vous poser le congé ?"

    if "?" in last_ai_msg and _is_short_reply(message):
        # "lundi prochain" → court + pas de verbe → c'est une réponse
        return {**state, "target_agent": last_active_agent}
```

**Pourquoi `target_agent` est absent de `initial_state` :** Si on le mettait à `None`, le checkpoint serait écrasé et FAST PATH 3 ne marcherait jamais. On l'omet pour que LangGraph lise la valeur sauvegardée.

#### Le prompt du LLM routeur

Le prompt est **construit dynamiquement** à partir des Agent Cards A2A :
```python
agents_section = manifest.routing_prompt
# Ex: "AGENTS DISPONIBLES (2 agents actifs):
#      ## AGENT: rh
#         Description: Gestion des congés...
#         • leave_create (Créer un congé)
#           → Permet de déposer une demande de congé
#           Ex: "pose un congé du 5 au 10 avril"
#      ## AGENT: calendar
#         ..."
```

Le LLM (modèle `openai/gpt-oss-20b` via Groq) répond en JSON pur :
```json
{"target_agent": "rh"}
```
ou pour multi-agent :
```json
{"targets": [
    {"agent": "rh",       "sub_task": "pose un congé lundi"},
    {"agent": "calendar", "sub_task": "crée une réunion mardi"}
]}
```

**Output du Node 1 :**
```python
# Mono-agent
return {**state, "target_agent": "rh", "target_agents": None}

# Multi-agent
return {**state,
    "target_agent":  "rh",   # ← premier agent de la liste (PAS None !)
    "target_agents": [
        {"agent": "rh",       "sub_task": "pose un congé lundi"},
        {"agent": "calendar", "sub_task": "crée une réunion mardi"},
    ]
}
# ⚠️ Pourquoi target_agent = "rh" et pas None en multi-agent ?
#
# 1. Node 3 utilise target_agents (avec S) pour détecter le multi-agent,
#    pas target_agent. Le check est :
#      if target_agents and len(target_agents) >= 2 → dispatch parallèle
#    Donc target_agent est ignoré dans Node 3 pour ce cas.
#
# 2. target_agent sert au tour SUIVANT : si l'utilisateur répond "oui" ou
#    "mercredi" après une réponse multi-agent, FAST PATH 3 lit
#    state["target_agent"] pour savoir vers quel agent continuer.
#    Avec "rh", une réponse courte est correctement routée vers l'agent RH
#    sans appeler le LLM.
#
#    Si on mettait None → FAST PATH 3 ne s'activerait pas → le LLM serait
#    appelé inutilement pour router "oui" / "lundi" / "mercredi".
```

---

## ÉTAPE 3bis — Discovery & Routing Manifest

**Fichier :** `backend/app/a2a/discovery.py`
**Classes :** `AgentDiscovery`, `RoutingManifest`

### Comment Node 1 sait quels agents existent ?

Avant d'appeler le LLM, Node 1 appelle `routing_manifest.build()` qui :

1. Appelle `discovery.scan_agents()` → contacte chaque agent sur `/.well-known/agent.json`
2. Récupère l'**Agent Card** de chaque agent (JSON décrivant les skills)
3. Construit un prompt de routage et un keyword_map

```python
# URL scannées :
AGENT_ENDPOINTS = {
    "rh":       "http://localhost:8001",
    "calendar": "http://localhost:8002",
    "crm":      "http://localhost:8003",
    "jira":     "http://localhost:8004",
    "slack":    "http://localhost:8005",
}

# Un agent actif répond avec son Agent Card :
GET http://localhost:8001/.well-known/agent.json
→ {
    "name": "RH Agent",
    "description": "Gestion des congés et RH",
    "skills": [
        {
            "id": "leave_create",
            "name": "Créer un congé",
            "description": "...",
            "examples": ["pose un congé du 5 au 10 avril"],
            "tags": ["congé", "absence", "rh"]
        },
        ...
    ]
}
```

**Cache :** Le résultat est mis en cache 300 secondes (configurable via `DISCOVERY_CACHE_TTL`). Pas besoin de rescanner à chaque message.

---

## ÉTAPE 4 — Node 3 : Dispatch

**Fichier :** `backend/app/orchestrator/nodes/node3_dispatch.py`
**Fonction :** `async def node3_dispatch(state: AssistantState) -> AssistantState`
**Tracé LangSmith :** `node3_dispatch`

**Input :** State avec `target_agent` + optionnellement `target_agents`
**Output :** State avec `final_response` rempli

Node 3 a **3 cas** :

### Cas 1 — Chat (réponses déterministes, sans LLM)

```python
if target_agent == "chat":
    if message in MERCI_KEYWORDS:
        return {**state, "final_response": "De rien ! N'hésitez pas..."}
    if message in SALUTATION_KEYWORDS:
        return {**state, "final_response": PRESENTATION}
    if message in _AU_REVOIR_KEYWORDS:
        return {**state, "final_response": "Au revoir ! Bonne continuation."}
    # Fallback si non reconnu
    return {**state, "final_response": "Je n'ai pas compris..."}
```

Pas de LLM ici. Toutes les réponses sont codées en dur pour éviter la latence.

### Cas 2 — Multi-agent (dispatch parallèle)

```python
if target_agents and len(target_agents) >= 2:
    multi_response = await _dispatch_multi_agent(target_agents, ...)
```

```python
async def _dispatch_multi_agent(targets, user_id, role, today_iso, trimmed_messages):
    # 1. Résout les URLs en parallèle
    discovered_list = await asyncio.gather(
        *[discovery.find_agent_by_name(name) for name in agent_names],
        return_exceptions=True,
    )

    # 2. Envoie les tâches en parallèle
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 3. Fusionne les réponses
    # Output: "**RH** :\n[réponse rh]\n\n---\n\n**CALENDAR** :\n[réponse calendar]"
```

Les deux agents travaillent **en même temps** (parallèle), ce qui réduit la latence de moitié.

### Cas 3 — Mono-agent (un seul agent A2A)

```python
discovered_agent = await discovery.find_agent_by_name(target_agent)
agent_url = discovered_agent.url  # ex: "http://localhost:8001"

# Construit le message enrichi
message = (
    f"Date du jour : 2026-03-31 (mardi)\n"
    f"Historique récent (LECTURE SEULE) :\n"
    f"Utilisateur: pose un congé lundi\n"
    f"---\n"
    f"INSTRUCTION À EXÉCUTER MAINTENANT :\n"
    f"pose un congé lundi\n"
    f"---\n"
    f"Role utilisateur : consultant\n"
    f"User ID : 12"
)

response = await send_task_to_url(agent_url, message)
return {**state, "final_response": response}
```

**Pourquoi enrichir le message ?** L'agent spécialisé (RH, Calendar) ne connaît pas la date, l'historique ou le rôle de l'utilisateur. On lui injecte tout dans le corps du message.

---

## ÉTAPE 5 — Client A2A : Communication inter-agents

**Fichier :** `backend/app/a2a/client.py`
**Fonction :** `async def send_task_to_url(agent_url, user_message) -> str`
**Tracé LangSmith :** `a2a.send_task`

```python
async with httpx.AsyncClient(timeout=300, headers={"Authorization": f"Bearer {A2A_SECRET}"}) as client:
    client = await ClientFactory.connect(agent_url, ...)
    message = create_text_message_object(content=user_message)

    async for response in client.send_message(message):
        if isinstance(response, Message):
            text_content = get_message_text(response)
        # ...

return text_content  # ex: '{"response": "Congé créé pour le lundi...", "react_steps": [...]}'
```

**Protocole A2A (Agent-to-Agent) :** Standard développé par Google. Permet à des agents indépendants de communiquer via HTTP. Chaque agent expose :
- `GET /.well-known/agent.json` : sa "carte de visite" (skills, description)
- `POST /` : reçoit les messages et retourne des réponses

**Sécurité :** Un token Bearer (`A2A_SECRET_TOKEN`) est inclus dans chaque requête. L'agent vérifie ce token avant de traiter.

---

## ÉTAPE 6 — Agent RH : Exécution ReAct

**Fichier :** `backend/agents/rh/agent.py`
**Classe :** `RHAgentExecutor`
**Méthode :** `async def execute(context, event_queue)`
**Tracé LangSmith :** `rh_agent.execute`

L'agent fonctionne avec le pattern **ReAct (Reason + Act)** :

```
Pensée (Think) : "L'utilisateur veut poser un congé lundi. Je dois d'abord
                  vérifier son solde, puis créer la demande."

Action (Act)   : appel d'outil → create_leave(user_id=12, start="2026-04-06", ...)

Observation    : "Congé créé avec succès. Solde restant: 20 jours."

Réponse finale : "Votre congé du lundi 6 avril a été créé avec succès.
                  Il reste 20 jours dans votre solde."
```

### Implémentation

```python
result = await self.react_agent.ainvoke({
    "messages": [HumanMessage(content=user_input)]
})
# user_input = le message enrichi construit par Node 3
```

`self.react_agent` est créé avec `create_react_agent(model=llm, tools=TOOLS, prompt=RH_REACT_PROMPT)`.

**TOOLS** sont définies dans `backend/agents/rh/tools.py` : `create_leave`, `cancel_leave`, `get_leave_balance`, `list_leaves`, `get_team_availability`, etc.

Chaque tool est une fonction Python décorée avec `@tool` qui fait des appels SQL à la base de données PostgreSQL.

### Failover des clés API Groq

```python
max_retries = 3
for attempt in range(max_retries):
    try:
        result = await self.react_agent.ainvoke(...)
        break
    except Exception as e:
        if _is_quota_error(e):      # "tokens per minute" → inutile de changer de clé
            return FRIENDLY_QUOTA_MSG
        elif _is_fallback_error(e): # "rate_limit_exceeded" → changer de clé
            rotate_llm_key()
            self._build_react_agent()  # reconstruit avec la nouvelle clé
            continue
```

### Rotation des clés par PID

**Fichier :** `backend/app/core/groq_client.py`
**Fonction :** `_load_keys()`

```python
# Ex: 3 clés dans le .env : GROQ_API_KEY_1, GROQ_API_KEY_2, GROQ_API_KEY_3
# Agent RH   (PID=1234) : offset = 1234 % 3 = 2 → démarre sur clé 3
# Agent Cal  (PID=5678) : offset = 5678 % 3 = 1 → démarre sur clé 2
# Orchestrat (PID=9012) : offset = 9012 % 3 = 0 → démarre sur clé 1
# → Chaque processus utilise une clé différente en parallèle
```

### Output de l'agent

L'agent retourne un JSON stringifié :
```json
{
    "response": "Votre congé du lundi 6 avril a été créé avec succès. Solde restant : 20 jours.",
    "react_steps": [
        "📋 Vérification du solde de congés\n   → 22 jours disponibles",
        "✅ Création du congé du 06/04/2026\n   → ID #47, statut : en attente d'approbation"
    ]
}
```

Ce JSON revient via HTTP A2A → `send_task_to_url` → `final_response` dans le state LangGraph.

---

## ÉTAPE 7 — Node 4 : Sauvegarde dans le state

**Fichier :** `backend/app/orchestrator/graph.py`
**Fonction :** `node4_save_ai_message(state)`

```python
def node4_save_ai_message(state):
    final_response = state.get("final_response", "")

    # Parse le JSON si c'est du JSON (ex: réponse de l'agent RH)
    try:
        parsed = json.loads(final_response)
        clean_response = parsed.get("response", final_response)
    except:
        clean_response = final_response

    # Ajoute le message AI dans la liste des messages
    return {
        **state,
        "messages": [AIMessage(content=clean_response)]
        # ↑ add_messages l'AJOUTE à la liste (n'écrase pas)
    }
```

**Pourquoi ce nœud ?** LangGraph checkpoint sauvegarde `state["messages"]`. En ajoutant ici l'AIMessage, la prochaine requête aura l'historique complet pour FAST PATH 3 (continuation de contexte).

---

## ÉTAPE 8 — Retour à FastAPI

**Fichier :** `backend/app/api/chat.py` (suite de la fonction `chat`)

```python
result = await graph.ainvoke(...)  # retourne ici

# Parse la réponse finale
raw_response = result["final_response"]  # le JSON de l'agent ou texte simple

parsed = json.loads(raw_response)
final_text  = parsed.get("response", raw_response)
react_steps = parsed.get("react_steps", [])
ui_hint     = parsed.get("ui_hint")  # ex: {"type": "date_range"} pour picker de date

# Détecte ui_hint si absent (ex: l'agent demande une date → afficher un sélecteur)
if ui_hint is None:
    ui_hint = _detect_ui_hint(final_text)

# Sauvegarde les messages dans la DB
db.add(Message(conversation_id=conv.id, role="user",      content=request.message))
db.add(Message(conversation_id=conv.id, role="assistant", content=final_text,
               intent=target_agent, target_agent=target_agent))
await db.commit()

# Retourne au frontend
return ChatResponse(
    response=final_text,
    intent="rh",
    target_agent="rh",
    conversation_id=42,
    steps=[ReActStep(status="done", text="📋 Vérification du solde...")],
    ui_hint=None,
)
```

---

## ÉTAPE 9 — Le Frontend reçoit et affiche

Le frontend React reçoit la `ChatResponse` et :
- Affiche `response` comme message de l'assistant
- Affiche `steps` en accordéon (les étapes ReAct)
- Si `ui_hint.type === "date_range"` → affiche un sélecteur de dates

---

## Résumé des fichiers par étape

| Étape | Fichier | Fonction |
|-------|---------|----------|
| 0 | `client/src/pages/Chat.jsx` | Envoi HTTP |
| 1 | `backend/app/api/chat.py` | `chat()` |
| 1 | `backend/app/core/security.py` | `get_current_user()` |
| 2 | `backend/app/orchestrator/graph.py` | `init_graph()`, `get_graph()` |
| 2 | `backend/app/orchestrator/state.py` | `AssistantState` |
| 3 | `backend/app/orchestrator/nodes/node1_intent.py` | `node1_detect_intent()` |
| 3bis | `backend/app/a2a/discovery.py` | `scan_agents()`, `build()` |
| 4 | `backend/app/orchestrator/nodes/node3_dispatch.py` | `node3_dispatch()` |
| 5 | `backend/app/a2a/client.py` | `send_task_to_url()` |
| 6 | `backend/agents/rh/agent.py` | `execute()` |
| 6 | `backend/agents/rh/tools.py` | tools SQL |
| 6 | `backend/app/core/groq_client.py` | `build_llm()`, `rotate_llm_key()` |
| 7 | `backend/app/orchestrator/graph.py` | `node4_save_ai_message()` |
| 8 | `backend/app/api/chat.py` | Suite de `chat()` |

---

## LangSmith — Observabilité

Toutes les étapes clés sont tracées dans LangSmith (`LANGCHAIN_PROJECT=talan-assistant`) :

| Span LangSmith | Ce qu'il montre |
|----------------|-----------------|
| `node1_detect_intent` | Message entrant → `target_agent` choisi |
| `discovery.scan_agents` | Agents disponibles |
| `discovery.find_agent` | URL de l'agent ciblé |
| `node3_dispatch` | Dispatch mono ou multi-agent |
| `a2a.send_task` | Message envoyé à l'agent + réponse brute |
| `rh_agent.execute` | Input complet + steps ReAct + réponse finale |
| `calendar_agent.execute` | Idem pour le calendrier |

---

## Gestion des erreurs

| Erreur | Où | Comportement |
|--------|-----|--------------|
| LLM indisponible (Node 1) | `node1_intent.py` | fallback keyword match |
| Rate limit Groq (agent) | `agent.py` | rotation de clé → retry |
| Token quota dépassé | `agent.py` | message convivial sans retry |
| Agent A2A down | `node3_dispatch.py` | message "agent indisponible" |
| toutes clés épuisées | `groq_client.py` | message d'erreur final |
| JSON mal formé (agent) | `chat.py` | `final_text = raw_response` (texte brut) |
