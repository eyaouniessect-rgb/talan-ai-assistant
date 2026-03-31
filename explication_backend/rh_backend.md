# Module RH — Backend : Documentation Complète

> Ce document couvre l'ensemble des fonctionnalités RH côté backend : les modèles de base de données, les endpoints API, la logique métier et les décisions techniques.

---

## Vue d'ensemble du module RH

Le module RH permet à un utilisateur avec le rôle `rh` de :
1. **Créer des comptes utilisateurs** (User + Employee + Skills en une seule opération atomique)
2. **Lister les utilisateurs** existants
3. **Explorer l'organisation** (départements → équipes → employés → compétences)
4. **Gérer les demandes de congé** (approuver / rejeter avec traçabilité)
5. **Consulter les compétences** disponibles

---

## Architecture de la base de données

### Schémas PostgreSQL

Le projet utilise **3 schémas** pour séparer les données :

```
PostgreSQL
├── public                    # Tables générales
│   ├── users                 # Comptes de connexion
│   ├── conversations         # Historique des conversations chat
│   ├── messages              # Messages individuels
│   └── checkpoints           # Mémoire LangGraph (checkpoint)
│
├── hris                      # Human Resources Information System
│   ├── departments           # Départements Talan Tunisie
│   ├── teams                 # Équipes (liées à un département)
│   ├── employees             # Profils employés (liés à un user)
│   ├── skills                # Catalogue de compétences
│   ├── employee_skills       # Compétences d'un employé (N-N)
│   ├── leaves                # Demandes de congé
│   ├── leave_logs            # Historique des actions congé
│   ├── calendar_events       # Événements Google Calendar
│   └── calendar_event_logs   # Historique des actions calendrier
│
└── crm                       # Customer Relationship Management
    ├── projects              # Projets Talan
    └── assignments           # Affectation d'employés à des projets
```

### Diagramme des relations HRIS

```
users (public)
  │
  │ 1─────1
  ▼
employees (hris)
  │ manager_id (auto-référence)
  ├──────────────────────────────┐
  │                              │
  │ team_id                      ▼ manager (même table)
  │
  ▼
teams (hris)
  │ manager_id → employees.id
  │ department_id
  ▼
departments (hris)

employees ──────── employee_skills ──────── skills
           N              N─N              1
           │
           ├── leaves
           ├── leave_logs
           ├── calendar_events
           └── calendar_event_logs
```

---

## Fichier 1 : Modèles SQLAlchemy

**Fichier :** `backend/app/database/models/hris.py`

### Table `users` (public schema)

**Fichier :** `backend/app/database/models/user.py`

```python
class User(Base):
    __tablename__ = "users"    # pas de schéma = schéma "public"

    id         = Column(Integer, primary_key=True)
    name       = Column(String, nullable=False)
    email      = Column(String, unique=True, nullable=False)
    password   = Column(String, nullable=False)   # hashé avec bcrypt
    role       = Column(String, default="consultant")  # consultant | pm | rh
    is_active  = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="user", uselist=False)
```

Un `User` = un compte de connexion. Il a une relation 1-1 avec `Employee`.

### Table `departments`

```python
class DepartmentEnum(str, enum.Enum):
    INNOVATION_FACTORY = "innovation_factory"
    SALESFORCE         = "salesforce"
    DATA               = "data"
    DIGITAL_FACTORY    = "digital_factory"
    TESTING            = "testing"
    CLOUD              = "cloud"
    SERVICE_NOW        = "service_now"

class Department(Base):
    __tablename__ = "departments"
    __table_args__ = {"schema": "hris"}

    id   = Column(Integer, primary_key=True)
    name = Column(SAEnum(DepartmentEnum, ...), unique=True, nullable=False)

    teams = relationship("Team", back_populates="department")
```

### Table `teams`

```python
class Team(Base):
    __tablename__ = "teams"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    name          = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey("hris.departments.id"))
    manager_id    = Column(
        Integer,
        ForeignKey("hris.employees.id", use_alter=True, name="fk_team_manager_id"),
        # use_alter=True : résout la dépendance circulaire
        # Team.manager_id → Employee.id
        # Employee.team_id → Team.id
    )

    department = relationship("Department", back_populates="teams")
    employees  = relationship("Employee", back_populates="team",
                              foreign_keys="[Employee.team_id]")
    manager    = relationship("Employee", foreign_keys=[manager_id], uselist=False)
```

**Dépendance circulaire Team ↔ Employee :**
- `Team.manager_id` pointe vers un `Employee`
- `Employee.team_id` pointe vers une `Team`

