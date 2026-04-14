# Explication complète du module PM — Du nouveau projet au pipeline

Ce document trace **tout le flux** du module Project Management (PM), du clic sur "Nouveau Projet"
jusqu'à la fin du pipeline en 12 phases. Pour chaque appel : quel fichier, quelle fonction,
quels inputs, quels outputs.

---

## Table des matières

1. [Architecture globale](#1-architecture-globale)
2. [Partie Frontend — Fichiers et responsabilités](#2-partie-frontend--fichiers-et-responsabilités)
3. [Partie Backend — Fichiers et responsabilités](#3-partie-backend--fichiers-et-responsabilités)
4. [Flux 1 — Création d'un projet (wizard 4 étapes)](#4-flux-1--création-dun-projet-wizard-4-étapes)
5. [Flux 2 — Lancement du pipeline](#5-flux-2--lancement-du-pipeline)
6. [Flux 3 — Suivi et validation des phases](#6-flux-3--suivi-et-validation-des-phases)
7. [Flux 4 — Résumé complet A → Z avec tous les appels](#7-flux-4--résumé-complet-a--z-avec-tous-les-appels)
8. [Schéma des phases du pipeline](#8-schéma-des-phases-du-pipeline)
9. [Base de données — Tables clés](#9-base-de-données--tables-clés)
10. [Incohérences et stubs à connaître](#10-incohérences-et-stubs-à-connaître)

---

## 1. Architecture globale

```
┌─────────────────────────────────────────────────────────────────────┐
│  FRONTEND (React / Vite)                                            │
│                                                                     │
│  App.jsx ──► /nouveau-projet ──► NouveauProjet.jsx (wizard)        │
│              /mes-projets    ──► MesProjets.jsx (liste)             │
│              /projet/:id     ──► PipelineDetail.jsx (suivi)         │
│                                                                     │
│  API layer : api/crm.js  api/projects.js  api/pipeline.js          │
│              └── axios instance pointant sur http://localhost:8000  │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP REST
┌────────────────────────────▼────────────────────────────────────────┐
│  BACKEND (FastAPI / Python)                                         │
│                                                                     │
│  /crm/*      ──► CRM routes (clients, projets)                     │
│  /projects/* ──► Documents upload                                  │
│  /pipeline/* ──► pipeline.py  (start, get, validate)               │
│                      │                                             │
│              agents/pm/graph/graph.py  (LangGraph)                 │
│                      │                                             │
│              12 noeuds (phases) + node_validate + jira_sync         │
│                      │                                             │
│              PostgreSQL  (project_management schema)                │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Partie Frontend — Fichiers et responsabilités

### 2.1 Routage — `client/src/App.jsx`

Déclare les routes React Router. Seules les routes PM sont listées ici.

| Route | Composant | Garde |
|---|---|---|
| `/nouveau-projet` | `NouveauProjet` | `ProtectedRoute` + rôle `pm` |
| `/mes-projets` | `MesProjets` | `ProtectedRoute` + rôle `pm` |
| `/projet/:id` | `PipelineDetail` | `ProtectedRoute` + rôle `pm` |

---

### 2.2 Couche API — fichiers dans `client/src/api/`

Ces fichiers sont la **seule** couche qui parle au backend. Ils exportent des fonctions async.

#### `client/src/api/crm.js`

| Fonction exportée | Méthode + URL | Input | Output (Promise) |
|---|---|---|---|
| `getClients()` | `GET /crm/clients` | — | `[{id, name, industry, contact_email, ...}]` |
| `createClient(body)` | `POST /crm/clients` | `{name, industry?, contact_email?}` | `{id, name, ...}` |
| `getCrmProjects(clientId)` | `GET /crm/projects?client_id={clientId}` | `clientId: int` | `[{id, name, client_id, ...}]` |
| `createProject(body)` | `POST /crm/projects` | `{name, client_id}` | `{id, name, client_id, ...}` |

#### `client/src/api/projects.js`

| Fonction exportée | Méthode + URL | Input | Output (Promise) |
|---|---|---|---|
| `uploadDocument(projectId, file)` | `POST /projects/{projectId}/document` | `projectId: int`, `file: File` (multipart) | `{document_id, filename, size, ...}` |
| `getDocument(projectId)` | `GET /projects/{projectId}/document` | `projectId: int` | `{document_id, filename, ...}` ou `null` |

#### `client/src/api/pipeline.js`

| Fonction exportée | Méthode + URL | Input | Output (Promise) |
|---|---|---|---|
| `getPipelineProjects()` | `GET /pipeline/projects` | — | `[{project_id, project_name, client_name, phases_done, phases_total, current_phase, global_status, created_at}]` |
| `startPipeline(projectId, body)` | `POST /pipeline/{projectId}/start` | `projectId: int`, `{document_id: int, jira_project_key?: str}` | `{project_id, document_id, status: "running", message}` |
| `getPipelineDetail(projectId)` | `GET /pipeline/{projectId}` | `projectId: int` | `{project_id, project_name, phases: [{id, phase, status, ai_output, pm_comment, validated_by, validated_at, updated_at}]}` |
| `validatePhase(projectId, body)` | `POST /pipeline/{projectId}/validate` | `projectId: int`, `{approved: bool, feedback?: str}` | `{project_id, phase, decision, message}` |

---

### 2.3 Pages PM — `client/src/pages/pm/`

#### `NouveauProjet.jsx` — Wizard 4 étapes

```
client/src/pages/pm/NouveauProjet.jsx
```

**Rôle** : Orchestre le wizard de création. Garde en mémoire :
- `step` (1-4)
- `selectedClient` (objet client choisi)
- `createdProject` (objet projet créé)
- `uploadedDoc` (objet document uploadé)

Render conditionnel selon `step` :

| step | Composant rendu | Props transmis |
|---|---|---|
| 1 | `StepClient` | `onNext(client)` |
| 2 | `StepProjet` | `selectedClient`, `onNext(project)`, `onBack` |
| 3 | `StepCDC` | `createdProject`, `onNext(doc)`, `onBack` |
| 4 | `StepLancement` | `selectedClient`, `createdProject`, `uploadedDoc`, `onBack` |

Également affiche `StepIndicator` en haut (barre de progression).

---

#### `MesProjets.jsx` — Liste des projets

```
client/src/pages/pm/MesProjets.jsx
```

**Au montage** :

```
useEffect(() => {
  getPipelineProjects()           ← api/pipeline.js
    .then(data => setProjects(data))
})
```

**Input de `getPipelineProjects()`** : aucun  
**Output** : liste de projets avec statut global + progression phases

**Filtres** : par texte (nom projet / client) et par status (`all`, `pending_human`, `in_progress`, `completed`)

**Clic sur une carte** → `navigate('/projet/{project_id}')` via `ProjectCard`

---

#### `PipelineDetail.jsx` — Vue détaillée pipeline

```
client/src/pages/pm/PipelineDetail.jsx
```

**Au montage** :
```
fetchData()  →  getPipelineDetail(project_id)    ← api/pipeline.js
```

**Polling automatique** : toutes les 4 secondes si `hasRunning = true`
(phases avec status `pending_ai` ou `in_progress` détectées)

**Détection de la phase active** :
1. Cherche la première phase avec `status === "pending_human"` (en attente de validation PM)
2. Si aucune, prend la première phase `in_progress` ou `running`

**Sur validation** :
```
validatePhase(project_id, { approved, feedback })    ← api/pipeline.js
  → fetchData()  (rafraîchit l'état)
```

**Mapping status DB → UI** (fonction interne `getPhaseStatus`) :

| DB status | UI status |
|---|---|
| `validated` | `done` (vert) |
| `pending_human` | `active` (ambre) |
| `pending_ai` ou `in_progress` | `running` (bleu animé) |
| `rejected` | `rejected` (rouge) |
| absent | `pending` (gris) |

---

### 2.4 Composants des étapes — `client/src/pages/pm/steps/`

#### `StepClient.jsx`

**Rôle** : Sélectionner ou créer un client (étape 1)

```
Montage :
  getClients()              ← api/crm.js
    → affiche liste clients

Création :
  createClient({name, industry, contact_email})    ← api/crm.js
    → appelle onNext(client)  (remonte à NouveauProjet)
```

**Input de `createClient`** : `{name: string (requis), industry?: string, contact_email?: string}`  
**Output** : objet client `{id, name, ...}`

---

#### `StepProjet.jsx`

**Rôle** : Créer ou sélectionner un projet pour le client choisi (étape 2)

```
Montage :
  getCrmProjects(selectedClient.id)    ← api/crm.js
    → affiche projets existants du client

Création :
  createProject({name, client_id: selectedClient.id})    ← api/crm.js
    → appelle onNext(project)

Cas 409 (projet existe déjà) :
  → récupère project_id depuis la réponse d'erreur
  → appelle onNext({id: existingId, name})
```

---

#### `StepCDC.jsx`

**Rôle** : Uploader le CDC (Cahier des Charges) — étape 3

```
Montage :
  getDocument(createdProject.id)    ← api/projects.js
    → si document existe, propose de le réutiliser

Upload :
  uploadDocument(createdProject.id, file)    ← api/projects.js
    → appelle onNext({document_id, filename, ...})

Cas 409 (doc existe déjà) :
  → récupère document_id existant
  → appelle onNext avec document existant
```

**Validation fichier (côté frontend avant upload)** :
- Extensions autorisées : `.pdf`, `.docx`, `.txt`
- Taille max : 10 MB

---

#### `StepLancement.jsx`

**Rôle** : Récapitulatif + lancement pipeline (étape 4)

```
Affiche : client, projet, document choisis

Input optionnel : jira_project_key (clé projet Jira, ex: "TALAN")

Sur clic "Lancer" :
  startPipeline(createdProject.id, {
    document_id: uploadedDoc.document_id,
    jira_project_key: jiraKey || undefined
  })                              ← api/pipeline.js
    → navigate('/projet/' + createdProject.id)
```

---

### 2.5 Composants UI réutilisables — `client/src/pages/pm/components/`

| Composant | Rôle |
|---|---|
| `PhaseList.jsx` | Sidebar : liste des 12 phases avec icône de statut, cliquable |
| `PhaseResult.jsx` | Affiche le résultat IA de la phase sélectionnée (rendu spécialisé par phase) |
| `ValidationCard.jsx` | Boutons Approuver/Rejeter + champ feedback obligatoire si rejet |
| `ProjectCard.jsx` | Carte projet dans MesProjets (nom, client, progression, statut) |
| `StepIndicator.jsx` | Barre 4 étapes du wizard |
| `StatusBadge.jsx` | Badge coloré selon statut global |
| `ProgressBar.jsx` | Barre de progression phases (X/12) |
| `ErrorBanner.jsx` | Bannière d'erreur |
| `SkeletonCard.jsx` | Skeleton de chargement pour ProjectCard |

#### `PhaseResult.jsx` — Rendu par phase

| Phase | Ce qui est affiché |
|---|---|
| `extract` | Stats fichier (pages estimées, caractères, taille), aperçu texte, rapport sécurité |
| `epics` | Liste d'épics (titre, description, stratégie de découpage) |
| `stories` | Cartes stories (epic_id, story points, critères d'acceptation) |
| `cpm` | Durée projet, nb tâches critiques, slack max, chemin critique |
| autres | Dump JSON brut de `ai_output` |

#### `ValidationCard.jsx` — Logique d'interaction

```
Clic "Approuver" :
  onValidate({ approved: true })
    → dans PipelineDetail.jsx : validatePhase(project_id, {approved: true})

Clic "Rejeter" :
  → affiche textarea (feedback obligatoire)
  onValidate({ approved: false, feedback: texte })
    → dans PipelineDetail.jsx : validatePhase(project_id, {approved: false, feedback})
```

---

### 2.6 Constantes phases — `client/src/pages/pm/constants/phases.js`

Définit les 12 phases avec métadonnées UI :

| Clé interne | Label affiché | N° phase |
|---|---|---|
| `extract` | Extraction CDC | 1 |
| `epics` | Epics | 2 |
| `stories` | User Stories | 3 |
| `refinement` | Raffinement | 4 |
| `story_deps` | Dépendances Stories | 5 |
| `prioritization` | Priorisation MoSCoW | 6 |
| `tasks` | Tasks | 7 |
| `task_deps` | Dépendances Tasks | 8 |
| `cpm` | Chemin Critique (CPM) | 9 |
| `sprints` | Sprint Planning | 10 |
| `staffing` | Staffing | 11 |
| `monitoring` | Monitoring | 12 |

`PHASE_KEY_MAP` fait la correspondance entre le nom DB (`phase_1_extraction`) et la clé courte (`extract`).

---

## 3. Partie Backend — Fichiers et responsabilités

### 3.1 Endpoints pipeline — `backend/app/api/pipeline/pipeline.py`

Prefix : `/pipeline` — Toutes les routes nécessitent le rôle PM.

#### `GET /pipeline/projects`

```python
async def list_pipeline_projects(current_user, db) -> list[dict]
```

**Logique** :
1. Résout `user_id` → `employee_id` via `get_employee_id_by_user()`
2. Récupère tous les projets où `project_manager_id = employee_id`
3. Pour chaque projet, lit les `PipelineState` en DB
4. Calcule `phases_done` (count `validated`), `current_phase` (1ère non-validée), `global_status`

**Output** :
```json
[{
  "project_id": 1,
  "project_name": "Mon Projet",
  "client_name": "Talan",
  "phases_done": 3,
  "phases_total": 12,
  "current_phase": "story_deps",
  "current_status": "pending_human",
  "global_status": "pending_human",
  "created_at": "2026-04-10T..."
}]
```

---

#### `POST /pipeline/{project_id}/start`

```python
async def start_pipeline(project_id, body: StartPipelineRequest, current_user, db) -> dict
```

**Body** :
```json
{ "document_id": 42, "jira_project_key": "TALAN" }
```

**Logique** :
1. Vérifie que le projet appartient au PM
2. Vérifie que `document_id` appartient au projet
3. Construit `PMPipelineState` initial
4. Appelle `pm_graph.ainvoke(initial_state, config={"configurable": {"thread_id": f"pm_{project_id}"}})`
5. Le graphe tourne jusqu'au premier `interrupt` dans `node_validate`

**Output** :
```json
{ "project_id": 1, "document_id": 42, "status": "running", "message": "Pipeline lancé" }
```

---

#### `GET /pipeline/{project_id}`

```python
async def get_project_pipeline(project_id, current_user, db) -> dict
```

**Logique** :
1. Récupère toutes les `PipelineState` pour ce projet (triées par id)
2. Injection artificielle de la phase extraction en `validated` si absente (rétrocompatiblité)
3. Mappe chaque entrée DB → dict JSON

**Output** :
```json
{
  "project_id": 1,
  "project_name": "Mon Projet",
  "phases": [{
    "id": 10,
    "phase": "phase_1_extraction",
    "status": "validated",
    "ai_output": { "pages_est": 12, "char_count": 5400, ... },
    "pm_comment": null,
    "validated_by": 5,
    "validated_at": "2026-04-11T...",
    "updated_at": "2026-04-11T..."
  }, ...]
}
```

---

#### `POST /pipeline/{project_id}/validate`

```python
async def validate_phase(project_id, body: ValidateRequest, current_user, db) -> dict
```

**Body** :
```json
{ "approved": true }
// ou
{ "approved": false, "feedback": "Les epics sont trop grossiers, refais avec plus de détail" }
```

**Logique** :
1. Trouve la ligne `PipelineState` avec `status = PENDING_VALIDATION`
2. Update en DB → `VALIDATED` ou `REJECTED` + `pm_comment`, `validated_by`, `validated_at`
3. `pm_graph.aupdate_state(config, {validation_status, human_feedback}, as_node="node_validate")`
4. `pm_graph.ainvoke(None, config)` → reprend le graphe

**Output** :
```json
{ "project_id": 1, "phase": "epics", "decision": "validated", "message": "Phase validée, pipeline reprend" }
```

---

### 3.2 Upload document — `backend/app/api/documents/documents.py`

#### `POST /projects/{project_id}/document`

**Logique** :
1. Vérifie PM + ownership du projet
2. Vérifie extension (`.pdf`, `.docx`, `.txt`) et taille (max 10 MB)
3. Calcule SHA-256 du fichier pour détecter un re-upload identique
4. Écrit le fichier sur disque : `backend/data/documents/{project_id}/{filename}`
5. Insert/Update dans `project_management.project_documents`

**Output** : `{document_id, filename, size, mime_type, sha256}`

---

### 3.3 État du pipeline — `backend/agents/pm/state/state.py`

`PMPipelineState` (TypedDict) — tout l'état partagé entre tous les noeuds :

```python
class PMPipelineState(TypedDict):
    # Identification
    project_id: int
    user_id: int
    document_id: int

    # Phase 1 - Extraction
    cdc_text: str
    security_scan: dict | None

    # Phases 2-12 - Résultats
    epics: list[dict]
    stories: list[dict]
    refinement_rounds: list[dict]
    refined_stories: list[dict]
    story_dependencies: list[dict]
    priorities: list[dict]
    tasks: list[dict]
    task_dependencies: list[dict]
    cpm_result: dict
    critical_path: list[int]
    sprints: list[dict]
    staffing: dict          # {task_idx → employee_id}
    monitoring_plan: dict

    # Contrôle de flux
    current_phase: str      # ex: "epics", "stories", ...
    pipeline_state_id: int  # ID de la ligne en DB

    # Validation humaine
    validation_status: str  # pending_ai | pending_human | validated | rejected
    human_feedback: str | None

    # Jira
    jira_project_key: str
    jira_epic_map: dict        # {local_idx → jira_epic_key}
    jira_story_map: dict
    jira_task_map: dict
    jira_sprint_map: dict
    jira_synced_phases: list[str]

    # Erreur
    error: str | None
```

---

### 3.4 Base de données — `backend/agents/pm/db/db.py`

Fonctions d'accès DB utilisées par tous les noeuds :

| Fonction | Signature | Output |
|---|---|---|
| `upsert_pipeline_state` | `(project_id, phase, status, ai_output?, pm_comment?, validated_by?, validated_at?)` | `PipelineState` ORM |
| `get_pipeline_state` | `(project_id, phase)` | `PipelineState` ou `None` |
| `get_all_pipeline_states` | `(project_id)` | `list[PipelineState]` |
| `get_employee_id_by_user` | `(user_id)` | `int` ou `None` |
| `phase_str_to_enum` | `(phase: str)` | `PipelinePhaseEnum` |

`upsert_pipeline_state` utilise `INSERT ... ON CONFLICT DO UPDATE` (contrainte `uq_pipeline_project_phase`).

---

### 3.5 Graphe LangGraph — `backend/agents/pm/graph/graph.py`

#### Initialisation au démarrage FastAPI

```python
# app/main.py - lifespan
await init_pm_graph()
```

`init_pm_graph()` :
1. Crée une connexion `AsyncPostgresSaver` vers PostgreSQL
2. Configure la table de checkpoint LangGraph
3. Compile le graphe via `build_pm_graph(checkpointer)`
4. Stocke dans la variable globale `pm_graph`

#### Structure du graphe

```
START
  └── node_extraction (phase 1)
        └── node_validate
              ├── (validated) ──► jira_sync ──► node_epics (phase 2)
              │                                    └── node_validate
              │                                          ├── (validated) ──► jira_sync ──► node_stories (phase 3)
              │                                          └── (rejected)  ──► node_epics  (relance)
              └── (rejected)  ──► node_extraction (relance)

  ... même pattern pour phases 3 → 11 ...

  node_monitoring (phase 12) ──► END  (pas de validation humaine)
```

**Routage après `node_validate`** (fonction `_route_after_validate`) :
- `validation_status == "validated"` → `"jira_sync"`
- sinon → retour au noeud de la phase courante

**Routage après `jira_sync`** (fonction `_route_after_jira_sync`) :
- Lit `current_phase` et renvoie vers le noeud suivant selon `_PHASE_ORDER`
- Si dernière phase → `END`

**Thread de checkpoint** : `thread_id = f"pm_{project_id}"` — chaque projet a son propre fil de reprise.

---

### 3.6 Noeud de validation — `backend/agents/pm/graph/node_validate.py`

```python
async def node_validate(state: PMPipelineState) -> dict
```

**Étapes** :
1. Lit `state["current_phase"]`
2. Appelle `_get_phase_output(state, phase)` pour sérialiser le résultat IA en dict JSON
3. `upsert_pipeline_state(project_id, phase, PENDING_VALIDATION, ai_output=...)` → persist en DB
4. `interrupt({"phase": ..., "ai_output": ..., "message": "..."})` → **suspend le graphe**
5. À la reprise (après `/validate`) :
   - lit `decision = {"approved": bool, "feedback": str}`
   - retourne `{validation_status: "validated" | "rejected", human_feedback}`

**`_get_phase_output(state, phase)`** — mapping phase → champ état :

| Phase | Champ retourné |
|---|---|
| `extract` | `{pages_est, char_count, preview, security_scan, ...}` |
| `epics` | `state["epics"]` |
| `stories` | `state["stories"]` |
| `refinement` | `state["refined_stories"]` |
| `story_deps` | `state["story_dependencies"]` |
| `prioritization` | `state["priorities"]` |
| `tasks` | `state["tasks"]` |
| `task_deps` | `state["task_dependencies"]` |
| `cpm` | `state["cpm_result"]` |
| `sprints` | `state["sprints"]` |
| `staffing` | `state["staffing"]` |

---

### 3.7 Noeuds de phase — `backend/agents/pm/agents/`

#### Phase 1 — Extraction : `agents/pm/agents/extraction/agent.py`

```python
async def node_extraction(state: PMPipelineState) -> dict
```

1. Récupère `document_id` depuis state
2. Lit le record `ProjectDocument` en DB → récupère `file_path`
3. Charge le fichier depuis disque
4. Valide extension + taille via `service.validate_file()`
5. Extrait le texte via `service.extract_text(file_bytes, extension)` :
   - `.pdf` → `pdfplumber`
   - `.docx` → `python-docx`
   - `.txt` → décodage UTF-8
6. Scan de sécurité (nom fichier + contenu) via `service.scan_document()`
7. Retourne :
```python
{
    "cdc_text": "texte extrait...",
    "security_scan": {"threats": [...], "blocked": False, ...},
    "current_phase": "extract",
    "validation_status": "pending_human",
    "error": None
}
```

---

#### Phase 2 — Epics : `agents/pm/agents/epics/agent.py`

```python
async def node_epics(state: PMPipelineState) -> dict
```

1. Vérifie `cdc_text` non vide
2. Appelle `service.generate_epics(cdc_text, human_feedback)` → appel LLM (`openai/gpt-oss-120b` via `invoke_with_fallback`)
3. Parse + normalise le JSON retourné
4. Persist via `repository.save_epics(project_id, epics)` → table `project_management.epics`
5. Retourne :
```python
{
    "epics": [{
        "title": "...",
        "description": "...",
        "splitting_strategy": "..."
    }, ...],
    "current_phase": "epics",
    "validation_status": "pending_human",
    "human_feedback": None,
    "error": None
}
```

---

#### Phase 3 — Stories : `agents/pm/agents/stories/agent.py`

```python
async def node_stories(state: PMPipelineState) -> dict
```

1. Vérifie `epics` non vide
2. Appelle `service.generate_stories(epics, human_feedback)` → LLM
3. ⚠️ `repository.save_stories()` est un **STUB** (`pass`) — les stories ne sont PAS persistées dans la table métier
4. Retourne :
```python
{
    "stories": [{
        "title": "...",
        "epic_id": 0,
        "story_points": 5,
        "acceptance_criteria": ["..."]
    }, ...],
    "current_phase": "stories",
    "validation_status": "pending_human",
    "human_feedback": None,
    "error": None
}
```

---

#### Phases 4 à 11 — Stubs

| Phase | Fichier | État |
|---|---|---|
| `refinement` (4) | `agents/pm/agents/refinement/agent.py` | STUB — retourne `refined_stories=[]` |
| `story_deps` (5) | `agents/pm/agents/dependencies/story_deps.py` | STUB |
| `prioritization` (6) | `agents/pm/agents/prioritization/agent.py` | STUB |
| `tasks` (7) | `agents/pm/agents/tasks/agent.py` | STUB |
| `task_deps` (8) | `agents/pm/agents/dependencies/task_deps.py` | STUB |
| `cpm` (9) | `agents/pm/agents/cpm/agent.py` | Structure algo présente, sortie vide |
| `sprints` (10) | `agents/pm/agents/sprints/agent.py` | STUB |
| `staffing` (11) | `agents/pm/agents/staffing/agent.py` | STUB |

Ces phases renvoient des structures vides mais passent quand même par `node_validate` — le PM peut les valider.

---

#### Phase 12 — Monitoring : `agents/pm/agents/monitoring/agent.py`

```python
async def node_monitoring(state: PMPipelineState) -> dict
```

1. Génère un plan de monitoring (stub) : KPIs, alertes, fréquence de review, webhooks Jira
2. **Auto-valide** : appelle directement `upsert_pipeline_state(..., status=VALIDATED)` sans passer par `node_validate`
3. Pas d'interruption humaine — fin du graphe

---

### 3.8 Synchronisation Jira — `backend/agents/pm/graph/node_jira_sync.py`

```python
async def node_jira_sync(state: PMPipelineState) -> dict
```

**Conditions d'activation** :
- `JIRA_BASE_URL` et `JIRA_API_TOKEN` présents dans `.env`
- Phase courante pas déjà dans `jira_synced_phases`

**Actions par phase** :

| Phase | Action Jira | Fonction appelée |
|---|---|---|
| `extract` | Rien | — |
| `epics` | Créer les épics | `actions.create_epic(title, description)` |
| `stories` | Créer les stories liées aux épics | `actions.create_story(title, description, acceptance_criteria, epic_key, story_points)` |
| `tasks` | Créer les sous-tâches | `actions.create_task(title, description, parent_key)` |
| `sprints` | Créer les sprints + ajouter les issues | `actions.create_sprint()` + `actions.add_issues_to_sprint()` |

**Maps construites dans le state** :
- `jira_epic_map`: `{local_idx → jira_epic_key}`
- `jira_story_map`: `{local_idx → jira_issue_key}`
- `jira_task_map`: `{local_idx → jira_subtask_key}`
- `jira_sprint_map`: `{local_idx → jira_sprint_id}`

Fichiers Jira :
- `agents/pm/jira/client.py` — client HTTP Jira (Basic Auth)
- `agents/pm/jira/actions.py` — fonctions haut niveau (create_epic, etc.)

---

## 4. Flux 1 — Création d'un projet (wizard 4 étapes)

```
UTILISATEUR clique "Nouveau Projet" dans la sidebar
  │
  ▼
App.jsx  →  route /nouveau-projet  →  NouveauProjet.jsx
  │
  ▼ step=1
StepClient.jsx (montage)
  │
  ├── getClients()
  │     ← api/crm.js : getClients()
  │     → GET /crm/clients
  │     ← Backend: liste clients [{id, name, industry, ...}]
  │
  ├── Utilisateur sélectionne un client OU crée un nouveau :
  │     createClient({name, industry, contact_email})
  │       ← api/crm.js : createClient(body)
  │       → POST /crm/clients  body: {name, industry, contact_email}
  │       ← Backend: {id, name, ...}
  │
  └── onNext(client)  →  NouveauProjet : setSelectedClient(client), setStep(2)

  ▼ step=2
StepProjet.jsx (montage, reçoit selectedClient)
  │
  ├── getCrmProjects(selectedClient.id)
  │     ← api/crm.js : getCrmProjects(clientId)
  │     → GET /crm/projects?client_id={id}
  │     ← Backend: [{id, name, client_id, ...}]
  │
  ├── Utilisateur choisit un projet existant OU crée un nouveau :
  │     createProject({name, client_id: selectedClient.id})
  │       ← api/crm.js : createProject(body)
  │       → POST /crm/projects  body: {name, client_id}
  │       ← Backend: {id, name, client_id, ...}
  │       Si 409 → récupère l'id existant depuis la réponse d'erreur
  │
  └── onNext(project)  →  NouveauProjet : setCreatedProject(project), setStep(3)

  ▼ step=3
StepCDC.jsx (montage, reçoit createdProject)
  │
  ├── getDocument(createdProject.id)
  │     ← api/projects.js : getDocument(projectId)
  │     → GET /projects/{id}/document
  │     ← Backend: {document_id, filename, ...} ou null
  │
  ├── Utilisateur drag-and-drop ou sélectionne un fichier
  │     Validation locale : extension (.pdf/.docx/.txt) + taille (≤10MB)
  │
  ├── uploadDocument(createdProject.id, file)
  │     ← api/projects.js : uploadDocument(projectId, file)
  │     → POST /projects/{id}/document  (multipart/form-data, champ "file")
  │     ← Backend: {document_id, filename, size, mime_type, sha256}
  │     Si 409 → réutilise document existant
  │
  └── onNext(doc)  →  NouveauProjet : setUploadedDoc(doc), setStep(4)

  ▼ step=4
StepLancement.jsx (reçoit selectedClient, createdProject, uploadedDoc)
  │
  ├── Affiche récapitulatif
  ├── Champ optionnel : jira_project_key
  │
  └── Clic "Lancer le pipeline" :
        startPipeline(createdProject.id, {
          document_id: uploadedDoc.document_id,
          jira_project_key: "TALAN"  // si renseigné
        })
          ← api/pipeline.js : startPipeline(projectId, body)
          → POST /pipeline/{id}/start
          ← Backend: {project_id, document_id, status: "running", message}
        
        navigate('/projet/' + createdProject.id)
          → PipelineDetail.jsx
```

---

## 5. Flux 2 — Lancement du pipeline (backend)

```
POST /pipeline/{project_id}/start
  │
  ▼
pipeline.py : start_pipeline(project_id, body, current_user, db)
  │
  ├── Résout user_id → employee_id
  │     db.py : get_employee_id_by_user(user_id)
  │
  ├── Vérifie projet : project.project_manager_id == employee_id
  │
  ├── Vérifie document : document.project_id == project_id
  │
  ├── Construit PMPipelineState :
  │     {
  │       project_id, user_id, document_id,
  │       jira_project_key,
  │       current_phase: "extract",
  │       validation_status: "pending_ai",
  │       cdc_text: "",
  │       epics: [], stories: [], ...
  │     }
  │
  └── pm_graph.ainvoke(initial_state, config={"thread_id": f"pm_{project_id}"})
        │
        ▼
        node_extraction(state)       ← agents/pm/agents/extraction/agent.py
          │
          ├── Lit ProjectDocument depuis DB (document_id → file_path)
          ├── Charge fichier depuis disque (backend/data/documents/...)
          ├── service.validate_file(bytes, extension)
          ├── service.extract_text(bytes, extension)  → cdc_text
          ├── service.scan_document(filename, text)   → security_scan
          └── Retourne {cdc_text, security_scan, current_phase:"extract", validation_status:"pending_human"}
                │
                ▼
                node_validate(state)     ← agents/pm/graph/node_validate.py
                  │
                  ├── _get_phase_output(state, "extract") → dict sérialisable
                  ├── upsert_pipeline_state(project_id, "extract", PENDING_VALIDATION, ai_output)
                  │     ← db.py : upsert_pipeline_state(...)
                  │     → INSERT/UPDATE project_management.pipeline_state
                  │
                  └── interrupt({phase, ai_output, message})
                        ← LangGraph : suspend le graphe
                        ← Le thread PostgreSQL est sauvegardé (AsyncPostgresSaver)
                        ← Retour à start_pipeline qui catch GraphInterrupt
                        ← Retourne au frontend : {status: "running"}
```

---

## 6. Flux 3 — Suivi et validation des phases

### 6.1 Polling frontend

```
PipelineDetail.jsx (montage, project_id depuis URL params)
  │
  ├── fetchData()
  │     getPipelineDetail(project_id)
  │       ← api/pipeline.js : getPipelineDetail(projectId)
  │       → GET /pipeline/{project_id}
  │       ← {project_id, project_name, phases: [{phase, status, ai_output, ...}]}
  │
  ├── setPhases(data.phases)
  ├── Cherche activePhase : première phase "pending_human"
  │
  ├── Si hasRunning (phases pending_ai/in_progress) :
  │     setInterval(fetchData, 4000)  → polling toutes les 4s
  │
  └── Affiche :
        ├── PhaseList (sidebar gauche, toutes les phases + statuts)
        ├── PhaseResult (contenu principal, ai_output de activePhase)
        └── ValidationCard (si activePhase.status === "pending_human")
```

### 6.2 PM valide ou rejette une phase

```
Utilisateur clique "Approuver" dans ValidationCard
  │
  ▼
ValidationCard.jsx : handleValidate(true)
  → appelle onValidate({approved: true})
    │
    ▼
PipelineDetail.jsx : validatePhase(project_id, {approved: true})
  ← api/pipeline.js : validatePhase(projectId, body)
  → POST /pipeline/{project_id}/validate  body: {approved: true}
  │
  ▼
pipeline.py : validate_phase(project_id, body, current_user, db)
  │
  ├── Trouve PipelineState avec status=PENDING_VALIDATION
  ├── upsert_pipeline_state(..., VALIDATED, pm_comment=None, validated_by, validated_at=now)
  │
  ├── pm_graph.aupdate_state(
  │     config={"thread_id": f"pm_{project_id}"},
  │     values={"validation_status": "validated", "human_feedback": None},
  │     as_node="node_validate"
  │   )
  │
  └── pm_graph.ainvoke(None, config)  → reprend le graphe
        │
        ▼
        node_validate reprend (validation_status == "validated")
          └── retourne {validation_status: "validated"}
                │
                ▼
                _route_after_validate → "jira_sync"
                  │
                  ▼
                  node_jira_sync(state)      ← graph/node_jira_sync.py
                    │
                    ├── Si Jira activé ET phase == "epics" :
                    │     actions.create_epic(title, description) pour chaque epic
                    │     → met à jour jira_epic_map
                    │
                    └── Retourne state mis à jour
                          │
                          ▼
                          _route_after_jira_sync → "node_epics" (phase suivante)
                            │
                            ▼
                            node_epics(state)    ← agents/pm/agents/epics/agent.py
                              │
                              ├── service.generate_epics(cdc_text, human_feedback=None)
                              │     → appel LLM → liste d'épics
                              ├── repository.save_epics(project_id, epics)
                              └── Retourne {epics, current_phase:"epics", validation_status:"pending_human"}
                                    │
                                    ▼
                                    node_validate → interrupt (attente prochaine validation)
                                      ← upsert PENDING_VALIDATION en DB avec epics dans ai_output
```

### 6.3 PM rejette une phase

```
Utilisateur remplit feedback + clique "Rejeter" dans ValidationCard
  │
  ▼
ValidationCard.jsx : handleValidate(false)
  → onValidate({approved: false, feedback: "Les epics sont trop vagues"})
    │
    ▼
PipelineDetail.jsx : validatePhase(project_id, {approved: false, feedback: "..."})
  → POST /pipeline/{project_id}/validate
    │
    ▼
pipeline.py : validate_phase
  ├── upsert_pipeline_state(..., REJECTED, pm_comment="Les epics sont trop vagues")
  ├── pm_graph.aupdate_state(..., {validation_status:"rejected", human_feedback:"..."})
  └── pm_graph.ainvoke(None, config)
        │
        ▼
        node_validate reprend → validation_status == "rejected"
          └── retourne {validation_status:"rejected", human_feedback:"Les epics sont trop vagues"}
                │
                ▼
                _route_after_validate → "node_epics"  (même phase, relance)
                  │
                  ▼
                  node_epics(state)  — state contient human_feedback
                    └── service.generate_epics(cdc_text, human_feedback="Les epics sont trop vagues")
                          → LLM prend en compte le feedback
                          → nouvelle liste d'épics
                    → node_validate → interrupt (nouvelle attente validation)
```

---

## 7. Flux 4 — Résumé complet A → Z avec tous les appels

```
1.  NouveauProjet.jsx (étape 1)
      → api/crm.js : getClients()
      → GET /crm/clients
      ← [{id, name, industry}]

2.  StepClient.jsx
      → api/crm.js : createClient({name, industry, contact_email})
      → POST /crm/clients
      ← {id, name}

3.  NouveauProjet.jsx (étape 2)
      → api/crm.js : getCrmProjects(clientId)
      → GET /crm/projects?client_id=X
      ← [{id, name}]

4.  StepProjet.jsx
      → api/crm.js : createProject({name, client_id})
      → POST /crm/projects
      ← {id, name, client_id}

5.  NouveauProjet.jsx (étape 3)
      → api/projects.js : getDocument(projectId)
      → GET /projects/{id}/document
      ← {document_id, ...} ou null

6.  StepCDC.jsx
      → api/projects.js : uploadDocument(projectId, file)
      → POST /projects/{id}/document  (multipart)
      Backend :
        documents.py : upload_document()
          → valide extension, taille
          → écrit sur disque
          → INSERT project_management.project_documents
      ← {document_id, filename, size, sha256}

7.  StepLancement.jsx
      → api/pipeline.js : startPipeline(projectId, {document_id, jira_project_key})
      → POST /pipeline/{id}/start
      Backend :
        pipeline.py : start_pipeline()
          → graph.py : get_pm_graph()
          → pm_graph.ainvoke(initial_state)
          → extraction/agent.py : node_extraction()
              → service.py : validate_file()
              → service.py : extract_text()
              → service.py : scan_document()
              ← {cdc_text, security_scan, current_phase:"extract", validation_status:"pending_human"}
          → node_validate.py : node_validate()
              → db.py : upsert_pipeline_state("extract", PENDING_VALIDATION, ai_output)
              → interrupt()  ← graphe suspendu
      ← {status: "running"}

8.  navigate('/projet/{id}')
      → PipelineDetail.jsx monte

9.  PipelineDetail.jsx (montage)
      → api/pipeline.js : getPipelineDetail(projectId)
      → GET /pipeline/{id}
      Backend :
        pipeline.py : get_project_pipeline()
          → db.py : get_all_pipeline_states(project_id)
          ← [{phase:"phase_1_extraction", status:"pending_human", ai_output:{...}}]
      ← {phases: [{...}]}
      → Affiche PhaseResult (résultat extraction) + ValidationCard

10. PM clique "Approuver" sur la phase extraction
      → api/pipeline.js : validatePhase(projectId, {approved: true})
      → POST /pipeline/{id}/validate
      Backend :
        pipeline.py : validate_phase()
          → db.py : upsert_pipeline_state("extract", VALIDATED, validated_by, validated_at)
          → pm_graph.aupdate_state({validation_status:"validated"}, as_node="node_validate")
          → pm_graph.ainvoke(None)
          → node_validate reprend → route "jira_sync"
          → node_jira_sync.py : node_jira_sync()
              → phase "extract" : rien à créer dans Jira
              ← state inchangé
          → _route_after_jira_sync → "node_epics"
          → epics/agent.py : node_epics()
              → service.py : generate_epics(cdc_text, None)  ← appel LLM
              → repository.py : save_epics(project_id, epics)
              ← {epics:[...], current_phase:"epics", validation_status:"pending_human"}
          → node_validate.py : node_validate()
              → db.py : upsert_pipeline_state("epics", PENDING_VALIDATION, epics)
              → interrupt()
      ← {phase:"epics", decision:"validated"}

11. PipelineDetail.jsx (polling 4s)
      → getPipelineDetail(projectId)
      ← phases avec "epics" en PENDING_VALIDATION
      → Affiche résultat épics + ValidationCard

12. PM valide les épics
      → validatePhase(projectId, {approved: true})
      Backend :
        → VALIDATED en DB pour epics
        → node_jira_sync : create_epic() × N  (si Jira actif)
            → jira/actions.py : create_epic(title, description)
                → jira/client.py : POST /rest/api/3/issue (type Epic)
            → jira_epic_map = {0:"TALAN-1", 1:"TALAN-2", ...}
        → node_stories()
            → service.py : generate_stories(epics, None)  ← LLM
            ← {stories:[...], current_phase:"stories", validation_status:"pending_human"}
        → node_validate → interrupt (attente validation stories)

13. [Cycle se répète pour phases 3 → 11]
    Chaque phase :
      a. Agent génère résultat (LLM ou stub)
      b. node_validate persist PENDING_VALIDATION + interrupt
      c. Frontend poll → détecte pending_human → affiche résultat + ValidationCard
      d. PM approuve ou rejette
      e. Si approuvé → jira_sync → phase suivante
      f. Si rejeté → relance même phase avec human_feedback

14. Phase 12 — Monitoring
      → node_monitoring()
          → génère monitoring_plan (stub)
          → db.py : upsert_pipeline_state("monitoring", VALIDATED)  ← auto-validé
          ← {monitoring_plan:{...}, validation_status:"validated"}
      → END  (graphe terminé)

15. PipelineDetail.jsx (dernier poll)
      → getPipelineDetail(projectId)
      ← 12/12 phases VALIDATED → global_status = "completed"
      → Affiche pipeline complété (plus de ValidationCard)
```

---

## 8. Schéma des phases du pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│  Phase  │ Noeud            │ LLM │ Validation PM │ Jira sync       │
├─────────┼──────────────────┼─────┼───────────────┼─────────────────┤
│  1      │ node_extraction  │ Non │ Oui           │ Non             │
│  2      │ node_epics       │ Oui │ Oui           │ create_epic     │
│  3      │ node_stories     │ Oui │ Oui           │ create_story    │
│  4      │ node_refinement  │ Oui*│ Oui           │ Non             │
│  5      │ node_story_deps  │ Oui*│ Oui           │ Non             │
│  6      │ node_prioritiz.  │ Oui*│ Oui           │ Non             │
│  7      │ node_tasks       │ Oui*│ Oui           │ create_task     │
│  8      │ node_task_deps   │ Oui*│ Oui           │ Non             │
│  9      │ node_cpm         │ Non │ Oui           │ Non             │
│  10     │ node_sprints     │ Oui*│ Oui           │ create_sprint   │
│  11     │ node_staffing    │ Oui*│ Oui           │ Non             │
│  12     │ node_monitoring  │ Non │ Non (auto)    │ Non             │
└─────────┴──────────────────┴─────┴───────────────┴─────────────────┘
* = stub (retourne structure vide pour l'instant)
```

---

## 9. Base de données — Tables clés

### `project_management.project_documents`

| Colonne | Type | Description |
|---|---|---|
| `id` | int PK | document_id |
| `project_id` | int FK | projet associé |
| `filename` | varchar | nom original du fichier |
| `file_path` | varchar | chemin sur disque |
| `file_size` | int | taille en octets |
| `mime_type` | varchar | ex: `application/pdf` |
| `sha256` | varchar | empreinte pour détecter doublons |
| `created_at` | timestamp | |

### `project_management.pipeline_state`

| Colonne | Type | Description |
|---|---|---|
| `id` | int PK | |
| `project_id` | int FK | |
| `phase` | PipelinePhaseEnum | ex: `PHASE_2_EPICS` |
| `status` | PipelineStatusEnum | `pending_ai`, `pending_validation`, `validated`, `rejected` |
| `ai_output` | JSONB | résultat IA sérialisé |
| `pm_comment` | text | feedback du PM en cas de rejet |
| `validated_by` | int FK | employee_id du PM |
| `validated_at` | timestamp | |
| `updated_at` | timestamp | |

Contrainte unique : `uq_pipeline_project_phase` → `(project_id, phase)` — un seul état par phase par projet.

### `project_management.epics`

Alimentée par `repository.save_epics()` en phase 2 (delete + insert).

---

## 10. Incohérences et stubs à connaître

| Problème | Fichier | Impact |
|---|---|---|
| `stories/repository.py` est un stub (`pass`) | `agents/pm/agents/stories/repository.py` | Les stories n'ont pas de table métier |
| Phases 4-11 sont des stubs (retournent `[]`) | `agents/pm/agents/*/agent.py` | Pipeline complétable mais sans vraies données |
| Commentaire trompeur dans `graph.py` : "extraction pas de validation" | `agents/pm/graph/graph.py` | L'extraction passe bien par `node_validate` |
| `GET /pipeline/{id}` injecte la phase extraction en `validated` si absente | `pipeline.py` | Comportement rétrocompatible mais masque l'état réel |
| `jira_*_map` dans le state ne sont pas écrits dans les colonnes `jira_*_key` des tables métier | `node_jira_sync.py` | Les clés Jira ne sont pas persistées dans les tables epics/stories/tasks |
| `thread_id` dans l'ancien code était `str(project_id)`, maintenant `f"pm_{project_id}"` | `pipeline.py` | Anciens checkpoints incompatibles si migration |

---

*Document généré le 2026-04-12 — couvre la branche `feature/project-management-db-schema`*
