# agents/pm/agents/epics/ — Documentation Technique

> Dossier responsable de la **Phase 2** du pipeline PM : génération, modification et suppression des Epics.

---

## Sommaire

1. [Structure du dossier](#1-structure-du-dossier)
2. [Rôle dans le pipeline LangGraph](#2-rôle-dans-le-pipeline-langgraph)
3. [State reçu — ce que node_epics lit](#3-state-reçu--ce-que-node_epics-lit)
4. [State retourné — ce que node_epics écrit](#4-state-retourné--ce-que-node_epics-écrit)
5. [Les 3 cas de traitement](#5-les-3-cas-de-traitement)
6. [agent.py — Orchestrateur](#6-agentpy--orchestrateur)
7. [service.py — Logique LLM](#7-servicepy--logique-llm)
8. [repository.py — Persistance DB](#8-repositorypy--persistance-db)
9. [prompt.py — Prompts LLM](#9-promptpy--prompts-llm)
10. [Gestion des IDs (db_id)](#10-gestion-des-ids-db_id)
11. [Chaîne d'appels complète](#11-chaîne-dappels-complète)
12. [Questions fréquentes](#12-questions-fréquentes)

---

## 1. Structure du dossier

```
agents/pm/agents/epics/
├── agent.py        ← Nœud LangGraph — point d'entrée, orchestre les 3 cas
├── service.py      ← Logique LLM — construction des prompts, appels, parsing
├── repository.py   ← Persistance DB — CRUD sur la table project_management.epics
└── prompt.py       ← Textes des prompts système et utilisateur
```

Chaque fichier a une responsabilité unique. `agent.py` ne fait pas d'appels LLM directs, `service.py` ne touche pas à la DB, `repository.py` ne connaît pas les prompts.

---

## 2. Rôle dans le pipeline LangGraph

Le nœud `node_epics` est enregistré dans le graph dans `agents/pm/graph/graph.py` :

```python
graph.add_node("node_epics", node_epics)
graph.add_edge("jira_sync", "node_epics")      # arrivée après validation extraction
graph.add_edge("node_epics", "node_validate")  # départ vers validation PM
```

**Position dans le pipeline :**
```
node_extraction → node_validate → jira_sync → node_epics → node_validate
                                                               │
                                               ┌──────────────┘
                                               │ si validé → jira_sync → node_stories
                                               │ si rejeté → node_epics (re-exécuté)
```

Quand `node_validate` détecte `validation_status = "rejected"`, le routeur retourne `"node_epics"` et le nœud se ré-exécute avec le `human_feedback` injecté dans le state via `aupdate_state()`.

---

## 3. State reçu — ce que node_epics lit

`node_epics` reçoit un objet `PMPipelineState` (TypedDict défini dans `agents/pm/state/state.py`). Il lit exactement ces 5 champs :

```python
project_id        = state.get("project_id")
cdc_text          = state.get("cdc_text", "")
human_feedback    = state.get("human_feedback")
targeted_epic_ids = state.get("targeted_epic_ids") or []
existing_epics    = state.get("epics", [])
```

### Description de chaque champ lu

| Champ | Type | Valeur à la 1ère exécution | Valeur après rejet PM |
|-------|------|---------------------------|----------------------|
| `project_id` | `int` | ID du projet (ex: 42) | Inchangé |
| `cdc_text` | `str` | Texte extrait du CDC | Inchangé |
| `human_feedback` | `str \| None` | `None` | Feedback du PM (ex: `"Découpe l'epic 3"`) |
| `targeted_epic_ids` | `list \| None` | `None` ou `[]` | Liste de db_id (ex: `[14, 17]`) ou `[]` si global |
| `existing_epics` | `list[dict]` | `[]` | Epics du state précédent |

### Format d'un epic dans `existing_epics`

```python
{
    "title":              "Gestion des candidats",
    "description":        "Permet aux recruteurs de créer et gérer...",
    "splitting_strategy": "by_feature"
    # IMPORTANT : pas de db_id — le state ne stocke jamais les IDs DB des epics
}
```

Le `db_id` est absent volontairement. Voir [section 10](#10-gestion-des-ids-db_id) pour l'explication complète.

---

## 4. State retourné — ce que node_epics écrit

`node_epics` retourne toujours un dict via la fonction `_done()` :

```python
def _done(epics: list[dict]) -> dict:
    return {
        "epics":              epics,           # liste des epics générés/modifiés
        "current_phase":      "epics",         # indique à node_validate la phase en cours
        "validation_status":  "pending_human", # signale que le PM doit valider
        "human_feedback":     None,            # réinitialise pour le prochain cycle
        "targeted_epic_ids":  None,            # réinitialise
        "targeted_story_ids": None,            # réinitialise (précaution)
        "error":              None,
    }
```

**Pourquoi `validation_status = "pending_human"` ?**
`node_validate` lit ce champ. S'il vaut `"pending_human"`, il interrompt le graph (interrupt LangGraph) et attend que l'API `/validate` soit appelée par le PM.

**Pourquoi réinitialiser `human_feedback` à `None` ?**
Si on ne le réinitialise pas, lors du prochain rejet le nœud lirait l'ancien feedback en plus du nouveau.

**Format d'un epic dans la liste retournée :**
```python
{
    "title":              "Gestion des candidats",
    "description":        "Permet aux recruteurs de...",
    "splitting_strategy": "by_feature"
    # Toujours sans db_id — _reload_epics() et generate_epics() le stripent tous les deux
}
```

---

## 5. Les 3 cas de traitement

La logique de branchement dans `node_epics` est un `if/elif/else` séquentiel basé sur 3 variables :

```python
# CAS 3 : PRIORITÉ MAXIMALE — targeted ids présents
if human_feedback and targeted_epic_ids and project_id:
    → _targeted_regen()

# CAS 2 : feedback global (pas d'IDs ciblés mais epics existants)
elif human_feedback and existing_epics and project_id:
    → _global_regen()

# CAS 1 : première génération (pas de feedback)
else:
    → generate_epics()
```

### Tableau récapitulatif

| Cas | `human_feedback` | `targeted_epic_ids` | `existing_epics` | Action |
|-----|-----------------|--------------------|--------------------|--------|
| 1 | `None` | `[]` | `[]` | Génère depuis le CDC |
| 2 | `"Renomme..."` | `[]` | `[epic1, epic2...]` | Améliore tous les epics |
| 3 | `"Découpe..."` | `[14, 17]` | `[epic1, epic2...]` | Améliore seulement les epics 14 et 17 |

---

## 6. agent.py — Orchestrateur

### Fonction principale : `node_epics()`

```python
async def node_epics(state: PMPipelineState) -> dict:
```

Point d'entrée unique appelé par LangGraph. Lit le state, choisit le cas, délègue aux helpers.

---

### CAS 1 — `generate_epics()` + `save_epics()`

```python
# Appel direct à service.py
epics = await generate_epics(cdc_text, human_feedback)

# Sauvegarde en DB si on a un project_id
if project_id:
    await save_epics(project_id, epics)

return _done(epics)
```

`generate_epics()` retourne des dicts **sans db_id** (ils ne sont pas encore en base au moment de l'appel). `save_epics()` les insère en DB mais ne modifie pas la liste en mémoire — les epics dans le state restent sans db_id.

---

### CAS 2 — `_global_regen()`

```python
async def _global_regen(project_id, existing_epics_state, cdc_text, feedback) -> list[dict]:
    # 1. Charge les epics depuis la DB pour récupérer leurs db_id
    db_epics = await get_epics(project_id)

    # 2. Enrichit les epics du state avec leur db_id (matching par INDEX)
    epics_with_db_id = []
    for i, e in enumerate(existing_epics_state):
        db_id = db_epics[i].id if i < len(db_epics) else None
        epics_with_db_id.append({
            "db_id":              db_id,   # ex: 12, 13, 14...
            "title":              e.get("title", ""),
            "description":        e.get("description", ""),
            "splitting_strategy": e.get("splitting_strategy", "by_feature"),
        })

    # 3. Collecte les db_ids originaux pour détecter les suppressions plus tard
    original_db_ids = [e["db_id"] for e in epics_with_db_id if e.get("db_id")]

    # 4. Appelle le LLM avec TOUS les epics + feedback
    improved = await improve_all_epics(epics_with_db_id, cdc_text, feedback)

    # 5. Applique les modifications en DB
    return await _apply_improved_epics(project_id, improved, original_db_ids)
```

**Pourquoi le matching par index ?**
Le state ne stocke pas les db_id des epics. La DB les stocke. L'ordre garanti par `ORDER BY id` dans `get_epics()` assure que `db_epics[0]` correspond à `existing_epics_state[0]`.

---

### CAS 3 — `_targeted_regen()`

```python
async def _targeted_regen(project_id, targeted_epic_ids, cdc_text, feedback) -> list[dict]:
    # 1. Charge TOUS les epics du projet depuis la DB
    db_epics = await get_epics(project_id)

    # 2. Filtre seulement les epics ciblés par le PM
    epics_to_fix = [
        {
            "db_id":              e.id,
            "title":              e.title,
            "description":        e.description or "",
            "splitting_strategy": e.splitting_strategy,
        }
        for e in db_epics
        if e.id in targeted_epic_ids   # ← filtre par db_id
    ]

    if not epics_to_fix:
        return await _reload_epics(project_id)  # sécurité : IDs invalides

    # 3. Appelle le LLM avec SEULEMENT les epics ciblés
    improved = await improve_targeted_epics(epics_to_fix, cdc_text, feedback)

    # 4. Applique en DB — passe targeted_epic_ids comme original_db_ids
    return await _apply_improved_epics(project_id, improved, targeted_epic_ids)
```

**Différence clé CAS 2 vs CAS 3 :**
- CAS 2 : LLM voit **tous** les epics → retourne **tous** les epics → absents = supprimés
- CAS 3 : LLM voit **seulement** les ciblés → retourne **seulement** les ciblés → les autres ne bougent pas

---

### `_apply_improved_epics()` — Logique centrale UPDATE/INSERT/DELETE

```python
async def _apply_improved_epics(
    project_id: int,
    improved: list[dict],          # epics retournés par le LLM
    original_db_ids: list[int] | None = None,  # epics qui existaient avant
) -> list[dict]:

    # Ensemble des db_ids présents dans la réponse LLM
    returned_db_ids = {e["db_id"] for e in improved if e.get("db_id")}

    # ── SUPPRESSIONS ──────────────────────────────────────────
    # Un epic présent avant mais absent du retour LLM = le PM veut le supprimer
    if original_db_ids:
        for db_id in original_db_ids:
            if db_id not in returned_db_ids:
                await delete_epic(db_id)
                # DELETE CASCADE → supprime aussi toutes les user_stories de cet epic

    # ── MISES À JOUR et INSERTIONS ───────────────────────────
    for e in improved:
        payload = {
            "title":              e["title"],
            "description":        e.get("description", ""),
            "splitting_strategy": e.get("splitting_strategy", "by_feature"),
        }
        if e.get("db_id"):
            await update_epic(e["db_id"], payload)    # UPDATE en DB
        else:
            new_e = await add_epic(project_id, payload)  # INSERT → nouvel ID auto

    # ── RECHARGEMENT FINAL ───────────────────────────────────
    return await _reload_epics(project_id)   # recharge tout depuis la DB (sans db_id)
```

**Les 3 opérations possibles selon la réponse LLM :**

| db_id dans réponse LLM | Opération | Explication |
|------------------------|-----------|-------------|
| `14` (existant) | `UPDATE` | Renommage, description modifiée |
| `null` | `INSERT` | Nouvel epic (scission ou ajout) |
| Absent de la réponse | `DELETE` | PM a demandé la suppression |

---

### `_reload_epics()` — Rechargement sans db_id

```python
async def _reload_epics(project_id: int) -> list[dict]:
    db_epics = await get_epics(project_id)
    return [
        {
            "title":              e.title,
            "description":        e.description or "",
            "splitting_strategy": e.splitting_strategy,
            # db_id volontairement absent
        }
        for e in db_epics
    ]
```

Appelée en fin de `_apply_improved_epics()` et en cas d'erreur (fail-safe). Garantit que le state ne contient jamais de db_id.

---

## 7. service.py — Logique LLM

### Constantes

```python
_RETRY_DELAYS     = [3, 7]        # délais entre tentatives (secondes)
_VALID_STRATEGIES = {"by_feature", "by_user_role", "by_workflow_step", "by_component"}
_MODEL            = "openai/gpt-oss-120b"
```

---

### `_normalize_epics()` — Validation et nettoyage de la réponse LLM

```python
def _normalize_epics(raw_list: list) -> list[dict]:
    result = []
    for e in raw_list:
        if not isinstance(e, dict):
            continue                    # ignore les entrées non-dict

        strategy = e.get("splitting_strategy", "by_feature")
        if strategy not in _VALID_STRATEGIES:
            strategy = "by_feature"     # fallback si valeur inconnue

        title = str(e.get("title", "")).strip()
        if not title:
            continue                    # filtre les epics sans titre

        # db_id : accepte int, null/None, ou absent
        raw_db_id = e.get("db_id")
        db_id = (
            int(raw_db_id)
            if raw_db_id is not None and str(raw_db_id).lstrip("-").isdigit()
            else None
        )

        result.append({
            "db_id":              db_id,
            "title":              title,
            "description":        str(e.get("description", "")),
            "splitting_strategy": strategy,
        })
    return result
```

**Cas couverts :**
- LLM retourne `"splitting_strategy": "par_feature"` → corrigé en `"by_feature"`
- LLM retourne un epic sans `"title"` → filtré
- LLM retourne `"db_id": null` → conservé comme `None` (scission)
- LLM retourne `"db_id": "14"` (string) → converti en `int(14)`

---

### `_call_llm()` — Appel LLM avec retry

```python
async def _call_llm(prompt: str, max_tokens: int = 2048) -> list[dict]:
    last_error = None
    for attempt in range(1 + len(_RETRY_DELAYS)):   # 3 tentatives
        try:
            raw = await invoke_with_fallback(
                model      = _MODEL,
                messages   = [
                    {"role": "system", "content": EPICS_SYSTEM_PROMPT},
                    {"role": "user",   "content": prompt},
                ],
                max_tokens  = max_tokens,
                temperature = 0,          # déterministe
            )
            if not raw or not raw.strip():
                raise ValueError("Réponse vide du LLM")

            # Retire les balises markdown si le LLM en ajoute malgré les instructions
            clean  = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
            data   = json.loads(clean)
            result = _normalize_epics(data.get("epics", []))
            if not result:
                raise ValueError("Aucun epic valide dans la réponse LLM")
            return result

        except Exception as e:
            last_error = e
            if attempt < len(_RETRY_DELAYS):
                delay = _RETRY_DELAYS[attempt]
                await asyncio.sleep(delay)   # 3s, puis 7s

    raise RuntimeError(f"Échec après 3 tentatives : {last_error}")
```

**Séquence des tentatives :**
```
Tentative 1 → immédiate
Tentative 2 → après 3 secondes
Tentative 3 → après 7 secondes (depuis la tentative 2)
Si tout échoue → RuntimeError → agent.py le catch → _reload_epics() (fail-safe)
```

---

### `generate_epics()` — CAS 1 uniquement

```python
async def generate_epics(cdc_text: str, human_feedback: str | None = None) -> list[dict]:
    user_prompt = build_epics_prompt(cdc_text, human_feedback)
    raw_content = await invoke_with_fallback(
        model       = _MODEL,
        messages    = [system, user_prompt],
        max_tokens  = 4096,    # plus grand que _call_llm car génération complète
        temperature = 0,
    )
    # ... parse JSON, _normalize_epics ...

    # SUPPRIME le db_id des résultats (pas encore en base)
    return [
        {"title": e["title"], "description": e["description"], "splitting_strategy": e["splitting_strategy"]}
        for e in validated
    ]
```

**Appelle directement `invoke_with_fallback`** (pas `_call_llm`) car c'est un appel unique avec `max_tokens=4096` et gestion d'erreur différente.

---

### `improve_all_epics()` — CAS 2

```python
async def improve_all_epics(existing_epics: list[dict], cdc_text: str, feedback: str) -> list[dict]:
```

Reçoit les epics **enrichis avec db_id** (fournis par `_global_regen`). Construit un prompt avec :
```
FEEDBACK : "Renomme l'epic Recherche en Moteur de matching"

EPICS ACTUELS (6) :
  Epic #1 [db_id=12] — Profilage automatisé des candidats
  Epic #2 [db_id=13] — Gestion des projets et des exigences
  Epic #3 [db_id=14] — Recherche et matching
  ...

CONTEXTE CDC : [2000 premiers caractères]

INSTRUCTIONS :
- Pour RENOMMER : garde le db_id, change seulement le titre.
- Pour SCINDER : garde le db_id pour la 1ère partie, null pour la 2e.
- Pour AJOUTER : utilise db_id null.
- Pour SUPPRIMER : ne l'inclus PAS dans la réponse.
- Retourne la liste COMPLÈTE après modifications.
```

Appelle `_call_llm(prompt, max_tokens=3000)`.

---

### `improve_targeted_epics()` — CAS 3

```python
async def improve_targeted_epics(epics: list[dict], cdc_text: str, feedback: str) -> list[dict]:
```

Reçoit **seulement les epics ciblés** avec leurs db_id. Le prompt est plus détaillé (titre + description + stratégie pour chaque epic) et demande de ne retourner **que** les epics de remplacement.

Appelle `_call_llm(prompt, max_tokens=2048)`.

---

## 8. repository.py — Persistance DB

Toutes les fonctions ouvrent leur propre session `AsyncSessionLocal()` et la ferment après. Pas de session partagée entre appels.

---

### `save_epics()` — Utilisé uniquement dans le CAS 1

```python
async def save_epics(project_id: int, epics: list[dict]) -> list[Epic]:
    async with AsyncSessionLocal() as session:
        # 1. Supprime TOUS les epics existants du projet
        #    (DELETE CASCADE supprime aussi les user_stories)
        await session.execute(
            delete(Epic).where(Epic.project_id == project_id)
        )

        # 2. Crée les nouveaux ORM
        orm_epics = [
            Epic(
                project_id         = project_id,
                title              = epic["title"],
                description        = epic["description"],
                splitting_strategy = epic["splitting_strategy"],
                status             = EpicStatusEnum.DRAFT,
                ai_metadata        = {"source": "llm_generated"},
            )
            for epic in epics
        ]
        session.add_all(orm_epics)
        await session.commit()

        # 3. Refresh pour récupérer les IDs auto-générés par PostgreSQL
        for e in orm_epics:
            await session.refresh(e)

        return orm_epics   # retourne les ORM avec leurs ids
```

**Important :** `save_epics` retourne les ORM avec `id` mais `node_epics` n'utilise pas ce retour pour mettre à jour le state. Les epics dans le state restent sans db_id.

---

### `update_epic()` — Utilisé dans `_apply_improved_epics`

```python
async def update_epic(epic_id: int, updates: dict) -> bool:
    async with AsyncSessionLocal() as session:
        values = {}
        if "title" in updates and updates["title"]:
            values["title"] = updates["title"]
        if "description" in updates:
            values["description"] = updates["description"]
        if "splitting_strategy" in updates and updates["splitting_strategy"]:
            values["splitting_strategy"] = updates["splitting_strategy"]
        if not values:
            return False    # rien à mettre à jour
        result = await session.execute(
            sa_update(Epic).where(Epic.id == epic_id).values(**values)
        )
        await session.commit()
        return result.rowcount > 0
```

---

### `delete_epic()` — Utilisé dans `_apply_improved_epics`

```python
async def delete_epic(epic_id: int) -> bool:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            sa_delete(Epic).where(Epic.id == epic_id)
        )
        await session.commit()
        return result.rowcount > 0
```

La suppression en cascade est gérée par la contrainte FK définie dans le modèle SQLAlchemy :
```python
# epic.py
user_stories = relationship("UserStory", back_populates="epic", cascade="all, delete-orphan")
```

Supprimer un epic supprime automatiquement toutes ses `user_stories`.

---

### `add_epic()` — Utilisé dans `_apply_improved_epics` pour les scissions

```python
async def add_epic(project_id: int, epic_data: dict) -> Epic:
    async with AsyncSessionLocal() as session:
        orm_e = Epic(
            project_id         = project_id,
            title              = epic_data["title"],
            description        = epic_data.get("description", ""),
            splitting_strategy = epic_data.get("splitting_strategy", "by_feature"),
            status             = EpicStatusEnum.DRAFT,
            ai_metadata        = {"source": "manual"},  # distingue de "llm_generated"
        )
        session.add(orm_e)
        await session.commit()
        await session.refresh(orm_e)
        return orm_e   # retourne l'ORM avec le nouvel id PostgreSQL
```

---

### `get_epics()` — Utilisé par `_global_regen`, `_targeted_regen`, `_reload_epics`

```python
async def get_epics(project_id: int) -> list[Epic]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Epic)
            .where(Epic.project_id == project_id)
            .order_by(Epic.id)          # ORDER BY id — CRUCIAL pour le mapping d'index
        )
        return result.scalars().all()
```

**Le `ORDER BY id` est fondamental** : il garantit que `db_epics[0]` correspond à l'epic qui était à l'index 0 dans le state.

---

### `update_epic_jira_key()` — Utilisé par le nœud Jira sync uniquement

```python
async def update_epic_jira_key(epic_db_id: int, jira_key: str) -> None:
```

Pas utilisé dans le flux normal — appelé par `node_jira_sync` après synchronisation Jira.

---

## 9. prompt.py — Prompts LLM

### `EPICS_SYSTEM_PROMPT` — Prompt système (commun à tous les appels)

```
"Tu es un expert en gestion de projet Agile et en analyse de cahiers des charges.
Tu aides un Project Manager à décomposer un projet en epics LangGraph pour un pipeline de développement Scrum.

Règles absolues :
- Réponds UNIQUEMENT avec du JSON valide, sans texte avant ni après.
- Génère entre 3 et 8 epics maximum selon la taille du projet.
- Chaque epic doit être autonome et livrable indépendamment.
- La splitting_strategy doit refléter la meilleure façon de découper CET epic en stories.
- Les descriptions doivent être en français et orientées valeur métier."
```

**Utilisé par :** `generate_epics()` (via `build_epics_prompt`), `_call_llm()` (via `improve_all_epics` et `improve_targeted_epics`)

---

### `build_epics_prompt()` — Prompt utilisateur pour le CAS 1

```python
def build_epics_prompt(cdc_text: str, human_feedback: str | None = None) -> str:
    feedback_section = ""
    if human_feedback:
        feedback_section = f"""
⚠️ CORRECTIONS DEMANDÉES PAR LE PM :
{human_feedback}

Tu dois corriger les epics en tenant compte de ces remarques.
"""
    return f"""Analyse ce Cahier des Charges (CDC) et génère les epics du projet.
{feedback_section}
Pour chaque epic, détermine la splitting_strategy la plus appropriée :
  - "by_feature"       : l'epic contient des fonctionnalités distinctes
  - "by_user_role"     : différents types d'utilisateurs ont des besoins différents
  - "by_workflow_step" : l'epic suit un processus séquentiel
  - "by_component"     : l'epic concerne plusieurs couches techniques

Retourne UNIQUEMENT ce JSON :
{{ "epics": [{{ "title": "...", "description": "...", "splitting_strategy": "..." }}] }}

CDC à analyser :
{cdc_text}"""
```

**Note :** Ce prompt est utilisé **uniquement** pour le CAS 1. Les CAS 2 et 3 construisent leurs prompts directement dans `service.py` (dans `improve_all_epics` et `improve_targeted_epics`).

---

## 10. Gestion des IDs (db_id)

### Problème fondamental

Le state LangGraph n'a pas de `db_id` dans les epics. La DB a des IDs auto-incrémentés. Ces deux mondes doivent être réconciliés pour chaque rejet.

### Cycle de vie du db_id

```
CAS 1 — Première génération :
    generate_epics() → epics sans db_id
    save_epics()     → INSERT en DB → PostgreSQL génère id=12, 13, 14...
    state["epics"]   → toujours sans db_id

CAS 2 — Rejet global :
    state["epics"] = [{title, desc, strategy}, ...]  ← pas de db_id
    get_epics()    → [Epic(id=12), Epic(id=13), ...]  ← a les db_id
    matching par index : state[0] ↔ db[0] ↔ db_id=12
    improve_all_epics reçoit [{db_id:12, title...}, {db_id:13...}]
    LLM répond avec db_ids dans sa réponse
    _apply_improved_epics → UPDATE/INSERT/DELETE en DB
    _reload_epics → state mis à jour, toujours sans db_id

CAS 3 — Rejet ciblé :
    targeted_epic_ids = [14] → vient de l'API (frontend charge via GET /epics)
    get_epics() → Epic(id=14) trouvé dans la DB
    improve_targeted_epics reçoit [{db_id:14, title...}]
    LLM répond avec db_id=14 (modifié) ou db_id=null (scission)
    _apply_improved_epics → UPDATE(14) + INSERT(nouveau)
    _reload_epics → state mis à jour, toujours sans db_id
```

### Pourquoi le state ne stocke pas les db_id des epics ?

1. **Cohérence** : après une scission (1 epic → 2 epics), l'index dans le state change. Un db_id stocké deviendrait incohérent.
2. **Simplicité** : la phase 3 (stories) utilise `epic_id = index` (0, 1, 2...) pour grouper les stories. Elle ne connaît pas les db_id des epics.
3. **Source de vérité** : la DB est la seule source de vérité pour les IDs. Le state LangGraph est une vue temporaire.

### Comment le frontend obtient les db_id des epics ?

Via l'API `GET /pipeline/{project_id}/epics` qui charge directement depuis la DB :
```python
# pipeline.py
@router.get("/{project_id}/epics")
async def get_project_epics(project_id: int):
    epics = await get_epics(project_id)
    return [{"db_id": e.id, "title": e.title, ...} for e in epics]
```

Le frontend utilise ces `db_id` pour remplir `targeted_epic_ids` lors d'un rejet ciblé.

---

## 11. Chaîne d'appels complète

### CAS 1 — Première génération

```
API POST /pipeline/{id}/start
  └── pipeline.py : pm_graph.ainvoke(initial_state, config)
        └── graph.py : node_extraction → node_validate → jira_sync → node_epics
              └── agent.py : node_epics(state)
                    state: { cdc_text="...", human_feedback=None, epics=[], project_id=42 }
                    └── service.py : generate_epics(cdc_text, None)
                          └── prompt.py : build_epics_prompt(cdc_text, None)
                                → prompt sans section feedback
                          └── groq_client.py : invoke_with_fallback(model, messages, max_tokens=4096)
                                → raw JSON string
                          └── re.sub(r"```(?:json)?...") → clean JSON
                          └── json.loads(clean) → { "epics": [{...}, {...}] }
                          └── service.py : _normalize_epics([{...}])
                                → valide strategy, titre, db_id
                          └── strip db_id → [{title, desc, strategy}, ...]
                    └── repository.py : save_epics(42, epics)
                          └── AsyncSessionLocal()
                          └── DELETE FROM project_management.epics WHERE project_id=42
                          └── INSERT INTO project_management.epics VALUES (...) × N
                          └── session.commit()
                          └── session.refresh(orm_e) × N → IDs générés
                    └── agent.py : _done(epics)
                          → { epics:[...sans db_id...], validation_status:"pending_human", ... }
              └── node_validate → interrupt() → attend PM
```

---

### CAS 2 — Rejet global

```
API POST /pipeline/{id}/validate { approved:false, feedback:"Renomme epic 3...", targeted_epic_ids:[] }
  └── pipeline.py : aupdate_state(config, { validation_status:"rejected", human_feedback:"...", targeted_epic_ids:None })
  └── pipeline.py : pm_graph.ainvoke(None, config)
        └── node_validate → routeur → node_epics
              └── agent.py : node_epics(state)
                    state: { human_feedback="Renomme...", targeted_epic_ids=[], existing_epics=[{...}×6] }
                    → CAS 2 (human_feedback SET + targeted_epic_ids VIDE)
                    └── agent.py : _global_regen(42, existing_epics, cdc_text, "Renomme...")
                          └── repository.py : get_epics(42)
                                → SELECT * FROM epics WHERE project_id=42 ORDER BY id
                                → [Epic(id=12), Epic(id=13), Epic(id=14), ...]
                          └── matching index :
                                existing[0] ↔ db[0].id=12 → {db_id:12, title:..., ...}
                                existing[1] ↔ db[1].id=13 → {db_id:13, title:..., ...}
                                ...
                          └── original_db_ids = [12, 13, 14, 15, 16, 17]
                          └── service.py : improve_all_epics(epics_with_db_id, cdc_text, "Renomme...")
                                → prompt avec liste [db_id=12]...[db_id=17] + feedback + CDC
                                └── service.py : _call_llm(prompt, max_tokens=3000)
                                      → tentative 1 → invoke_with_fallback
                                      → json.loads → _normalize_epics
                                      → [{db_id:12,...}, {db_id:13,...}, {db_id:14,title:"Moteur..."}, ...]
                          └── agent.py : _apply_improved_epics(42, improved, [12,13,14,15,16,17])
                                returned_db_ids = {12,13,14,15,16,17}
                                [SUPPRESSION] aucun absent → rien
                                [UPDATE] db_id=14 title="Moteur..." → repository.py : update_epic(14, payload)
                                [UPDATE] autres db_ids → update_epic(12), update_epic(13)...
                                └── agent.py : _reload_epics(42)
                                      └── repository.py : get_epics(42)
                                      → [{title,desc,strategy}, ...]  sans db_id
                    └── agent.py : _done(epics)
              └── node_validate → interrupt()
```

---

### CAS 3 — Rejet ciblé avec scission

```
API POST /pipeline/{id}/validate { approved:false, feedback:"Découpe en 2", targeted_epic_ids:[14] }
  └── pipeline.py : aupdate_state(config, { validation_status:"rejected", targeted_epic_ids:[14], human_feedback:"Découpe..." })
  └── pipeline.py : pm_graph.ainvoke(None, config)
        └── node_epics(state)
              state: { human_feedback="Découpe...", targeted_epic_ids=[14] }
              → CAS 3 (human_feedback SET + targeted_epic_ids NON VIDE)
              └── agent.py : _targeted_regen(42, [14], cdc_text, "Découpe...")
                    └── repository.py : get_epics(42) → [Epic(id=12),...,Epic(id=14),...]
                    └── filtre : epics_to_fix = [Epic(id=14)] → [{db_id:14, title:"Recherche..."}]
                    └── service.py : improve_targeted_epics([{db_id:14,...}], cdc_text, "Découpe...")
                          → prompt avec SEULEMENT l'epic 14
                          └── service.py : _call_llm(prompt, max_tokens=2048)
                                → LLM retourne :
                                  [{ db_id:14, title:"Moteur de matching candidats" },
                                   { db_id:null, title:"Gestion des alertes matching" }]
                          → _normalize_epics → [{db_id:14,...}, {db_id:None,...}]
                    └── agent.py : _apply_improved_epics(42, improved, [14])
                          returned_db_ids = {14}
                          [SUPPRESSION] 14 in returned → rien supprimé
                          [UPDATE] db_id=14 → update_epic(14, {title:"Moteur..."})
                          [INSERT] db_id=None → add_epic(42, {title:"Gestion alertes..."})
                                → PostgreSQL génère id=18
                          └── _reload_epics(42)
                                → 7 epics (6 originaux modifiés + 1 nouveau)
                                → tous sans db_id
              └── _done(7 epics)
        └── node_validate → interrupt()
```

---

## 12. Questions fréquentes

**Q : Pourquoi `save_epics` fait un DELETE avant d'INSERT ?**
Parce que c'est appelé uniquement dans le CAS 1 (première génération). S'il existe des epics résiduels d'un test précédent, ils seraient en doublon. Le DELETE garantit un état propre.

**Q : Que se passe-t-il si `targeted_epic_ids` contient un ID qui n'existe plus en DB ?**
`_targeted_regen` filtre `epics_to_fix = [e for e in db_epics if e.id in targeted_epic_ids]`. Si l'ID est introuvable, `epics_to_fix` est vide → `_reload_epics()` est appelé et retourne les epics sans modification.

**Q : Pourquoi `improve_all_epics` demande au LLM de retourner la liste COMPLÈTE ?**
Pour détecter les suppressions. Si le LLM ne retourne pas un epic, `_apply_improved_epics` voit que son `db_id` est absent de `returned_db_ids` et le supprime. C'est le seul mécanisme de suppression disponible.

**Q : Pourquoi `improve_targeted_epics` ne demande PAS la liste complète ?**
Parce que les epics non ciblés ne doivent pas être touchés. Le LLM ne voit que les epics ciblés et ne retourne que ceux-là. Les autres epics restent intacts en DB.

**Q : Comment éviter qu'un rejet global ne supprime tous les epics ?**
`original_db_ids` est construit **avant** l'appel LLM. Même si le LLM retourne une liste vide (hallucination), les suppressions détectées seraient toutes les IDs originales. C'est le seul risque non protégé — c'est pourquoi le prompt insiste sur "retourne la liste COMPLÈTE".

**Q : `temperature=0` — pourquoi ?**
Déterminisme total. Avec temperature=0 le LLM produit toujours la même réponse pour le même input. Cela rend le comportement prévisible et les bugs reproductibles.

**Q : Que se passe-t-il si le LLM retourne du markdown autour du JSON ?**
```python
clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
```
Cette regex retire les balises ` ```json ` et ` ``` ` que certains modèles ajoutent malgré l'instruction "sans markdown".