SQLAlchemy résout cela avec `use_alter=True` : la FK `manager_id` est créée APRÈS les deux tables, comme une contrainte ALTER TABLE.

### Table `employees`

```python
class Employee(Base):
    __tablename__ = "employees"
    __table_args__ = {"schema": "hris"}

    id            = Column(Integer, primary_key=True)
    user_id       = Column(Integer, ForeignKey("users.id"), nullable=False)
    team_id       = Column(Integer, ForeignKey("hris.teams.id"), nullable=False)
    manager_id    = Column(Integer, ForeignKey("hris.employees.id"), nullable=True)
    job_title     = Column(String, nullable=True)
    seniority     = Column(SAEnum(SeniorityEnum, ...), nullable=True)
    hire_date     = Column(Date, nullable=True)
    leave_date    = Column(Date, nullable=True)   # date de départ (NULL = en poste)
    leave_balance = Column(Integer, default=22)   # jours de congé restants
    created_at    = Column(DateTime, server_default=func.now())

    user  = relationship("User", back_populates="employee")
    team  = relationship("Team", back_populates="employees", foreign_keys=[team_id])

    # Auto-référence : un employé peut être le manager d'un autre employé
    manager = relationship(
        "Employee",
        foreign_keys="[Employee.manager_id]",
        primaryjoin="Employee.manager_id == Employee.id",
        uselist=False,   # un seul manager (pas une liste)
    )

    employee_skills     = relationship("EmployeeSkill", back_populates="employee",
                                       cascade="all, delete-orphan")
    leaves              = relationship("Leave", ...)
    leave_logs          = relationship("LeaveLog", ...)
    calendar_events     = relationship("CalendarEvent", ...)
    calendar_event_logs = relationship("CalendarEventLog", ...)
```

**Auto-référence (self-referential relationship) :**
Un `Employee` peut avoir un autre `Employee` comme manager. SQLAlchemy a besoin de `primaryjoin` explicite pour lever l'ambiguïté entre :
- `Employee.manager_id` → FK vers `Employee.id` (le manager de cet employé)
- Et tous les autres employés

### Tables `skills` et `employee_skills`

```python
class Skill(Base):
    __tablename__ = "skills"
    __table_args__ = {"schema": "hris"}

    id   = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)  # "Python", "React", "AWS"

    employee_skills = relationship("EmployeeSkill", back_populates="skill",
                                   cascade="all, delete-orphan")

class SkillLevelEnum(str, enum.Enum):
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    EXPERT       = "expert"

class EmployeeSkill(Base):
    __tablename__ = "employee_skills"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"), nullable=False)
    skill_id    = Column(Integer, ForeignKey("hris.skills.id"),    nullable=False)
    level       = Column(SAEnum(SkillLevelEnum, ...), nullable=True)

    employee = relationship("Employee", back_populates="employee_skills")
    skill    = relationship("Skill",    back_populates="employee_skills")
```

**Relation N-N :** Un employé peut avoir plusieurs compétences, une compétence peut être maîtrisée par plusieurs employés. La table `employee_skills` est la **table de jonction** avec l'attribut supplémentaire `level`.

### Tables `leaves` et `leave_logs`

```python
class LeaveTypeEnum(str, enum.Enum):
    ANNUAL = "annual"       # Congé annuel
    MATERNITY = "maternity" # Maternité
    PATERNITY = "paternity" # Paternité
    BEREAVEMENT = "bereavement" # Décès
    UNPAID = "unpaid"       # Sans solde
    SICK = "sick"           # Maladie
    OTHER = "other"

class LeaveStatusEnum(str, enum.Enum):
    PENDING   = "pending"    # En attente d'approbation
    APPROVED  = "approved"   # Approuvé par RH
    REJECTED  = "rejected"   # Rejeté par RH
    CANCELLED = "cancelled"  # Annulé par l'employé

class Leave(Base):
    __tablename__ = "leaves"
    __table_args__ = {"schema": "hris"}

    id                = Column(Integer, primary_key=True)
    employee_id       = Column(Integer, ForeignKey("hris.employees.id"))
    leave_type        = Column(SAEnum(LeaveTypeEnum, ...), default=LeaveTypeEnum.ANNUAL)
    start_date        = Column(Date, nullable=False)
    end_date          = Column(Date, nullable=False)
    days_count        = Column(Integer)                   # calculé par l'agent
    status            = Column(SAEnum(LeaveStatusEnum, ...), default=LeaveStatusEnum.PENDING)
    justification_url = Column(String, nullable=True)    # URL vers justificatif
    created_at        = Column(DateTime, server_default=func.now())

    employee = relationship("Employee", back_populates="leaves")
    logs     = relationship("LeaveLog", back_populates="leave", cascade="all, delete-orphan")

class LeaveLog(Base):
    __tablename__ = "leave_logs"
    __table_args__ = {"schema": "hris"}

    id          = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("hris.employees.id"))
    leave_id    = Column(Integer, ForeignKey("hris.leaves.id"), nullable=True)
    action      = Column(String)      # "requested" | "approved" | "rejected" | "cancelled"
    description = Column(Text)        # Détail de l'action
    created_at  = Column(DateTime, server_default=func.now())
```

