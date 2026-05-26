# Step 5 — Matching : Guide complet

Ce document explique tout ce que fait le matching, de l'entrée à la sortie,
sans jargon technique inutile. Lis-le de haut en bas la première fois.

---

## C'est quoi le matching ?

Le matching répond à une question simple :
**"Pour chaque user story de chaque sprint, quel employé doit travailler dessus ?"**

C'est l'étape 5 du pipeline staffing. Elle reçoit les sprints avec leurs stories,
et la liste des candidats disponibles, et elle produit une affectation complète.

---

## Vue d'ensemble : ce qui se passe en 3 étapes

```
ENTRÉE
  └─ sprints + stories (step 4 : distribution)
  └─ candidats disponibles par sprint (step 4 : filtre)
  └─ profils requis par story (step 2 : extraction)
  └─ décisions PM (recruter ou non un profil)

ÉTAPE A — Scoring LLM (1 appel par profil)
  └─ Le LLM évalue les compétences de chaque couple (story × candidat)

ÉTAPE B — Sélection déterministe (aucun LLM)
  └─ Pour chaque (story, profil) : filtrer → scorer → choisir → consommer capacité

SORTIE
  └─ Pour chaque sprint → pour chaque story → pour chaque profil :
       qui est affecté, son score, ses compétences, son statut
```

---

## Les fichiers et leur rôle

| Fichier | Rôle |
|---|---|
| `service.py` | Chef d'orchestre : appelle le LLM puis traite chaque sprint |
| `selection.py` | Toute la logique de calcul pure (score, filtres, sélection) |
| `prompt.py` | Le texte envoyé au LLM pour scorer les compétences |
| `repository.py` | Sauvegarde les résultats en base de données |

---

## ENTRÉE — Ce que le matching reçoit

### 1. Les stories réparties dans les sprints

Chaque sprint contient ses user stories dans l'ordre de priorité :

```json
{
  "sprint_number": 1,
  "start_date": "2024-01-15",
  "end_date": "2024-01-29",
  "assigned_stories": [
    {
      "story_id": 42,
      "title": "Page de connexion utilisateur",
      "story_points": 3
    }
  ]
}
```

### 2. Les profils requis par story

Chaque story a besoin de un ou plusieurs types d'employés :

```json
{
  "story_id": 42,
  "required_profiles": ["Frontend Developer", "Backend Developer"],
  "required_skills": ["React", "CSS", "FastAPI", "PostgreSQL", "JWT"],
  "required_level": "MID"
}
```

> **Note :** Les `required_skills` sont pour toute la story. Un Backend ne sera
> jugé que sur ses compétences backend (FastAPI, PostgreSQL, JWT), pas sur React.

### 3. Les candidats disponibles par sprint

Pour chaque sprint, on sait quels employés sont disponibles pour quel profil :

```json
{
  "sprint_1": {
    "candidates_by_profile": {
      "Backend Developer": [
        {
          "employee_id": 7,
          "name": "Ahmed Ben Salah",
          "seniority": "MID",
          "skills": ["FastAPI", "PostgreSQL", "Python"]
        }
      ]
    }
  }
}
```

---

## ÉTAPE A — Scoring LLM : évaluer les compétences

### Pourquoi un LLM ?

On ne peut pas simplement compter les mots en commun entre les compétences
d'un employé et les besoins d'une story. Un développeur React connaît
implicitement JavaScript, HTML et CSS — même si ce n'est pas écrit dans son
profil. Le LLM fait ce travail d'inférence intelligente.

### Ce que le LLM fait exactement

Pour chaque couple **(story × candidat)**, le LLM classe les compétences
de la story (scopées au profil évalué) en 3 catégories :

| Catégorie | Signification | Exemple |
|---|---|---|
| `matched` | Compétence directement présente chez le candidat | La story requiert "PostgreSQL", le candidat l'a |
| `inferred` | Compétence déduite d'une compétence proche | La story requiert "JavaScript", le candidat a "React JS" → déduit |
| `missing` | Compétence requise et absente | La story requiert "Docker", le candidat ne l'a pas |

### Le scoping par profil — règle importante

Une story peut requérir plusieurs profils. Le LLM est appelé **une fois par profil**
et ne juge chaque candidat que sur les compétences qui concernent son profil.

