# Module RH — Frontend : Documentation Complète

> Ce document explique chaque composant, page et fichier API du module RH côté frontend React. Il couvre la structure, les données manipulées, les interactions utilisateur et les appels réseau.

---

## Vue d'ensemble de l'architecture frontend

```
client/src/
├── api/
│   └── rh.js                   # Toutes les fonctions d'appel API backend
│
├── pages/
│   └── rh/
│       ├── RHPage.jsx           # Page principale avec les 3 onglets
│       ├── tabs/
│       │   ├── LeavesTab.jsx    # Onglet congés (tableau + approve/reject)
│       │   ├── UsersTab.jsx     # Onglet utilisateurs (tableau + création)
│       │   └── OrgTab.jsx       # Onglet organisation (drill-down hiérarchique)
│       └── components/
│           ├── CreateUserModal.jsx  # Modal 2 étapes pour créer un compte
│           └── SkillsPicker.jsx     # Sélecteur de compétences avec autocomplétion
│
├── App.jsx                     # Routing React + garde RHRoute
└── components/layout/
    └── Sidebar.jsx              # Navigation latérale avec lien RH
```

---

## Technologie utilisée

| Technologie | Version | Rôle |
|-------------|---------|------|
| React | 18 | UI et composants |
| React Router v6 | 6 | Navigation entre pages |
| Zustand | — | Store global (auth token, user info) |
| Tailwind CSS | 3 | Styles utilitaires |
| Axios (via `api/index.js`) | — | Requêtes HTTP avec token JWT auto |
| Lucide React | — | Icônes |
| clsx | — | Classes CSS conditionnelles |

---

## Fichier 1 : `api/rh.js` — Couche API

**Chemin :** `client/src/api/rh.js`

Ce fichier centralise **tous les appels HTTP vers le backend RH**. Il utilise l'instance Axios configurée dans `api/index.js` qui injecte automatiquement le header `Authorization: Bearer <token>`.

### Fonctions disponibles

```js
// Créer un compte + employé + skills en une seule requête
export const createUserApi = async (data) => {
  const response = await api.post('/rh/users', data)
  return response.data
  // data = { name, email, role, team_id, job_title, seniority, hire_date, skills: [{name, level}] }
}

// Lister tous les utilisateurs
export const getUsersApi = async () => {
  const response = await api.get('/rh/users')
  return response.data
  // retourne: [{ id, name, email, role, is_active, created_at }, ...]
}

// Lister les départements (avec nombre d'équipes)
export const getDepartmentsApi = async () => {
  const response = await api.get('/rh/departments')
  return response.data
  // retourne: [{ id, name, team_count }, ...]
}

// Lister les équipes (avec manager)
export const getTeamsApi = async () => {
  const response = await api.get('/rh/teams')
  return response.data
  // retourne: [{ id, name, department, manager_name }, ...]
}

// Lister les employés avec leurs skills
export const getEmployeesApi = async () => {
  const response = await api.get('/rh/employees')
  return response.data
  // retourne: [{ id, name, email, role, job_title, seniority, hire_date,
  //              leave_balance, team, department, manager,
  //              skills: [{name, level}] }, ...]
}

// Lister les compétences existantes (pour SkillsPicker)
export const getSkillsApi = async () => {
  const response = await api.get('/rh/skills')
  return response.data
  // retourne: [{ id, name }, ...]
}

// Lister les demandes de congé (avec filtre optionnel)
export const getLeavesApi = async (status = null) => {
  const params = status ? { status } : {}
  const response = await api.get('/rh/leaves', { params })
  return response.data
  // ?status=pending → seulement les congés en attente
}

// Approuver un congé
export const approveLeaveApi = async (leaveId) => {
  const response = await api.post(`/rh/leaves/${leaveId}/approve`)
  return response.data
  // retourne: { success: true, status: "approved" }
}

// Rejeter un congé avec raison
export const rejectLeaveApi = async (leaveId, reason = '') => {
  const response = await api.post(`/rh/leaves/${leaveId}/reject`, { reason })
  return response.data
  // retourne: { success: true, status: "rejected" }
}
```