---

## Fichier 2 : API RH

**Fichier :** `backend/app/api/rh.py`
**Préfixe :** `/rh`
**Enregistrement :** `backend/app/main.py` → `app.include_router(rh_router)`

### Sécurité — Dépendance `require_rh`

```python
async def require_rh(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "rh":
        raise HTTPException(status_code=403, detail="Accès réservé au rôle RH")
    return current_user
```

Tous les endpoints RH ont `Depends(require_rh)`. Si l'utilisateur n'est pas RH :
- HTTP 403 Forbidden
- Message : "Accès réservé au rôle RH"

---

### Endpoint 1 : `POST /rh/users` — Créer un compte + profil employé

**Input (Pydantic) :**
```python
class SkillInput(BaseModel):
    name:  str
    level: str = "intermediate"   # beginner | intermediate | advanced | expert

class CreateUserRequest(BaseModel):
    name:      str       # "Mohamed Ben Ali"
    email:     EmailStr  # "m.benali@talan.tn"
    role:      str       # "consultant" | "pm" | "rh"
    team_id:   int       # ID de l'équipe choisie
    job_title: Optional[str]   # "Développeur Full Stack"
    seniority: Optional[str]   # "junior" | "mid" | "senior" | "lead" | "principal"
    hire_date: Optional[str]   # "2026-03-31" (ISO date, défaut = aujourd'hui)
    skills:    List[SkillInput] = []
```

**Logique en 5 étapes (dans une seule transaction) :**

```python
# 1. Validation
if body.role not in ("consultant", "pm", "rh"):
    raise HTTPException(400, "Rôle invalide")

existing = await db.execute(select(User).where(User.email == body.email))
if existing.scalar_one_or_none():
    raise HTTPException(409, "Email déjà utilisé")

team = await db.execute(select(Team).where(Team.id == body.team_id))
if not team:
    raise HTTPException(404, "Équipe introuvable")

# 2. Créer le User
password = _generate_password()  # 12 chars aléatoires
user = User(name=..., email=..., password=hash_password(password), role=..., is_active=True)
db.add(user)
await db.flush()   # ← génère user.id SANS committer
                   # Nécessaire car on en a besoin pour Employee.user_id

# 3. Créer l'Employee
hire_date = datetime.date.fromisoformat(body.hire_date) if body.hire_date \
            else datetime.date.today()   # défaut = aujourd'hui

employee = Employee(
    user_id    = user.id,
    team_id    = body.team_id,
    manager_id = team.manager_id,   # ← déduit automatiquement du team
    job_title  = body.job_title,
    seniority  = SeniorityEnum(body.seniority) if body.seniority else None,
    hire_date  = hire_date,
    leave_balance = 22,   # solde initial standard
)
db.add(employee)
await db.flush()   # génère employee.id

# 4. Créer les Skills
for skill_input in body.skills:
    # Cherche si la skill existe déjà dans la table skills
    skill = await db.execute(select(Skill).where(Skill.name == skill_name))
    if not skill:
        skill = Skill(name=skill_name)   # crée une nouvelle skill globale
        db.add(skill)
        await db.flush()

    # Associe la skill à l'employé avec son niveau
    db.add(EmployeeSkill(
        employee_id = employee.id,
        skill_id    = skill.id,
        level       = SkillLevelEnum(level),
    ))

# 5. Commit global (tout ou rien)
await db.commit()

# 6. Envoie les identifiants par email
send_credentials_email(to_email=body.email, name=body.name, password=password)
```

**Output :**
```json
{
    "id": 57,
    "name": "Mohamed Ben Ali",
    "email": "m.benali@talan.tn",
    "role": "consultant",
    "is_active": true,
    "employee_id": 51,
    "created_at": "2026-03-31T10:00:00"
}
```

