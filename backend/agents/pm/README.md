# Pipeline PM — Documentation Technique Complète

> **Destinataire :** juriste/rapporteur technique — chaque détail d'implémentation, flux de données, gestion d'IDs, appels de fonctions et cas métier est documenté ici.

---

## Table des matières

1. [Vue d'ensemble](#1-vue-densemble)
2. [Architecture LangGraph](#2-architecture-langgraph)
3. [State partagé (PMPipelineState)](#3-state-partagé-pmpipelinestate)
4. [Phase 2 — Génération des Epics](#4-phase-2--génération-des-epics)
5. [Phase 3 — Génération des User Stories](#5-phase-3--génération-des-user-stories)
6. [Phase 4 — Raffinement PO ↔ Tech Lead](#6-phase-4--raffinement-po--tech-lead)
7. [Gestion des IDs (epic_id, db_id, story_id)](#7-gestion-des-ids)
8. [Validation humaine & feedback](#8-validation-humaine--feedback)
9. [API REST — Endpoints du pipeline](#9-api-rest--endpoints-du-pipeline)
10. [Chaîne d'appels complète (qui appelle qui)](#10-chaîne-dappels-complète)
11. [Schéma de la base de données](#11-schéma-de-la-base-de-données)
12. [Modèle LLM & gestion des erreurs](#12-modèle-llm--gestion-des-erreurs)

---

## 1. Vue d'ensemble

Le pipeline PM est un **orchestrateur LangGraph de 12 phases** qui transforme un **Cahier des Charges (CDC)** en un plan projet complet : epics → stories → raffinement → dépendances → prioritisation → tâches → CPM → sprints → staffing → monitoring.

```
CDC (PDF/DOCX)
    │
    ▼
[Phase 1] Extraction texte + analyse VLM
    │
    ▼ validation PM
[Phase 2] Génération Epics        ← sujet principal de ce README
    │
    ▼ validation PM
[Phase 3] Génération User Stories ← sujet principal de ce README
    │
    ▼ validation PM
[Phase 4] Raffinement PO ↔ TL     ← sujet principal de ce README
    │
    ▼ validation PM
[Phases 5-12] deps / priorisation / tâches / CPM / sprints / staffing / monitoring
    │
    ▼
Projet complet en DB + Jira (optionnel)
```

**Technologie :** Python 3.11+, FastAPI, LangGraph, SQLAlchemy async, PostgreSQL, modèle LLM `openai/gpt-oss-120b` via `invoke_with_fallback`.

---

## 2. Architecture LangGraph

### Fichier : `agents/pm/graph/graph.py`

Le graph est construit avec `StateGraph(PMPipelineState)`. Chaque phase est un **nœud**, et la logique de routage est déterministe (pas de LLM dans le routeur).

### Schéma des nœuds et arêtes

```
node_extraction
    │ (edge)
    ▼
node_validate ──(validated)──► jira_sync ──► node_epics
    │                                             │
    │ (rejected)                                  │ (edge)
    ▼                                             ▼
node_extraction (relancé avec feedback)      node_validate ──(validated)──► jira_sync ──► node_stories
                                                  │
                                                  │ (rejected)
                                                  ▼
                                             node_epics (relancé avec feedback)
```

Ce pattern `phase → node_validate → [jira_sync → phase_suivante | retour_phase]` se répète pour chaque phase.

### Routeur `_route_after_validate()`

```python
def _route_after_validate(state: PMPipelineState) -> str:
    if state.get("validation_status") == "validated":
        return "jira_sync"          # → phase suivante
    phase = state.get("current_phase", "")
    return _PHASE_TO_NODE.get(phase, END)  # → retour à la phase pour regen
```

- `validation_status == "validated"` → avancer
- `validation_status == "rejected"` → retourner au nœud de la même phase qui relira `human_feedback` dans le state

### Persistance (checkpointer)

```python
conn = await psycopg.AsyncConnection.connect(DB_URI, autocommit=True)
checkpointer = AsyncPostgresSaver(conn)
pm_graph = build_pm_graph(checkpointer)
```

- Chaque nœud checkpoint son état en PostgreSQL sous `thread_id = f"pm_{project_id}"` (ex: projet id=5 → `"pm_5"`)
- Permet la reprise après interruption (serveur redémarré, timeout réseau…)
- `aupdate_state(config, values)` injecte des valeurs dans le state AVANT de reprendre

### Ordre des phases

```python
_PHASE_ORDER = [
    "extract", "epics", "stories", "refinement",
    "story_deps", "prioritization", "tasks", "task_deps",
    "cpm", "sprints", "staffing", "monitoring",
]
```

---

## 3. State partagé (PMPipelineState)

### Fichier : `agents/pm/state/state.py`

`PMPipelineState` est un `TypedDict` Python qui circule entre tous les nœuds. Chaque nœud lit les champs dont il a besoin et écrit uniquement ses champs de sortie.

### Champs critiques pour les phases 2-4

| Champ | Type | Produit par | Utilisé par |
|-------|------|------------|------------|
| `cdc_text` | `str` | node_extraction | node_epics, node_stories |
| `epics` | `list[dict]` | node_epics | node_stories, node_refinement |
| `stories` | `list[dict]` | node_stories | node_refinement |
| `refined_stories` | `list[dict]` | node_refinement | phases suivantes |
| `human_feedback` | `Optional[str]` | API /validate | node_epics, node_stories, node_refinement |
| `targeted_epic_ids` | `Optional[list]` | API /validate | node_epics |
| `targeted_story_ids` | `Optional[list]` | API /validate | node_stories |
| `validation_status` | `str` | node_validate | routeur |
| `current_phase` | `str` | chaque nœud | routeur |
| `project_id` | `int` | lancement pipeline | tous les nœuds |

### Structure d'un epic dans le state

```python
{
    "title":              "Gestion des candidats",
    "description":        "Permet aux recruteurs de...",
    "splitting_strategy": "by_feature"   # ou by_user_role, by_workflow_step, by_component
    # NOTE : pas de db_id ici — le state ne stocke pas les IDs DB des epics
}
```

### Structure d'une story dans le state

```python
{
    "epic_id":             0,            # INDEX de l'epic dans la liste (pas l'ID DB)
    "title":               "En tant que recruteur, je veux...",
    "description":         "Contexte fonctionnel...",
    "story_points":        3,            # Fibonacci : {1, 2, 3, 5, 8}
    "acceptance_criteria": ["Étant donné..., quand..., alors..."],
    "splitting_strategy":  "by_feature",
    "db_id":               42,           # ID DB — injecté après save_stories()
    "_review":             {             # Injecté par react_agent après review
        "coverage_ok": True,
        "gaps": [],
        "scope_creep_issues": [],
        "quality_issues": [],
        "suggestions": []
    }
}
```

---

## 4. Phase 2 — Génération des Epics

### Vue d'ensemble des fichiers

```
agents/pm/agents/epics/
├── agent.py        ← Nœud LangGraph — orchestre les 3 cas
├── service.py      ← Logique LLM — génération et amélioration
├── repository.py   ← Persistance DB (CRUD epics)
└── prompt.py       ← Prompts système et utilisateur
```

---

### 4.1 Nœud principal : `node_epics()` — `agent.py`

```python
async def node_epics(state: PMPipelineState) -> dict:
    project_id        = state.get("project_id")
    cdc_text          = state.get("cdc_text", "")
    human_feedback    = state.get("human_feedback")
    targeted_epic_ids = state.get("targeted_epic_ids") or []
    existing_epics    = state.get("epics", [])
```

**Décision :** Le nœud distingue 3 cas selon ce qui est présent dans le state :

```
human_feedback ──────────────────────────────────────────────────────┐
    │                                                                 │
    ├── None → CAS 1 : première génération                           │
    │                                                                 │
    └── Set ──────────────────────────────────────────────────────┐   │
             targeted_epic_ids ────────────────────────────────┐  │  │
                 │                                             │  │  │
                 ├── non vide → CAS 3 : rejet ciblé           │  │  │
                 │                                             │  │  │
                 └── vide + existing_epics → CAS 2 : global   │  │  │
```

---

### 4.2 CAS 1 — Première génération

**Déclencheur :** `human_feedback is None` (ou pas d'epics existants)

**Chaîne d'appels :**
```
node_epics()
    └── generate_epics(cdc_text, human_feedback=None)   [service.py]
            └── invoke_with_fallback(model, messages, max_tokens=4096)
                    └── LLM → JSON { "epics": [...] }
            └── _normalize_epics(raw_list)              [service.py]
            └── supprime db_id des résultats
    └── save_epics(project_id, epics)                   [repository.py]
            └── DELETE FROM pm.epics WHERE project_id=X
            └── INSERT INTO pm.epics (title, description, splitting_strategy, ...)
            └── session.refresh(orm_e) → récupère les IDs générés
    └── _done(epics) → { epics, current_phase="epics", validation_status="pending_human", ... }
```

**Prompt système** (`EPICS_SYSTEM_PROMPT` dans `prompt.py`) :
```
"Génère entre 3 et 8 epics maximum selon la taille du projet.
 Chaque epic doit être autonome et livrable indépendamment.
 splitting_strategy doit refléter la meilleure façon de découper CET epic en stories."
```

**Prompt utilisateur** (fonction `build_epics_prompt()` dans `prompt.py`) :
- Inclut le CDC complet
- Si `human_feedback` est présent : section `⚠️ CORRECTIONS DEMANDÉES PAR LE PM` ajoutée
- JSON attendu :
  ```json
  { "epics": [{ "title": "...", "description": "...", "splitting_strategy": "..." }] }
  ```

**`save_epics()` dans `repository.py` :**
```python
async def save_epics(project_id: int, epics: list[dict]) -> list[Epic]:
    # 1. Supprime les anciens epics (DELETE CASCADE → stories supprimées aussi)
    await session.execute(delete(Epic).where(Epic.project_id == project_id))
    # 2. Insère les nouveaux avec status=DRAFT
    orm_epics = [Epic(project_id=..., title=..., splitting_strategy=..., status=EpicStatusEnum.DRAFT) for epic in epics]
    session.add_all(orm_epics)
    await session.commit()
    # 3. Refresh pour récupérer les IDs auto-générés
    for e in orm_epics: await session.refresh(e)
    return orm_epics
```

**IMPORTANT :** `save_epics` fait un DELETE complet avant d'insérer. Si le PM rejette et régénère depuis le CAS 1, toutes les stories liées sont supprimées en cascade.

---

### 4.3 CAS 2 — Rejet global (feedback sur tous les epics)

**Déclencheur :** `human_feedback` défini + `targeted_epic_ids` vide + `existing_epics` non vide

**Problème résolu :** Avant cette implémentation, un feedback global appelait `generate_epics(cdc_text, feedback)` qui régénérait depuis le CDC sans connaître les epics existants → le LLM créait de nouveaux epics au lieu de modifier les existants.

**Solution :** `improve_all_epics()` passe les epics existants **avec leurs db_id** au LLM.

**Chaîne d'appels :**
```
node_epics()
    └── _global_regen(project_id, existing_epics, cdc_text, feedback)   [agent.py]
            └── get_epics(project_id)                                    [repository.py]
                    └── SELECT * FROM pm.epics WHERE project_id=X ORDER BY id
            └── enrichit les epics avec db_id depuis la DB
                (matching par INDEX : existing_epics[i] ↔ db_epics[i])
            └── original_db_ids = [e["db_id"] for e in epics_with_db_id]
            └── improve_all_epics(epics_with_db_id, cdc_text, feedback) [service.py]
                    └── _call_llm(prompt, max_tokens=3000)
                            └── invoke_with_fallback(...)
                            └── _normalize_epics(data["epics"])
            └── _apply_improved_epics(project_id, improved, original_db_ids)
                    └── [SUPPRESSION] pour chaque db_id absent du retour LLM → delete_epic()
                    └── [UPDATE] pour chaque epic avec db_id existant → update_epic()
                    └── [INSERT] pour chaque epic avec db_id=null → add_epic()
                    └── _reload_epics(project_id)
                            └── get_epics(project_id) → list[Epic]
                            └── retourne dicts sans db_id (format state)
```

**Prompt `improve_all_epics()` dans `service.py` :**

Le LLM reçoit :
```
FEEDBACK : "Renomme l'epic 3 en Moteur de matching"

EPICS ACTUELS (6) :
  Epic #1 [db_id=12] — Profilage des candidats
  Epic #2 [db_id=13] — Gestion des projets
  Epic #3 [db_id=14] — Recherche et matching
  ...

CONTEXTE CDC (extrait) : [2000 premiers caractères]

INSTRUCTIONS :
- Pour RENOMMER : garde le db_id, change seulement le titre.
- Pour SCINDER en 2 : garde le db_id pour la 1ère partie, null pour la 2e.
- Pour AJOUTER : utilise db_id null.
- Pour SUPPRIMER : ne l'inclus PAS dans la réponse (ses stories seront supprimées).
- Retourne la liste COMPLÈTE après modifications.
```

**Le LLM doit retourner la liste COMPLÈTE** (pas seulement les modifiés) → les epics absents sont détectés comme supprimés par `_apply_improved_epics`.

---

### 4.4 CAS 3 — Rejet ciblé (epics sélectionnés)

**Déclencheur :** `human_feedback` défini + `targeted_epic_ids` non vide

Le PM coche des epics spécifiques dans l'UI (`EpicsSelector` dans `ValidationCard.jsx`), l'API reçoit `targeted_epic_ids: [14, 17]`.

**Chaîne d'appels :**
```
node_epics()
    └── _targeted_regen(project_id, targeted_epic_ids, cdc_text, feedback)  [agent.py]
            └── get_epics(project_id)                                        [repository.py]
            └── filtre : epics_to_fix = [e for e in db_epics if e.id in targeted_epic_ids]
            └── improve_targeted_epics(epics_to_fix, cdc_text, feedback)    [service.py]
                    └── _call_llm(prompt, max_tokens=2048)
            └── _apply_improved_epics(project_id, improved, targeted_epic_ids)
                    └── [SUPPRESSION] epic ciblé absent du retour → delete_epic()
                    └── [UPDATE] epic ciblé retourné avec db_id → update_epic()
                    └── [INSERT] db_id=null dans retour → add_epic() (scission)
                    └── _reload_epics(project_id)
```

**Différence clé avec le CAS 2 :**
- CAS 2 : le LLM voit TOUS les epics, retourne TOUS les epics → suppressions détectées par absence
- CAS 3 : le LLM voit SEULEMENT les epics ciblés, retourne SEULEMENT ceux-ci → les autres ne sont PAS touchés

**Exemple de scission :** Le PM sélectionne l'epic #14 "Recherche et matching" et dit "Découpe-le en 2".

Le LLM retourne :
```json
{ "epics": [
    { "db_id": 14, "title": "Moteur de matching candidats", "description": "..." },
    { "db_id": null, "title": "Gestion des alertes matching",  "description": "..." }
]}
```

`_apply_improved_epics` :
- db_id=14 → `update_epic(14, {...})`
- db_id=null → `add_epic(project_id, {...})` → nouvel ID généré par PostgreSQL

---

### 4.5 `_apply_improved_epics()` — Logique centrale

```python
async def _apply_improved_epics(
    project_id: int,
    improved: list[dict],
    original_db_ids: list[int] | None = None,
) -> list[dict]:
    # 1. Extraire les db_ids présents dans la réponse LLM
    returned_db_ids = {e["db_id"] for e in improved if e.get("db_id")}

    # 2. SUPPRESSIONS : epics présents avant mais absents du retour LLM
    if original_db_ids:
        for db_id in original_db_ids:
            if db_id not in returned_db_ids:
                await delete_epic(db_id)   # CASCADE → stories aussi supprimées

    # 3. MISES À JOUR et INSERTIONS
    for e in improved:
        payload = { "title": e["title"], "description": ..., "splitting_strategy": ... }
        if e.get("db_id"):
            await update_epic(e["db_id"], payload)     # UPDATE
        else:
            new_e = await add_epic(project_id, payload) # INSERT

    return await _reload_epics(project_id)
```

---

### 4.6 `_normalize_epics()` — Normalisation de la réponse LLM

```python
def _normalize_epics(raw_list: list) -> list[dict]:
    result = []
    for e in raw_list:
        if not isinstance(e, dict): continue
        strategy = e.get("splitting_strategy", "by_feature")
        if strategy not in {"by_feature", "by_user_role", "by_workflow_step", "by_component"}:
            strategy = "by_feature"   # fallback si valeur invalide
        title = str(e.get("title", "")).strip()
        if not title: continue        # filtre les entrées sans titre
        # db_id : int existant ou None (LLM peut retourner null ou omettre)
        raw_db_id = e.get("db_id")
        db_id = int(raw_db_id) if raw_db_id is not None and str(raw_db_id).lstrip("-").isdigit() else None
        result.append({ "db_id": db_id, "title": title, "description": ..., "splitting_strategy": strategy })
    return result
```

---

### 4.7 Retry Logic dans `_call_llm()`

```python
_RETRY_DELAYS = [3, 7]   # 3 tentatives total : 0s, +3s, +7s

for attempt in range(1 + len(_RETRY_DELAYS)):   # 3 tentatives
    try:
        raw = await invoke_with_fallback(...)
        if not raw or not raw.strip():
            raise ValueError("Réponse vide du LLM")
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()  # strip markdown
        data  = json.loads(clean)
        result = _normalize_epics(data.get("epics", []))
        if not result:
            raise ValueError("Aucun epic valide")
        return result
    except Exception as e:
        if attempt < len(_RETRY_DELAYS):
            await asyncio.sleep(_RETRY_DELAYS[attempt])

raise RuntimeError("Echec après 3 tentatives")
```

---

### 4.8 Résultat retourné par `node_epics()`

```python
def _done(epics: list[dict]) -> dict:
    return {
        "epics":              epics,
        "current_phase":      "epics",
        "validation_status":  "pending_human",   # signale à node_validate d'attendre le PM
        "human_feedback":     None,              # réinitialise pour le prochain feedback
        "targeted_epic_ids":  None,              # réinitialise
        "targeted_story_ids": None,
        "error":              None,
    }
```

---

## 5. Phase 3 — Génération des User Stories

### Vue d'ensemble des fichiers

```
agents/pm/agents/stories/
├── agent.py                    ← Nœud LangGraph — 3 cas (identique pattern epics)
├── service.py                  ← Délègue au ReAct agent
├── repository.py               ← CRUD stories + mapping epic_idx ↔ db_id
├── react_agent.py              ← Orchestrateur parallèle (Semaphore max 3 epics)
└── tools/
    ├── generate.py             ← 1 appel LLM : titre + desc + SP + AC par epic
    ├── review.py               ← 1 appel LLM : audit couverture par epic
    └── targeted_regen.py       ← Amélioration ciblée de stories sélectionnées
```

---

### 5.1 Nœud principal : `node_stories()` — `agent.py`

```python
async def node_stories(state: PMPipelineState) -> dict:
    project_id         = state.get("project_id")
    epics              = state.get("epics", [])
    human_feedback     = state.get("human_feedback")
    targeted_story_ids = state.get("targeted_story_ids") or []
    architecture_detected = state.get("architecture_detected", False)
    architecture_details  = state.get("architecture_details") if architecture_detected else None
```

**3 cas (même logique que les epics) :**

| Condition | Cas | Action |
|-----------|-----|--------|
| `human_feedback` AND `targeted_story_ids` | CAS 3 | `_partial_regen()` — améliore seulement les stories ciblées |
| `human_feedback` sans ciblage | CAS 2 | `generate_stories()` complet avec feedback |
| Pas de `human_feedback` | CAS 1 | `generate_stories()` première génération |

---

### 5.2 CAS 1 & 2 — Génération complète (avec ou sans feedback)

**Chaîne d'appels :**
```
node_stories()
    └── generate_stories(epics, human_feedback, architecture_details, project_id)  [service.py]
            └── run_stories_react_agent(epics, human_feedback, architecture_details, project_id) [react_agent.py]
                    └── asyncio.gather avec Semaphore(3)
                        └── _safe_process(epic_idx, epic)
                                └── _process_epic(epic_idx, epic, emit)
                                        └── [1] run_generate_for_epic(epic, ...)  [tools/generate.py]
                                        └── [2] run_review_coverage(epic, ...)    [tools/review.py]
                                        └── [3] SI gaps → run_generate_for_epic(missing_features=gaps)
    └── save_stories(project_id, stories)   [repository.py]
```

---

### 5.3 ReAct Agent — `react_agent.py`

**Pattern d'exécution : déterministe, parallèle avec Semaphore**

```python
MAX_CONCURRENT_EPICS = 3   # Limite d'API rate limiting
semaphore = asyncio.Semaphore(MAX_CONCURRENT_EPICS)

async def _safe_process(epic_idx: int, epic: dict) -> None:
    async with semaphore:
        await _process_epic(epic_idx, epic, emit)

await asyncio.gather(*[_safe_process(i, e) for i, e in enumerate(epics)])
```

**Pourquoi le Semaphore ?** Sans limite, 10 epics = 20 appels LLM simultanés → le provider répond avec des messages vides ("No message content") à cause du rate limiting. Avec `MAX_CONCURRENT_EPICS=3` : 3 epics × 2 appels = 6 appels max en parallèle.

**Stockage intermédiaire :**
```python
_epic_store:   dict[int, list[dict]] = {}   # epic_idx → stories générées
_review_store: dict[int, dict]       = {}   # epic_idx → résultat review
```

---

### 5.4 Génération par epic — `_process_epic()` dans `react_agent.py`

```python
async def _process_epic(epic_idx: int, epic: dict, emit) -> None:
    # ÉTAPE 1 : Génération complète
    stories = await run_generate_for_epic(
        epic=epic, epic_idx=epic_idx,
        architecture_details=_current_architecture_details,
        missing_features=None,
        human_feedback=_current_human_feedback,
    )
    _epic_store[epic_idx] = stories

    # ÉTAPE 2 : Revue de couverture
    review = await run_review_coverage(epic, epic_idx, stories)
    _review_store[epic_idx] = review

    # ÉTAPE 3 : Retry si gaps détectés
    if not review.get("coverage_ok", True) and review.get("gaps"):
        gaps = [g if isinstance(g, str) else str(g) for g in review["gaps"]]
        stories = await run_generate_for_epic(
            epic=epic, epic_idx=epic_idx,
            missing_features=gaps,           # ← passe les gaps au LLM
            human_feedback=_current_human_feedback,
        )
        _epic_store[epic_idx] = stories
```

**Événements SSE émis :**
- `epic_start` → début de traitement d'un epic
- `tool_start` → début de la review
- `gap_detected` → gaps trouvés, retry en cours
- `retry_start` → début du 2ème appel LLM
- `coverage_ok` → aucun gap détecté
- `epic_done` → epic terminé
- `error` → erreur non rattrapée

---

### 5.5 `run_generate_for_epic()` — `tools/generate.py`

**1 seul appel LLM** pour générer titre + description + story_points + acceptance_criteria.

**Prompt système :**
```
"Tu décomposes un epic en User Stories complètes.
 Format titre : 'En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]'
 Coupe verticale obligatoire (UI + backend + DB si applicable)
 2 à 8 stories selon la complexité de l'epic
 Story Points Fibonacci uniquement : 1, 2, 3, 5, 8 (13 interdit)
 Critères d'acceptation Gherkin : 2 à 3 par story, jamais plus"
```

**Prompt utilisateur (construit par `_build_prompt()`) :**
```
[feedback_section si feedback]  ← "⚠ CORRECTIONS DU PM"
[missing_section si gaps]       ← "⚠ FONCTIONNALITÉS MANQUANTES À COUVRIR"
[arch_section si architecture]  ← "ARCHITECTURE CIBLE — nommer les composants"

EPIC #2 (stratégie : by_feature)
Titre       : Gestion des projets et des exigences
Description : ...

FORMAT JSON ATTENDU :
{ "stories": [{ "title": "...", "description": "...", "story_points": 3, "acceptance_criteria": [...] }] }
```

**Validation Fibonacci :**
```python
_FIBONACCI = {1, 2, 3, 5, 8}
sp = s.get("story_points", 3)
if not isinstance(sp, int) or sp not in _FIBONACCI:
    sp = min(_FIBONACCI, key=lambda x: abs(x - (sp if isinstance(sp, (int, float)) else 3)))
    # Ex: LLM retourne 4 → snap vers 3 (le plus proche)
    # Ex: LLM retourne 13 → snap vers 8
```

---

### 5.6 `run_review_coverage()` — `tools/review.py`

**Rôle :** Audite les stories générées par rapport à l'epic sur 3 dimensions.

**Prompt :**
```
VÉRIFIE CES 3 POINTS :
1. GAPS (complétude) : fonctionnalités majeures non couvertes
2. SCOPE CREEP : stories qui sortent du périmètre de l'epic
3. QUALITÉ INVEST : stories mal formulées, trop grandes, non testables

Retourne :
{ "coverage_ok": bool, "gaps": [], "scope_creep_issues": [], "quality_issues": [], "suggestions": [] }
```

**`_to_str_list()` — normalisation des listes :** Le LLM peut retourner les gaps sous forme de dicts `{"gap": "..."}`  au lieu de strings. Cette fonction normalise :
```python
def _to_str_list(lst: list) -> list[str]:
    for item in lst:
        if isinstance(item, str): result.append(item)
        elif isinstance(item, dict):
            text = item.get("description") or item.get("gap") or item.get("issue") or str(item)
            result.append(str(text))
```

**Fail-safe :** Si la review échoue (3 tentatives), retourne `coverage_ok=True` pour ne pas bloquer la génération.

---

### 5.7 `save_stories()` — `repository.py` — Mapping epic_idx ↔ db_id

C'est ici que se résout la **question critique des IDs**.

**Problème :** Le LLM génère des stories avec `epic_id = 0, 1, 2...` (index dans le tableau). La DB stocke des epics avec des IDs auto-incrémentés (ex: 12, 13, 14). Il faut mapper.

```python
async def save_stories(project_id: int, stories: list[dict]) -> list[UserStory]:
    # 1. Récupère les epics triés par id (même ordre que le LLM les a reçus)
    db_epics = await session.execute(
        select(Epic).where(Epic.project_id == project_id).order_by(Epic.id)
    )
    # Mapping : index LLM → ID DB réel
    index_to_db_id = {i: e.id for i, e in enumerate(db_epics)}
    # ex: {0: 12, 1: 13, 2: 14}

    # 2. Supprime les stories existantes
    await session.execute(delete(UserStory).where(UserStory.epic_id.in_(epic_ids)))

    # 3. Insère les nouvelles stories en mappant epic_id
    for s in stories:
        epic_idx   = s.get("epic_id", 0)      # 0, 1, 2...
        db_epic_id = index_to_db_id.get(epic_idx)  # 12, 13, 14...
        orm_s = UserStory(epic_id=db_epic_id, ...)

    # 4. Écrit db_id en retour dans les dicts (pour ai_output)
    for story_dict, orm_s in zip(saved_dicts, orm_stories):
        story_dict["db_id"] = orm_s.id   # ← LE PM voit ce db_id dans l'UI
```

**CRUCIAL :** Les stories retournées dans le state LangGraph ont `epic_id = INDEX` (0, 1, 2…) mais ont aussi `db_id = ID_DB` (ex: 42, 43, 44…). Le frontend utilise `db_id` pour les checkboxes de sélection.

---

### 5.8 CAS 3 — Rejet ciblé de stories

**Déclencheur :** PM coche des stories spécifiques dans `StoriesSelector` (UI), API reçoit `targeted_story_ids: [42, 47, 51]`.

**Chaîne d'appels :**
```
node_stories()
    └── _partial_regen(project_id, targeted_story_ids, feedback)   [agent.py]
            └── get_stories_by_ids(targeted_story_ids)             [repository.py]
                    └── SELECT UserStory, Epic.title
                        FROM user_stories JOIN epics ON ...
                        WHERE user_stories.id IN (42, 47, 51)
                    └── retourne dicts avec db_id + epic_title
            └── improve_targeted_stories(stories_to_fix, feedback) [tools/targeted_regen.py]
                    └── invoke_with_fallback(...)
                    └── LLM retourne les mêmes stories avec contenu amélioré
                    └── db_id préservé IDENTIQUE
                    └── Fibonacci snap sur story_points
                    └── fail-safe : retourne originales si 3 tentatives échouent
            └── pour chaque story améliorée :
                    update_story(s["db_id"], { title, description, story_points, acceptance_criteria })
            └── get_all_stories_as_dicts(project_id)               [repository.py]
                    └── recharge TOUTES les stories du projet
                    └── recalcule epic_id = INDEX (pas db_id epic)
```

**Différence clé vs epics :** Pour les stories, pas de DELETE/INSERT — uniquement UPDATE. Le `db_id` est préservé pour maintenir la traçabilité des rounds de raffinement.

**Prompt `improve_targeted_stories()` :**
```
FEEDBACK DU PM : "Les stories 2 et 5 manquent de critères négatifs..."

STORIES À CORRIGER (2) :
Story #1 [db_id=42] — epic: Gestion des projets
  Titre       : En tant que recruteur...
  Description : ...
  SP          : 3
  Critères    : [...]

RÈGLE ABSOLUE : le champ "db_id" doit rester IDENTIQUE à celui fourni.
```

---

### 5.9 `get_all_stories_as_dicts()` — Rechargement depuis DB

Après `_partial_regen`, les stories modifiées sont en DB mais les stories non modifiées sont toujours en state. Pour cohérence, on recharge TOUT depuis la DB :

```python
async def get_all_stories_as_dicts(project_id: int) -> list[dict]:
    # Mapping db_epic_id → index
    db_id_to_idx = {e.id: i for i, e in enumerate(db_epics)}
    
    for s in stories:
        result.append({
            "db_id":   s.id,
            "epic_id": db_id_to_idx.get(s.epic_id, 0),  # reconvertit DB id → index
            "title":   s.title,
            ...
        })
```

---

## 6. Phase 4 — Raffinement PO ↔ Tech Lead

### Vue d'ensemble des fichiers

```
agents/pm/agents/refinement/
├── agent.py        ← Nœud LangGraph — exécute Round 1 uniquement
├── service.py      ← Orchestrateur : run_one_round() et run_refinement()
├── repository.py   ← Met à jour les stories en status REFINED
└── tools/
    ├── po_review.py    ← LLM simulant le Product Owner
    ├── tech_review.py  ← LLM simulant le Tech Lead
    └── patch.py        ← Fusion patches + application (Python pur, pas de LLM)
```

---

### 6.1 Nœud principal : `node_refinement()` — `agent.py`

```python
async def node_refinement(state: PMPipelineState) -> dict:
    stories = state.get("stories", [])
    epics   = state.get("epics", [])

    # Exécute UNIQUEMENT le Round 1
    refined_stories, round_data = await run_one_round(
        stories=stories, epics=epics,
        round_number=1,
        architecture_details=architecture_details,
        previous_rounds=[],    # Round 1 : aucun round précédent
    )

    await save_refined_stories(project_id, refined_stories)

    return {
        "refined_stories":      refined_stories,
        "stories_before_round": stories,   # snapshot avant modification
        "refinement_rounds":    [round_data],
        "current_round":        1,
        "refinement_consensus": round_data.get("consensus", False),
        "validation_status":    "pending_human",
        ...
    }
```

**Pourquoi seulement Round 1 ?** Les rounds suivants sont déclenchés par le PM via `POST /pipeline/{id}/refinement/round/apply`. Le PM peut choisir d'accepter/rejeter chaque patch story par story avant de lancer le round suivant.

---

### 6.2 `run_one_round()` — `service.py`

**Flux pour UN round :**

```python
for epic_idx, epic in enumerate(epics):
    epic_stories = [s for s in current_stories if s.get("epic_id") == epic_idx]

    # PO et TL reviewent EN PARALLÈLE (même stories, analyses indépendantes)
    (po_patches, po_summary), (tl_patches, tl_summary) = await asyncio.gather(
        run_po_review(epic, epic_idx, epic_stories),
        run_tech_review(epic, epic_idx, epic_stories, architecture_details),
    )

    # Fusion des patches (Python pur)
    epic_patches = merge_patches(po_patches, tl_patches)

    # Application + capture des old_value pour le diff UI
    current_stories, enriched = apply_patches_enriched(current_stories, epic_idx, epic_patches)

    # Filtre les re-patches (déjà appliqués dans rounds précédents)
    enriched_new = _filter_new_patches(enriched, already_patched)
    round_patches.extend(enriched_new)

consensus = check_consensus(round_patches)
```

---

### 6.3 Structure d'un Patch

Un patch est un dict qui décrit une modification à appliquer sur une story :

```python
{
    "story_local_idx": 2,        # index LOCAL dans epic_stories (0-based)
    "field":           "story_points",  # champ modifié
    "new_value":       5,        # valeur proposée
    "reason":          "Story trop complexe pour 3 pts",
    # Champs ajoutés par apply_patches_enriched :
    "db_id":           42,       # ID DB de la story (pour le diff UI)
    "old_value":       3,        # valeur avant patch
    "new_value_applied": 5,      # valeur effectivement appliquée
}
```

**Champs patchables :**
- `title` — reformulation du titre
- `story_points` — révision de l'estimation
- `description` — clarification
- `acceptance_criteria` — ajout/modification de critères
- `flag` — story marquée comme problématique (pas de modif de contenu)

---

### 6.4 `merge_patches()` — `tools/patch.py`

Fusionne les patches PO et TL. Règle de conflit :
- Si PO et TL patchent le même champ de la même story :
  - Pour `story_points` : prend le **max** (le plus conservateur)
  - Pour les autres champs : le patch PO a priorité
- Max 2 patches par story par reviewer (évite le spam)

---

### 6.5 `check_consensus()` — critère d'arrêt

```python
def check_consensus(patches: list[dict]) -> bool:
    actionable = [p for p in patches if p.get("field") != "flag"]
    major = sum(1 for p in actionable if p.get("field") in {"title", "story_points"})
    return major < 2 and len(actionable) < 5
```

- **Consensus = moins de 2 changements majeurs ET moins de 5 patches actionnables au total**
- Si consensus atteint → le raffinement s'arrête même avant le round 3
- Max 3 rounds absolus

---

### 6.6 `_filter_new_patches()` — anti-boucle

Empêche le LLM de re-proposer indéfiniment les mêmes corrections :

```python
def _build_already_patched(previous_rounds: list[dict]) -> set[tuple]:
    seen = set()
    for r in previous_rounds:
        for p in r.get("stories_patch", []):
            if p.get("db_id") and p.get("field") != "flag":
                seen.add((p["db_id"], p["field"]))   # ex: (42, "story_points")
    return seen

def _filter_new_patches(patches, already_patched) -> list[dict]:
    return [p for p in patches if (p.get("db_id"), p.get("field")) not in already_patched]
```

Si au Round 1 on a patché `(db_id=42, field=story_points)`, au Round 2 tout patch sur ce même (db_id, field) est ignoré.

---

### 6.7 Flux multi-round (PM-driven)

```
ROUND 1 :
    node_refinement() → run_one_round() → patches → awaiting_round_review=True
    PM voit les diffs story par story dans l'UI (RoundReviewSection)
    PM choisit "Garder nouveau" ou "Garder ancien" pour chaque story
    PM appuie "Continuer — Round 2"

POST /pipeline/{id}/refinement/round/apply
    → applique les choix PM (new/old) sur les stories en DB
    → run_one_round(round_number=2, previous_rounds=[round1_data])
    → _filter_new_patches élimine les re-patches du Round 1
    → patches Round 2 affichés

...jusqu'à consensus ou Round 3
```

---

## 7. Gestion des IDs

C'est le point le plus critique et source de bugs si mal compris.

### 7.1 Les 3 types d'IDs

| ID | Valeur | Où il vit | Qui le génère |
|----|--------|-----------|---------------|
| `epic_id` (index) | 0, 1, 2... | State LangGraph, `stories[n].epic_id` | Séquence Python |
| `Epic.id` (db_id) | 12, 13, 14... | Table `pm.epics` | PostgreSQL auto-increment |
| `UserStory.id` (db_id) | 42, 43, 44... | Table `pm.user_stories` | PostgreSQL auto-increment |

### 7.2 Problème fondamental du mapping

```
État LangGraph           DB PostgreSQL
─────────────────        ──────────────────────
epics[0]           →     pm.epics WHERE id = 12
epics[1]           →     pm.epics WHERE id = 13
epics[2]           →     pm.epics WHERE id = 14

stories[n].epic_id=0  →  stories[n].epic_id (DB) = 12
stories[n].epic_id=1  →  stories[n].epic_id (DB) = 13
```

**Règle absolue :** `ORDER BY id` sur les epics garantit que `index 0 = epic avec le plus petit id`.

### 7.3 `db_id` dans le state

Après `save_stories()`, chaque story dans le state a un `db_id` :
```python
story_dict["db_id"] = orm_s.id   # ex: 42
```

Ce `db_id` est transmis au frontend via `ai_output.stories[n].db_id`. Le PM coche les stories par `db_id`, l'API reçoit `targeted_story_ids: [42, 47]`, le nœud fait `get_stories_by_ids([42, 47])`.

### 7.4 `db_id` dans les epics du state

**Les epics dans le state n'ont PAS de db_id** par défaut. Seul `save_epics()` retourne les ORM avec IDs.

Pour le CAS 2 (`_global_regen`), on récupère les db_ids depuis la DB :
```python
db_epics = await get_epics(project_id)   # SELECT ORDER BY id
for i, e in enumerate(existing_epics_state):
    db_id = db_epics[i].id if i < len(db_epics) else None
    epics_with_db_id.append({ "db_id": db_id, ... })
```

Pour le CAS 3, `targeted_epic_ids` contient directement les `db_id` des epics (récupérés depuis l'API `GET /pipeline/{id}/epics` qui charge depuis la DB).

### 7.5 Reconstruction `epic_id` index après reload

`get_all_stories_as_dicts()` reconstruit les indices après un reload DB :

```python
db_id_to_idx = {e.id: i for i, e in enumerate(db_epics)}
# ex: {12: 0, 13: 1, 14: 2}

for s in stories:
    result.append({
        "epic_id": db_id_to_idx.get(s.epic_id, 0),  # 12 → 0, 13 → 1...
        "db_id":   s.id,
        ...
    })
```

---

## 8. Validation humaine & feedback

### 8.1 `node_validate` — `graph/node_validate.py`

Ce nœud est appelé après CHAQUE phase. Il vérifie `validation_status` :
- `"pending_human"` → il interrompt le graph (interrupt) et attend
- `"validated"` → laisse passer vers `jira_sync`
- `"rejected"` → laisse retourner vers la phase courante

### 8.2 Endpoint `POST /pipeline/{project_id}/validate`

```python
class ValidateRequest(BaseModel):
    approved:           bool
    feedback:           Optional[str] = None
    targeted_story_ids: Optional[list[int]] = None
    targeted_epic_ids:  Optional[list[int]] = None
```

**Logique :**
```python
if body.approved:
    await graph.aupdate_state(config, {
        "validation_status": "validated",
        "human_feedback":    None,
        "targeted_epic_ids": None,
        "targeted_story_ids": None,
    })
else:
    await graph.aupdate_state(config, {
        "validation_status":  "rejected",
        "human_feedback":     body.feedback,
        "targeted_epic_ids":  body.targeted_epic_ids  if not body.approved else None,
        "targeted_story_ids": body.targeted_story_ids if not body.approved else None,
    })
await graph.ainvoke(None, config)   # reprend le graph depuis le checkpoint
```

### 8.3 Flux complet d'un rejet

```
1. PM voit les epics dans l'UI
2. PM coche Epic #3 dans EpicsSelector
3. PM tape "Découpe cet epic en deux"
4. PM clique "Corriger 1 élément"

5. Frontend :
   POST /pipeline/42/validate
   Body: { approved: false, feedback: "Découpe...", targeted_epic_ids: [14] }

6. API :
   aupdate_state({ validation_status: "rejected", human_feedback: "Découpe...", targeted_epic_ids: [14] })
   ainvoke(None, config)

7. LangGraph :
   node_validate lit validation_status = "rejected"
   → routeur retourne "node_epics"
   → node_epics s'exécute

8. node_epics :
   human_feedback = "Découpe..."
   targeted_epic_ids = [14]
   → CAS 3 : _targeted_regen(42, [14], cdc_text, "Découpe...")

9. LLM retourne { "epics": [
     { "db_id": 14, "title": "Partie 1..." },
     { "db_id": null, "title": "Partie 2..." }
   ]}

10. _apply_improved_epics :
    UPDATE pm.epics SET title="Partie 1..." WHERE id=14
    INSERT INTO pm.epics (title="Partie 2...") → id=17

11. _reload_epics → retourne 7 epics (6 originaux + 1 nouveau)
12. node_epics → _done() → validation_status="pending_human"
13. node_validate → interrompt à nouveau
14. PM voit les 7 epics dans l'UI
```

---

## 9. API REST — Endpoints du pipeline

### Fichier : `app/api/pipeline/pipeline.py`

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `POST` | `/pipeline/{id}/start` | Lance le pipeline avec document_id |
| `GET` | `/pipeline/{id}` | État détaillé de toutes les phases |
| `POST` | `/pipeline/{id}/validate` | Approuver ou rejeter une phase avec feedback |
| `POST` | `/pipeline/{id}/resume` | Relancer un pipeline bloqué |
| `GET` | `/pipeline/{id}/stories` | Liste toutes les stories avec db_id |
| `PUT` | `/pipeline/stories/{story_id}` | Modifier une story (titre, desc, SP, AC) |
| `DELETE` | `/pipeline/stories/{story_id}` | Supprimer une story |
| `GET` | `/pipeline/{id}/epics` | Liste tous les epics avec db_id |
| `PUT` | `/pipeline/epics/{epic_id}` | Modifier un epic |
| `DELETE` | `/pipeline/epics/{epic_id}` | Supprimer un epic (cascade stories) |
| `POST` | `/pipeline/{id}/epics` | Créer un epic manuellement |
| `GET` | `/pipeline/{id}/stories/stream` | SSE — événements temps réel génération stories |
| `POST` | `/pipeline/{id}/stories/restart` | Relancer la génération d'un epic manquant |
| `POST` | `/pipeline/{id}/refinement/restart` | Relancer le raffinement |
| `POST` | `/pipeline/{id}/refinement/round/apply` | Appliquer les choix PM + lancer round suivant |
| `PATCH` | `/pipeline/{id}/status` | Changer le statut (`pipeline_done` → `in_development` → `delivered`) |
| `PATCH` | `/pipeline/{id}/archive` | Archiver le projet |
| `DELETE` | `/pipeline/{id}` | Supprimer le projet + toutes données en cascade |

### Endpoint SSE `/stories/stream`

Diffuse en temps réel les événements du ReAct agent pendant la génération des stories. Le frontend reçoit :

```json
{ "type": "epic_start",  "epic_idx": 2, "epic_title": "Gestion des projets", "nb_epics": 6 }
{ "type": "gap_detected", "epic_idx": 2, "gaps": ["Export PDF", "Notifications"] }
{ "type": "retry_start", "epic_idx": 2, "missing_features": ["Export PDF", "Notifications"] }
{ "type": "epic_done",   "epic_idx": 2, "stories_count": 7 }
{ "type": "done",        "total_stories": 39, "nb_epics": 6 }
```

---

## 10. Chaîne d'appels complète

### Phase 2 — Epics (CAS 1 : Première génération)

```
POST /pipeline/{id}/start
  └── pipeline.py : ainvoke(state, config)
        └── graph.py : node_extraction → node_validate → jira_sync → node_epics
              └── agent.py : node_epics(state)
                    └── service.py : generate_epics(cdc_text, None)
                          └── prompt.py : build_epics_prompt(cdc_text)
                          └── groq_client.py : invoke_with_fallback(model, messages)
                                └── LLM → raw JSON
                          └── service.py : _normalize_epics(raw_list)
                    └── repository.py : save_epics(project_id, epics)
                          └── SQLAlchemy DELETE pm.epics WHERE project_id=X
                          └── SQLAlchemy INSERT pm.epics (×N)
                          └── session.refresh(orm_e) → IDs auto
                    └── agent.py : _done(epics)
              └── node_validate → interrupt (pending_human)
```

### Phase 2 — Epics (CAS 3 : Rejet ciblé)

```
POST /pipeline/{id}/validate { approved: false, targeted_epic_ids: [14] }
  └── pipeline.py : aupdate_state({ validation_status: "rejected", targeted_epic_ids: [14], human_feedback: "..." })
  └── pipeline.py : ainvoke(None, config)
        └── node_validate → routeur → node_epics
              └── agent.py : node_epics(state)
                    human_feedback SET, targeted_epic_ids=[14]
                    └── agent.py : _targeted_regen(project_id, [14], cdc_text, feedback)
                          └── repository.py : get_epics(project_id)
                                └── SELECT * FROM pm.epics WHERE project_id=X ORDER BY id
                          └── filtre : epics_to_fix = [epic où id=14]
                          └── service.py : improve_targeted_epics([epic14], cdc_text, feedback)
                                └── service.py : _call_llm(prompt, max_tokens=2048)
                                      └── groq_client.py : invoke_with_fallback
                                      └── service.py : _normalize_epics
                          └── agent.py : _apply_improved_epics(project_id, improved, [14])
                                returned_db_ids = {14} (ou {14, null} si scission)
                                [SUPPRESSION] 14 in returned → rien
                                [UPDATE] db_id=14 → repository.py : update_epic(14, payload)
                                [INSERT] db_id=null → repository.py : add_epic(project_id, payload)
                                └── agent.py : _reload_epics(project_id)
                                      └── repository.py : get_epics(project_id)
                                      └── retourne [{title, description, splitting_strategy}]
                    └── agent.py : _done(epics)
              └── node_validate → interrupt (pending_human)
```

### Phase 3 — Stories (CAS 1 : Première génération)

```
graph.py : jira_sync → node_stories
  └── agent.py : node_stories(state)
        epics = state["epics"]   # 6 epics sans db_id
        └── service.py : generate_stories(epics, None, architecture_details, project_id)
              └── react_agent.py : run_stories_react_agent(epics, None, arch, project_id)
                    _epic_store.clear(), _review_store.clear()
                    queue = get_or_create_queue(project_id)   # SSE queue
                    semaphore = asyncio.Semaphore(3)
                    asyncio.gather(*[_safe_process(i, e) for i, e in enumerate(epics)])
                      └── _process_epic(0, epic_0, emit)
                            └── tools/generate.py : run_generate_for_epic(epic, 0, arch, None, None)
                                  └── _build_prompt(epic, 0, arch, None, None)
                                  └── groq_client.py : invoke_with_fallback(model, messages, max_tokens=4096)
                                  └── json.loads(clean) → data["stories"]
                                  └── Fibonacci snap sur story_points
                                  └── retourne [{epic_id:0, title, desc, sp, ac, strategy}]
                            _epic_store[0] = stories
                            └── tools/review.py : run_review_coverage(epic_0, 0, stories)
                                  └── groq_client.py : invoke_with_fallback(max_tokens=768)
                                  └── _to_str_list(data["gaps"])   # normalise dicts → strings
                                  └── retourne {coverage_ok, gaps, scope_creep_issues, ...}
                            _review_store[0] = review
                            SI NOT coverage_ok AND gaps:
                              └── tools/generate.py : run_generate_for_epic(epic, 0, arch, gaps, None)
                                    # 2ème appel LLM avec missing_features=gaps
                                  └── retourne stories enrichies
                              _epic_store[0] = nouvelles_stories
                      └── [parallel] _process_epic(1, epic_1, emit)
                      └── [parallel] _process_epic(2, epic_2, emit)
                      └── ... (max 3 en parallèle)
                    _collect_stories_from_store(6)
                      → chaque story reçoit _review
                    queue.put({ "type": "done", "total_stories": 39 })
                    retourne all_stories
        └── repository.py : save_stories(project_id, stories)
              SELECT pm.epics WHERE project_id ORDER BY id → db_epics
              index_to_db_id = {0: 12, 1: 13, ...}
              DELETE pm.user_stories WHERE epic_id IN [12,13,14...]
              INSERT pm.user_stories (epic_id=db_id_mappé, ...)
              session.refresh → story.id auto
              story_dict["db_id"] = orm_s.id   # injecte db_id dans state
        └── agent.py : _done(stories)
  └── node_validate → interrupt (pending_human)
```

### Phase 4 — Raffinement (Round 1)

```
graph.py : jira_sync → node_refinement
  └── agent.py : node_refinement(state)
        stories = state["stories"]   # avec db_id
        epics   = state["epics"]
        └── service.py : run_one_round(stories, epics, round_number=1, previous_rounds=[])
              already_patched = {} (vide pour round 1)
              for epic_idx in range(len(epics)):
                  epic_stories = [s for s in stories if s["epic_id"] == epic_idx]
                  asyncio.gather(
                    po_review.py : run_po_review(epic, epic_idx, epic_stories)
                        └── invoke_with_fallback → [{story_local_idx, field, new_value, reason}]
                    tech_review.py : run_tech_review(epic, epic_idx, epic_stories, arch)
                        └── invoke_with_fallback → [{story_local_idx, field, new_value, reason}]
                  )
                  patch.py : merge_patches(po_patches, tl_patches)
                      # résolution conflits : max sur story_points, PO prioritaire sinon
                  patch.py : apply_patches_enriched(current_stories, epic_idx, epic_patches)
                      # modifie les stories en mémoire
                      # capture old_value + db_id pour diff UI
                  _filter_new_patches(enriched, already_patched={})  # rien à filtrer round 1
                  round_patches.extend(enriched_new)
              patch.py : check_consensus(round_patches)
                  actionable = [p for p in patches if field != "flag"]
                  major = count(p for p if field in {"title", "story_points"})
                  return major < 2 AND len(actionable) < 5
        └── repository.py : save_refined_stories(project_id, refined_stories)
        └── retourne { refined_stories, stories_before_round, refinement_rounds: [round_data], ... }
  └── node_validate → interrupt (pending_human)
```

---

## 11. Schéma de la base de données

### Tables principales (schéma `project_management`)

```sql
-- Projets
pm.projects (
    id          SERIAL PRIMARY KEY,
    user_id     INT,
    name        VARCHAR,
    description TEXT,
    status      ENUM('draft','in_progress','pipeline_done','in_development','delivered','archived'),
    ...
)

-- Documents CDC
pm.project_documents (
    id          SERIAL PRIMARY KEY,
    project_id  INT REFERENCES pm.projects(id) ON DELETE CASCADE,
    file_path   VARCHAR,
    ...
)

-- Epics
pm.epics (
    id                 SERIAL PRIMARY KEY,
    project_id         INT REFERENCES pm.projects(id) ON DELETE CASCADE,
    title              VARCHAR NOT NULL,
    description        TEXT,
    splitting_strategy VARCHAR,   -- by_feature | by_user_role | by_workflow_step | by_component
    status             ENUM('draft','in_progress','done'),
    jira_epic_key      VARCHAR,   -- ex: "PROJ-1"
    ai_metadata        JSONB,
    ...
)

-- User Stories
pm.user_stories (
    id                  SERIAL PRIMARY KEY,
    epic_id             INT REFERENCES pm.epics(id) ON DELETE CASCADE,
    title               VARCHAR NOT NULL,
    description         TEXT,
    story_points        INT,      -- Fibonacci : 1, 2, 3, 5, 8
    splitting_strategy  VARCHAR,
    acceptance_criteria TEXT,     -- JSON array sérialisé : '["Étant donné...", "..."]'
    status              ENUM('draft','refined','in_sprint','done'),
    jira_issue_key      VARCHAR,
    ai_metadata         JSONB,
    ...
)

-- État du pipeline (checkpoint métier, distinct du checkpoint LangGraph)
pm.pipeline_state (
    id             SERIAL PRIMARY KEY,
    project_id     INT REFERENCES pm.projects(id) ON DELETE CASCADE,
    current_phase  VARCHAR,
    ai_output      JSONB,    -- résultat de la dernière phase (ai_output stocké ici)
    status         VARCHAR,  -- pending_ai | pending_human | validated | rejected
    ...
)
```

### Cascade DELETE

```
pm.projects
    └── pm.epics (ON DELETE CASCADE)
            └── pm.user_stories (ON DELETE CASCADE)
    └── pm.project_documents (ON DELETE CASCADE)
    └── pm.pipeline_state (ON DELETE CASCADE)
```

**Conséquence :** Supprimer un epic supprime toutes ses stories. Supprimer un projet supprime tout.

---

## 12. Modèle LLM & gestion des erreurs

### Modèle utilisé

```python
_MODEL = "openai/gpt-oss-120b"
```

Tous les agents (epics, stories generate, review, targeted_regen, po_review, tech_review) utilisent ce modèle via `invoke_with_fallback()` depuis `app/core/groq_client.py`.

### Stratégie de retry

```python
_RETRY_DELAYS = [3, 7]   # 3 tentatives total

for attempt in range(3):
    try:
        raw = await invoke_with_fallback(...)
        if not raw or not raw.strip():
            raise ValueError("Réponse vide")
        clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()  # strip markdown
        data = json.loads(clean)
        # validation des données...
        return result
    except Exception as e:
        if attempt < 2:
            await asyncio.sleep(_RETRY_DELAYS[attempt])  # 3s puis 7s
raise RuntimeError("Échec après 3 tentatives")
```

### Fail-safes

| Situation | Comportement |
|-----------|-------------|
| `run_review_coverage()` échoue | Retourne `coverage_ok=True` → pas de retry, génération continue |
| `run_generate_for_epic()` échoue totalement | Retourne 1 story `_fallback_story()` avec "À définir" |
| `improve_targeted_stories()` échoue | Retourne les stories originales inchangées |
| `_targeted_regen()` épics échoue | Appelle `_reload_epics()` → retourne les epics actuels sans modification |
| `_global_regen()` épics échoue | Appelle `_reload_epics()` → retourne les epics actuels sans modification |
| `run_one_round()` raffinement échoue | Retourne les stories originales, PM peut quand même valider |

### Normalisation anti-crash

**Problème :** Le LLM retourne parfois des listes de dicts au lieu de listes de strings.

Exemple : `"gaps": [{"gap": "Export PDF"}]` au lieu de `"gaps": ["Export PDF"]`.

**Solution dans `review.py` :**
```python
def _to_str_list(lst: list) -> list[str]:
    for item in lst:
        if isinstance(item, str): result.append(item)
        elif isinstance(item, dict):
            text = item.get("description") or item.get("gap") or item.get("issue") or str(item)
            result.append(str(text))
        else:
            result.append(str(item))
```

**Solution dans `react_agent.py` :**
```python
gaps = [g if isinstance(g, str) else str(g) for g in review["gaps"]]
gaps_disp = _gaps_display(gaps)   # évite le crash de ", ".join(list_of_dicts)
```

---

## Récapitulatif — Questions clés pour le jury

**Q : Comment le LLM sait-il qu'il ne doit pas recréer les epics depuis zéro lors d'un feedback global ?**
→ La fonction `improve_all_epics()` lui passe les epics existants avec leurs db_id. La fonction `generate_epics()` (CAS 1) ne les lui passe pas. Le CAS 2 appelle `improve_all_epics()`, jamais `generate_epics()`.

**Q : Comment les IDs DB des epics sont-ils transmis au LLM ?**
→ `_global_regen()` appelle `get_epics(project_id)` puis mappe `existing_epics_state[i] ↔ db_epics[i]` par index. Le LLM reçoit `[db_id=12] — Profilage...` dans le prompt.

**Q : Comment les stories savent-elles à quel epic DB elles appartiennent ?**
→ Le LLM génère `epic_id=0,1,2...` (index). `save_stories()` fait `SELECT epics ORDER BY id` puis mappe `index → epic.id`. La DB stocke l'ID réel, le state stocke l'index.

**Q : Pourquoi MAX_CONCURRENT_EPICS=3 dans le ReAct agent ?**
→ Sans limite, N epics = 2N appels LLM simultanés → rate limiting → réponses vides. Le Semaphore(3) limite à 6 appels en parallèle max.

**Q : Que se passe-t-il si un epic est absent de la réponse LLM lors d'un rejet global ?**
→ `_apply_improved_epics()` compare `original_db_ids` avec `returned_db_ids`. Tout db_id absent → `delete_epic()` → cascade supprime les stories de cet epic.

**Q : Comment le consensus du raffinement est-il calculé ?**
→ `check_consensus()` : moins de 2 patches "majeurs" (title ou story_points) ET moins de 5 patches actionnables au total dans le round.

**Q : Comment les re-patches sont-ils évités aux rounds suivants ?**
→ `_build_already_patched()` collecte tous les `(db_id, field)` déjà patchés. `_filter_new_patches()` filtre les patches sur ces combinaisons dans le round courant.

**Q : Que stocke `acceptance_criteria` en DB ?**
→ Un string JSON : `'["Étant donné contexte, quand action, alors résultat", "Étant donné données invalides, ..."]'`. `save_stories()` fait `json.dumps(ac)`, `get_stories_by_ids()` fait `json.loads(story.acceptance_criteria)`.