**Gestion des erreurs :**
Axios rejette la promesse si le serveur retourne un code >= 400. Les composants attrapent ces erreurs avec `try/catch` et affichent `err?.response?.data?.detail` (le message d'erreur FastAPI).

---

## Fichier 2 : `App.jsx` — Routing et garde RH

**Chemin :** `client/src/App.jsx`

### Garde d'accès `RHRoute`

```jsx
function RHRoute({ children }) {
  const { role } = useAuthStore()
  if (role !== 'rh') return <Navigate to="/dashboard" replace />
  return children
}
```

Si un utilisateur non-RH tente d'accéder à `/rh`, il est redirigé vers `/dashboard`. `useAuthStore()` lit le rôle depuis le store Zustand (persisté dans `localStorage`).

### Route RH

```jsx
<Route
  path="/rh"
  element={
    <RHRoute>
      <Layout>      {/* Sidebar + Header */}
        <RHPage />
      </Layout>
    </RHRoute>
  }
/>
```

### Redirection automatique après login

```jsx
// Dans Login.jsx, après authentification réussie :
if (role === 'rh') {
  navigate('/rh')
} else {
  navigate('/dashboard')
}
```

---

## Fichier 3 : `RHPage.jsx` — Page principale

**Chemin :** `client/src/pages/rh/RHPage.jsx`

### Rôle
Conteneur principal avec 3 onglets. Gère uniquement quelle tab est active.

### Structure

```jsx
const TABS = [
  { id: 'leaves', label: 'Congés',       icon: Calendar },
  { id: 'users',  label: 'Utilisateurs', icon: Users },
  { id: 'org',    label: 'Organisation', icon: Building2 },
]

export default function RHPage() {
  const [activeTab, setActiveTab] = useState('leaves')  // congés par défaut
  // ...
  return (
    <div>
      {/* Header avec titre + onglets */}
      <TabBar tabs={TABS} active={activeTab} onChange={setActiveTab} />

      {/* Contenu de l'onglet actif */}
      {activeTab === 'leaves' && <LeavesTab />}
      {activeTab === 'users'  && <UsersTab />}
      {activeTab === 'org'    && <OrgTab />}
    </div>
  )
}
```

**Onglet par défaut : Congés** car c'est l'action la plus fréquente du RH (approuver/rejeter les demandes).

---

## Fichier 4 : `LeavesTab.jsx` — Gestion des congés

**Chemin :** `client/src/pages/rh/tabs/LeavesTab.jsx`

### État local

```js
const [leaves, setLeaves]             = useState([])    // liste des congés
const [loading, setLoading]           = useState(true)  // chargement initial
const [filter, setFilter]             = useState('pending') // filtre actif
const [actionId, setActionId]         = useState(null)  // ID du congé en cours de traitement
const [rejectTarget, setRejectTarget] = useState(null)  // congé ciblé pour rejet
```

### Chargement des données

```js
const load = async (f = filter) => {
  setLoading(true)
  setLeaves(await getLeavesApi(f || null))  // null = tous les statuts
  setLoading(false)
}

useEffect(() => { load() }, [filter])  // recharge quand le filtre change
```

### Filtres disponibles

```js
const FILTERS = [
  { value: '',         label: 'Tous'       },
  { value: 'pending',  label: 'En attente' },
  { value: 'approved', label: 'Approuvés'  },
  { value: 'rejected', label: 'Rejetés'    },
]
```

### Approuver un congé

```js
const handleApprove = async (lv) => {
  setActionId(lv.id)   // désactive les boutons de ce congé pendant le traitement
  await approveLeaveApi(lv.id)
  // Mise à jour optimiste : pas besoin de recharger toute la liste
  setLeaves(prev => prev.map(l =>
    l.id === lv.id ? { ...l, status: 'approved' } : l
  ))
  setActionId(null)
}
```

**Mise à jour optimiste :** Au lieu de refaire un appel API pour recharger la liste, on met à jour directement le state local. L'interface est instantanée.

### Rejeter un congé (avec modal de raison)

```js
// Clic sur "Rejeter" → ouvre le RejectModal
onClick={() => setRejectTarget(lv)}

// Le RH tape la raison dans le modal, confirme
const handleReject = async (reason) => {
  const lv = rejectTarget
  setRejectTarget(null)     // ferme le modal
  setActionId(lv.id)
  await rejectLeaveApi(lv.id, reason)   // envoie au backend
  setLeaves(prev => prev.map(l =>
    l.id === lv.id ? { ...l, status: 'rejected' } : l
  ))
  setActionId(null)
}
```

### Composant `RejectModal`

```jsx
function RejectModal({ leave, onConfirm, onCancel }) {
  const [reason, setReason] = useState('')
  return (
    // Overlay sombre + carte blanche
    // Affiche le nom de l'employé
    // Textarea pour la raison (optionnel)
    // Boutons "Annuler" et "Confirmer le rejet"
  )
}
```

### Tableau

| Colonne | Source de la donnée |
|---------|---------------------|
| Employé | `lv.employee_name` + `lv.team` |
| Type | `LEAVE_TYPE_LABEL[lv.leave_type]` (traduit en français) |
| Période | `start_date → end_date` formaté en `fr-FR` |
| Jours | `lv.days_count` |
| Statut | badge coloré selon `STATUS_STYLE[lv.status]` |
| Justificatif | lien `ExternalLink` si `lv.justification_url` existe |
| Actions | Boutons Approuver/Rejeter seulement si `status === 'pending'` |

### Stats rapides (onglet "Tous")

Quand le filtre est vide (tous les congés), des cartes de comptage s'affichent :
```js
['pending', 'approved', 'rejected', 'cancelled'].map(s => {
  const count = leaves.filter(l => l.status === s).length
  // → affiche le nombre dans une carte colorée
})
```

---

## Fichier 5 : `UsersTab.jsx` — Gestion des utilisateurs

**Chemin :** `client/src/pages/rh/tabs/UsersTab.jsx`

### État local

```js
const [users, setUsers]         = useState([])
const [loading, setLoading]     = useState(true)
const [showModal, setShowModal] = useState(false)  // ouvre CreateUserModal
const [search, setSearch]       = useState('')
```

### Recherche en temps réel (côté client)

```js
const filtered = users.filter(u =>
  u.name.toLowerCase().includes(search.toLowerCase()) ||
  u.email.toLowerCase().includes(search.toLowerCase())
)
```

Pas d'appel API à chaque frappe — le filtrage se fait dans le navigateur sur la liste déjà chargée.

### Intégration du modal

```jsx
<button onClick={() => setShowModal(true)}>Nouveau compte</button>

{showModal && (
  <CreateUserModal
    onClose={() => setShowModal(false)}
    onCreated={user => {
      setUsers(prev => [user, ...prev])  // ajoute en tête de liste
      setShowModal(false)
    }}
  />
)}
```

Quand le modal confirme la création (`onCreated`), le nouvel utilisateur est ajouté en tête de la liste sans recharger.

---

## Fichier 6 : `OrgTab.jsx` — Navigation hiérarchique

**Chemin :** `client/src/pages/rh/tabs/OrgTab.jsx`

### Concept : Drill-down

L'utilisateur navigue niveau par niveau :
```
Départements
    └── [clic sur Innovation Factory]
            Équipes de Innovation Factory
                └── [clic sur Team A]
                        Employés de Team A
                            └── [clic sur Yassine]
                                    Profil complet + Skills
```

### État de navigation

```js
const [departments, setDepartments] = useState([])
const [teams, setTeams]             = useState([])
const [employees, setEmployees]     = useState([])

// Niveau actuel de navigation
const [selectedDept, setSelectedDept] = useState(null)  // département sélectionné
const [selectedTeam, setSelectedTeam] = useState(null)  // équipe sélectionnée
const [selectedEmp,  setSelectedEmp]  = useState(null)  // employé sélectionné
```

### Chargement initial (tout en parallèle)

```js
useEffect(() => {
  Promise.all([getDepartmentsApi(), getTeamsApi(), getEmployeesApi()])
    .then(([d, t, e]) => {
      setDepartments(d)
      setTeams(t)
      setEmployees(e)
    })
    .finally(() => setLoading(false))
}, [])
```

**Pourquoi charger tout d'un coup ?** Les données de département/équipe/employé sont liées. En les chargeant toutes une fois, la navigation entre niveaux est instantanée (pas de requête supplémentaire à chaque clic).

### Logique d'affichage

```jsx
// Affiche en fonction du niveau de navigation
if (selectedEmp)  return <EmployeeDetail employee={selectedEmp} onBack={...} />
if (selectedTeam) return <EmployeeList team={selectedTeam} employees={employees} ... />
if (selectedDept) return <TeamList department={selectedDept} teams={teams} ... />
return              <DepartmentList departments={departments} ... />
```

### Filtre des teams par département

```js
// Dans TeamList
const deptTeams = teams.filter(t => t.department === department.name)
// t.department = "innovation_factory"
// department.name = "innovation_factory"
// → garde seulement les équipes de ce département
```

### Filtre des employés par équipe

```js
// Dans EmployeeList
const teamEmps = employees.filter(e => e.team === team.name)
```

### Affichage du manager dans TeamList

```jsx
<Card key={t.id} onClick={() => onSelect(t)}>
  <div className="font-semibold">{t.name}</div>
  <div className="text-xs text-slate-400">
    Manager : {t.manager_name || '—'}  {/* vient de GET /rh/teams */}
  </div>
</Card>
```

### Vue détaillée d'un employé (`EmployeeDetail`)

Affiche :
- Avatar avec initiales (ex: "YC" pour Yassine Cherif)
- Nom, intitulé de poste, badge séniorité coloré
- Grille d'infos : Email, Équipe, Département, Manager, Solde congés, Date d'embauche
- Liste des compétences avec niveau (chip coloré)

```jsx
const SKILL_LEVEL_COLOR = {
  beginner:     'bg-slate-100 text-slate-500',
  intermediate: 'bg-sky-100 text-sky-600',
  advanced:     'bg-blue-100 text-blue-700',
  expert:       'bg-violet-100 text-violet-700',
}
```

### Breadcrumb (fil d'Ariane)

```jsx
<Breadcrumb items={['Départements', 'Innovation Factory', 'Team A', 'Yassine Cherif']} />
// → Départements > Innovation Factory > Team A > Yassine Cherif
```

---

## Fichier 7 : `CreateUserModal.jsx` — Modal de création (2 étapes)

**Chemin :** `client/src/pages/rh/components/CreateUserModal.jsx`

### Étape 1 : Informations du compte

```
┌────────────────────────────────────────┐
│ Créer un compte  — Étape 1/2           │
│ ████████░░ (barre de progression)      │
│                                        │
│ Nom complet    [Prénom Nom............] │
│ Email          [prenom.nom@talan.tn...] │
│ Rôle           [Consultant ▼]          │
│                                        │
│ [Annuler]              [Suivant →]     │
└────────────────────────────────────────┘
```

Le bouton "Suivant" est désactivé tant que `name`, `email` et `role` ne sont pas remplis.

### Étape 2 : Profil employé

```
┌────────────────────────────────────────┐
│ Créer un compte  — Étape 2/2           │
│ ████████████████ (barre complète)      │
│                                        │
│ Département *  [Choisir ▼]             │
│ Équipe *       [— département d'abord] │  ← désactivé si pas de dept
│                                        │
│ Intitulé       [Développeur Full Stack] │
│ Séniorité  [Mid ▼]  Date embauche [...]│
│                                        │
│ Compétences                            │
│ [Composant SkillsPicker]               │
│                                        │
│ [← Retour]         [Créer le compte]   │
└────────────────────────────────────────┘
```

### Cascade Département → Équipe

```js
const set = (k, v) => {
  setForm(prev => {
    const next = { ...prev, [k]: v }
    if (k === 'department_id') next.team_id = ''  // reset équipe si dept change
    return next
  })
}

// Filtre les équipes selon le département sélectionné
const filteredTeams = allTeams.filter(t => {
  if (!form.department_id) return false
  const dept = departments.find(d => d.id === Number(form.department_id))
  return dept && t.department === dept.name  // compare les noms enum
})
```

Quand le RH change de département, l'équipe précédemment sélectionnée est effacée pour éviter une incohérence (équipe d'un autre département).

