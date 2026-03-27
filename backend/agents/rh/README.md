# Agent RH
> Serveur FastAPI indépendant — Port **8001**

## Rôle
Gère tout ce qui concerne les ressources humaines : création de congés, consultation du solde, disponibilités d'équipe, compétences des membres.
Il utilise un cycle **ReAct** (Reason + Act) via LangGraph avec le modèle `gpt-oss-120b` (Groq, failover automatique sur plusieurs clés).
Toutes les actions passent par un contrôle **RBAC** (rôles : `consultant`, `pm`).

---

## Lancer l'agent
```bash
uvicorn agents.rh.server:app --port 8001 --reload
```

## Agent Card A2A
```
GET http://localhost:8001/.well-known/agent.json
```

---

## Outils disponibles

### 1. `check_leave_balance`
Vérifie le solde de congés d'un employé.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'utilisateur |
| `requested_days` | int | ❌ (défaut: 0) | Jours demandés — active la vérification `can_create` |

**Output :**
```json
{
  "success": true,
  "solde_total": 26,
  "jours_pending": 3,
  "solde_effectif": 23,
  "can_create": true,
  "message": "Solde suffisant. Vous avez 23 jours disponibles. Après cette demande il vous restera 20 jours.",
  "pending_details": [
    { "id": 1, "start_date": "2026-04-01", "end_date": "2026-04-03", "days_count": 3 }
  ]
}
```

---

### 2. `create_leave`
Crée une demande de congé. Vérifie automatiquement le solde et les chevauchements.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'utilisateur |
| `start_date` | str | ✅ | Date de début (`YYYY-MM-DD`) |
| `end_date` | str | ✅ | Date de fin (`YYYY-MM-DD`) |

**Output succès :**
```json
{
  "success": true,
  "leave_id": 42,
  "start_date": "2026-04-07",
  "end_date": "2026-04-10",
  "days_count": 4,
  "status": "pending",
  "solde_restant": 19
}
```

**Output erreur — chevauchement :**
```json
{
  "error": "overlap",
  "message": "Chevauchement avec un congé existant du 2026-04-05 au 2026-04-08 (statut: pending)."
}
```

**Output erreur — solde insuffisant :**
```json
{
  "error": "solde_insuffisant",
  "message": "Solde insuffisant. Vous avez 2 jours disponibles...",
  "solde_effectif": 2,
  "jours_demandes": 5
}
```

---

### 3. `get_my_leaves`
Retourne la liste des congés d'un employé.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'utilisateur |
| `status_filter` | str | ❌ | `"pending"`, `"approved"`, `"rejected"` ou `null` (tous) |

**Output :**
```json
{
  "success": true,
  "total": 2,
  "leaves": [
    { "id": 1, "start_date": "2026-04-01", "end_date": "2026-04-03", "days_count": 3, "status": "pending" },
    { "id": 2, "start_date": "2026-05-12", "end_date": "2026-05-12", "days_count": 1, "status": "approved" }
  ]
}
```

---

### 4. `get_team_availability`
Retourne la disponibilité **aujourd'hui** des membres de l'équipe (exclut l'utilisateur lui-même).

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'utilisateur (détermine l'équipe) |

**Output :**
```json
{
  "success": true,
  "team_id": 3,
  "members": [
    { "name": "Alice Dupont", "available": true, "on_leave": false },
    { "name": "Bob Martin", "available": false, "on_leave": true }
  ]
}
```

---

