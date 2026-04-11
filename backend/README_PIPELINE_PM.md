# Pipeline PM - Guide Complet (A a Z)

Ce document explique tout le flux PM depuis l'upload du Cahier des Charges (CDC) jusqu'a la generation des epics/stories et la synchronisation Jira.

## 1) Vue d'ensemble

Le pipeline PM est un graphe LangGraph en 12 phases.

- Phase 1: extraction CDC
- Phase 2: epics
- Phase 3: stories
- Phase 4: refinement
- Phase 5: story deps
- Phase 6: prioritization
- Phase 7: tasks
- Phase 8: task deps
- Phase 9: CPM
- Phase 10: sprints
- Phase 11: staffing
- Phase 12: monitoring

Pattern global:

1. Un noeud de phase produit un resultat.
2. `node_validate` persiste `PENDING_VALIDATION` dans `project_management.pipeline_state`.
3. Le graphe se suspend (`interrupt`).
4. Le PM appelle l'API `/pipeline/{project_id}/validate`.
5. Si valide: passage par `jira_sync`, puis phase suivante.
6. Si rejete: relance de la meme phase avec `human_feedback`.

## 2) Point d'entree et initialisation

### 2.1 Demarrage serveur

Fichier: `app/main.py`

- Au startup FastAPI, deux graphes sont initialises:
  - `init_graph()` (orchestrateur chat)
  - `init_pm_graph()` (pipeline PM)

Donc si `init_pm_graph()` echoue, les endpoints pipeline ne pourront pas lancer le flow.

### 2.2 Construction du graphe PM

Fichier: `agents/pm/graph/graph.py`

- `build_pm_graph()` enregistre tous les noeuds.
- Entry point: `node_extraction`.
- Toutes les phases 1->11 vont vers `node_validate`.
- `node_validate` route:
  - `validated` -> `jira_sync`
  - `rejected` -> retour meme noeud de phase
- `jira_sync` route vers la phase suivante.
- `node_monitoring` (phase 12) va directement a `END`.

Checkpoint:

- `AsyncPostgresSaver` est utilise pour reprendre le graphe apres interruption.
- `thread_id = str(project_id)` est la cle de reprise.

## 3) APIs impliquees

## 3.1 Upload CDC

Fichier: `app/api/documents/documents.py`

Endpoint:

- `POST /projects/{project_id}/document`

Ce que fait cet endpoint:

1. Verifie que l'utilisateur est PM et proprietaire du projet.
2. Verifie extension (`.pdf`, `.docx`, `.txt`).
3. Verifie la taille (max 10 MB).
4. Calcule SHA-256 pour detecter re-upload identique.
5. Ecrit le fichier sur disque: `backend/data/documents/{project_id}/...`.
6. Ecrit en DB dans `project_management.project_documents`.
7. Retourne `document_id`.

## 3.2 Lancer pipeline

Fichier: `app/api/pipeline/pipeline.py`

Endpoint:

- `POST /pipeline/{project_id}/start`

Input:

- `document_id`
- `jira_project_key` (optionnel)

Ce que fait l'endpoint:

1. Verifie PM/projet.
2. Verifie que `document_id` appartient bien au projet.
3. Construit `initial_state` (`PMPipelineState`).
4. Lance `pm_graph.ainvoke(initial_state, config)` avec `thread_id = project_id`.
5. Le graphe tourne jusqu'au premier `interrupt` de `node_validate`.

## 3.3 Suivre l'etat

Fichier: `app/api/pipeline/pipeline.py`

Endpoint:

- `GET /pipeline/{project_id}`

Retourne les lignes `pipeline_state` (phase, status, ai_output, commentaire PM, etc).

## 3.4 Valider/Rejeter

Fichier: `app/api/pipeline/pipeline.py`

Endpoint:

- `POST /pipeline/{project_id}/validate`

Input:

- `approved: bool`
- `feedback: str` (obligatoire si `approved=false`)

Ce que fait l'endpoint:

1. Cherche la phase en `PENDING_VALIDATION`.
2. Upsert en DB avec `VALIDATED` ou `REJECTED`.
3. Injecte dans l'etat LangGraph:
   - `validation_status`
   - `human_feedback`
4. Reprend le graphe avec `pm_graph.ainvoke(None, config)`.

## 4) Chaine d'appel complete (fichier -> fonction)

## 4.1 Upload CDC