### Données chargées au montage

```js
useEffect(() => {
  Promise.all([getDepartmentsApi(), getTeamsApi(), getSkillsApi()])
    .then(([d, t, s]) => {
      setDepartments(d)    // pour le select Département
      setAllTeams(t)       // pour le select Équipe (filtré après)
      setExistingSkills(s) // pour SkillsPicker
    })
}, [])
```

### Soumission

```js
const payload = {
  name:      form.name,
  email:     form.email,
  role:      form.role,
  team_id:   Number(form.team_id),
  job_title: form.job_title  || null,
  seniority: form.seniority  || null,
  hire_date: form.hire_date  || null,   // ISO date "YYYY-MM-DD"
  skills:    form.skills,               // [{ name: "Python", level: "expert" }]
}
const user = await createUserApi(payload)
setSuccess(true)
onCreated(user)   // callback vers UsersTab pour mettre à jour la liste
```

### État de succès

```
┌────────────────────────────────────────┐
│                  ✓                     │
│     Compte et profil employé créés     │
│  Les identifiants ont été envoyés      │
│           par email.                   │
│                                        │
│              [Fermer]                  │
└────────────────────────────────────────┘
```

---

## Fichier 8 : `SkillsPicker.jsx` — Sélecteur de compétences

**Chemin :** `client/src/pages/rh/components/SkillsPicker.jsx`

