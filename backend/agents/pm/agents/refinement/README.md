# Pipeline PM — Phases 2, 3 et 4

---

## Phase 2 — Génération des Epics

### Vue d'ensemble

La Phase 2 transforme le **texte brut du CDC** (cahier des charges) en une liste d'**Epics** —
les grandes fonctionnalités du projet.

```
[Phase 1 — Extraction CDC terminée]
        │
        ▼
node_epics (agent.py)
        │  lit cdc_text + human_feedback depuis le state
        ▼
generate_epics (service.py)
        │  appel LLM → JSON d'epics
        ▼
save_epics (repository.py)
        │  DELETE existing + INSERT
        │  PostgreSQL affecte epic.id
        │  ⚠ db_id NON écrit dans les dicts
        ▼
state["epics"] = [ { "title": "...", "splitting_strategy": "..." }, ... ]
        │
        ▼
node_validate → interrupt() → attente PM
```

### Structure des fichiers

```
agents/pm/agents/epics/
│
├── agent.py       ← Nœud LangGraph — point d'entrée
├── service.py     ← Appel LLM + parsing JSON
├── prompt.py      ← Prompt système du LLM
└── repository.py  ← INSERT epics en DB
```

### Fichier par fichier

#### `agent.py` — Nœud LangGraph

**Input (lu depuis le state)** :

| Champ | Type | Description |
|---|---|---|
| `cdc_text` | `str` | Texte brut extrait du CDC (Phase 1) |
| `human_feedback` | `str \| None` | Feedback PM si la phase a été rejetée |

**Output (retourné dans le state)** :

| Champ | Type | Description |
|---|---|---|
| `epics` | `list[dict]` | Epics générés par le LLM |
| `current_phase` | `str` | `"epics"` |
| `validation_status` | `str` | `"pending_human"` |
| `human_feedback` | `None` | Réinitialisé après traitement |

#### `repository.py` — `save_epics()`

Supprime les epics existants du projet, insère les nouveaux.

```python
session.add_all(orm_epics)
await session.commit()
for e in orm_epics:
    await session.refresh(e)   # orm_epics[0].id = 42 ← assigné par PostgreSQL
# ⚠ db_id NON réécrit dans les dicts epics (contrairement aux stories)
```

**Important** : les epics dans le state n'ont **pas** de champ `db_id`.
Ils sont identifiés par leur **position dans la liste** (index 0, 1, 2…).
`save_stories()` (Phase 3) fait le pont : `SELECT epics ORDER BY id` → `db_epics[0].id = 42` correspond à `state["epics"][0]`.

### Structure d'un epic en mémoire (state LangGraph)

```python
{
    "title":              "Gestion des utilisateurs",
    "description":        "Fonctionnalités de création, modification et suppression des comptes.",
    "splitting_strategy": "by_user_role"   # "by_feature" | "by_user_role" | "by_workflow_step" | "by_component"
}
```

**Pas de `db_id`** — l'index dans la liste suffit pour Phase 3 et Phase 4.

### Ce qui est sauvegardé en base (Phase 2)

**Table** `project_management.epics` :

```
┌──────────────────────┬──────────────────────────────────────────────┐
│ Colonne              │ Valeur                                       │
├──────────────────────┼──────────────────────────────────────────────┤
│ id                   │ auto-incrémenté par PostgreSQL               │
│ project_id           │ identifiant du projet                        │
│ title                │ titre de l'epic                              │
│ description          │ description                                  │
│ splitting_strategy   │ stratégie de découpage                       │
│ status               │ "draft"                                      │
│ jira_epic_key        │ NULL (rempli après validation PM → Jira sync)│
└──────────────────────┴──────────────────────────────────────────────┘
```

---

## Phase 3 — Génération des User Stories

### Vue d'ensemble

La Phase 3 génère les **User Stories** pour chaque epic.
Le LLM utilise `epic_id` comme un **index local** (0, 1, 2…) — pas un ID PostgreSQL.
C'est `save_stories()` qui mappe cet index vers le vrai ID DB de l'epic.