**Pourquoi `flush` et pas `commit` ?**
`flush` envoie le SQL à la DB et génère les IDs, mais ne valide pas la transaction. Si une étape suivante échoue (ex: email invalide), le `rollback` annule tout. C'est **atomique** : soit tout réussit, soit rien n'est créé.

---

### Endpoint 2 : `GET /rh/users` — Lister les utilisateurs

```python
result = await db.execute(select(User).order_by(User.name))
```

**Output :** Liste de `UserOut` (id, name, email, role, is_active, created_at)

---

### Endpoint 3 : `GET /rh/departments` — Lister les départements

```python
result = await db.execute(
    select(Department).options(selectinload(Department.teams))
)
```

**`selectinload`** : charge les relations en une requête SQL séparée pour éviter le problème N+1 (faire 1 requête + 1 par département au lieu de N+1).

**Output :**
```json
[
    {"id": 1, "name": "innovation_factory", "team_count": 3},
    {"id": 2, "name": "data",               "team_count": 2}
]
```

---

### Endpoint 4 : `GET /rh/teams` — Lister les équipes avec manager

```python
result = await db.execute(
    select(Team)
    .options(
        selectinload(Team.department),
        selectinload(Team.manager).selectinload(Employee.user),
        #            ↑ charge Team.manager (Employee)
        #                                  ↑ puis charge Employee.user
        #            Deux niveaux de eager loading chaîné
    )
)

for t in teams:
    manager_name = t.manager.user.name if t.manager and t.manager.user else None
```

**Output :**
```json
[
    {
        "id": 1,
        "name": "Team Innovation A",
        "department": "innovation_factory",
        "manager_name": "Yassine Cherif"
    }
]
```

---

### Endpoint 5 : `GET /rh/employees` — Lister les employés avec skills

```python
result = await db.execute(
    select(Employee)
    .options(
        selectinload(Employee.user),
        selectinload(Employee.team).selectinload(Team.department),
        selectinload(Employee.manager).selectinload(Employee.user),
        selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
    )
)
```

4 niveaux de relations chargées en eager loading. Chaque `selectinload` génère une requête SQL dédiée (efficace car une seule par relation, pas une par employé).

**Output :**
```json
[
    {
        "id": 1,
        "user_id": 12,
        "name": "Yassine Cherif",
        "email": "y.cherif@talan.tn",
        "role": "consultant",
        "job_title": "Développeur Backend",
        "seniority": "senior",
        "hire_date": "2023-01-15",
        "leave_balance": 18,
        "team": "Team Innovation A",
        "department": "innovation_factory",
        "manager": "Ahmed Bensalah",
        "skills": [
            {"name": "Python", "level": "expert"},
            {"name": "FastAPI", "level": "advanced"}
        ]
    }
]
```

---

### Endpoint 6 : `GET /rh/skills` — Lister les compétences disponibles

```python
result = await db.execute(select(Skill).order_by(Skill.name))
```

**But :** Permet au frontend (SkillsPicker) d'afficher toutes les compétences existantes pour que le RH puisse les sélectionner sans les retaper.

**Output :**
```json
[
    {"id": 1, "name": "AWS"},
    {"id": 2, "name": "Angular"},
    {"id": 3, "name": "FastAPI"},
    {"id": 4, "name": "Python"}
]
```

---

### Endpoint 7 : `GET /rh/leaves` — Demandes de congé

```python
query = (
    select(Leave)
    .options(
        selectinload(Leave.employee).selectinload(Employee.user),
        selectinload(Leave.employee).selectinload(Employee.team),
    )
    .order_by(Leave.created_at.desc())
)
if status:   # filtre optionnel : ?status=pending
    query = query.where(Leave.status == status)
```

**Output :**
```json
[
    {
        "id": 47,
        "employee_id": 1,
        "employee_name": "Yassine Cherif",
        "employee_email": "y.cherif@talan.tn",
        "team": "Team Innovation A",
        "leave_type": "annual",
        "start_date": "2026-04-06",
        "end_date": "2026-04-10",
        "days_count": 5,
        "status": "pending",
        "justification_url": null,
        "created_at": "2026-03-31T09:00:00"
    }
]
```

---

### Endpoint 8 : `POST /rh/leaves/{leave_id}/approve`

```python
leave.status = LeaveStatusEnum.APPROVED
db.add(LeaveLog(
    employee_id = leave.employee_id,
    leave_id    = leave.id,
    action      = "approved",
    description = "Congé approuvé par le responsable RH",
))
await db.commit()
```

**Vérifications :**
- Le congé doit exister (404 sinon)
- Le statut doit être `PENDING` (400 sinon — ne peut pas approuver un congé déjà traité)

