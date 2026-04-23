# Cycle de vie des IDs — Phase 2 (Epics) → Phase 3 (Stories) → Phase 4 (Raffinement) → Jira

Ce document répond à la question : **qui crée les IDs, quand, et comment ils circulent ?**

---

## Vue d'ensemble

```
Phase 2 — Epics          Phase 3 — Stories        Phase 4 — Raffinement    Jira sync
──────────────────        ──────────────────        ─────────────────────    ─────────
LLM génère epics          LLM génère stories        LLM propose patches      PM valide
(pas d'ID)                (epic_id = local 0,1,2)   (story_local_idx)        → Jira crée issues
    │                          │                          │                       │
    ▼                          ▼                          ▼                       ▼
save_epics()              save_stories()            apply_patches_enriched  node_jira_sync
INSERT → epic.id          INSERT → story.id         local_idx → db_id       → jira_issue_key
(PAS écrit dans dict)     db_id écrit dans dict     UPDATE WHERE db_id      UPDATE user_story
    │                          │                          │                       │
    ▼                          ▼                          ▼                       ▼
state["epics"]            state["stories"]          state["refined_stories"]  jira_story_map
(index = position)        (db_id présent)           (db_id présent)           epic.jira_epic_key
```

**Différence clé epics vs stories** :
- Epics : `save_epics()` ne réécrit **pas** l'ID dans les dicts. Les epics sont identifiés par leur **position** dans la liste triée.
- Stories : `save_stories()` réécrit **explicitement** `db_id` dans chaque dict. Les stories sont identifiées par `db_id` partout.

---

## Phase 2 — Génération des Epics

### 2a — Génération LLM (sans IDs)

**Fichier** : `agents/pm/agents/epics/service.py`

Le LLM lit le CDC (cahier des charges) et génère les epics en JSON brut.  
**Le LLM ne crée aucun ID.** Il retourne simplement une liste de dicts :

```json
[
  { "title": "Gestion des utilisateurs", "description": "...", "splitting_strategy": "by_user_role" },
  { "title": "Tableau de bord", "description": "...", "splitting_strategy": "by_feature" },
  { "title": "Notifications", "description": "...", "splitting_strategy": "by_workflow_step" }
]
```

À ce stade : **aucun ID** dans les dicts.

### 2b — Insertion en base

**Fichier** : `agents/pm/agents/epics/repository.py` → `save_epics()`

```python
orm_epics = [
    Epic(project_id=project_id, title=epic["title"], ...)
    for epic in epics
]
session.add_all(orm_epics)
await session.commit()

for e in orm_epics:
    await session.refresh(e)   # charge l'ID auto-incrémenté depuis PostgreSQL

# ← PostgreSQL affecte : orm_epics[0].id = 42, orm_epics[1].id = 43, ...
```

**Important** : `save_epics()` ne réécrit **PAS** `db_id` dans les dicts epic.  
Les dicts retournés dans le state n'ont toujours pas d'ID explicite.

### 2c — Propagation dans le state

**Fichier** : `agents/pm/agents/epics/agent.py` → `node_epics()`

```python
return {
    "epics": epics,   # ← liste de dicts SANS db_id
    "current_phase": "epics",
    ...
}
```

Les epics dans le state ressemblent à :

```json
[
  { "title": "Gestion des utilisateurs", "description": "...", "splitting_strategy": "by_user_role" },
  { "title": "Tableau de bord", "description": "...", "splitting_strategy": "by_feature" }
]
```

**Comment les epics sont-ils identifiés ensuite ?**  
Par leur **position dans la liste** (index 0, 1, 2…).  
La Phase 3 fait `SELECT epics ORDER BY epic.id` → `db_epics[0].id = 42` correspond à `state["epics"][0]`.  
L'ordre d'insertion préserve la correspondance position ↔ ID DB.

### 2d — Jira sync pour les epics

**Fichier** : `agents/pm/graph/node_jira_sync.py` + `agents/pm/agents/epics/repository.py`

Après validation PM de la Phase 2 :

```python
# node_jira_sync crée un Epic Jira et écrit la clé en DB
await update_epic_jira_key(epic_db_id=orm_epics[i].id, jira_key="PROJ-1")
# UPDATE epic SET jira_epic_key="PROJ-1" WHERE id=42
```

Le `jira_epic_key` est stocké dans `jira_epic_map` dans le state.

---

## Phase 3 — Génération des User Stories

### 3a — Génération LLM (epic_id = index local)

**Fichier** : `agents/pm/agents/stories/react_agent.py`