```
[Phase 2 validée par le PM]
        │
        ▼
node_stories (agent.py)
        │  lit epics + cdc_text depuis le state
        ▼
generate_stories (react_agent.py)
        │  appel LLM → JSON de stories (epic_id = index local)
        ▼
save_stories (repository.py)
        │  SELECT epics ORDER BY id → index_to_db_id = {0: 42, 1: 43}
        │  DELETE existing stories
        │  INSERT UserStory(epic_id=42, ...)
        │  COMMIT → REFRESH → orm_s.id = 101
        │  story_dict["db_id"] = 101  ← écrit dans le dict ✓
        ▼
state["stories"] = [ { "db_id": 101, "epic_id": 0, ... }, ... ]
        │
        ▼
node_validate → interrupt() → attente PM
```

### Structure des fichiers

```
agents/pm/agents/stories/
│
├── agent.py         ← Nœud LangGraph — point d'entrée
├── react_agent.py   ← Appel LLM (ReAct pattern)
├── tools/           ← Outils disponibles pour l'agent
│   ├── generate.py  ← Génération des stories par epic
│   └── criteria.py  ← Génération des critères d'acceptation
└── repository.py    ← INSERT + mapping epic_id → db_id
```

### `repository.py` — `save_stories()`

C'est ici que les `db_id` sont créés et écrits dans les dicts :

```python
# 1. Mapping index LLM → vrai ID DB de l'epic
index_to_db_id = {i: e.id for i, e in enumerate(db_epics)}
# ex: {0: 42, 1: 43}

# 2. INSERT avec le vrai epic_id DB
orm_s = UserStory(epic_id=index_to_db_id[s["epic_id"]], ...)

# 3. Après commit + refresh
story_dict["db_id"] = orm_s.id   # ex: 101 ← écrit dans le dict Python
```

### Structure d'une story en mémoire (state LangGraph)

```python
{
    "epic_id":             0,          # index local LLM (PAS l'ID DB de l'epic)
    "db_id":               101,        # ID PostgreSQL de la ligne user_story ✓
    "title":               "En tant que recruteur, je veux...",
    "description":         "Cette story permet de...",
    "story_points":        3,          # Fibonacci : 1, 2, 3, 5, 8
    "acceptance_criteria": ["...", "..."],
    "splitting_strategy":  "by_feature"
}
```

### Ce qui est sauvegardé en base (Phase 3)

**Table** `project_management.user_stories` :

```
┌──────────────────────┬──────────────────────────────────────────────┐
│ Colonne              │ Valeur                                       │
├──────────────────────┼──────────────────────────────────────────────┤
│ id                   │ auto-incrémenté par PostgreSQL (= db_id)     │
│ epic_id              │ ID DB réel de l'epic (ex: 42)                │
│ title                │ titre généré par le LLM                      │
│ description          │ description                                  │
│ story_points         │ estimation Fibonacci                         │
│ acceptance_criteria  │ JSON texte                                   │
│ status               │ "draft"                                      │
│ jira_issue_key       │ NULL (rempli après validation PM → Jira sync)│
└──────────────────────┴──────────────────────────────────────────────┘
```

---

## Phase 4 — Raffinement PO ↔ Tech Lead

### Vue d'ensemble

La Phase 4 est le **mécanisme de contrôle qualité automatique** des User Stories générées en Phase 3.
Deux agents IA jouent des rôles opposés et complémentaires :