### 5. `get_team_stack`
Retourne les compétences techniques de chaque membre de l'équipe.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'utilisateur (détermine l'équipe) |

**Output :**
```json
{
  "success": true,
  "team_stack": [
    { "name": "Alice Dupont", "skills": "React, TypeScript, Node.js" },
    { "name": "Bob Martin", "skills": "Python, FastAPI, PostgreSQL" }
  ]
}
```

---

### 6. `check_calendar_conflicts`
Vérifie les conflits Google Calendar pour une période de congé (appel réel via l'agent Calendar).

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'utilisateur |
| `start_date` | str | ✅ | Date de début (`YYYY-MM-DD`) |
| `end_date` | str | ✅ | Date de fin (`YYYY-MM-DD`) |

**Output — aucun conflit :**
```json
{
  "success": true,
  "conflicts": []
}
```

**Output — conflits détectés :**
```json
{
  "success": true,
  "conflicts": [
    {
      "id": "abc123xyz",
      "title": "Stand-up quotidien",
      "start": "2026-04-07T10:00:00+01:00",
      "end":   "2026-04-07T10:30:00+01:00"
    }
  ]
}
```

> Si le service Calendar est indisponible : `mcp_error: true` + `conflicts: []` → le congé est créé sans vérification.

---

### 7. `reschedule_meeting`
Déplace une réunion conflictuelle via l'agent Calendar (A2A). Utilise l'`event_id` issu de `check_calendar_conflicts`.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `event_id` | str | ✅ | ID Google Calendar de l'événement |
| `event_title` | str | ✅ | Titre (pour confirmation) |
| `current_start` | str | ✅ | Heure de début actuelle (format ISO) |
| `current_end` | str | ✅ | Heure de fin actuelle (format ISO) |
| `new_date` | str | ✅ | Nouvelle date (`YYYY-MM-DD`) |

---

### 8. `notify_manager` *(mock)*
Notifie le manager via Slack.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `user_id` | int | ✅ | ID de l'employé |
| `message` | str | ✅ | Contenu du message |

---

## Source de données
**PostgreSQL** via SQLAlchemy — schéma `hris`
- Table `employees` — profils, solde de congés, compétences
- Table `leaves` — demandes de congés (statuts : pending / approved / rejected)
- Table `teams` — composition des équipes

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI A2A : routes `/.well-known/agent.json` et `POST /` |
| `agent.py` | ReAct executor LangGraph + failover Groq + extraction des steps |
| `tools.py` | Implémentation des outils (accès direct PostgreSQL via SQLAlchemy) |
| `schemas.py` | AgentCard A2A + modèles Pydantic |
| `prompts.py` | Prompt système : règles métier RH, workflows, résolution des dates |

---

## Cas de test — du basique au complexe

> Envoyez ces messages via le chat. L'orchestrateur les route automatiquement vers l'agent RH.
> Le `user_id` est injecté par l'orchestrateur (token JWT).

---

### NIVEAU 1 — Consultation simple (1 outil)

#### T1.1 — Consulter son solde de congés
```
Combien de jours de congé il me reste ?
```
**Steps ReAct attendus :**
1. `check_leave_balance(user_id=X, requested_days=0)`

**Réponse attendue :**
```
Votre solde de congés :
- Solde total : 26 jours
- Jours en attente (pending) : 3 jours
- Solde effectif disponible : 23 jours
```

**Variantes à tester :**
- `"Mon solde de congé ?"`
- `"J'ai combien de jours restants ?"`
- `"Quel est mon solde ?"`

---

#### T1.2 — Consulter tous ses congés
```
Montre-moi tous mes congés
```
**Steps ReAct attendus :**
1. `get_my_leaves(user_id=X)` — sans filtre

**Réponse attendue :** tableau complet (pending + approved + rejected)

---

#### T1.3 — Consulter uniquement les congés en attente
```
Montre-moi mes congés en attente d'approbation
```
**Steps ReAct attendus :**
1. `get_my_leaves(user_id=X, status_filter="pending")`

**Réponse attendue :** uniquement les congés au statut `pending`

---

#### T1.4 — Disponibilité de l'équipe
```
Qui est disponible aujourd'hui dans mon équipe ?
```
**Steps ReAct attendus :**
1. `get_team_availability(user_id=X)`

**Réponse attendue :**
```
Disponibilité de votre équipe aujourd'hui :
✅ Alice Dupont — disponible
❌ Bob Martin — en congé
```

> ⚠️ L'utilisateur demandeur **ne doit pas** apparaître dans la liste.
> ⚠️ L'agent **ne doit pas** poser de question de suivi après cette réponse.

**Variantes à tester :**
- `"Qui est au bureau aujourd'hui ?"`
- `"Montre-moi la dispo de l'équipe"`

---

#### T1.5 — Compétences de l'équipe
```
Quelles sont les compétences de mon équipe ?
```
**Steps ReAct attendus :**
1. `get_team_stack(user_id=X)`

**Réponse attendue :** liste des membres avec leurs compétences techniques

> ⚠️ L'agent **ne doit pas** poser de question de suivi après cette réponse.

---

### NIVEAU 2 — Création de congé (sans conflit calendar)

#### T2.1 — Congé avec dates explicites
```
Je veux poser un congé du 7 au 10 avril
```
**Steps ReAct attendus :**
1. `check_leave_balance(user_id=X, requested_days=4)`
2. `check_calendar_conflicts(user_id=X, start_date="2026-04-07", end_date="2026-04-10")`
3. `create_leave(user_id=X, start_date="2026-04-07", end_date="2026-04-10")`
4. `notify_manager(user_id=X, message="...")`

**Réponse attendue :**
```
✅ Congé créé du 07/04/2026 au 10/04/2026 (4 jours ouvrés)
💰 Solde restant : 19 jours
📢 Manager notifié
```

---

#### T2.2 — Congé avec date relative
```
Je serai absent demain
```
**Steps ReAct attendus :**
1. L'agent résout automatiquement : `start_date = end_date = J+1`
2. `check_leave_balance` → `check_calendar_conflicts` → `create_leave` → `notify_manager`

**Comportement incorrect à détecter :**
- L'agent demande "Pouvez-vous me donner la date en format YYYY-MM-DD ?" → **bug**

**Variantes à tester :**
- `"Je suis malade lundi"`
- `"Je ne viendrai pas vendredi"`
- `"Prends-moi un congé pour lundi prochain"`
- `"Je veux poser la semaine prochaine"` → 5 jours ouvrés

---

#### T2.3 — Congé d'un seul jour
```
Je veux un congé pour après-demain
```
**Steps ReAct attendus :**
- `start_date = end_date` (congé d'un jour)
- Même workflow que T2.1

---

#### T2.4 — Solde insuffisant (STOP attendu)
```
Je veux poser 30 jours de congé à partir de demain
```
**Steps ReAct attendus :**
1. `check_leave_balance(user_id=X, requested_days=30)` → `can_create: false`
2. **STOP** — `create_leave` ne doit **jamais** être appelé

**Réponse attendue :**
```
Solde insuffisant. Vous avez X jours disponibles, votre demande de 30 jours dépasse ce solde.
```

---

#### T2.5 — Chevauchement avec un congé existant
```
Je veux créer un congé du 1 au 5 avril
```
*(Un congé pending/approved existe déjà sur cette période)*

**Steps ReAct attendus :**
1. `check_leave_balance` → OK
2. `check_calendar_conflicts` → OK (pas de réunion)
3. `create_leave` → `error: "overlap"`

**Réponse attendue :**
```
Vous avez déjà un congé du ... au ... (statut: pending). Impossible de créer un congé qui se chevauche.
```

---

### NIVEAU 3 — Congé avec conflits calendrier (interaction 2 tours)

#### T3.1 — Congé avec réunions existantes → option 1 (créer quand même)

**Tour 1 :**
```
Je veux un congé du 7 au 9 avril
```
*(Des réunions existent sur ces jours dans Google Calendar)*

**Steps ReAct attendus :**
1. `check_leave_balance` → OK
2. `check_calendar_conflicts` → 2 conflits détectés
3. L'agent liste les conflits et propose 3 options :
   ```
   Vous avez des réunions pendant cette période :
   - "Stand-up" le 07/04 de 10h à 10h30
   - "Point projet" le 08/04 de 14h à 15h

   Souhaitez-vous :
   1. Créer le congé quand même (les réunions restent en place)
   2. Créer le congé ET déplacer les réunions conflictuelles
   3. Annuler la demande de congé
   ```

**Tour 2 :**
```
1
```
**Steps ReAct attendus (continuation → agent rh) :**
1. `create_leave(user_id=X, start_date="2026-04-07", end_date="2026-04-09")`
2. `notify_manager(user_id=X, message="...")`

**Réponse attendue :**
```
✅ Congé créé du 07/04 au 09/04 (3 jours ouvrés)
💰 Solde restant : X jours
📢 Manager notifié
```

---

#### T3.2 — Congé avec réunions existantes → option 3 (annulation)

**Tour 1 :** (même que T3.1)

**Tour 2 :**
```
3
```
**Réponse attendue :**
```
Demande de congé annulée. Aucun changement effectué.
```

> ⚠️ Aucun outil ne doit être appelé après l'annulation.

---

### NIVEAU 4 — Workflow croisé RH → Calendar (reschedule)

> Ce workflow est le plus complexe : l'agent RH appelle l'agent Calendar via A2A
> pour déplacer une réunion conflictuelle avant de créer le congé.

#### T4.1 — Congé avec réunion conflictuelle → déplacer d'un jour

**Tour 1 :**
```
Je veux prendre congé du 7 au 8 avril
```
*(Un "Stand-up" existe le 07/04 à 10h)*

**Steps ReAct attendus :**
1. `check_leave_balance` → OK
2. `check_calendar_conflicts` → 1 conflit : `{ "id": "abc123", "title": "Stand-up", "start": "2026-04-07T10:00:00+01:00", "end": "2026-04-07T10:30:00+01:00" }`
3. L'agent propose les 3 options

**Tour 2 :**
```
2
```
L'agent demande : *"À quelle date voulez-vous déplacer la réunion ?"*

**Tour 3 :**
```
Le 9 avril
```

**Steps ReAct attendus (appel croisé RH → Calendar) :**
1. `reschedule_meeting(event_id="abc123", event_title="Stand-up", current_start="2026-04-07T10:00:00+01:00", current_end="2026-04-07T10:30:00+01:00", new_date="2026-04-09")` → appel A2A vers l'agent Calendar
2. `create_leave(user_id=X, start_date="2026-04-07", end_date="2026-04-08")`
3. `notify_manager(user_id=X, message="...")`

**Réponse attendue :**
```
✅ Congé créé du 07/04 au 08/04 (2 jours ouvrés)
📅 "Stand-up" déplacé au 09/04/2026
💰 Solde restant : X jours
📢 Manager notifié
```

> ⚠️ L'`event_id` utilisé dans `reschedule_meeting` doit être copié **exactement**
> depuis le résultat de `check_calendar_conflicts` — jamais inventé.

---

#### T4.2 — Congé avec plusieurs réunions conflictuelles → toutes déplacer

**Tour 1 :**
```
Je veux prendre la semaine prochaine entière en congé
```
*(2 réunions existent : "Stand-up" lundi et "Point projet" mercredi)*

**Steps ReAct attendus :**
1. `check_leave_balance` → OK
2. `check_calendar_conflicts` → 2 conflits
3. L'agent liste les 2 réunions et propose les 3 options

**Tour 2 :**
```
Déplace-les toutes au vendredi de la semaine d'après
```

**Steps ReAct attendus :**
1. `reschedule_meeting(event_id="id_standup", ...)` → appel Calendar
2. `reschedule_meeting(event_id="id_point_projet", ...)` → appel Calendar
3. `create_leave(...)` → congé sur toute la semaine
4. `notify_manager(...)`

> ⚠️ L'agent doit appeler `reschedule_meeting` **pour chaque** conflit, pas seulement le premier.

---

#### T4.3 — Congé → Calendar indisponible (graceful fallback)

**Contexte :** le service MCP Google Calendar est down.

**Message :**
```
Je veux un congé pour demain
```

**Steps ReAct attendus :**
1. `check_leave_balance` → OK
2. `check_calendar_conflicts` → `{ "success": true, "conflicts": [], "mcp_error": true }`
3. `create_leave` → congé créé sans vérification calendrier
4. `notify_manager`

**Réponse attendue :**
```
Le calendrier est temporairement indisponible.
✅ Congé créé pour demain (1 jour ouvré) sans vérification de conflits.
💰 Solde restant : X jours
📢 Manager notifié
```

---

### NIVEAU 5 — Cas limites et rejets

#### T5.1 — Message hors périmètre
```
Crée-moi un ticket Jira
```
**Comportement attendu :**
- Aucun outil appelé
- Réponse : `"Je suis spécialisé uniquement en RH. Pour cette demande, veuillez utiliser l'assistant général."`

---

#### T5.2 — Message sans sens (gibberish)
```
bksjdflksiiisi
```
**Comportement attendu :**
- Routé vers `chat` par node1 (détection gibberish)
- Réponse du fallback : aide générale sur les capacités

---

#### T5.3 — RBAC — accès refusé
*(Envoyé avec un rôle sans permission)*
```
Crée-moi un congé pour demain
```
**Comportement attendu :**
```
Accès refusé. Vous n'avez pas la permission d'effectuer cette action.
```
```json
{ "error": "...", "rbac_denied": true }
```

---

#### T5.4 — Chevauchement week-end
```
Je veux un congé samedi et dimanche
```
**Comportement attendu :**
```
La période sélectionnée ne contient aucun jour ouvré (week-end).
```

---

## Règles critiques du prompt

| Règle | Description |
|-------|-------------|
| **Pas de question de suivi** | Après `get_team_availability`, `get_team_stack`, `get_my_leaves` ou `check_leave_balance` → STOP, pas de "Souhaitez-vous..." |
| **Résolution des dates** | "demain", "lundi prochain", "la semaine prochaine" → résolus automatiquement sans demander le format |
| **event_id** | Toujours copié depuis `check_calendar_conflicts`, jamais inventé |
| **STOP sur solde insuffisant** | `can_create=false` → arrêt immédiat, pas de `create_leave` |
| **STOP sur chevauchement** | `error: overlap` → arrêt, pas de retry |
| **notify_manager** | Uniquement après `success: true` de `create_leave` |
