# Évaluation Agent RH avec LangSmith

## Données utilisées (RÉELLES de la base)

| Acteur | Nom | Email | Rôle |
|---|---|---|---|
| Consultant test | Eya ouni | eyaouniessect@gmail.com | consultant |
| RH | Ons RH | ons.rh.talan@gmail.com | rh |
| Équipe de test | Innovation Factory | — | — |
| Demandes PENDING d'Eya | leave_id=11 (18-20 mai), leave_id=12 (29 juin) | — | — |

---

## Étapes d'exécution

### 1. Démarrer l'agent RH (terminal 1)

```bash
cd backend
python -m agents.rh.server
```

L'agent écoute sur `http://localhost:8001`.

### 2. Créer le dataset dans LangSmith (terminal 2, une seule fois)

```bash
cd backend
python -m tests.evaluation.create_dataset
```

Cela crée le dataset `agent-rh-evaluation-v1` avec 12 exemples.

### 3. Configurer les evaluators dans l'UI LangSmith

Va sur https://smith.langchain.com → **Datasets** → `agent-rh-evaluation-v1` → **+ Add evaluator** → **Create from a template**, puis ajoute :

| Template | Catégorie | Objectif |
|---|---|---|
| **Tool Selection** | Trajectory | Bons tools choisis |
| **Trajectory Accuracy** | Trajectory | Chemin ReAct logique |
| **Hallucination** | Quality | Pas de données inventées |
| **PII Leakage** | Security | Pas de fuite données privées |
| **Language** | Conversation | Réponse en français |
| **Task Completion** | Conversation | Tâche complétée |

Les evaluators custom (`tool_calls_f1`, `rbac_respected`, `no_technical_error`) sont déjà inclus dans le code et tournent automatiquement.

### 4. Lancer l'évaluation

```bash
cd backend
python -m tests.evaluation.run_evaluation
```

### 5. Voir les résultats

→ https://smith.langchain.com → **Experiments** → expérience `rh-agent-XXXX`

---

## Architecture

```
backend/tests/evaluation/
├── create_dataset.py    ← Étape 1 : crée le dataset
├── rh_target.py         ← Étape 2 : appelle l'agent via HTTP A2A
├── rh_evaluators.py     ← Étape 3 : 3 evaluators custom
├── run_evaluation.py    ← Étape 4 : orchestre l'évaluation
└── README.md            ← Ce fichier
```

## Évaluateurs en place

| Métrique | Type | Source |
|---|---|---|
| `tool_calls_f1` | F1 score sur tools | Code custom |
| `rbac_respected` | 0/1 sécurité | Code custom |
| `no_technical_error` | 0/1 robustesse | Code custom |
| `tool_selection` | LLM judge | Template LangSmith UI |
| `trajectory_accuracy` | LLM judge | Template LangSmith UI |
| `hallucination` | LLM judge | Template LangSmith UI |
| `pii_leakage` | LLM judge | Template LangSmith UI |
| `language` | LLM judge | Template LangSmith UI |
| `task_completion` | LLM judge | Template LangSmith UI |
