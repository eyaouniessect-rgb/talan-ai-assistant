# Structure de la Base de Données — Talan Assistant

Base PostgreSQL organisée en **3 schémas** : `public`, `hris`, `crm`.

---

## Vue d'ensemble

```
public                    hris                          crm
──────────────────        ──────────────────────────    ──────────────────────
users                     departments                   clients
conversations             teams                         projects
messages                  employees                     assignments
permissions               leaves
                          leave_logs
                          skills
                          employee_skills
                          calendar_events
                          calendar_event_logs
```

---

## Schéma public

### `users`

Comptes d'authentification. Un utilisateur peut être consultant, PM ou RH.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | Identifiant |
| `name` | String | Nom complet |
| `email` | String UNIQUE | Email de connexion |
| `password` | String | Hash bcrypt |
| `role` | String | `consultant` \| `pm` \| `rh` |
| `is_active` | Boolean | Compte activé |
| `created_at` | DateTime | Date de création |

```sql
-- Exemple
INSERT INTO users (name, email, password, role)
VALUES ('Ahmed Ben Salah', 'ahmed.bensalah@talan.tn', '$2b$12$...', 'pm');
```

---

### `conversations`

Une conversation = une session de chat avec l'assistant.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → users.id | Propriétaire |
| `title` | String | Titre auto (40 premiers caractères du 1er message) |
| `created_at` | DateTime | |
| `updated_at` | DateTime | Mise à jour à chaque message |

---

### `messages`

Chaque échange dans une conversation (rôle `user` ou `assistant`).

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `conversation_id` | FK → conversations.id | |
| `role` | String | `user` \| `assistant` |
| `content` | Text | Contenu du message |
| `intent` | String | Agent ciblé (ex: `rh`, `calendar`) |
| `target_agent` | String | Idem — utilisé par le frontend pour l'affichage |
| `timestamp` | DateTime | |

```sql
-- Exemple d'historique
SELECT role, content, target_agent FROM messages
WHERE conversation_id = 1 ORDER BY timestamp;

-- role       | content                              | target_agent
-- user       | combien de jours de congé il me reste? | rh
-- assistant  | Il vous reste 18 jours de congé.     | rh
-- user       | crée une réunion demain à 10h         | calendar
-- assistant  | Réunion créée ✅ — Lien : https://...  | calendar
```

---

### `permissions`

