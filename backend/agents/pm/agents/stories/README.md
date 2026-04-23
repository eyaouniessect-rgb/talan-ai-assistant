# Phase 3 — Génération des User Stories

## Vue d'ensemble

La Phase 3 transforme les **épics validés** (Phase 2) en **User Stories Agile** complètes, prêtes pour le backlog. Elle est déclenchée automatiquement après validation PM des épics et produit, pour chaque epic, un ensemble de stories avec story points et critères d'acceptation Gherkin.

---

## Architecture du module

```
stories/
├── agent.py          # Nœud LangGraph — point d'entrée de la phase
├── service.py        # Façade vers l'orchestrateur
├── react_agent.py    # Orchestrateur déterministe + gestion SSE
├── repository.py     # Persistance DB (user_stories)
├── prompt.py         # Prompts partagés (si applicable)
└── tools/
    ├── generate.py   # LLM : génération brute des stories
    ├── estimate.py   # LLM : estimation story points (Fibonacci)
    ├── criteria.py   # LLM : critères d'acceptation Gherkin
    └── review.py     # LLM : revue de couverture fonctionnelle
```

---

## Flux d'exécution

### Entrée
- Liste des épics validés (`state["epics"]`)
- Feedback PM optionnel (`state["human_feedback"]`)
- Détails d'architecture optionnels (`state["architecture_details"]`)

### Séquence par epic (ordre strict 0 → N-1)

```
Pour chaque epic[i] :
    ┌─────────────────────────────┐
    │  1. Génération des stories  │  → run_generate_for_epic()
    └────────────┬────────────────┘
                 │
    ┌────────────▼────────────────┐
    │  2. Estimation story points │  → run_estimate_story_points()
    │     Fibonacci : 1,2,3,5,8  │     (13 interdit → remplace par 8)
    └────────────┬────────────────┘
                 │
    ┌────────────▼────────────────┐
    │  3. Critères d'acceptation  │  → run_generate_acceptance_criteria()
    │     Format Gherkin          │     max 3 par story, ≥1 cas négatif
    │     (batch de 15 stories)   │
    └────────────┬────────────────┘
                 │
    ┌────────────▼────────────────┐
    │  4. Revue de couverture     │  → run_review_coverage()
    │     Complétude + INVEST     │
    └────────────┬────────────────┘
                 │
         coverage_ok ?
        /              \
      Non               Oui
       │                 │
    ┌──▼──────────┐   ┌──▼──────┐
    │  Retry ×1   │   │  Done   │
    │  (gaps only)│   │  → i+1  │
    └──┬──────────┘   └─────────┘
       │ generate(missing_features)
       │ estimate
       │ criteria
       └─→ epic suivant (pas de 2ème review)
```

### Sortie
- Liste de dicts `UserStory` avec : `epic_id`, `title`, `description`, `story_points`, `acceptance_criteria`, `splitting_strategy`, `_review`
- Persistée en DB via `save_stories()` (supprime + réinsère à chaque génération)
- `ai_output` de la phase : `{ "stories": [...], "epics": [...] }`

---

## Détail des 4 appels LLM

### 1. `generate.py` — Génération des stories
- **Modèle** : `openai/gpt-oss-120b`, `max_tokens=2048`, `temperature=0`
- **Entrée** : epic (titre, description, stratégie de découpage) + architecture + feedback PM
- **Sortie** : 2 à 8 stories au format *"En tant que [rôle], je veux [action] afin de [bénéfice]"*
- **Stratégies** : `by_feature` (défaut), `by_user_role`, `by_workflow`, etc.
- **Fail-safe** : si JSON invalide → 1 story placeholder retournée (ne bloque pas la chaîne)

