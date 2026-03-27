# Agent Calendar
> Serveur FastAPI indépendant — Port **8005**

## Rôle
Gère les événements **Google Calendar** : création, modification, suppression, recherche et vérification de disponibilités.
Il utilise un cycle **ReAct** (Reason + Act) via LangGraph avec le modèle `gpt-oss-120b` (Groq, failover automatique).
Toutes les actions passent par un contrôle **RBAC** (rôles : `consultant`, `pm`).

---

## Lancer l'agent
```bash
uvicorn agents.calendar.server:app --port 8005 --reload
```

## Agent Card A2A
```
GET http://localhost:8005/.well-known/agent.json
```

---

## Outils disponibles

### 1. `check_calendar_conflicts`
Vérifie si des événements existent sur un créneau (via `list-events` Google Calendar).

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `start_date` | str | ✅ | Date de début (`YYYY-MM-DD` ou `YYYY-MM-DDTHH:MM:SS`) |
| `end_date` | str | ✅ | Date de fin (`YYYY-MM-DD` ou `YYYY-MM-DDTHH:MM:SS`) |

**Output — créneau libre :**
```json
{
  "success": true,
  "conflicts": []
}
```

**Output — créneau occupé :**
```json
{
  "success": true,
  "conflicts": [
    {
      "id": "abc123xyz",
      "start": "2026-04-07T10:00:00+01:00",
      "end": "2026-04-07T11:00:00+01:00",
      "title": "Stand-up quotidien"
    }
  ]
}
```

> ⚠️ Le champ `id` est critique : il est utilisé par l'agent RH pour `reschedule_meeting`.

---

### 2. `get_calendar_events`
Liste tous les événements Google Calendar entre deux dates.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `start_date` | str | ✅ | Date de début |
| `end_date` | str | ✅ | Date de fin |

**Output :**
```json
{
  "success": true,
  "events": [
    {
      "id": "abc123xyz",
      "summary": "Réunion projet Alpha",
      "start": { "dateTime": "2026-04-07T09:00:00+01:00" },
      "end":   { "dateTime": "2026-04-07T10:00:00+01:00" },
      "htmlLink": "https://calendar.google.com/event?eid=..."
    }
  ]
}
```

---

### 3. `create_meeting`
Crée un événement dans Google Calendar.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `title` | str | ✅ | Titre de l'événement |
| `start_date` | str | ✅ | Date (`YYYY-MM-DD`) |
| `start_time` | str | ✅ | Heure de début (`HH:MM`) |
| `end_time` | str | ✅ | Heure de fin (`HH:MM`) |
| `attendees` | list[str] | ❌ | Liste d'emails des participants |
| `add_meet` | bool | ❌ (défaut: false) | Ajouter un lien Google Meet |

**Output :**
```json
{
  "success": true,
  "event": {
    "id": "event_id_google",
    "summary": "Réunion projet Alpha",
    "start": { "dateTime": "2026-04-07T09:00:00+01:00" },
    "end":   { "dateTime": "2026-04-07T10:00:00+01:00" },
    "htmlLink": "https://calendar.google.com/event?eid=...",
    "hangoutLink": "https://meet.google.com/xxx-yyyy-zzz"
  }
}
```

---