### Props

```js
SkillsPicker({
  existingSkills: [{ id, name }],  // compétences disponibles en DB
  value:          [{ name, level }], // compétences sélectionnées (state parent)
  onChange:       (newSkills) => {}  // callback pour mettre à jour le parent
})
```

### Zone 1 : Compétences sélectionnées

En haut de la zone, chaque compétence sélectionnée est affichée avec :
- Nom de la compétence
- Select inline pour changer le niveau sans tout refaire
- Badge coloré du niveau actuel
- Bouton Supprimer (poubelle)

```jsx
{value.map((s, i) => (
  <div key={i}>
    <span>{s.name}</span>
    <select value={s.level} onChange={e => updateLevel(i, e.target.value)}>
      {SKILL_LEVELS.map(l => <option>{l.label}</option>)}
    </select>
    <span className={levelColor(s.level)}>{levelLabel(s.level)}</span>
    <button onClick={() => remove(i)}>🗑</button>
  </div>
))}
```

### Zone 2 : Barre de recherche

```jsx
<input
  type="text"
  value={search}
  onChange={e => setSearch(e.target.value)}
  placeholder="Rechercher une compétence…"
/>
```

La recherche filtre les chips affichés **en temps réel** (côté client, aucun appel API).

### Zone 3 : Chips cliquables (compétences DB)