### 2. `estimate.py` — Story Points
- **Modèle** : `openai/gpt-oss-120b`, `max_tokens=600`, `temperature=0`
- **Entrée** : liste de stories (titre + description courte)
- **Sortie** : Fibonacci **1, 2, 3, 5, 8** uniquement (13 interdit — si complexe → 8)
- **Fail-safe** : si erreur LLM → SP=3 par défaut pour toutes les stories du batch
- **Extension prévue** : ajout d'un paramètre `historical_data` pour calibrer sur les projets récents en DB (signature rétrocompatible : `historical_data=None`)

### 3. `criteria.py` — Critères d'acceptation Gherkin
- **Modèle** : `openai/gpt-oss-120b`, `max_tokens=4096`, `temperature=0`
- **Entrée** : batch de 15 stories maximum (1 appel LLM pour la plupart des épics)
- **Format** : `"Étant donné [contexte], quand [action], alors [résultat mesurable]"`
- **Règles** : maximum 3 critères par story, au moins 1 cas négatif obligatoire
- **Fail-safe** : si erreur → `["À définir"]`

### 4. `review.py` — Revue de couverture
- **Modèle** : `openai/gpt-oss-120b`, `max_tokens=768`, `temperature=0`
- **Vérifie** :
  - **Complétude** : les stories couvrent-elles les fonctionnalités majeures de l'epic ?
  - **Scope creep** : aucune story ne déborde sur un autre epic
  - **Qualité INVEST** : Indépendante, Négociable, Valeur, Estimable, Small, Testable
- **Sortie** : `{ coverage_ok, gaps, scope_creep_issues, quality_issues, suggestions }`
- **Fail-safe** : si erreur LLM → `coverage_ok=True` (ne bloque pas la progression)

---

## Garanties de robustesse

| Scénario | Comportement |
|---|---|
| LLM retourne JSON invalide (generate) | Story placeholder créée, epic continue |
| LLM échoue sur estimate | SP=3 appliqué par défaut |
| LLM échoue sur criteria | AC=`["À définir"]` appliqué |
| LLM échoue sur review | `coverage_ok=True` (fail-safe, pas de retry) |
| Un epic crashe complètement | Les autres epics continuent (isolation par epic) |
| Génération interrompue (partielle) | Endpoint `POST /pipeline/{id}/stories/restart` relance uniquement les epics manquants |

---

## Streaming SSE (temps réel)

Les événements suivants sont émis vers `GET /pipeline/{id}/stories/stream` pendant la génération :

| Événement | Déclenché quand |
|---|---|
| `epic_start` | Début de traitement d'un epic |
| `tool_start` | Début d'un des 3 tools (estimate, criteria, review) |
| `gap_detected` | Review détecte des fonctionnalités manquantes |
| `retry_start` | Régénération ciblée sur les gaps |
| `coverage_ok` | Review valide la couverture |
| `epic_done` | Epic terminé (N stories produites) |
| `done` | Toute la génération terminée |
| `error` | Erreur sur un epic spécifique (non bloquant) |

---

## Persistance DB

```
project_management.user_stories
├── id                  PK
├── epic_id             FK → epics.id (mapped depuis epic_idx LLM → id DB)
├── title               "En tant que…"
├── description         Contexte fonctionnel
├── story_points        Fibonacci 1-8
├── acceptance_criteria JSON text (liste de strings Gherkin)
├── splitting_strategy  by_feature | by_user_role | …
├── status              draft → refined → validated | rejected
└── ai_metadata         { source, llm_epic_idx }
```

**Comportement idempotent** : `save_stories()` supprime toutes les stories existantes du projet avant de réinsérer. Cela garantit la cohérence en cas de re-génération ou de rejet PM.

---

## Déclenchement

```
POST /pipeline/{project_id}/validate   # PM approuve les épics → déclenche la Phase 3
POST /pipeline/{project_id}/stories/restart  # Relance uniquement les epics sans stories
```

La phase passe par les statuts :
- `pending_ai` → génération en cours (SSE actif)
- `pending_validation` → génération terminée, en attente du PM
- `validated` → PM a approuvé → Phase 4 (Refinement) débloquée
- `rejected` → PM a rejeté avec feedback → re-génération avec `human_feedback`