1. `app/api/documents/documents.py` -> `upload_document`
2. Ecriture fichier disque
3. Insert/Update `ProjectDocument` (`project_management.project_documents`)
4. Retour `document_id`

## 4.2 Start Pipeline

1. `app/api/pipeline/pipeline.py` -> `start_pipeline`
2. `agents/pm/graph/graph.py` -> `get_pm_graph`
3. `pm_graph.ainvoke(initial_state)`
4. `agents/pm/agents/extraction/agent.py` -> `node_extraction`
5. `agents/pm/agents/extraction/service.py` -> `validate_file`, `extract_text`
6. `agents/pm/graph/node_validate.py` -> `node_validate`
7. `interrupt` (attente validation PM)

## 4.3 Resume apres validation

1. `app/api/pipeline/pipeline.py` -> `validate_phase`
2. `pm_graph.aupdate_state(..., as_node="node_validate")`
3. `pm_graph.ainvoke(None)`
4. Si valide:
   - `agents/pm/graph/node_jira_sync.py` -> `node_jira_sync`
   - route vers phase suivante
5. Si rejete:
   - route vers meme noeud de phase (avec feedback)

## 5) Detail de chaque phase (etat actuel du code)

## 5.1 Phase 1 - Extraction (implementee)

Fichiers:

- `agents/pm/agents/extraction/agent.py`
- `agents/pm/agents/extraction/service.py`

Actions:

- Lit `project_documents.file_path` depuis DB via `document_id`.
- Charge le fichier en bytes.
- Verifie extension + taille (10 MB).
- Extrait texte PDF/DOCX/TXT.
- Met `cdc_text` dans le state.
- Passe a `node_validate`.

## 5.2 Phase 2 - Epics (implementee)

Fichiers:

- `agents/pm/agents/epics/agent.py`
- `agents/pm/agents/epics/service.py`
- `agents/pm/agents/epics/repository.py`

Actions:

- Appel LLM (`invoke_with_fallback`, modele `openai/gpt-oss-120b`).
- Parse/normalise JSON.
- Persist `pm.epics` (delete + insert) via `save_epics`.
- Passe a validation humaine.

## 5.3 Phase 3 - Stories (partiellement implementee)

Fichiers:

- `agents/pm/agents/stories/agent.py`
- `agents/pm/agents/stories/service.py`
- `agents/pm/agents/stories/repository.py`

Actions:

- Genere stories via LLM.
- Retourne stories dans le state.
- Appelle `save_stories(...)` mais le repository est STUB (`pass`).

Conclusion: stories existent dans l'etat et dans `pipeline_state.ai_output`, mais pas persistees dans table metier stories via ce repository.

## 5.4 Phases 4 a 11 (majoritairement STUB)

Fichiers:

- `agents/pm/agents/refinement/agent.py` (stub)
- `agents/pm/agents/dependencies/story_deps.py` (stub)
- `agents/pm/agents/prioritization/agent.py` (stub)
- `agents/pm/agents/tasks/agent.py` (stub)
- `agents/pm/agents/dependencies/task_deps.py` (stub)
- `agents/pm/agents/cpm/agent.py` (structure algo, sortie vide)
- `agents/pm/agents/sprints/agent.py` (stub)
- `agents/pm/agents/staffing/agent.py` (stub)

Toutes ces phases renvoient des structures vides (ou quasi vides), mais passent quand meme par la validation humaine.

## 5.5 Phase 12 - Monitoring

Fichier:

- `agents/pm/agents/monitoring/agent.py`

Comportement:

- Construit un plan vide par defaut.
- Persiste directement `VALIDATED` dans `pipeline_state`.
- Pas de validation humaine.
- Fin du graphe (`END`).

## 6) Validation humaine (coeur du human-in-the-loop)

Fichier: `agents/pm/graph/node_validate.py`

`node_validate`:

1. Lit `current_phase`.
2. Extrait `ai_output` depuis le state (`_get_phase_output`).
3. Upsert DB `PENDING_VALIDATION`.
4. `interrupt({...})` pour suspendre.
5. A la reprise:
   - `approved=true` -> `validation_status=validated`
   - sinon -> `validation_status=rejected` + `human_feedback`

Le resume est pilote exclusivement par `POST /pipeline/{project_id}/validate`.

## 7) Synchronisation Jira

Fichiers:

- `agents/pm/graph/node_jira_sync.py`
- `agents/pm/jira/actions.py`
- `agents/pm/jira/client.py`