```js
const filtered = useMemo(() => {
  const q = search.trim().toLowerCase()
  if (!q) return existingSkills                         // affiche tout si vide
  return existingSkills.filter(s => s.name.toLowerCase().includes(q))
}, [existingSkills, search])
```

```jsx
{filtered.map(s => {
  const selected = selectedNames.has(s.name.toLowerCase())
  return (
    <button
      onClick={() => toggleExisting(s)}       // clic = ajoute OU retire
      className={selected ? 'bg-cyan/10 border-cyan' : 'bg-white border-slate-200'}
    >
      {selected && <span>✓</span>}
      {s.name}
    </button>
  )
})}
```

**Toggle :**
```js
const toggleExisting = (skill) => {
  const already = selectedNames.has(skill.name.toLowerCase())
  if (already) {
    // Retire la compétence
    onChange(value.filter(s => s.name.toLowerCase() !== skill.name.toLowerCase()))
  } else {
    // Ajoute avec niveau par défaut "intermediate"
    onChange([...value, { name: skill.name, level: 'intermediate' }])
  }
}
```

### Zone 4 : Nouvelle compétence (si absente de la DB)

```js
const isNewSkill = searchTrimmed.length > 0
  && !existingSkills.some(s => s.name.toLowerCase() === searchTrimmed.toLowerCase())
```

Si `isNewSkill === true`, un bandeau ambre apparaît :

```
┌──────────────────────────────────────────┐
│ ✨ "GraphQL" n'existe pas encore.         │
│                    [Intermédiaire ▼] [+] │
└──────────────────────────────────────────┘
```

```js
const addNew = () => {
  onChange([...value, { name: searchTrimmed, level: newSkillLevel }])
  setSearch('')   // vide la recherche
}
```

**Ce qui se passe côté backend :** quand la compétence n'existe pas, `POST /rh/users` la crée dans la table `skills` avant de l'associer à l'employé.

### Optimisation avec `useMemo`

```js
const selectedNames = useMemo(
  () => new Set(value.map(s => s.name.toLowerCase())),
  [value]
)
// → recalculé seulement quand value change
// → O(1) pour vérifier si une skill est sélectionnée (Set vs Array.find)
```

---

## Fichier 9 : `Sidebar.jsx` — Navigation avec lien RH

**Chemin :** `client/src/components/layout/Sidebar.jsx`

```jsx
const { role } = useAuthStore()
const isRH = role === 'rh'

// Le lien RH apparaît seulement pour les utilisateurs RH
{isRH && (
  <NavLink to="/rh" className={...}>
    <ShieldCheck size={18} />
    Espace RH
    <span className="badge-rh">RH</span>
  </NavLink>
)}
```

