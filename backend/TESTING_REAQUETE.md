# Testing Reaquete

Ce document contient les test cases de validation des flux RH et Calendar.
Chaque test inclut:

- Requete utilisateur
- Flux attendu
- Expected output

## Preconditions

- Agent RH demarre
- Agent Calendar demarre
- MCP Google Calendar actif
- Utilisateur authentifie avec role autorise (`consultant` ou `pm`)
- Donnees de test disponibles (conges + evenements)

---

## RH Agent - Test Cases

### RH-T1 - Verifier solde de conges

**Requete**

```
Combien de jours de conge il me reste ?
```

**Flux attendu**

1. `check_leave_balance(user_id=X, requested_days=0)`

**Expected output**

- Affiche `solde_total`, `jours_pending`, `solde_effectif`
- Message clair sur le nombre de jours restants

---

### RH-T2 - Lister tous mes conges

**Requete**

```
Montre-moi tous mes conges
```

**Flux attendu**

1. `get_my_leaves(user_id=X)`

**Expected output**

- Liste complete des conges (pending, approved, rejected)

---

### RH-T3 - Lister conges en attente

**Requete**

```
Montre-moi mes conges en attente d'approbation
```

**Flux attendu**

1. `get_my_leaves(user_id=X, status_filter="pending")`

**Expected output**

- Retourne uniquement les conges `pending`

---

### RH-T4 - Disponibilite equipe

**Requete**

```
Qui est disponible aujourd'hui dans mon equipe ?
```

**Flux attendu**

1. `get_team_availability(user_id=X)`

**Expected output**

- Liste des membres de l'equipe avec statut disponible/en conge
- L'utilisateur courant n'apparait pas

---

### RH-T5 - Stack technique equipe

**Requete**

```
Quelles sont les competences de mon equipe ?
```

**Flux attendu**

1. `get_team_stack(user_id=X)`

**Expected output**

- Liste des membres avec leurs competences techniques

---

### RH-T6 - Creer conge (dates explicites)

**Requete**

```
Je veux poser un conge du 7 au 10 avril
```

**Flux attendu**

1. `check_leave_balance(user_id=X, requested_days=4)`
2. `check_calendar_conflicts(user_id=X, start_date="2026-04-07", end_date="2026-04-10")`
3. `create_leave(user_id=X, start_date="2026-04-07", end_date="2026-04-10")`
4. `notify_manager(user_id=X, message="...")`

**Expected output**

- Conge cree (`status: pending`)
- Solde restant affiche
- Confirmation de notification manager

---

### RH-T7 - Conge date relative

**Requete**

```
Je serai absent demain
```

**Flux attendu**

1. Resolution automatique de la date (J+1)
2. `check_leave_balance` -> `check_calendar_conflicts` -> `create_leave` -> `notify_manager`

**Expected output**

- Conge cree sur un seul jour
- Pas de demande de format `YYYY-MM-DD`

---

### RH-T8 - Solde insuffisant (STOP)

**Requete**

```
Je veux poser 30 jours de conge a partir de demain
```

**Flux attendu**

1. `check_leave_balance(user_id=X, requested_days=30)` -> `can_create: false`
2. STOP

**Expected output**

- Message de refus pour solde insuffisant
- Aucun `create_leave`

---

### RH-T9 - Chevauchement conge

**Requete**

```
Je veux creer un conge du 1 au 5 avril
```

**Flux attendu**

1. `check_leave_balance` -> OK
2. `check_calendar_conflicts` -> OK/NA
3. `create_leave` -> `error: overlap`

**Expected output**

- Refus avec details de la periode qui chevauche

---

### RH-T10 - Conflits calendar + option 1

**Tour 1**

```
Je veux un conge du 7 au 9 avril
```

**Tour 2**

```
1
```

**Flux attendu**

1. `check_leave_balance`
2. `check_calendar_conflicts` -> conflits detectes
3. Proposition options (1/2/3)
4. Si `1`: `create_leave` + `notify_manager`

**Expected output**

- Conge cree malgre conflits
- Solde restant + manager notifie

---

### RH-T11 - Conflits calendar + option 3 (annulation)

**Tour 1**

```
Je veux un conge du 7 au 9 avril
```

**Tour 2**

```
3
```

**Flux attendu**

- Annulation immediate
- Aucun outil de creation execute apres

**Expected output**

- Message: demande annulee, aucun changement

---

### RH-T12 - Workflow croise RH -> Calendar (reschedule)

**Tour 1**

```
Je veux prendre conge du 7 au 8 avril
```

**Tour 2**

```
2
```

**Tour 3**

