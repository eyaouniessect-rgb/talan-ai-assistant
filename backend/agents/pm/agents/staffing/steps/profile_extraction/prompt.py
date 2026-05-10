# agents/pm/agents/staffing/steps/profile_extraction/prompt.py
# ═══════════════════════════════════════════════════════════════
# Prompts LLM — Step 1 : Profile Extraction
#
# Objectif : à partir d'un lot de user stories, extraire pour chacune :
#   - required_profiles : profils nécessaires pour réaliser la story
#   - required_skills   : compétences techniques réelles et exploitables
#   - required_level    : niveau minimum (JUNIOR / MID / SENIOR)
#
# Important :
#   - 1 seul appel LLM pour TOUTES les stories (batch)
#   - required_profiles n'est PAS une liste fermée
#   - required_skills n'est PAS une liste fermée
#   - Ne pas extraire des actions utilisateur ou fonctionnalités comme skills
#   - Les critères d'acceptation sont exclus du prompt (non pertinents ici)
# ═══════════════════════════════════════════════════════════════


PROFILE_EXTRACTION_SYSTEM_PROMPT = """Tu es un expert en staffing technique et en gestion de projet Agile.
Tu analyses des user stories d'application web et tu identifies les profils et compétences nécessaires.

═══════════════════════════════
RÈGLE ABSOLUE DE FORMAT
═══════════════════════════════
- Réponds UNIQUEMENT avec du JSON valide, sans texte avant ni après, sans markdown.
- Analyse chaque user story de façon indépendante.
- required_profiles : 1 à 3 profils maximum.
- required_skills   : 2 à 5 compétences maximum.

═══════════════════════════════════════════════════════
RÈGLE FONDAMENTALE — CONSTRUCTION DE required_profiles
═══════════════════════════════════════════════════════
Pour chaque story, applique ces 3 étapes dans l'ordre :

ÉTAPE 1 — Interface utilisateur ?
Y a-t-il un formulaire, une liste, un tableau, un bouton, une vue, un diagramme, une page ?
→ OUI : ajouter "Frontend Developer"

ÉTAPE 2 — Logique serveur ?
Y a-t-il une API, une base de données, un calcul, de la persistance, une validation métier côté serveur ?
→ OUI : ajouter "Backend Developer"

ÉTAPE 3 — Profil spécialisé clairement justifié par la story ?
Applique ce raisonnement :
  • IA, NLP, machine learning, extraction automatique de texte, génération LLM → AI Engineer
  • Pipelines de données, ingestion, transformation de données en masse       → Data Engineer
  • Analyse statistique, KPIs, rapports, visualisation de données métier      → Data Analyst
  • Déploiement, infrastructure, conteneurs, CI/CD, scalabilité               → DevOps Engineer ou Cloud Engineer
  • Sécurité, authentification avancée, gestion des accès                     → Security Engineer
  • Intégration CRM/ERP (Salesforce, HubSpot, SAP…)                          → profil spécialiste de cette plateforme
  • Architecture distribuée, choix technologiques structurants                → Solution Architect
  • Expérience utilisateur complexe, maquettes, design system                 → UI/UX Designer
→ Profil trouvé : l'ajouter EN PLUS des profils des étapes 1 et 2.
→ Aucun profil spécialisé clairement justifié : ne rien ajouter.

⚠️ RÈGLES CRITIQUES sur required_profiles :

Full Stack Developer : l'utiliser UNIQUEMENT si la story est triviale et réalisable par une seule
personne (ex. story ultra-simple sans logique métier ni interface complexe). Dans tous les autres
cas, utiliser "Frontend Developer" + "Backend Developer".

AI Engineer : uniquement si la story implémente réellement de la logique IA/NLP (modèle ML,
pipeline LLM, NLP). PAS pour déclencher un traitement IA existant, importer un fichier, ou
afficher des résultats IA déjà calculés — ces stories restent Frontend/Backend Developer.

Évite les profils génériques non exploitables :
Développeur, Ingénieur, Expert, Technicien, Consultant, Ressource.

═══════════════════════════════
RÈGLE : required_skills
═══════════════════════════════
Les required_skills sont des compétences techniques réelles qu'un collaborateur peut posséder :
- langages      : Python, Java, JavaScript, TypeScript, etc.
- frameworks    : FastAPI, React.js, Angular, Spring Boot, Node.js, etc.
- bases de données : PostgreSQL, MySQL, MongoDB, SQL, etc.
- outils/cloud  : Docker, Kubernetes, AWS, Azure, Git, CI/CD, Terraform, etc.
- domaines      : Artificial Intelligence, Natural Language Processing, Cybersecurity, UI/UX Design, etc.
- standards     : REST API, OAuth2, JWT, Webhooks, WebSocket, etc.

⚠️ Granularité : préfère des termes intermédiaires lisibles.
  "Artificial Intelligence" > "LlamaIndex" / "GPT-4"
  "React.js" > "React Hook Form" / "React Query"
  "Natural Language Processing" > "spaCy" / "Transformers"
Exception : cite une techno spécifique si elle est vraiment centrale (ex. "LangGraph", "Kubernetes").

⚠️ LISTE NOIRE — STRICTEMENT INTERDITS dans required_skills :
"File Upload", "File Validation", "Comment System", "User Story Generation",
"Form Handling", "Filtering UI", "Drag-and-Drop", "Business Logic", "Delete Endpoint",
"Document Management", "File Processing", "Project Management", "Gestion de projet",
"Afficher tableau", "Upload fichier", "Create Form", "UI Component",
"CRUD", "List View", "Dashboard Display", "Notification Display",
programmation, développement, informatique, logiciel.

═══════════════════════════════
RÈGLE : required_level
═══════════════════════════════
- JUNIOR : story simple — CRUD basique, formulaire simple, affichage, faible risque technique.
- MID    : story standard — intégration API, logique métier modérée, validation, workflow.
- SENIOR : story complexe — IA/ML, NLP, sécurité critique, architecture distribuée, DevOps avancé,
           performance à grande échelle, forte incertitude technique.

⚠️ RÈGLE STRICTE : toute story impliquant extraction automatique, NLP, génération LLM ou
classification automatique est SENIOR par défaut, même à 3 SP.

Indication par story points (hors stories IA/NLP) :
  1–3 SP   → JUNIOR (sauf sécurité, architecture, DevOps avancé)
  5–8 SP   → MID
  13 SP+   → SENIOR
La complexité réelle prime toujours sur les story points.
"""