Activation Jira:

- Active seulement si `JIRA_BASE_URL` et `JIRA_API_TOKEN` sont presents.
- `jira_project_key` pris depuis state (wizard) sinon fallback `.env`.

Par phase:

- `extract`: rien a creer
- `epics`: `create_epic`
- `stories`: `create_story` (lien epic)
- `tasks`: `create_task` (sub-task si parent)
- `sprints`: `create_sprint` + `add_issues_to_sprint`

Idempotence:

- `jira_synced_phases` evite de resynchroniser deux fois la meme phase.

Important:

- Les cles Jira sont stockees dans le state (`jira_epic_map`, etc.), mais le code actuel ne les ecrit pas explicitement dans les colonnes metier `jira_*_key` des tables PM.

## 8) Tables et enums importants

Fichiers:

- `app/database/models/pm/project_document.py`
- `app/database/models/pm/pipeline_state.py`
- `app/database/models/pm/enums.py`

Tables cles:

- `project_management.project_documents`
  - document source (path, hash, size, mime)
- `project_management.pipeline_state`
  - audit de chaque phase (status + ai_output + feedback)
- `project_management.epics`
  - effectivement alimentee en phase 2

Enums:

- `PipelinePhaseEnum` (12 phases)
- `PipelineStatusEnum` (`pending_ai`, `pending_validation`, `validated`, `rejected`)

## 9) Sequence complete (A -> Z)

1. PM upload CDC -> `POST /projects/{id}/document`.
2. API sauvegarde fichier + DB `project_documents`.
3. PM lance pipeline -> `POST /pipeline/{id}/start`.
4. Graph start -> `node_extraction` -> `node_validate` (interrupt).
5. PM valide/rejette -> `POST /pipeline/{id}/validate`.
6. Si valide -> `jira_sync` -> `node_epics`.
7. `node_epics` -> `node_validate` (interrupt).
8. PM valide/rejette phase epics.
9. Si valide -> `jira_sync` cree epics Jira -> `node_stories`.
10. `node_stories` -> `node_validate` (interrupt).
11. PM valide/rejette phase stories.
12. Si valide -> `jira_sync` cree stories Jira.
13. Puis phases 4->11 (majoritairement stubs) avec meme cycle validation.
14. Phase 12 monitoring auto-validee -> fin.

## 10) Incoherences et points de vigilance

1. Commentaire trompeur dans `graph.py`: il indique "extraction (pas de validation)", mais extraction passe bien par `node_validate`.
2. `stories/repository.py` est stub: pas de persistance metier stories.
3. Plusieurs phases sont stubs mais validables quand meme (risque de faux sentiment de completion).
4. `GET /pipeline/{project_id}` injecte artificiellement la phase 1 en `validated` si absente.
5. Les mappings Jira du state ne sont pas assures d'etre repercutes dans les champs `jira_*_key` des tables metier.

## 11) Fichiers a lire en priorite pour comprendre rapidement

1. `app/api/documents/documents.py`
2. `app/api/pipeline/pipeline.py`
3. `agents/pm/graph/graph.py`
4. `agents/pm/graph/node_validate.py`
5. `agents/pm/graph/node_jira_sync.py`
6. `agents/pm/agents/extraction/agent.py`
7. `agents/pm/agents/extraction/service.py`
8. `agents/pm/agents/epics/agent.py`
9. `agents/pm/agents/epics/service.py`
10. `agents/pm/agents/stories/agent.py`
11. `agents/pm/db/db.py`
12. `app/database/models/pm/pipeline_state.py`

## 12) Mini checklist de debug

Si le pipeline ne bouge pas:

1. Verifier `init_pm_graph()` au startup (`app/main.py`).
2. Verifier que `document_id` est du meme projet.
3. Verifier qu'il existe une ligne `PENDING_VALIDATION` avant `/validate`.
4. Verifier les variables Jira (`JIRA_BASE_URL`, `JIRA_API_TOKEN`, `JIRA_EMAIL`, `JIRA_PROJECT_KEY`).
5. Verifier que le checkpointer postgres est accessible (`DB_URI` dans `graph.py`).

---

Si vous voulez, je peux aussi vous preparer une version "pas a pas" avec des exemples de requetes JSON (`curl`/Postman) pour simuler un run complet extraction -> epics -> stories -> validation -> Jira.