```
Le 9 avril
```

**Flux attendu**

1. `check_leave_balance`
2. `check_calendar_conflicts` -> 1+ conflit
3. `reschedule_meeting(...)` via agent Calendar
4. `create_leave(...)`
5. `notify_manager(...)`

**Expected output**

- Reunion deplacee
- Conge cree
- Solde restant + manager notifie

---

## Calendar Agent - Test Cases

### CAL-T1 - Verifier disponibilite

**Requete**

```
Suis-je disponible demain de 10h a 11h ?
```

**Flux attendu**

1. `check_calendar_conflicts(start_date=..., end_date=...)`

**Expected output**

- Si libre: confirmation de disponibilite
- Si occupe: liste des conflits (titre + horaire)

---

### CAL-T2 - Lister evenements semaine

**Requete**

```
Montre-moi mes evenements cette semaine
```

**Flux attendu**

1. `get_calendar_events(start_date=..., end_date=...)`

**Expected output**

- Liste des evenements avec date/heure

---

### CAL-T3 - Recherche par titre

**Requete**

```
Trouve la reunion Sprint Review
```

**Flux attendu**

1. `search_meetings("Sprint Review")`
2. Fallback si vide (variante query puis periode probable)

**Expected output**

- Evenement trouve ou message explicite si introuvable

---

### CAL-T4 - Creer reunion simple

**Requete**

```
Cree une reunion Point projet demain a 14h jusqu'a 15h
```

**Flux attendu**

1. `check_calendar_conflicts(...)`
2. Si libre: `create_meeting(...)`

**Expected output**

- Reunion creee
- Lien Google Calendar retourne

---

### CAL-T5 - Creer reunion + participants + Meet

**Requete**

```
Organise une reunion Sprint Review vendredi de 9h a 10h avec alice@talan.com et bob@talan.com, avec un lien Meet
```

**Flux attendu**

1. `check_calendar_conflicts(...)`
2. `create_meeting(..., attendees=[...], add_meet=true)`

**Expected output**

- Reunion creee
- Participants confirmes
- Lien Meet present

---

### CAL-T6 - Conflit = STOP absolu

**Requete**

```
Cree une reunion Test demain de 10h a 11h
```

**Flux attendu**

1. `check_calendar_conflicts(...)` -> conflit detecte
2. STOP (pas de `create_meeting`)

**Expected output**

- Message de conflit
- Proposition de choisir un autre horaire

---

### CAL-T7 - Deplacer reunion (update)

**Requete**

```
Decale la reunion Point projet a 16h au lieu de 14h
```

**Flux attendu**

1. `search_meetings("Point projet")`
2. `update_meeting(event_id="...", start_time="16:00", end_time="17:00")`

**Expected output**

- Reunion mise a jour
- Jamais `delete_meeting` + `create_meeting`

---

### CAL-T8 - Renommer reunion

**Requete**

```
Renomme la reunion Point projet en Demo client
```

**Flux attendu**

1. `search_meetings("Point projet")`
2. `update_meeting(event_id="...", title="Demo client")`

**Expected output**

- Nouveau titre confirme

---

### CAL-T9 - Ajouter participant (liste complete)

**Requete**

```
Ajoute carol@talan.com a la reunion Sprint Review
```

**Flux attendu**

1. `search_meetings("Sprint Review")`
2. `update_meeting(event_id="...", attendees=[existants + carol])`

**Expected output**

- Carol ajoutee sans supprimer les participants existants

---

### CAL-T10 - Supprimer reunion

**Requete**

```
Supprime la reunion Point projet de demain
```

**Flux attendu**

1. `search_meetings("Point projet")`
2. `delete_meeting(event_id="...")`

**Expected output**

- Confirmation de suppression

---

### CAL-T11 - Recherche accent/sans accent

**Requete**

```
Trouve la reunion sur le dejeuner
```

**Flux attendu**

1. `search_meetings("dejeuner")`
2. Variante accentuee/non accentuee selon besoin

**Expected output**

- Resultat retrouve si evenement existe

---

### CAL-T12 - RBAC deny

**Requete**

```
Cree une reunion demain a 10h
```

_(avec role non autorise)_

**Expected output**

```json
{ "error": "Acces refuse.", "rbac_denied": true }
```

---

## Smoke Test Rapide (5 checks)

1. RH: `Combien de jours de conge il me reste ?`
2. Calendar: `Qu'est-ce que j'ai demain ?`
3. RH: `Je veux un conge du 7 au 8 avril`
4. Si conflits: repondre `2` puis `Le 9 avril`
5. Verifier que la reunion est deplacee puis conge cree