**Exemple :**
```
Story "Page de connexion" :
  required_skills = ["React", "CSS", "FastAPI", "PostgreSQL", "JWT"]
  required_profiles = ["Frontend Developer", "Backend Developer"]

Quand on score un Backend Developer :
  → Skills évaluées : FastAPI, PostgreSQL, JWT
  → React et CSS sont IGNORÉS (c'est le travail du Frontend)
  → Un backend qui ne connaît pas React n'est PAS pénalisé
```

### Combien d'appels LLM ?

**1 appel par profil** (pas par sprint, pas par story).

Tous les sprints et toutes les stories sont regroupés dans un seul appel
pour chaque profil. Si on a 3 profils différents dans le projet, c'est
exactement 3 appels LLM, peu importe le nombre de sprints ou de stories.

Si le batch est trop gros (plus de 30 couples story × candidat par appel),
il est découpé en plusieurs morceaux envoyés en parallèle pour éviter que
la réponse JSON soit tronquée.

### Ce que le LLM ne fait PAS

- Il ne calcule pas de score numérique
- Il ne choisit pas le meilleur candidat
- Il ne connaît pas la capacité des candidats
- Il ne connaît pas les sprints

Il se contente de classer les compétences. Tout le reste est fait en Python.

---

## Calcul du score de compétences

C'est une formule simple calculée en Python après la réponse du LLM.

### La formule

```
skill_score = (matched + inferred) / (matched + inferred + missing)
```

Le dénominateur = toutes les compétences scopées au profil pour cette story.
Le numérateur = celles que le candidat a (directement ou par déduction).

### Exemples

| Story requiert (profil Backend) | Candidat | matched | inferred | missing | Score |
|---|---|---|---|---|---|
| FastAPI, PostgreSQL, JWT | A les 3 | 3 | 0 | 0 | 3/3 = **100%** |
| FastAPI, PostgreSQL, JWT | A FastAPI, a Python (→infère rien ici) | 1 | 0 | 2 | 1/3 = **33%** |
| FastAPI, PostgreSQL, JWT | A FastAPI, PostgreSQL | 2 | 0 | 1 | 2/3 = **67%** |
| Aucune skill backend | N'importe qui | 0 | 0 | 0 | 0/0 = **100%** ← scope vide |

> Le score **100% sur scope vide** : si aucune compétence de la story
> ne relève du profil, le candidat obtient 1.0 — il n'a rien à prouver.

### Les niveaux de match

| Score | Niveau | Couleur UI |
|---|---|---|
| ≥ 85% | `excellent` | Vert foncé |
| ≥ 65% | `good` | Vert |
| ≥ 40% | `medium` | Orange → alerte PM |
| < 40% | `weak` | Rouge → alerte forte |

---

## ÉTAPE B — Sélection déterministe

C'est ici que le vrai travail se passe, sprint par sprint, story par story.

### 1. Initialisation de la capacité

Au début de chaque sprint, chaque candidat reçoit une capacité en Story Points
selon sa séniorité. Cette capacité diminue au fur et à mesure qu'on lui affecte
des stories.

```
JUNIOR  → 6 SP par sprint
MID     → 8 SP par sprint
SENIOR  → 10 SP par sprint
```

**Exemple :** Ahmed (MID) commence avec 8 SP. On lui affecte une story de 3 SP.
Il lui reste 5 SP pour les stories suivantes du même sprint.

> Les capacités sont **réinitialisées à chaque sprint**. Un MID a 8 SP dans
> le sprint 1 et aussi 8 SP dans le sprint 2.

### 2. Calcul des SP alloués par profil

Pour chaque story, on divise les story points équitablement entre les profils :

```
Story de 3 SP avec 2 profils (Frontend + Backend)
→ allocated_sp = 3 / 2 = 1.5 SP par profil
```

Cela signifie que l'employé affecté à cette story "consomme" 1.5 SP de sa
capacité sprint.

### 3. Filtrage des candidats éligibles

Avant de choisir, on élimine les candidats qui ne peuvent pas prendre la story :

**Filtre capacité :** le candidat doit avoir assez de SP restants.
```
remaining_capacity_sp >= allocated_sp
```

**Filtre séniorité avec dégradation gracieuse :**

Si la story requiert un SENIOR mais aucun SENIOR n'est disponible, le système
descend automatiquement d'un niveau plutôt que de bloquer :

```
Story requiert SENIOR
  → cherche SENIOR disponible
  → si aucun : cherche MID disponible
  → si aucun : cherche JUNIOR disponible
  → si aucun : affectation impossible
```