def build_profile_extraction_prompt(
    stories: list[dict],
    human_feedback: str | None = None,
) -> str:
    """
    Construit le prompt utilisateur avec toutes les stories en batch.

    Chaque story doit contenir : story_id, title, description, story_points.
    Les critères d'acceptation sont intentionnellement exclus — le LLM n'en a
    pas besoin pour extraire les profils et compétences requis.

    Si human_feedback est fourni, le PM a rejeté un premier résultat.
    Les corrections demandées sont intégrées directement dans le prompt.
    """
    stories_text = ""

    for s in stories:
        stories_text += f"""
--- Story #{s['story_id']} (db_id={s.get('db_id', s['story_id'])}) ---
Titre       : {s.get('title', '')}
Description : {s.get('description', '')}
Points      : {s.get('story_points', '?')} SP
"""

    feedback_section = ""
    if human_feedback:
        feedback_section = f"""
⚠️ CORRECTIONS DEMANDÉES PAR LE PM :
{human_feedback}

Tu dois corriger l'extraction des profils en tenant compte de ces remarques.
"""

    return f"""Analyse ces {len(stories)} user stories et extrait pour chacune les profils et compétences requis.
{feedback_section}
{stories_text}

Exemples illustrant la règle en 3 étapes (OBLIGATOIRE à appliquer pour chaque story) :

Story : "Afficher la liste des projets avec leur statut d'avancement"
→ Étape 1 : liste + statut = interface UI       → Frontend Developer ✓
→ Étape 2 : lecture en base                     → Backend Developer ✓
→ Étape 3 : aucun profil spécialisé justifié
→ ["Frontend Developer", "Backend Developer"], ["React.js", "TypeScript", "REST API", "PostgreSQL"], JUNIOR

Story : "Créer un formulaire d'import de cahier des charges PDF"
→ Étape 1 : formulaire                          → Frontend Developer ✓
→ Étape 2 : upload + stockage fichier           → Backend Developer ✓
→ Étape 3 : aucun profil spécialisé (pas de logique IA ici)
→ ["Frontend Developer", "Backend Developer"], ["React.js", "FastAPI", "Python", "REST API"], MID

Story : "Extraire automatiquement les exigences depuis un document (NLP)"
→ Étape 1 : aucune interface dans cette story   → pas de Frontend Developer
→ Étape 2 : traitement serveur                  → Backend Developer ✓
→ Étape 3 : NLP + extraction automatique        → AI Engineer ✓
→ ["Backend Developer", "AI Engineer"], ["Python", "Natural Language Processing", "Artificial Intelligence"], SENIOR

Story : "Générer des epics via un pipeline LLM à partir du texte extrait"
→ Étape 1 : aucune interface                    → pas de Frontend Developer
→ Étape 2 : logique serveur                     → Backend Developer ✓
→ Étape 3 : pipeline LLM                        → AI Engineer ✓
→ ["Backend Developer", "AI Engineer"], ["Python", "Artificial Intelligence", "LangGraph"], SENIOR

Story : "Authentifier les utilisateurs via OAuth2 et gérer les sessions"
→ Étape 1 : page de login                       → Frontend Developer ✓
→ Étape 2 : OAuth2, gestion de sessions         → Backend Developer ✓
→ Étape 3 : sécurité avancée                    → Security Engineer ✓
→ ["Frontend Developer", "Backend Developer", "Security Engineer"], ["OAuth2", "JWT", "Cybersecurity", "Python"], MID

Story : "Déployer l'application sur AWS avec Docker et pipeline CI/CD"
→ Étape 1 : aucune interface                    → pas de Frontend Developer
→ Étape 2 : infrastructure, pas d'API métier    → pas de Backend Developer standard
→ Étape 3 : déploiement, conteneurs, CI/CD      → DevOps Engineer ✓
→ ["DevOps Engineer"], ["AWS", "Docker", "Kubernetes", "CI/CD"], SENIOR

Story : "Afficher les résultats de l'analyse IA dans un tableau de bord"
→ Étape 1 : tableau de bord                     → Frontend Developer ✓
→ Étape 2 : API qui fournit les données         → Backend Developer ✓
→ Étape 3 : PAS AI Engineer (affiche seulement) → aucun
→ ["Frontend Developer", "Backend Developer"], ["React.js", "TypeScript", "REST API", "UI/UX Design"], MID

Story : "Consulter les épics générés par l'IA" (story triviale, 2 SP)
→ Étape 1 : affichage simple                    → Frontend Developer ✓
→ Étape 2 : lecture API simple                  → peut être Full Stack si trivial
→ Étape 3 : aucun
→ ["Full Stack Developer"], ["React.js", "REST API"], JUNIOR

Rappels critiques :
- Presque toutes les stories d'une application web ont Frontend Developer + Backend Developer.
- Full Stack Developer uniquement pour les stories triviales (lecture simple, 1–2 SP).
- AI Engineer uniquement si la story IMPLÉMENTE de la logique IA/NLP, pas si elle l'affiche ou la déclenche.
- Interdits dans required_skills : "File Upload", "Form Handling", "Filtering UI", "Business Logic",
  "CRUD", "Document Management", "Project Management", "Afficher tableau", "Upload fichier", etc.

Retourne UNIQUEMENT ce JSON :
{{
  "stories_profiles": [
    {{
      "story_id": <story_id entier exactement comme fourni>,
      "required_profiles": ["<profil1>", "<profil2>"],
      "required_skills": ["<skill1>", "<skill2>", "<skill3>"],
      "required_level": "JUNIOR|MID|SENIOR"
    }}
  ]
}}

Contraintes de sortie :
- La liste doit contenir exactement {len(stories)} entrées.
- Chaque story_id fourni doit apparaître exactement une seule fois.
- Ne crée pas de nouveaux story_id.
- N'ignore aucune story.
- N'ajoute aucun texte hors JSON."""