Table RBAC — définit ce que chaque rôle peut faire (par nom d'outil agent).

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `role` | String | `consultant` \| `pm` \| `rh` |
| `action` | String | Nom de l'outil (ex: `create_leave`) |
| `allowed` | Boolean | Autorisé ou non |

```sql
-- Exemples
SELECT role, action, allowed FROM permissions ORDER BY role, action;

-- consultant | create_leave          | true
-- consultant | approve_leave         | false   ← réservé RH
-- pm         | get_all_leaves        | true    ← vision équipe
-- rh         | approve_leave         | true    ← exclusif RH
-- rh         | create_user_account   | true    ← exclusif RH
```

---

## Schéma hris

### `departments`

Les 7 départements de Talan Tunisie (valeurs enum).

| Colonne | Type | Valeurs possibles |
|---|---|---|
| `id` | PK | |
| `name` | Enum (String) | `innovation_factory` \| `salesforce` \| `data` \| `digital_factory` \| `testing` \| `cloud` \| `service_now` |

```sql
SELECT * FROM hris.departments;

-- id | name
--  1 | innovation_factory
--  2 | salesforce
--  3 | data
--  4 | digital_factory
--  5 | testing
--  6 | cloud
--  7 | service_now
```

---

### `teams`

Une équipe par département. La relation circulaire `Team ↔ Employee` est cassée
par `manager_id` nullable (on crée l'équipe sans manager, puis on met à jour).

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `name` | String | Nom de l'équipe |
| `department_id` | FK → departments.id | Département parent |
| `manager_id` | FK → employees.id (nullable) | Manager de l'équipe |

```sql
SELECT t.name, d.name as dept, u.name as manager
FROM hris.teams t
JOIN hris.departments d ON d.id = t.department_id
LEFT JOIN hris.employees e ON e.id = t.manager_id
LEFT JOIN users u ON u.id = e.user_id;

-- Innovation Factory | innovation_factory | Ahmed Ben Salah
-- Data & Analytics   | data               | Mohamed Gharbi
-- Testing            | testing            | Karim Mzoughi
```

---

### `employees`

Le profil RH d'un utilisateur. Relation 1-1 avec `users`.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `user_id` | FK → users.id | Lien vers le compte |
| `team_id` | FK → teams.id | Équipe d'appartenance |
| `manager_id` | FK → employees.id (nullable) | Manager hiérarchique direct |
| `job_title` | String | Intitulé du poste |
| `seniority` | Enum | `junior` \| `mid` \| `senior` \| `lead` \| `principal` |
| `hire_date` | Date | Date d'embauche |
| `leave_date` | Date (nullable) | Date de départ (NULL = encore en poste) |
| `leave_balance` | Integer | Jours de congé restants (défaut: 22) |
| `created_at` | DateTime | |

```sql
-- Profil complet d'un employé
SELECT u.name, u.role, e.job_title, e.seniority, e.hire_date, e.leave_balance,
       t.name as team, d.name as dept,
       m.name as manager
FROM hris.employees e
JOIN users u ON u.id = e.user_id
JOIN hris.teams t ON t.id = e.team_id
JOIN hris.departments d ON d.id = t.department_id
LEFT JOIN hris.employees me ON me.id = e.manager_id
LEFT JOIN users m ON m.id = me.user_id
WHERE u.email = 'yassine.cherif@talan.tn';

-- name            | role       | job_title           | seniority | hire_date   | leave_balance | team                 | dept               | manager
-- Yassine Cherif  | consultant | Full Stack Developer | senior    | 2021-02-01  | 22            | Innovation Factory   | innovation_factory | Ahmed Ben Salah
```

---

### `skills`

Référentiel des compétences techniques.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `name` | String UNIQUE | Nom de la compétence (ex: "React", "AWS") |

```sql
SELECT name FROM hris.skills ORDER BY name;
-- Airflow, Angular, Apex, AWS, Azure, Cypress, Docker, ...
```

---

### `employee_skills`

Table de liaison N-N entre employés et compétences, avec niveau.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `employee_id` | FK → employees.id | |
| `skill_id` | FK → skills.id | |
| `level` | Enum | `beginner` \| `intermediate` \| `advanced` \| `expert` |

```sql
-- Compétences d'un employé
SELECT s.name, es.level
FROM hris.employee_skills es
JOIN hris.skills s ON s.id = es.skill_id
JOIN hris.employees e ON e.id = es.employee_id
JOIN users u ON u.id = e.user_id
WHERE u.email = 'yassine.cherif@talan.tn';

-- name       | level
-- React      | advanced
-- Node.js    | advanced
-- PostgreSQL | advanced

-- Trouver tous les experts AWS
SELECT u.name, e.job_title, d.name as dept
FROM hris.employee_skills es
JOIN hris.skills s ON s.id = es.skill_id
JOIN hris.employees e ON e.id = es.employee_id
JOIN users u ON u.id = e.user_id
JOIN hris.teams t ON t.id = e.team_id
JOIN hris.departments d ON d.id = t.department_id
WHERE s.name = 'AWS' AND es.level IN ('advanced', 'expert');
```

---

### `leaves`

Demandes de congé avec type, statut et justificatif.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `employee_id` | FK → employees.id | Demandeur |
| `leave_type` | Enum | `annual` \| `maternity` \| `paternity` \| `bereavement` \| `unpaid` \| `sick` \| `other` |
| `start_date` | Date | |
| `end_date` | Date | |
| `days_count` | Integer | Nombre de jours ouvrés |
| `status` | Enum | `pending` \| `approved` \| `rejected` \| `cancelled` |
| `justification_url` | String (nullable) | URL de l'image justificatif (obligatoire pour certains types) |
| `created_at` | DateTime | |

```sql
-- Congés en attente d'approbation
SELECT u.name, l.leave_type, l.start_date, l.end_date, l.days_count, l.justification_url
FROM hris.leaves l
JOIN hris.employees e ON e.id = l.employee_id
JOIN users u ON u.id = e.user_id
WHERE l.status = 'pending'
ORDER BY l.created_at;

-- name            | leave_type | start_date  | end_date    | days_count | justification_url
-- Yassine Cherif  | annual     | 2026-04-07  | 2026-04-11  | 5          | NULL
-- Sarra Ben Fredj | maternity  | 2026-05-01  | 2026-07-30  | 65         | https://...

-- Solde restant pour un employé (déjà géré par leave_balance dans employees)
SELECT e.leave_balance
FROM hris.employees e JOIN users u ON u.id = e.user_id
WHERE u.email = 'yassine.cherif@talan.tn';
```

> **Types de congé** :
> - `annual` — congé annuel (justificatif non requis)
> - `maternity` / `paternity` — justificatif médical requis
> - `bereavement` — décès d'un proche (acte de décès)
> - `unpaid` — congé sans solde
> - `sick` — maladie (certificat médical)

---

### `leave_logs`

Audit trail de toutes les actions sur les congés.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `employee_id` | FK → employees.id | Employé concerné |
| `leave_id` | FK → leaves.id (nullable) | Congé concerné |
| `action` | String | `requested` \| `approved` \| `rejected` \| `cancelled` |
| `description` | Text | Message descriptif |
| `created_at` | DateTime | |

```sql
-- Historique complet d'un congé
SELECT ll.action, ll.description, ll.created_at
FROM hris.leave_logs ll
WHERE ll.leave_id = 7
ORDER BY ll.created_at;

-- requested | Demande de congé annuel du 07/04 au 11/04 (5 jours)  | 2026-03-30 09:15
-- approved  | Congé approuvé par le responsable RH                   | 2026-03-30 14:32
```

---

### `calendar_events`

Événements Google Calendar créés via le chat, synchronisés localement.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `employee_id` | FK → employees.id | Créateur |
| `google_event_id` | String (nullable) | ID Google Calendar |
| `title` | String | Titre de l'événement |
| `start_datetime` | DateTime | |
| `end_datetime` | DateTime | |
| `location` | String (nullable) | Lieu physique |
| `attendees` | Text (nullable) | Emails séparés par virgule |
| `meet_link` | String (nullable) | Lien Google Meet |
| `html_link` | String (nullable) | Lien vers Google Calendar |
| `created_at` | DateTime | |

---

### `calendar_event_logs`

Audit trail des actions calendrier (créé, modifié, supprimé).

| Colonne | Type | Description |
|---|---|---|
| `action` | String | `created` \| `updated` \| `updated_schedule` \| `deleted` |
| `description` | Text | Détail de l'action |

---

## Schéma crm

### `clients`

Clients de Talan pour lesquels des projets sont réalisés.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `name` | String | Nom du client |
| `industry` | String | Secteur (Finance, Telecom...) |
| `contact_email` | String | Email du contact client |

---

### `projects`

Projets réalisés pour les clients.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `name` | String | Nom du projet |
| `client_id` | FK → clients.id | |
| `status` | String | `En cours` \| `Terminé` \| `En attente` |
| `progress` | Float | Avancement 0.0 → 100.0 |
| `start_date` | Date (nullable) | Début du projet |
| `end_date` | Date (nullable) | Fin prévue / deadline |
| `created_at` | DateTime | |

---

### `assignments`

Participation d'un employé à un projet (remplace `project_members`).

> **Règle métier** : la somme des `allocation_percent` actifs d'un même employé doit être ≤ 100%.
> Cette contrainte est vérifiée côté application.

| Colonne | Type | Description |
|---|---|---|
| `id` | PK | |
| `project_id` | FK → projects.id | |
| `employee_id` | FK → employees.id | |
| `role_in_project` | String | Ex: `Lead Dev`, `DevOps`, `UX Designer` |
| `allocation_percent` | Integer | % du temps alloué (défaut: 100) |
| `start_date` | Date (nullable) | Début de la mission |
| `end_date` | Date (nullable) | Fin de la mission (NULL = encore affecté) |
| `joined_at` | DateTime | Date d'enregistrement |

```sql
-- Charge d'un employé sur les projets actifs
SELECT p.name as projet, a.role_in_project, a.allocation_percent, a.start_date, a.end_date
FROM crm.assignments a
JOIN crm.projects p ON p.id = a.project_id
JOIN hris.employees e ON e.id = a.employee_id
JOIN users u ON u.id = e.user_id
WHERE u.email = 'yassine.cherif@talan.tn'
  AND a.end_date IS NULL   -- missions en cours
ORDER BY a.start_date;

-- projet          | role_in_project | allocation_percent | start_date  | end_date
-- Projet Alpha    | Lead Dev        | 70                 | 2026-01-15  | NULL
-- Projet Omega    | Tech Reviewer   | 30                 | 2026-03-01  | NULL
-- Total : 100% ✅

-- Tous les membres d'un projet
SELECT u.name, e.job_title, e.seniority, a.role_in_project, a.allocation_percent
FROM crm.assignments a
JOIN hris.employees e ON e.id = a.employee_id
JOIN users u ON u.id = e.user_id
WHERE a.project_id = 3
  AND a.end_date IS NULL
ORDER BY a.allocation_percent DESC;
```

---

## Diagramme des relations

```
users (1) ────────────── (1) employees
                               │
employees (*) ──────── (1) teams (*) ──────── (1) departments
employees (*) ──────── (1) employees    [manager hiérarchique]
teams (1) ──────────── (1) employees    [manager d'équipe]

employees (1) ──────── (*) leaves
employees (1) ──────── (*) leave_logs
employees (1) ──────── (*) calendar_events
employees (1) ──────── (*) employee_skills (*) ──── (1) skills

employees (*) ──────── (*) projects    [via assignments]
projects (*) ────────── (1) clients

users (1) ──────────── (*) conversations (1) ──── (*) messages
```

---

## Commandes utiles

```bash
# Appliquer toutes les migrations
alembic upgrade head

# Vérifier l'état des migrations
alembic current

# Remplir les permissions (rôles consultant / pm / rh)
python scripts/seed_permissions.py

# Remplir la base avec 50 employés Talan Tunisie
python scripts/seed_employees.py
```