Quand on dégrade, le PM en est informé via un badge "Séniorité dégradée" dans l'UI.

### 4. L'algorithme de sélection (best-fit)

Une fois les candidats éligibles filtrés et scorés, l'algorithme choisit
le meilleur en 5 étapes. **C'est totalement déterministe** (même entrée = même résultat).

#### Étape 1 : Choisir le meilleur groupe de compétences

On regroupe les candidats par niveau de match et on prend le meilleur groupe :
```
excellent + good  →  priorité maximale
medium            →  si pas de excellent/good
weak              →  en dernier recours
```

Si le groupe retenu est `medium` ou `weak`, le PM reçoit une alerte
("Affecté avec alerte") car aucun bon profil n'était disponible.

#### Étape 2 : Best-fit waste (minimiser le gaspillage)

Le **waste** = capacité restante de l'employé après affectation.

```
waste = remaining_capacity_sp - allocated_sp
```

**On choisit le candidat avec le waste le plus faible.**

Pourquoi ? Pour utiliser au maximum les ressources disponibles. Si Ahmed a
2 SP restants et la story coûte 1.5 SP (waste = 0.5) et Bilel a 8 SP restants
(waste = 6.5), on préfère Ahmed car il utilise sa capacité de façon plus efficace.

#### Étape 3 : Tie-break — meilleur score (si même waste)

Si plusieurs candidats ont exactement le même waste, on prend celui avec
le meilleur `skill_score`. Le score est arrondi à 2 décimales pour éviter
des départages sur des différences insignifiantes (0.671 vs 0.672 → même score).

#### Étape 4 : Tie-break — séniorité la plus proche (si même score)

On préfère le candidat dont la séniorité est la plus proche de celle requise.

```
Story requiert MID :
  Candidat A : MID   → distance 0  ← gagnant
  Candidat B : SENIOR → distance 1
```

#### Étape 5 : Tie-break final — employee_id le plus petit

Si toujours égalité, on prend l'employé avec le plus petit identifiant.
C'est arbitraire mais **100% déterministe** : relancer l'analyse deux fois
donne toujours le même résultat.

> Le PM peut toujours changer ce choix via le bouton "Changer l'affectation".

### 5. Consommation de la capacité

Une fois un candidat choisi, sa capacité est mise à jour immédiatement
**pour les stories suivantes du même sprint** :

```
Ahmed était à 8 SP → on lui affecte 1.5 SP → il passe à 6.5 SP restants
```

Les stories sont traitées dans l'ordre de priorité du sprint. Les premières
stories "consomment" la capacité des employés, et les dernières stories
doivent travailler avec ce qu'il reste.

---

## Les cas particuliers

### Aucun candidat disponible

Si après filtrage personne n'est éligible, la story reçoit un statut d'erreur :

| Statut | Signification |
|---|---|
| `missing_profile` | Ce profil a été marqué "à recruter" par le PM |
| `no_available_candidate` | Aucun employé de ce profil n'est disponible sur ce sprint |
| `capacity_gap` | Des employés existent mais tous ont épuisé leur capacité sprint |

---

## SORTIE — Ce que le matching produit

### Pour chaque sprint

```
SprintMatching
├── sprint_number, start_date, end_date
├── sprint_status  ("fully_staffed" | "partially_staffed" | "not_staffed")
├── planned_story_points  (somme des SP des stories du sprint)
├── recommended_team  ← liste des employés affectés à ce sprint
│     ├── name, seniority, job_title
│     ├── capacity_sp       (capacité totale : 6, 8 ou 10 SP)
│     ├── assigned_sp       (SP consommés par les affectations)
│     ├── remaining_capacity_sp  (capacité restante finale)
│     └── stories_handled   (nombre de stories pris en charge)
├── story_assignments  ← liste des stories et leurs affectations
│     ├── story_id, story_title, story_points
│     ├── story_status  ("fully_assigned" | "partially_assigned" | "not_assigned")
│     └── assignments  ← liste des profils et l'employé choisi
│           ├── required_profile  (ex: "Backend Developer")
│           ├── employee_id, employee_name, employee_seniority
│           ├── allocated_sp  (SP consommés pour cette affectation)
│           ├── skill_score  (0.0 → 1.0)
│           ├── match_level  ("excellent" | "good" | "medium" | "weak")
│           ├── matched_skills, inferred_matches, missing_skills
│           ├── status  ("assigned" | "assigned_with_warning" | "missing_profile" | "capacity_gap" | "no_available_candidate")
│           ├── warning_type  (null | "medium_skill_match" | "weak_skill_match")
│           ├── seniority_downgrade_from  (null | "SENIOR" | "MID")
│           ├── reason  (explication textuelle pour le PM)
│           └── alternative_candidates  ← TOUS les candidats évalués pour ce (story × profil)
│                 (utilisé par le bouton "Changer l'affectation")
└── issues  ← affectations en erreur (missing_profile, capacity_gap, no_available_candidate)
```