**Output :** `{"success": true, "status": "approved"}`

---

### Endpoint 9 : `POST /rh/leaves/{leave_id}/reject`

```python
class RejectBody(BaseModel):
    reason: Optional[str] = None

leave.status = LeaveStatusEnum.REJECTED
db.add(LeaveLog(
    ...
    action      = "rejected",
    description = f"Congé rejeté : {reason}",
))
```

**Output :** `{"success": true, "status": "rejected"}`

---

## Fichier 3 : Envoi d'email

**Fichier :** `backend/utils/email.py`

```python
EMAIL_HOST      = os.getenv("EMAIL_HOST")      # ex: smtp.gmail.com
EMAIL_PORT      = int(os.getenv("EMAIL_PORT")) # ex: 587
EMAIL_USER      = os.getenv("EMAIL_USER")      # compte expéditeur
EMAIL_PASSWORD  = os.getenv("EMAIL_PASSWORD")  # mot de passe SMTP
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME") # "Talan Assistant"
EMAIL_DEV_MODE  = os.getenv("EMAIL_DEV_MODE", "false").lower() == "true"
```

**Mode DEV (`EMAIL_DEV_MODE=true`) :** L'email est affiché dans le terminal au lieu d'être envoyé. Utile en développement pour voir les identifiants sans configurer un serveur SMTP.

**Aucune valeur par défaut** dans le code : si une variable est manquante, une erreur explicite est levée.

```python
def send_credentials_email(to_email, name, password):
    if EMAIL_DEV_MODE:
        print(f"[EMAIL DEV] To: {to_email} | Password: {password}")
        return

    msg = MIMEMultipart()
    msg["From"]    = f"{EMAIL_FROM_NAME} <{EMAIL_USER}>"
    msg["To"]      = to_email
    msg["Subject"] = "Vos identifiants Talan Assistant"
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASSWORD)
        server.send_message(msg)
```

---

## Registre des routes — `main.py`

**Fichier :** `backend/app/main.py`

```python
from app.api.rh import router as rh_router
app.include_router(rh_router)   # toutes les routes /rh/*
```

---

## Variables d'environnement requises (`.env`)

```env
# Base de données
POSTGRES_USER=postgres
POSTGRES_PASSWORD=password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=talan_assistant

# Email
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USER=no-reply@talan.tn
EMAIL_PASSWORD=xxx
EMAIL_FROM_NAME=Talan Assistant
EMAIL_DEV_MODE=true   # true en dev, false en prod

# Sécurité
JWT_SECRET=votre_secret_jwt
A2A_SECRET_TOKEN=votre_secret_a2a

# LLM (Groq)
GROQ_API_KEY_1=gsk_xxx
GROQ_API_KEY_2=gsk_yyy    # optionnel, pour le failover

# LangSmith (observabilité)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_PROJECT=talan-assistant
LANGCHAIN_API_KEY=lsv2_pt_xxx
```

---

## Sécurité RBAC (Role-Based Access Control)

Le contrôle d'accès est à deux niveaux :

### Niveau API (FastAPI)
```python
async def require_rh(current_user = Depends(get_current_user)):
    if current_user["role"] != "rh":
        raise HTTPException(403, "Accès réservé au rôle RH")
```
Tous les endpoints `/rh/*` vérifient ce guard.

### Niveau Agent (outils SQL)
Dans les agents RH et Calendar, chaque outil vérifie les permissions via la table `permissions` :
```python
# backend/app/core/rbac.py
allowed = await check_tool_permission(db, role, tool_name)
if not allowed:
    return tool_permission_denied_message(tool_name, role)
```

---

## Résumé des fichiers du module RH backend

| Fichier | Rôle |
|---------|------|
| `backend/app/api/rh.py` | Tous les endpoints REST du module RH |
| `backend/app/database/models/hris.py` | Modèles SQLAlchemy (Department, Team, Employee, Skill, Leave...) |
| `backend/app/database/models/user.py` | Modèle User (compte de connexion) |
| `backend/utils/email.py` | Envoi email des identifiants |
| `backend/app/core/security.py` | `get_current_user`, `hash_password` |
| `backend/app/main.py` | Enregistrement du router RH |
| `backend/app/database/connection.py` | Session SQLAlchemy async, `get_db` |
| `backend/agents/rh/tools.py` | Outils SQL pour l'agent RH (create_leave, get_balance...) |
| `backend/app/core/rbac.py` | Vérification des permissions par rôle |