Le LLM reçoit la liste des epics dans son prompt (dans l'ordre du state).  
Il génère les stories avec `epic_id` = **index de l'epic dans ce tableau** (0, 1, 2…).  
Ce n'est **pas** l'ID PostgreSQL de l'epic.

```json
[
  { "epic_id": 0, "title": "En tant qu'admin, je veux créer un utilisateur...", "story_points": 3, "acceptance_criteria": ["..."] },
  { "epic_id": 0, "title": "En tant qu'utilisateur, je veux me connecter...", "story_points": 5, ... },
  { "epic_id": 1, "title": "En tant que manager, je veux voir le tableau de bord...", "story_points": 2, ... }
]
```

À ce stade : **aucun `db_id`**, aucun vrai ID PostgreSQL dans les dicts.

### 3b — Insertion en base avec mapping epic_id → ID DB réel

**Fichier** : `agents/pm/agents/stories/repository.py` → `save_stories()`

C'est ici que le mapping entre l'index LLM et le vrai ID DB est résolu :

```python
# 1. Récupère les epics du projet triés par leur ID PostgreSQL
db_epics = SELECT Epic WHERE project_id=X ORDER BY Epic.id
# → db_epics[0].id = 42  (epic "Gestion des utilisateurs")
# → db_epics[1].id = 43  (epic "Tableau de bord")

# 2. Construit le mapping : index LLM → vrai ID DB epic
index_to_db_id = {i: e.id for i, e in enumerate(db_epics)}
# → {0: 42, 1: 43, 2: 44}

# 3. Insert avec l'ID DB réel de l'epic
orm_s = UserStory(
    epic_id = index_to_db_id[s["epic_id"]],  # ex: epic_id=0 → 42
    title   = s["title"],
    ...
)
```

Après commit et refresh :

```python
# 4. Écrit db_id dans le dict Python (contrairement à save_epics !)
for story_dict, orm_s in zip(saved_dicts, orm_stories):
    story_dict["db_id"] = orm_s.id   # ex: 101, 102, 103...
```

Chaque story dict après `save_stories()` :

```json
{
  "epic_id": 0,
  "db_id": 101,
  "title": "En tant qu'admin...",
  "story_points": 3,
  "acceptance_criteria": ["L'admin peut saisir nom, email, rôle", "..."]
}
```

**Rappel** : `epic_id=0` dans le dict reste l'index local LLM, **pas** l'ID DB de l'epic (42).

### 3c — Propagation dans le state

**Fichier** : `agents/pm/agents/stories/agent.py` → `node_stories()`

```python
return {
    "stories": stories,   # ← liste avec db_id déjà écrit
    ...
}
```

Ces dicts sont stockés dans :
- Le checkpoint LangGraph (en mémoire du graph)
- La colonne `ai_output` JSONB de `pipeline_states`

```
pipeline_states.ai_output = {
  "stories": [
    { "db_id": 101, "epic_id": 0, "title": "...", "story_points": 3, ... },
    { "db_id": 102, "epic_id": 0, "title": "...", "story_points": 5, ... },
    { "db_id": 103, "epic_id": 1, "title": "...", "story_points": 2, ... }
  ]
}
```

---

## Phase 4 — Raffinement PO ↔ Tech Lead

### 4a — Lecture depuis le state (pas depuis la DB)

**Fichier** : `agents/pm/agents/refinement/agent.py`

```python
stories = state.get("stories", [])   # db_id présent depuis Phase 3
epics   = state.get("epics",   [])   # PAS de db_id (identifiés par position)
```

**Pourquoi le state et pas la DB ?**  
Le state LangGraph est la source de vérité en cours de pipeline. La DB représente l'état *persisté validé*. Pendant le raffinement, le PM peut revertir story par story — le state gère cet état intermédiaire.

### 4b — Les LLMs (PO/TL) utilisent story_local_idx

**Fichiers** : `tools/po_review.py`, `tools/tech_review.py`

Le LLM reçoit les stories **d'un seul epic** avec leur indice local (0, 1, 2 dans l'epic).  
Il produit des patches avec `story_local_idx` :

```json
[
  { "story_local_idx": 0, "field": "story_points", "new_value": 5, "reason": "Trop complexe" },
  { "story_local_idx": 1, "field": "acceptance_criteria", "action": "add", "value": "Valider le format email" }
]
```

**Le LLM ne connaît pas les `db_id`** — voulu, pour ne pas polluer le prompt avec des détails techniques.

### 4c — Conversion local_idx → db_id dans apply_patches_enriched()

**Fichier** : `agents/pm/agents/refinement/tools/patch.py`