### Statuts possibles d'une affectation (profil)

| Statut | Signification |
|---|---|
| `assigned` | Employé affecté avec bon niveau de compétences |
| `assigned_with_warning` | Employé affecté mais compétences moyennes ou faibles — ou séniorité dégradée |
| `missing_profile` | Profil marqué à recruter par le PM |
| `no_available_candidate` | Aucun employé de ce profil disponible sur le sprint |
| `capacity_gap` | Tous les candidats ont épuisé leur capacité sprint |

### Statuts agrégés

**Story status** (calculé à partir de ses profils) :

| Statut | Signification |
|---|---|
| `fully_assigned` | Tous les profils de la story sont affectés |
| `partially_assigned` | Certains profils OK, d'autres en erreur |
| `not_assigned` | Aucun profil n'a pu être affecté |

**Sprint status** (calculé à partir de ses stories) :

| Statut | Signification |
|---|---|
| `fully_staffed` | Toutes les stories sont `fully_assigned` |
| `partially_staffed` | Mix de stories affectées et en erreur |
| `not_staffed` | Aucune story affectée |

---

## La fonctionnalité "Changer l'affectation"

### Pourquoi elle existe

L'algorithme est déterministe — il fait toujours le même choix selon les règles.
Mais le PM peut légitimement vouloir choisir un autre candidat, par exemple :
- Il préfère affecter quelqu'un avec plus d'expérience même si le waste est plus élevé
- Il sait que tel employé sera en congé pendant le sprint
- Il préfère garder la capacité d'un employé pour des stories futures

### Comment les alternatives sont stockées

Quand l'algorithme affecte un employé, il stocke dans `alternative_candidates`
**tous les candidats évalués** pour ce (story × profil), avec leur score complet.
C'est ce qui permet d'afficher la liste dans le dialog "Changer l'affectation".

### Ce que montre le dialog au PM

Pour chaque candidat alternatif :

```
Compatibilité compétences  [████████░░]  80%   ← skill_score

Maîtrisées : FastAPI, PostgreSQL
Inférées   : REST API
Manquantes : Docker

📊 Est-il disponible ?      [████████░░]  6/8 SP   ← charge actuelle dans le sprint
📥 Sa charge si affecté ?   [█████████░]  7.5/8 SP ← charge après l'affecter
🟢 Combien reste-t-il ?     0.5 SP libres          ← capacité restante après
```

### Comment les capacités sont calculées dans le dialog