**CSS `badge-rh`** (dans `index.css`) :
```css
.badge-rh {
  @apply bg-emerald-50 text-emerald-700 text-xs px-2 py-0.5 rounded-full font-medium;
}
```

---

## `Login.jsx` — Comptes de démonstration

**Chemin :** `client/src/pages/Login.jsx`

```js
const DEMO_ACCOUNTS = [
  { email: 'mariem.chaabane@talan.tn',  password: 'Talan2026!', label: 'RH' },
  { email: 'yassine.cherif@talan.tn',   password: 'Talan2026!', label: 'Consultant' },
  { email: 'ahmed.bensalah@talan.tn',   password: 'Talan2026!', label: 'Manager' },
]

const quickLogin = async (email, password) => {
  // Appel direct à login() → pas besoin de remplir le formulaire manuellement
  await login(email, password)
  // login() enregistre le token dans Zustand + localStorage
  // puis navigue vers /rh si role=rh, sinon /dashboard
}
```

Ces comptes sont **seedés** via `backend/scripts/seed_employees.py` avec le même hash bcrypt pour `Talan2026!`.

---

## Flux complet d'une action RH typique

### Scénario : Le RH approuve un congé

```
1. Le RH ouvre l'application → Login avec mariem.chaabane@talan.tn
2. Redirection automatique vers /rh (car role="rh")
3. RHPage s'affiche avec l'onglet "Congés" actif
4. LeavesTab charge : getLeavesApi("pending")
   → GET /rh/leaves?status=pending
   → Backend retourne la liste des congés en attente
5. Le RH clique sur "Approuver" pour le congé ID 47
   → handleApprove({ id: 47, ... })
   → approveLeaveApi(47)
   → POST /rh/leaves/47/approve
   → Backend : leave.status = "approved" + LeaveLog créé
   → Retour : { success: true, status: "approved" }
6. Mise à jour optimiste du state local
   → la ligne passe de "En attente" à "Approuvé" sans recharger
```

### Scénario : Le RH crée un nouveau compte

```
1. Onglet "Utilisateurs" → bouton "Nouveau compte"
2. Étape 1 : Nom + Email + Rôle → "Suivant"
3. Étape 2 :
   a. Choisit "Data & Analytics" dans le département
   b. Les équipes du département s'affichent → choisit "Team Data B"
      (avec indication "Manager: Ahmed Bensalah")
   c. Remplit intitulé: "Data Scientist"
   d. Séniorité: "Junior", Date: 31/03/2026
   e. Skills : clique sur "Python" (chip existant) + "Machine Learning" (existant)
      tape "Spark" → n'existe pas → bandeau ambre → choisit niveau → "Ajouter"
4. Clique "Créer le compte"
   → createUserApi({ name, email, role, team_id, job_title, seniority,
                     hire_date, skills: [{name:"Python",level:"intermediate"},
                                         {name:"Machine Learning",level:"intermediate"},
                                         {name:"Spark",level:"beginner"}] })
   → POST /rh/users
   → Backend crée User + Employee + EmployeeSkill (Spark créé dans skills)
   → Email envoyé avec le mot de passe généré
5. Écran de succès "✓ Compte et profil employé créés"
6. onCreated(user) → le nouvel user apparaît en tête de la liste
```

---

## Résumé des fichiers et leurs responsabilités

| Fichier | Responsabilité |
|---------|---------------|
| `api/rh.js` | Centralise tous les appels HTTP. Aucune logique UI. |
| `RHPage.jsx` | Conteneur des 3 onglets. Gère uniquement quelle tab est active. |
| `LeavesTab.jsx` | Tableau des congés + filtres + approve/reject + RejectModal |
| `UsersTab.jsx` | Tableau des utilisateurs + recherche + déclencheur du CreateUserModal |
| `OrgTab.jsx` | Navigation drill-down Dept→Team→Employee→Skills. Tout chargé d'un coup. |
| `CreateUserModal.jsx` | Formulaire 2 étapes : compte puis profil employé avec cascade dept→team |
| `SkillsPicker.jsx` | Chips cliquables (DB) + recherche + ajout nouvelle compétence |
| `App.jsx` | Route `/rh` avec garde `RHRoute` (redirige si pas RH) |
| `Sidebar.jsx` | Lien "Espace RH" affiché seulement pour `role === 'rh'` |
| `Login.jsx` | Comptes démo + redirection auto vers /rh si RH |