```python
# Pour l'epic_id (index local = 0, 1, 2...)
epic_indices = [i for i, s in enumerate(stories) if s.get("epic_id") == epic_id]
# ex: epic_id=0 → epic_indices = [0, 1]  (positions dans current_stories)

# local_idx=0 → global_idx=0 → stories[0].db_id = 101
global_idx = epic_indices[local_idx]
story      = stories[global_idx]
db_id      = story.get("db_id")   # 101
```

Le patch enrichi inclut maintenant le `db_id` :

```json
{
  "story_local_idx": 0,
  "field": "story_points",
  "old_value": 3,
  "new_value_applied": 5,
  "db_id": 101,
  "epic_id": 0,
  "applied": true
}
```

### 4d — Sauvegarde en base via db_id

**Fichier** : `agents/pm/agents/refinement/repository.py` → `save_refined_stories()`

```python
for story in refined_stories:
    db_id = story.get("db_id")   # lu depuis le state, pas de SELECT
    await session.execute(
        sa_update(UserStory)
        .where(UserStory.id == db_id)   # UPDATE ciblé par db_id
        .values(title=..., story_points=5, status="refined")
    )
```

Pas de SELECT, pas de reconstruction — `db_id` était présent depuis Phase 3.

---

## Phase Jira — Synchronisation après validation PM

**Fichier** : `agents/pm/graph/node_jira_sync.py`

Déclenché automatiquement après chaque "Valider" du PM sur une phase.

### Pour les epics (après validation Phase 2)

```python
patch = await _sync_epics(state)
# Pour chaque epic : POST Jira API → crée un Epic Jira
# update_epic_jira_key(epic_db_id=42, jira_key="PROJ-1")
# UPDATE epic SET jira_epic_key="PROJ-1" WHERE id=42
```

### Pour les stories (après validation Phase 3)

```python
patch = await _sync_stories(state)
# Pour chaque story : POST Jira API → crée une User Story Jira
# update_story_jira_key(story_db_id=101, jira_key="PROJ-42")
# UPDATE user_story SET jira_issue_key="PROJ-42" WHERE id=101
```

Les clés Jira sont aussi stockées dans le state :

```python
jira_epic_map  = { 0: "PROJ-1",  1: "PROJ-2"  }   # index epic → clé Jira
jira_story_map = { 0: "PROJ-42", 1: "PROJ-43" }    # index story → clé Jira
```

**Avant la validation** : `jira_epic_key` et `jira_issue_key` sont NULL en DB.  
**Après la validation** : clés Jira écrites en DB et dans le state.

---

## Récapitulatif — Tableau de tous les IDs

| Identifiant         | Exemple         | Qui le crée                  | Quand                                    | Où il vit                                    | Écrit dans dict ?       |
|---------------------|-----------------|------------------------------|------------------------------------------|----------------------------------------------|-------------------------|
| `epic_id` (LLM)     | `0`, `1`, `2`   | LLM Phase 2                  | Génération epics                         | Prompt LLM + story dict Python               | Oui (index local)       |
| `epic.id` (DB)      | `42`, `43`      | PostgreSQL (auto-incr.)      | Phase 2 `save_epics()` INSERT            | DB `pm.epics` + ORM object                   | **Non** (pas dans dict) |
| `story.db_id`       | `101`, `102`    | PostgreSQL (auto-incr.)      | Phase 3 `save_stories()` INSERT          | DB + state LangGraph + `ai_output` JSONB     | **Oui** (`db_id`)       |
| `story_local_idx`   | `0`, `1`, `2`   | Code Python (enumerate)      | Lors du passage au LLM Phase 4           | Prompt LLM + patches LLM                     | Oui (temporaire)        |
| `epic.jira_epic_key`| `"PROJ-1"`      | API Jira (externe)           | Après validation Phase 2 → `node_jira_sync` | DB `pm.epics` + `jira_epic_map` state     | Via `jira_epic_map`     |
| `story.jira_issue_key` | `"PROJ-42"` | API Jira (externe)           | Après validation Phase 3 → `node_jira_sync` | DB `pm.user_stories` + `jira_story_map`  | Via `jira_story_map`    |

---

## Schéma complet du flux