### 4. `update_meeting`
Modifie un événement existant (titre, date, heure, participants).

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `event_id` | str | ✅ | ID Google Calendar de l'événement |
| `title` | str | ❌ | Nouveau titre |
| `start_date` | str | ❌ | Nouvelle date (`YYYY-MM-DD`) |
| `start_time` | str | ❌ | Nouvelle heure de début (`HH:MM`) |
| `end_time` | str | ❌ | Nouvelle heure de fin (`HH:MM`) |
| `attendees` | list[str] | ❌ | **Liste complète** des emails (remplace l'existante) |

> **Important :** `attendees` est la liste **complète** — pas juste le delta.
> Pour ajouter quelqu'un, inclure les emails existants + le nouveau.

**Output :**
```json
{
  "success": true,
  "event": {
    "id": "event_id_google",
    "summary": "Nouveau titre",
    "start": { "dateTime": "2026-04-08T14:00:00+01:00" },
    "htmlLink": "https://calendar.google.com/event?eid=..."
  }
}
```

---

### 5. `delete_meeting`
Supprime un événement du calendrier.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `event_id` | str | ✅ | ID Google Calendar de l'événement |

**Output :**
```json
{
  "success": true,
  "message": "Event supprimé"
}
```

---

### 6. `search_meetings`
Recherche des événements par mot-clé. Essaie automatiquement les variantes accentuées.

**Input :**

| Paramètre | Type | Requis | Description |
|---|---|---|---|
| `query` | str | ✅ | Mot-clé à rechercher dans les titres |

**Output :**
```json
{
  "success": true,
  "results": [
    {
      "id": "abc123",
      "summary": "Déjeuner équipe",
      "start": { "dateTime": "2026-04-07T12:00:00+01:00" }
    }
  ]
}
```

---

## Source de données
**MCP Google Calendar** — API Google Calendar (OAuth2)
- Fuseau horaire : `Africa/Tunis` (UTC+1)
- Format dates : RFC 3339 (`YYYY-MM-DDTHH:MM:SS+01:00`)

---

## UI Hints (sélecteurs de date uniquement)

L'agent peut retourner un `ui_hint` pour afficher un composant de saisie de date dans le frontend :

| `ui_hint.type` | Condition de déclenchement | Composant affiché |
|---|---|---|
| `"event_datetime"` | L'agent demande date + heure début + heure fin | Sélecteur date + 2 champs heure |
| `"date_range"` | L'agent demande une plage de dates | Sélecteur début → fin |
| `"date_picker"` | L'agent demande une date simple | Calendrier simple |

> Les hints `"confirm"` (Oui/Non) et `"choice"` ont été supprimés pour éviter les faux
> positifs et les mauvais routages. L'utilisateur répond désormais en texte libre.

---

## Structure des fichiers

| Fichier | Contenu |
|---------|---------|
| `server.py` | Serveur FastAPI A2A : routes `/.well-known/agent.json` et `POST /` |
| `agent.py` | ReAct executor + failover Groq + extraction steps + détection `ui_hint` |
| `tools.py` | Implémentation des outils via MCP Google Calendar |
| `mcp_client.py` | Client MCP avec authentification OAuth2 Google |
| `schemas.py` | AgentCard A2A + modèles Pydantic |
| `prompts.py` | Prompt système : règles, workflows, règles absolues |

---

## Cas de test — du basique au complexe

> Envoyez ces messages via le chat. L'orchestrateur les route automatiquement vers l'agent Calendar.

---

### NIVEAU 1 — Consultation simple (1 outil)

#### T1.1 — Vérifier sa disponibilité sur un créneau
```
Suis-je disponible demain de 10h à 11h ?
```
**Steps ReAct attendus :**
1. `check_calendar_conflicts(start_date="2026-03-27", end_date="2026-03-27")`

**Réponse si créneau libre :**
```
Vous êtes disponible ✅ de 10h à 11h demain.
```

**Réponse si créneau occupé :**
```
Vous avez déjà : "Stand-up quotidien" de 10h00 à 10h30 ⚠️
```

---

#### T1.2 — Lister les événements de la semaine
```
Montre-moi mes événements cette semaine
```
**Steps ReAct attendus :**
1. `get_calendar_events(start_date="2026-03-23", end_date="2026-03-27")`

**Réponse attendue :** liste des événements avec titre, date et heure

**Variantes à tester :**
- `"Mon calendrier cette semaine"`
- `"Qu'est-ce que j'ai cette semaine ?"`
- `"Mes réunions d'aujourd'hui"`

---

#### T1.3 — Lister les événements de demain
```
Qu'est-ce que j'ai demain ?
```
**Steps ReAct attendus :**
1. `get_calendar_events(start_date="J+1", end_date="J+1")`

---

#### T1.4 — Rechercher une réunion par nom
```
Trouve la réunion "Sprint Review"
```
**Steps ReAct attendus :**
1. `search_meetings("Sprint Review")`
2. Si vide → `search_meetings("sprint review")` (variante sans accent)
3. Si toujours vide → `get_calendar_events` sur la période probable

**Comportement incorrect :**
- Répondre "introuvable" sans avoir essayé `get_calendar_events` → **bug**

---

### NIVEAU 2 — Création de réunion

#### T2.1 — Réunion simple (horaires complets fournis)
```
Crée une réunion "Point projet" demain à 14h jusqu'à 15h
```
**Steps ReAct attendus :**
1. `check_calendar_conflicts(start_date="J+1", end_date="J+1")`
2. Si `conflicts = []` → `create_meeting(title="Point projet", start_date="J+1", start_time="14:00", end_time="15:00")`

**Réponse attendue :**
```
Réunion créée ✅
📅 "Point projet" — 27 mars 2026 de 14h à 15h
🔗 Voir dans Google Calendar : https://...
```

> ⚠️ L'agent peut demander "Souhaitez-vous un lien Google Meet ?" si `add_meet` n'est pas précisé.

---

#### T2.2 — Réunion avec heure de fin manquante (sélecteur de date)
```
Crée une réunion "Démo" vendredi
```
**Comportement attendu :**
- L'agent demande les horaires → le **sélecteur `event_datetime`** s'affiche
- L'utilisateur sélectionne date + heure début + heure fin
- L'agent crée la réunion

---

#### T2.3 — Réunion avec Google Meet et participants
```
Organise une réunion "Sprint Review" vendredi de 9h à 10h avec alice@talan.com et bob@talan.com, avec un lien Meet
```
**Steps ReAct attendus :**
1. `check_calendar_conflicts(start_date="2026-03-27", end_date="2026-03-27")`
2. `create_meeting(title="Sprint Review", start_date="2026-03-27", start_time="09:00", end_time="10:00", attendees=["alice@talan.com", "bob@talan.com"], add_meet=true)`

**Réponse attendue :**
```
Réunion créée ✅
📅 "Sprint Review" — vendredi 27 mars de 9h à 10h
👥 Participants : alice@talan.com, bob@talan.com
🎥 Lien Meet : https://meet.google.com/...
```

---

#### T2.4 — Création bloquée par un conflit (règle absolue)
```
Crée une réunion "Test" demain de 10h à 11h
```
*(Un événement "Stand-up" existe déjà de 10h à 10h30)*

**Steps ReAct attendus :**
1. `check_calendar_conflicts` → 1 conflit détecté
2. **STOP ABSOLU** — `create_meeting` ne doit **jamais** être appelé

**Réponse attendue :**
```
Vous avez déjà "Stand-up quotidien" de 10h à 10h30 sur ce créneau ⚠️
Souhaitez-vous choisir une autre heure ?
```

**Comportements incorrects :**
- L'agent crée quand même → **bug critique**
- L'agent propose "Créer malgré le conflit ?" → **bug** (interdit par le prompt)

---

### NIVEAU 3 — Modification d'une réunion

#### T3.1 — Déplacer une réunion (heure)
```
Décale la réunion "Point projet" à 16h au lieu de 14h
```
**Steps ReAct attendus :**
1. `search_meetings("Point projet")` → récupère `event_id`
2. `update_meeting(event_id="...", start_time="16:00", end_time="17:00")`

**Comportement incorrect :**
- `delete_meeting` + `create_meeting` → **bug**, toujours utiliser `update_meeting`

---

#### T3.2 — Déplacer une réunion (date)
```
Reporte la réunion "Stand-up" de lundi à mardi
```
**Steps ReAct attendus :**
1. `search_meetings("Stand-up")`
2. `update_meeting(event_id="...", start_date="2026-03-24")`

---

#### T3.3 — Renommer un événement
```
Renomme la réunion "Point projet" en "Démo client"
```
**Steps ReAct attendus :**
1. `search_meetings("Point projet")`
2. `update_meeting(event_id="...", title="Démo client")`

---

#### T3.4 — Ajouter un participant
```
Ajoute carol@talan.com à la réunion "Sprint Review"
```
**Steps ReAct attendus :**
1. `search_meetings("Sprint Review")` → récupère `event_id` + attendees actuels : `["alice@talan.com", "bob@talan.com"]`
2. `update_meeting(event_id="...", attendees=["alice@talan.com", "bob@talan.com", "carol@talan.com"])`

> ⚠️ `attendees` = liste **complète** incluant les existants + le nouveau.
> Passer seulement `["carol@talan.com"]` supprimerait alice et bob → **bug**

---

#### T3.5 — Modifier via event_id fourni directement (appel depuis agent RH)
```
Déplace l'événement avec l'event_id 'abc123xyz' (titre : 'Stand-up') au 2026-04-09,
nouvelle heure de début : 2026-04-09T10:00:00+01:00, nouvelle heure de fin : 2026-04-09T10:30:00+01:00.
Utilise directement update_meeting avec cet event_id sans faire de recherche.
```
*(Ce message est envoyé par l'agent RH via A2A lors d'un reschedule)*

**Steps ReAct attendus :**
1. `update_meeting(event_id="abc123xyz", start_date="2026-04-09", start_time="10:00", end_time="10:30")`

> ⚠️ Pas de `search_meetings` ici — l'`event_id` est fourni directement, l'agent doit l'utiliser **immédiatement**.

---

### NIVEAU 4 — Suppression

#### T4.1 — Supprimer par nom
```
Supprime la réunion "Point projet" de demain
```
**Steps ReAct attendus :**
1. `search_meetings("Point projet")`
2. `delete_meeting(event_id="...")`

**Réponse attendue :**
```
Réunion supprimée ✅ "Point projet" — 27 mars 2026
```

---

#### T4.2 — Supprimer par date
```
Supprime tous mes événements de vendredi
```
**Steps ReAct attendus :**
1. `get_calendar_events(start_date="2026-03-27", end_date="2026-03-27")`
2. `delete_meeting(event_id="...")` pour chaque événement

---

### NIVEAU 5 — Recherche avancée et cas limites

#### T5.1 — Recherche avec accent
```
Trouve la réunion sur le déjeuner
```
**Steps ReAct attendus :**
1. `search_meetings("déjeuner")`
2. Si vide → `search_meetings("dejeuner")` (sans accent)

---

#### T5.2 — Réunion reçue via appel croisé depuis agent RH
*(Workflow automatique — pas initié par l'utilisateur directement)*

**Déclencheur :** l'utilisateur a demandé un congé à l'agent RH avec des réunions conflictuelles et a choisi de les déplacer.

**Message A2A reçu par Calendar :**
```
Date du jour : 2026-04-07
Déplace l'événement avec l'event_id 'abc123' (titre : 'Stand-up') au 2026-04-09,
nouvelle heure de début : 2026-04-09T10:00:00+01:00, nouvelle heure de fin : 2026-04-09T10:30:00+01:00.
Utilise directement update_meeting avec cet event_id sans faire de recherche.
```

**Steps ReAct attendus :**
1. `update_meeting(event_id="abc123", start_date="2026-04-09", start_time="10:00", end_time="10:30")`

**Comportement incorrect :**
- `search_meetings("Stand-up")` avant `update_meeting` → inutile et risqué si l'event n'est pas trouvable par titre → **anti-pattern**

---

#### T5.3 — Hors périmètre (rejet)
```
Crée-moi un congé pour la semaine prochaine
```
**Comportement attendu :**
- L'orchestrateur route vers l'agent **RH**, pas Calendar
- Si reçu par Calendar (erreur de routing) : réponse indiquant que ce n'est pas son domaine

---

#### T5.4 — RBAC — accès refusé
*(Envoyé avec un rôle sans permission `create_meeting`)*
```
Crée une réunion demain à 10h
```
**Comportement attendu :**
```json
{ "error": "Accès refusé.", "rbac_denied": true }
```

---

## Règles critiques du prompt

| Règle | Description |
|-------|-------------|
| **Conflit = STOP** | Jamais de `create_meeting` si `check_calendar_conflicts` retourne des conflits — règle absolue |
| **update, jamais delete+create** | Pour déplacer une réunion : `update_meeting` uniquement |
| **event_id fourni = pas de recherche** | Si l'`event_id` est dans le message → utiliser directement, sans `search_meetings` |
| **attendees = liste complète** | `update_meeting` remplace la liste entière, pas juste le delta |
| **Résolution des dates** | "demain", "vendredi prochain", "la semaine prochaine" → résolus via "Date du jour" fournie |
| **Fallback recherche** | Si `search_meetings` vide → essayer variante sans accent, puis `get_calendar_events` sur la date probable |
