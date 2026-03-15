# Talan Assistant — Frontend

Interface React de l'assistant d'entreprise intelligent & unifié.

## Installation

```bash
npm install
npm run dev
```

L'app sera disponible sur http://localhost:5173

## Comptes de démonstration

| Rôle | Email | Mot de passe |
|------|-------|--------------|
| Consultant | eya@talan.com | password |
| Project Manager | ahmed@talan.com | password |

## Pages disponibles

| Route | Description | Accès |
|-------|-------------|-------|
| `/` | Login | Public |
| `/dashboard` | Dashboard | Tous |
| `/chat` | Interface chat | Tous |
| `/historique` | Historique conversations | Tous |
| `/notifications` | Notifications | Tous |
| `/nouveau-projet` | Analyse CDC | PM uniquement |
| `/settings` | Paramètres | Tous |

## Stack technique

- **React 18** + Vite
- **Tailwind CSS** (sans TypeScript)
- **Zustand** (state management)
- **React Router v6**
- **Lucide React** (icônes)

## Pour connecter au backend FastAPI

Dans `src/store/index.js`, remplacer les données mock par des appels axios vers `http://localhost:8000`
avec le header `Authorization: Bearer {token}`.

## Structure du projet

```
src/
├── components/
│   └── layout/
│       ├── Layout.jsx    # Wrapper avec sidebar + topbar
│       └── Sidebar.jsx   # Navigation latérale
├── data/
│   └── mock.js           # Données de démonstration
├── pages/
│   ├── Login.jsx         # Page de connexion
│   ├── Chat.jsx          # Interface chat principale
│   ├── Dashboard.jsx     # Dashboard (Consultant + PM)
│   └── OtherPages.jsx    # Historique, Notifications, NouveauProjet, Settings
├── store/
│   └── index.js          # Zustand stores (auth, chat, notifications)
├── App.jsx               # Router principal
├── main.jsx              # Entry point
└── index.css             # Tailwind + styles custom
```