- Le **Product Owner (PO)** vérifie la qualité métier (format, valeur, critères d'acceptation)
- Le **Tech Lead (TL)** vérifie la faisabilité technique (story points, clarté, réalisme)

Ils débattent en **3 rounds maximum**. À chaque round, ils proposent des corrections précises
appelées **patches**. Un algorithme Python pur applique ces patches de façon déterministe.
Si le nombre de corrections nécessaires tombe en dessous d'un seuil, on considère que le
**consensus est atteint** et le raffinement s'arrête.

---

## Schéma général du flux

```
[Phase 3 termine]
      │
      ▼
node_refinement (agent.py)
      │  lit les stories + epics depuis le state LangGraph
      │
      ▼
run_refinement (service.py)  ←── boucle max 3 rounds
      │
      ├── Pour chaque epic :
      │       ├── [batch si > 6 stories]
      │       ├── run_po_review()   ──► patches PO
      │       ├── run_tech_review() ──► patches TL  (parallèle via asyncio.gather)
      │       ├── merge_patches()   ──► fusion Python
      │       └── apply_patches()   ──► stories mises à jour
      │
      ├── check_consensus()  → continuer ou arrêter
      │
      └── [si consensus ou 3 rounds atteints]
              │
              ▼
        save_refined_stories (repository.py)
              │  UPDATE user_stories SET status='refined', ...
              │
              ▼
        node_validate (graph/node_validate.py)
              │  persist en DB (status=PENDING_VALIDATION)
              │  suspend via interrupt() → attente PM
              │
              ▼
        [PM valide ou rejette dans le frontend]
              │
              ▼
        [Phase 5 : dépendances entre stories]
```

---

## Structure des fichiers

```
agents/pm/agents/refinement/
│
├── agent.py          ← Nœud LangGraph (point d'entrée depuis le graph)
├── service.py        ← Orchestrateur : boucle des rounds, logique de consensus
├── repository.py     ← Persistance en base de données (PostgreSQL)
│
└── tools/
    ├── po_review.py  ← Agent PO : appel LLM, génère des patches métier
    ├── tech_review.py← Agent TL : appel LLM, génère des patches techniques
    └── patch.py      ← Python pur : merge, apply, consensus (AUCUN LLM)
```

---

## Fichier par fichier

### `agent.py` — Nœud LangGraph

**Rôle** : point d'entrée appelé par le graph LangGraph. Fait le lien entre le state du
pipeline et la logique métier.

**Appelé par** : `agents/pm/graph/graph.py` (le graph PM principal)

**Appelle** : `service.run_refinement()` et `repository.save_refined_stories()`

**Input (lu depuis le state LangGraph)** :

| Champ | Type | Description |
|---|---|---|
| `project_id` | `int` | Identifiant du projet |
| `stories` | `list[dict]` | Stories brutes générées en Phase 3 |
| `epics` | `list[dict]` | Epics générés en Phase 2 (titres + descriptions) |
| `human_feedback` | `str \| None` | Feedback du PM si la phase a été rejetée et relancée |
| `architecture_detected` | `bool` | Le CDC contient-il une architecture détectée ? |
| `architecture_details` | `dict \| None` | Détails de l'archi (layers, APIs…) si détectée |

**Output (retourné dans le state LangGraph)** :

| Champ | Type | Description |
|---|---|---|
| `refined_stories` | `list[dict]` | Stories après raffinement |
| `refinement_rounds` | `list[dict]` | Historique de chaque round (patches, résumés) |
| `current_phase` | `str` | `"refinement"` |
| `validation_status` | `str` | `"pending_human"` |
| `human_feedback` | `None` | Réinitialisé après traitement |
| `error` | `str \| None` | Message d'erreur si exception |

**Fail-safe** : si `run_refinement()` lève une exception, les stories originales (Phase 3)
sont retournées sans modification. Le pipeline ne s'arrête pas.

---

### `service.py` — Orchestrateur déterministe

**Rôle** : boucle principale des rounds. Appelle PO et TL, applique les patches, décide
si le consensus est atteint.

**Appelé par** : `agent.py` et `app/api/pipeline/pipeline.py` (endpoint restart)

**Appelle** : `po_review.run_po_review()`, `tech_review.run_tech_review()`,
`patch.merge_patches()`, `patch.apply_patches()`, `patch.check_consensus()`

**Constantes** :

| Constante | Valeur | Signification |
|---|---|---|
| `MAX_ROUNDS` | `3` | Nombre maximum de rounds |
| `BATCH_SIZE` | `6` | Max stories par appel LLM (évite les JSONDecodeError sur grands epics) |

**Algorithme détaillé** :

```
Pour round de 1 à MAX_ROUNDS :

    Pour chaque epic (0, 1, 2, ...) :

        Récupérer les stories de cet epic
        Si epic a plus de BATCH_SIZE stories → découper en batches

        Pour chaque batch :
            Appeler PO et TL EN PARALLÈLE (asyncio.gather)
            → PO retourne (patches_po, résumé_po)
            → TL retourne (patches_tl, résumé_tl)

            Décaler les local_idx si batch > 0
            (batch 2 commence à local_idx 6, etc.)

            Fusionner patches PO + TL → liste unifiée

        Appliquer tous les patches de l'epic sur les stories

    Vérifier consensus :
        Si patches_majeurs < 3 ET patches_totaux < 10 → CONSENSUS → arrêt
        Sinon → round suivant

Retourner (stories_raffinées, historique_rounds)
```

---

### Ce que retourne concrètement `run_refinement()`

`run_refinement()` retourne un tuple Python de deux éléments :

```python
refined_stories, refinement_rounds = await run_refinement(...)
```

---

#### 1. `refined_stories` — liste des stories après tous les rounds

C'est la **même structure qu'en Phase 3**, mais avec les champs corrigés par les patches.
Chaque story est un dictionnaire :

```python
# Exemple : story avant raffinement (Phase 3)
{
    "epic_id":             0,
    "title":               "En tant que recruteur je veux voir les candidats",   # format incomplet
    "description":         "Affiche une liste de candidats.",                    # trop vague
    "story_points":        2,                                                    # sous-estimé
    "acceptance_criteria": ["La liste s'affiche."],                              # pas de cas négatif
    "splitting_strategy":  "by_feature",
    "db_id":               42
}

# La même story après raffinement (Phase 4)
{
    "epic_id":             0,
    "title":               "En tant que recruteur, je veux voir la liste des candidats afin de sélectionner les profils à contacter",  # corrigé PO
    "description":         "L'interface affiche la liste paginée des candidats avec leur score de matching. Chaque ligne montre le nom, le poste et le score.",  # corrigé TL
    "story_points":        3,                                                    # corrigé TL (Fibonacci le plus proche)
    "acceptance_criteria": [
        "La liste s'affiche.",
        "Un message s'affiche si aucun candidat ne correspond aux critères."     # ajouté PO (cas négatif)
    ],
    "splitting_strategy":  "by_feature",
    "db_id":               42    # même db_id → UPDATE en base, pas d'INSERT
}
```

La liste complète contient **toutes les stories de tous les epics**, dans le même ordre
qu'en Phase 3. L'`epic_id` permet de retrouver à quel epic chaque story appartient.

---

#### 2. `refinement_rounds` — historique complet de chaque round

C'est une **liste de dicts**, un dict par round exécuté (entre 1 et 3).

```python
refinement_rounds = [
    {   # ── Round 1 ──────────────────────────────────────────────
        "round":         1,       # numéro du round (commence à 1)
        "patches_count": 24,      # nombre total de patches appliqués ce round
        "consensus":     False,   # False = pas assez bon, on continue

        # Résumé PO : une phrase par epic, séparées par " | "
        "po_comment": (
            "Epic 0: Des stories manquent de bénéfice métier clair. | "
            "Epic 1: Aucun problème détecté. | "
            "Epic 2: Aucun problème détecté."
        ),

        # Résumé TL : une phrase par epic, séparées par " | "
        "tech_comment": (
            "Epic 0: Descriptions incomplètes pour les stories 0 à 3. | "
            "Epic 1: Story points sous-estimés sur 2 stories. | "
            "Epic 2: Story 5 trop grande pour un seul sprint."
        ),

        # Détail de chaque patch appliqué ce round
        "stories_patch": [
            {
                "story_local_idx": 0,         # index dans l'epic (0-based)
                "field":           "title",
                "new_value":       "En tant que recruteur, je veux...",
                "reason":          "Format 'En tant que' manquant."
            },
            {
                "story_local_idx": 0,
                "field":           "acceptance_criteria",
                "action":          "add",
                "value":           "Un message d'erreur s'affiche si le token est expiré.",
                "reason":          "Aucun cas négatif présent."
            },
            {
                "story_local_idx": 2,
                "field":           "story_points",
                "new_value":       5,          # était 2, corrigé à 5
                "reason":          "Intègre 3 composants et une API externe."
            },
            # ... autres patches du round
        ]
    },

    {   # ── Round 2 ──────────────────────────────────────────────
        "round":         2,
        "patches_count": 6,
        "consensus":     True,    # True = qualité suffisante, on s'arrête ici

        "po_comment":   "Epic 0: Aucun problème détecté. | Epic 1: Aucun problème détecté. | Epic 2: Aucun problème détecté.",
        "tech_comment":  "Epic 0: Aucun problème technique détecté. | Epic 1: Aucun problème technique détecté. | Epic 2: SP ajusté sur story 3.",

        "stories_patch": [
            {
                "story_local_idx": 3,
                "field":           "story_points",
                "new_value":       3,
                "reason":          "Réévaluation après clarification de la description."
            },
            # ... 5 autres patches mineurs
        ]
    }
    # Round 3 n'existe pas car consensus atteint au Round 2
]
```

---

**Relation entre les deux** :

```
refinement_rounds[0]["stories_patch"]  →  décrit les corrections du Round 1
refinement_rounds[1]["stories_patch"]  →  décrit les corrections du Round 2

refined_stories  →  état FINAL des stories après TOUS les rounds
                    (Round 1 appliqué, PUIS Round 2 appliqué par-dessus)
```

Autrement dit : `refined_stories` n'est pas le résultat d'un seul round, c'est
l'**accumulation** de tous les patches de tous les rounds dans l'ordre.

---

**Ce qui est stocké en base vs en mémoire** :

```
En mémoire LangGraph (state) :
  refined_stories    → liste complète en RAM
  refinement_rounds  → historique complet en RAM

Persisté dans pipeline_state.ai_output (JSONB) :
  { "refined_stories": [...], "refinement_rounds": [...], "epics": [...] }
  → visible par le frontend via GET /pipeline/{id}

Persisté dans user_stories (UPDATE) :
  → seulement les champs modifiés : title, description, story_points, acceptance_criteria
  → status passe à "refined"
  → les autres colonnes (epic_id, splitting_strategy, jira_issue_key...) sont inchangées
```

---

### `tools/po_review.py` — Agent Product Owner

**Rôle** : auditer les stories d'un epic du point de vue **métier**.

**Appelé par** : `service.py`

**Appelle** : `app/core/groq_client.invoke_with_fallback()` (LLM NVIDIA → Groq fallback)

**Modèle LLM** : `openai/gpt-oss-120b` (NVIDIA NIM, 128k context)

**max_tokens** : `4096`

**Input** :

| Paramètre | Type | Description |
|---|---|---|
| `epic` | `dict` | L'epic parent (`title`, `description`) |
| `epic_idx` | `int` | Index de l'epic dans la liste globale |
| `stories` | `list[dict]` | Stories de cet epic (batch de max 6) |

**Ce que le PO vérifie** :

1. **Format** : "En tant que [rôle précis], je veux [action concrète] afin de [bénéfice métier]"
2. **Valeur métier** : le bénéfice est-il clair et mesurable ?
3. **Critères d'acceptation** : testables, avec au moins un cas négatif (erreur réseau, token expiré…)
4. **Scope** : la story reste-t-elle dans le périmètre de l'epic ?
5. **Granularité** : une story > 8 pts doit être découpée

**Output** :

```python
(
    patches: list[dict],   # corrections proposées (max 2 par story)
    summary: str           # une phrase résumant les problèmes détectés
)
```

**Structure d'un patch PO** :

```python
{
    "story_local_idx": 2,               # index de la story dans le batch (0-based)
    "field":           "acceptance_criteria",
    "action":          "add",           # "add" | "remove" | "replace"
    "value":           "L'accès est refusé si le token est expiré.",
    "reason":          "Manque de cas négatif pour l'authentification."
}
```

**Champs que le PO peut modifier** : `title`, `description`, `acceptance_criteria`, `flag`
(le PO ne modifie JAMAIS les story points)

**Fail-safe** : si le LLM échoue ou retourne du JSON invalide → `([], "Revue PO indisponible (TypeError).")`

---

### `tools/tech_review.py` — Agent Tech Lead

**Rôle** : auditer les stories d'un epic du point de vue **technique**.

**Appelé par** : `service.py`

**Appelle** : `app/core/groq_client.invoke_with_fallback()`

**Modèle LLM** : `openai/gpt-oss-120b`

**max_tokens** : `4096`

**Input** :

| Paramètre | Type | Description |
|---|---|---|
| `epic` | `dict` | L'epic parent |
| `epic_idx` | `int` | Index de l'epic |
| `stories` | `list[dict]` | Stories du batch |
| `architecture_details` | `dict \| None` | Architecture détectée dans le CDC |

**Ce que le TL vérifie** :

1. **Story Points** : réalisme (suite Fibonacci 1,2,3,5,8 — 13 interdit dans ce contexte)
2. **Faisabilité sprint** : une story doit tenir en 1 sprint (2 semaines, 1 développeur)
3. **Clarté de description** : suffisamment précise pour implémenter sans ambiguïté
4. **INVEST** : Indépendante, Estimable, Small, Testable

**Champs que le TL peut modifier** : `story_points`, `description`, `flag`
(le TL ne modifie JAMAIS le titre — c'est la responsabilité du PO)

**Structure d'un patch TL** :

```python
{
    "story_local_idx": 0,
    "field":           "story_points",
    "new_value":       5,             # doit être dans {1, 2, 3, 5, 8}
    "reason":          "La story implique 3 composants et une intégration API."
}
```

**Fail-safe** : même comportement que le PO.

---

### `tools/patch.py` — Logique Python pure (aucun LLM)

**Rôle** : fusionner les patches PO+TL, les appliquer sur les stories, décider du consensus.

**Appelé par** : `service.py`

**Aucun appel LLM — 100% déterministe.**

#### `merge_patches(po_patches, tech_patches) → list[dict]`

Fusionne les deux listes de patches en évitant les doublons.

Règles de fusion :

| Cas | Comportement |
|---|---|
| Même story, même champ, valeur différente | Premier patch gagne (PO prioritaire) |
| Conflit sur `story_points` | On prend la valeur **la plus haute** (prudence technique) |
| `acceptance_criteria` action=`add` | On cumule (pas de conflit) |

#### `apply_patches(stories, epic_id, patches) → list[dict]`

Applique les patches sur la liste globale de stories.

**Résolution des indices** :
- Les patches contiennent des `story_local_idx` (0, 1, 2… relatifs à l'epic)
- La fonction calcule les indices globaux via `epic_indices = [i for i, s in enumerate(stories) if s.get("epic_id") == epic_id]`
- `global_idx = epic_indices[local_idx]`

**Règles d'application par champ** :

| Champ | Comportement |
|---|---|
| `title` | Remplace si nouvelle valeur non vide |
| `description` | Remplace si nouvelle valeur non vide |
| `story_points` | Arrondi sur Fibonacci le plus proche (`min({1,2,3,5,8}, key=lambda x: abs(x-sp))`) |
| `acceptance_criteria` action=`add` | Ajoute le critère s'il n'existe pas déjà |
| `acceptance_criteria` action=`remove` | Supprime par index |
| `acceptance_criteria` action=`replace` | Remplace toute la liste |
| `flag` | Ignoré (informatif, pas de modification de données) |

#### `check_consensus(round_patches) → bool`

Retourne `True` si le consensus est atteint, c'est-à-dire :
- Moins de **3 patches majeurs** (`title` ou `story_points`) ET
- Moins de **10 patches totaux** (hors `flag`)

Le double critère évite un faux consensus quand le TL échoue (0 patches TL → compteur bas
mais les problèmes persistent).

---

### `repository.py` — Persistance en base de données

**Rôle** : mettre à jour les `user_stories` en PostgreSQL après le raffinement.

**Appelé par** : `agent.py`

**Table modifiée** : `project_management.user_stories`

**Opération** : `UPDATE` (jamais d'INSERT — les lignes ont été créées en Phase 3)

**Champs mis à jour** :

| Champ DB | Condition |
|---|---|
| `status` | Toujours mis à `"refined"` |
| `title` | Si la story raffinée a un titre non vide |
| `description` | Si la story raffinée a une description |
| `story_points` | Si la valeur est non nulle |
| `acceptance_criteria` | Si la liste est non vide (stockée en JSON texte) |

**Identification des lignes** : via `db_id` (présent dans chaque story depuis la Phase 3).
Les stories sans `db_id` sont ignorées (cas rare).

---

## Ce qui est sauvegardé en base

### Table `project_management.user_stories`

Mise à jour par `repository.py` après chaque raffinement.

```
┌─────────────────────┬──────────────────────────────────────────────┐
│ Colonne             │ Valeur après Phase 4                         │
├─────────────────────┼──────────────────────────────────────────────┤
│ id                  │ inchangé (clé primaire)                      │
│ status              │ "refined"                                    │
│ title               │ mis à jour si patch PO                       │
│ description         │ mis à jour si patch TL                       │
│ story_points        │ mis à jour si patch TL (Fibonacci)           │
│ acceptance_criteria │ mis à jour si patch PO (JSON texte)          │
└─────────────────────┴──────────────────────────────────────────────┘
```

### Table `project_management.pipeline_state`

Mise à jour par `node_validate.py` (commun à toutes les phases).

```
┌─────────────────────┬──────────────────────────────────────────────┐
│ Colonne             │ Valeur                                       │
├─────────────────────┼──────────────────────────────────────────────┤
│ phase               │ "phase_4_refinement"                         │
│ status              │ "pending_validation" (en attente du PM)      │
│ ai_output           │ JSON complet (refined_stories, rounds, epics)│
└─────────────────────┴──────────────────────────────────────────────┘
```

Le champ `ai_output` contient :

```json
{
  "refined_stories":   [ ... ],
  "refinement_rounds": [
    {
      "round": 1,
      "patches_count": 12,
      "consensus": false,
      "po_comment": "Epic 0: ... | Epic 1: ...",
      "tech_comment": "Epic 0: ... | Epic 1: ...",
      "stories_patch": [ ... ]
    }
  ],
  "epics": [ ... ]
}
```

---

## Endpoint de relance (restart)

Si le PM veut relancer le raffinement après validation sans repasser par tout le pipeline :

```
POST /pipeline/{project_id}/refinement/restart
```

**Fichier** : `app/api/pipeline/pipeline.py` → `restart_refinement()`

**Ce qu'il fait** :
1. Lit le checkpoint LangGraph pour récupérer `stories`, `epics`, `human_feedback`, `architecture_details`
2. Passe le statut à `PENDING_AI` en base
3. Lance `_background_run_refinement()` en arrière-plan (FastAPI BackgroundTasks)
4. La tâche de fond appelle `run_refinement()`, `save_refined_stories()`, puis repasse à `PENDING_VALIDATION`

---

## Structure d'une story en mémoire (LangGraph state)

```python
{
    "epic_id":             2,          # index de l'epic parent (0-based)
    "title":               "En tant que recruteur, je veux...",
    "description":         "Cette story permet de...",
    "story_points":        3,          # Fibonacci : 1, 2, 3, 5, 8
    "acceptance_criteria": [           # liste de strings
        "Le score s'affiche en moins de 2 secondes.",
        "Un message d'erreur s'affiche si le matching échoue."
    ],
    "splitting_strategy":  "by_feature",
    "db_id":               42          # ID PostgreSQL (user_stories.id)
}
```

---

## Comprendre les logs backend

```
[refinement] ▶ 32 stories | 5 epics | project_id=18
[refinement]   Round 1 | Epic 0 (8 stories)
[po_review]   Epic 0 → 4 patch(es) PO
[tech_review]  Epic 0 → 3 patch(es) TL
[refinement]   Round 1 | Epic 1 (6 stories)
...
[refinement]   Round 1 terminé — 24 patch(es) | consensus=non
[refinement]   Round 2 terminé — 8 patch(es) | consensus=oui
[refinement] ✓ Consensus atteint au round 2
[refinement/repo] ✓ 32/32 stories mises à jour (projet 18)
```

Si un reviewer échoue :
```
[po_review] ⚠ Epic 1 erreur (JSONDecodeError): ... → fail-safe (0 patches)
```
→ Le round continue avec 0 patches pour cet epic. Les autres epics ne sont pas affectés.

---

## FAQ débutant

**Q : Pourquoi utiliser des "patches" plutôt que régénérer toutes les stories ?**
Les patches permettent de conserver les corrections déjà appliquées dans les rounds précédents
et d'avoir une traçabilité précise de chaque modification. Régénérer efface tout le travail
des rounds précédents.

**Q : Pourquoi max 3 rounds ?**
C'est un compromis coût/qualité. En pratique, 2 rounds suffisent dans 80% des cas.
Le 3e round est un filet de sécurité. Plus de 3 rounds coûterait cher en tokens LLM
et risquerait de tourner en rond.

**Q : Pourquoi le consensus peut être atteint avec encore des patches ?**
Le consensus ne signifie pas "zéro défaut" mais "suffisamment peu de corrections majeures
pour considérer que la qualité est acceptable". Le seuil est < 3 patches majeurs
(title/story_points) ET < 10 patches au total.

**Q : Que se passe-t-il si le LLM retourne du JSON invalide ?**
Le fail-safe retourne `([], "Revue indisponible")`. L'epic continue avec 0 patches.
Le round suivant retentera de reviewer les mêmes stories.

**Q : La story en base est-elle modifiée pendant le raffinement ou après ?**
Après. `repository.py` n'est appelé qu'une seule fois, à la fin de tous les rounds,
avec les stories dans leur état final. Pendant les rounds, tout est en mémoire (state LangGraph).