Les capacités viennent de `recommended_team` (l'état final du sprint), pas du
moment du matching. Pour chaque candidat :

```
# Pour l'employé actuellement affecté à cette story :
available = remaining_capacity_sprint + allocated_sp_de_cette_story
(il récupère ses SP si on le remplace)

# Pour les autres candidats :
available = remaining_capacity_sprint
(simplement ce qu'il leur reste)

# Charge après affectation :
charge_apres = assigned_sp + allocated_sp  (pour les autres)
charge_apres = assigned_sp               (pour l'actuel, rien ne change)
```

**Exemple :**
```
Story = 1.5 SP   |   Ahmed est l'affecté actuel
Ahmed : 7.5/8 SP utilisés → 0.5 SP restants
→ available = 0.5 + 1.5 = 2 SP  (il récupère ses 1.5 SP si on le change)
→ Sa charge si affecté : 7.5/8 SP (inchangé)
→ Reste après : 0.5 SP libres

Bilel : 0/8 SP utilisés → 8 SP restants
→ available = 8 SP
→ Sa charge si affecté : 1.5/8 SP
→ Reste après : 6.5 SP libres
```

Les candidats sans assez de capacité (`available < allocated_sp`) sont
**automatiquement masqués** du dialog.

### Ce qui se passe quand le PM change l'affectation

1. L'API reçoit `{ sprint_number, story_id, required_profile, new_employee_id }`
2. Elle vérifie que `new_employee_id` est bien dans les `alternative_candidates`
3. Elle reconstruit toute la capacité du sprint à partir des affectations actuelles
4. Elle met à jour l'affectation dans le state JSON du projet
5. Elle recalcule `recommended_team`, `story_status`, `sprint_status`
6. Elle sauvegarde en base de données (non-bloquant)
7. Elle retourne le résultat rafraîchi au PM

---

## Persistance en base de données

Après chaque calcul complet du matching, les résultats sont sauvegardés en
base dans la table `staffing_assignments`.

La stratégie est **delete + insert** : on efface toutes les lignes du projet
et on réinsère tout. C'est simple et idempotent — si on relance le matching
deux fois, on obtient le même résultat en base.

La source de vérité reste le **state JSON** du projet (stocké dans la table
`pipeline_state`). La base de données sert pour les requêtes analytics et
les dashboards multi-projets.

---

## Récapitulatif visuel du flux complet

```
Sprints + Stories
       │
       ▼
┌─────────────────────────────────────────────────────┐
│  ÉTAPE A : Scoring LLM                              │
│                                                     │
│  Pour chaque profil (Frontend / Backend / AI / ...) │
│  ├─ Regroupe toutes les stories de tous les sprints │
│  ├─ 1 appel LLM (chunké si > 30 paires)            │
│  └─ Retourne matched / inferred / missing           │
└─────────────────────────────────────────────────────┘
       │
       ▼  (scores disponibles pour tous les profils)
┌─────────────────────────────────────────────────────┐
│  ÉTAPE B : Sélection déterministe                   │
│                                                     │
│  Pour chaque sprint :                               │
│    Init capacité (JUNIOR=6 / MID=8 / SENIOR=10 SP) │
│                                                     │
│    Pour chaque story (ordre priorité) :             │
│      Pour chaque profil requis :                    │
│        1. Filtre séniorité + capacité               │
│        2. Récupère scores LLM pre-calculés          │
│        3. Calcule skill_score = (M+I)/(M+I+Miss)   │
│        4. Groupe par match_level                    │
│        5. Best-fit waste → tie-break score →        │
│           tie-break séniorité → tie-break id        │
│        6. Consomme la capacité du candidat choisi   │
│        7. Stocke tous les candidats (alternatives)  │
└─────────────────────────────────────────────────────┘
       │
       ▼
 SprintMatching × N sprints
       │
       ▼
 Sauvegarde DB (delete + insert)
       │
       ▼
 PM voit les résultats dans l'UI
   ├─ Peut relancer le matching complet
   ├─ Peut changer une affectation (dialog alternatifs)
   └─ Peut signaler un besoin en recrutement
```

---

## Questions fréquentes

**Q : Pourquoi les scores changent si on relance le matching ?**
Le LLM peut donner des réponses légèrement différentes à chaque appel même pour
le même input. Les scores peuvent varier de quelques %. La sélection reste
déterministe à partir du moment où les scores sont calculés.

**Q : Un employé peut-il être dans plusieurs sprints ?**
Oui. La capacité est réinitialisée à chaque sprint. Un employé à 100% dans
le sprint 1 repart à pleine capacité pour le sprint 2.

**Q : Que se passe-t-il si le LLM échoue ?**
L'appel est retenté 3 fois (avec 7 secondes entre chaque tentative). Si les 3
tentatives échouent, le candidat reçoit un score par défaut de 0.5 (medium)
pour ne pas bloquer l'affectation. Le PM voit "Compétences non disponibles"
dans l'UI.

**Q : Pourquoi "best-fit waste" et pas "meilleur score" en priorité ?**
Le meilleur score ne signifie pas qu'on utilise bien les ressources. Si le
meilleur candidat pour une story a 10 SP libres et qu'une story coûte 1 SP,
on gaspille 9 SP. Best-fit packing minimise ce gaspillage et permet de
traiter un maximum de stories avec l'équipe disponible.

**Q : À quoi sert `seniority_downgrade_from` ?**
C'est la traçabilité de la dégradation de séniorité. Si la story requiert
un SENIOR et qu'on a affecté un MID, `seniority_downgrade_from = "SENIOR"`.
Le PM voit le badge orange "Séniorité dégradée (SENIOR demandé)" dans l'UI.