```
PHASE 2 — Génération Epics
──────────────────────────
LLM génère epics (aucun ID)
    │
    ▼
save_epics(project_id, epics)
    │  DELETE existing epics
    │  INSERT Epic(project_id, title, ...)
    │  COMMIT
    │  REFRESH → orm_epics[0].id=42, orm_epics[1].id=43
    │  ⚠ db_id NON écrit dans les dicts
    ▼
state["epics"] = [
  { "title": "Gestion utilisateurs", "splitting_strategy": "by_user_role" },   ← index 0 = epic.id 42
  { "title": "Tableau de bord",      "splitting_strategy": "by_feature"   },   ← index 1 = epic.id 43
]
    │
    ▼  [validation PM]
node_jira_sync (phase="epics")
    │  POST Jira → Epic "Gestion utilisateurs" → key="PROJ-1"
    │  UPDATE epic SET jira_epic_key="PROJ-1" WHERE id=42
    ▼
jira_epic_map = { 0: "PROJ-1", 1: "PROJ-2" }


PHASE 3 — Génération Stories
─────────────────────────────
LLM génère stories (epic_id=0,1,2 — index local, PAS de db_id)
    │
    ▼
save_stories(project_id, stories)
    │  SELECT epics ORDER BY id → [id=42, id=43]
    │  index_to_db_id = {0: 42, 1: 43}
    │  DELETE existing stories
    │  INSERT UserStory(epic_id=42, title="En tant qu'admin...")
    │  COMMIT
    │  REFRESH → orm_s.id = 101  ← PostgreSQL affecte l'ID
    │  story_dict["db_id"] = 101  ← écrit dans le dict Python ✓
    ▼
state["stories"] = [
  { "db_id": 101, "epic_id": 0, "title": "En tant qu'admin...", "story_points": 3 },
  { "db_id": 102, "epic_id": 0, "title": "En tant qu'user...",  "story_points": 5 },
  { "db_id": 103, "epic_id": 1, "title": "En tant que manager...", "story_points": 2 },
]
ai_output JSONB : { "stories": [{ "db_id": 101, ... }, ...] }
    │
    ▼  [validation PM]
node_jira_sync (phase="stories")
    │  POST Jira → Story "En tant qu'admin..." → key="PROJ-42"
    │  UPDATE user_story SET jira_issue_key="PROJ-42" WHERE id=101
    ▼
jira_story_map = { 0: "PROJ-42", 1: "PROJ-43", 2: "PROJ-44" }


PHASE 4 — Raffinement
─────────────────────
node_refinement lit stories depuis state (db_id présent)
    │
    ▼
run_one_round(stories, epics, round_number=1)
    │  Pour epic_id=0 :
    │    PO review → patches [{ story_local_idx:0, field:"story_points", new_value:5 }]
    │    TL review → patches [{ story_local_idx:1, field:"acceptance_criteria", ... }]
    │    merge_patches()
    │    apply_patches_enriched()
    │      local_idx=0 → epic_indices=[0,1] → global_idx=0 → db_id=101
    │      → patch enrichi : { db_id:101, old_value:3, new_value_applied:5 }
    ▼
save_refined_stories(project_id, refined_stories)
    │  UPDATE user_story SET story_points=5, status="refined" WHERE id=101
    ▼
state["refined_stories"] = [{ "db_id": 101, "story_points": 5, ... }, ...]
```

---

## Questions fréquentes

**Pourquoi `save_epics()` n'écrit pas `db_id` dans les dicts, contrairement à `save_stories()` ?**  
Les epics sont identifiés par leur position dans la liste triée — c'est suffisant car `save_stories()` fait le mapping `index → epic.id` avec un SELECT. Les stories ont besoin de `db_id` dans leur dict car le raffinement les manipule individuellement (patch par patch), pas en groupe.

**Le frontend envoie-t-il des IDs au backend ?**  
Non. Le backend lit toujours les `db_id` depuis le state LangGraph. Le frontend envoie uniquement `project_id` dans l'URL.

**Si le PM rejette et relance Phase 2 (epics), que se passe-t-il avec les IDs des stories ?**  
`save_epics()` supprime les epics existants. La suppression des epics entraîne (CASCADE) la suppression des stories liées. Quand la Phase 3 regénère les stories, de nouveaux IDs PostgreSQL sont assignés.

**Si le PM rejette et relance Phase 3 (stories) sans toucher les epics, les `db_id` changent ?**  
Oui. `save_stories()` supprime toutes les stories et réinsère → nouveaux IDs. Les anciens `db_id` dans le state ne sont plus valides. Le state est mis à jour avec les nouveaux `db_id`.

**Les IDs dans les patches LLM sont-ils les db_id ?**  
Non. Le LLM utilise `story_local_idx` (0, 1, 2 dans l'epic courant). La conversion `local_idx → db_id` est faite dans `apply_patches_enriched()` côté Python, jamais par le LLM.

**Quand sont créés les IDs Jira ?**  
Uniquement après la validation PM de chaque phase. La génération LLM ne crée aucun objet Jira.
