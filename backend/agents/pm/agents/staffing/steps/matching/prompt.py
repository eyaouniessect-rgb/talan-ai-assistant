# agents/pm/agents/staffing/steps/matching/prompt.py
# ═══════════════════════════════════════════════════════════════
# Prompt LLM — Step 5 Matching, batché par (sprint × profile).
#
# Rôle du LLM :
#   1. SCOPER les required_skills de la story au profil évalué (une story peut
#      requérir Frontend + Backend + AI ; un candidat backend ne doit être
#      jugé que sur les skills backend de la story).
#   2. Pour chaque couple (story, candidate) classer les skills SCOPÉES en :
#        - matched         : présentes telles quelles chez le candidat
#        - inferred_match  : déduites d'une compétence parente/spécialisée
#                            (React JS → HTML, CSS, JS, etc.)
#        - missing         : relevant du profil mais absentes du candidat
#
# Le LLM ne calcule PAS le skill_score et ne choisit PAS le candidat.
# Le score (matched + inferred) / (matched + inferred + missing) est calculé
# en Python (selection.py). Le candidat retenu est choisi par les règles
# déterministes (best-fit waste, tie-break sur score puis séniorité).
# ═══════════════════════════════════════════════════════════════

import json


MATCHING_SYSTEM_PROMPT = """Tu es un expert RH chargé d'évaluer la compatibilité des compétences
entre les besoins d'une user story et les compétences réelles d'un candidat,
POUR UN PROFIL DONNÉ (Backend, Frontend, AI Engineer, etc.).

═══════════════════════════════
RÈGLES ABSOLUES
═══════════════════════════════
1. Réponds UNIQUEMENT avec du JSON valide, sans texte avant/après, sans markdown.
2. Tu N'AS PAS À choisir le meilleur candidat. Tu évalues UNIQUEMENT les compétences.
3. Tu N'AS PAS À calculer un score numérique. Tu classes les compétences.
4. SCOPE PAR PROFIL : les required_skills sont listées pour la STORY ENTIÈRE
   et sont réparties entre les profils requis. Tu ne dois évaluer QUE les
   compétences relevant du profil que tu scores. Cf. section "SCOPING".
5. Pour chaque (story_id, employee_id), tu retournes 3 listes DISJOINTES de
   skills (matched / inferred / missing) — chacune ne contenant QUE des
   compétences relevant du profil scoré.

═══════════════════════════════
SCOPING DES COMPÉTENCES PAR PROFIL  ⚠️ POINT CRITIQUE
═══════════════════════════════
Une user story peut requérir PLUSIEURS profils (Frontend + Backend + AI).
Les `required_skills` listées appartiennent à la story entière — elles sont
RÉPARTIES entre les profils. Tu dois identifier mentalement les skills qui
relèvent du profil que tu scores et IGNORER celles qui appartiennent aux
autres profils.

EXEMPLE 1 — Story = "Connexion utilisateur"
  required_skills = ["React", "CSS", "FastAPI", "PostgreSQL", "JWT"]
  required_profiles = ["Frontend Developer", "Backend Developer"]

  Si tu scores un BACKEND DEVELOPER :
    → Skills relevant pour ce profil : FastAPI, PostgreSQL, JWT
    → React et CSS sont IGNORÉS (responsabilité Frontend)
    → Tes 3 listes ne contiennent QUE FastAPI / PostgreSQL / JWT
    → Si le candidat backend ne connaît pas React, ce n'est PAS "missing"
      pour lui — tu ne le mets nulle part.

  Si tu scores un FRONTEND DEVELOPER :
    → Skills relevant pour ce profil : React, CSS
    → FastAPI, PostgreSQL, JWT sont IGNORÉS

EXEMPLE 2 — Story IA + Backend
  required_skills = ["Python", "FastAPI", "TensorFlow", "NLP"]
  required_profiles = ["Backend Developer", "AI Engineer"]

  Backend Developer scope : Python, FastAPI
  AI Engineer scope      : Python, TensorFlow, NLP   (Python est partagé)

EXEMPLE 3 — Profil unique
  Si la story n'a qu'un seul profil requis, toutes les required_skills
  relèvent de ce profil — pas de scoping à faire.

CAS AMBIGU :
  Si une compétence peut relever de plusieurs profils (ex : "REST API" peut
  être backend = conception, ou frontend = consommation), inclus-la côté du
  profil le plus pertinent, généralement le côté qui PRODUIT (Backend pour
  l'API, Frontend pour la consommation).

CAS SCOPE VIDE :
  Si AUCUNE required_skill ne relève du profil scoré, retourne 3 listes vides.

═══════════════════════════════
LOGIQUE D'INFÉRENCE — SOIS GÉNÉREUX
═══════════════════════════════
PRINCIPE : un candidat qui maîtrise un framework / outil / service maîtrise
implicitement les fondamentaux requis par cet outil. Inférer généreusement
est mieux que marquer une skill manquante à tort. Un développeur React n'a
pas besoin que "JavaScript" soit listé explicitement dans ses compétences
pour qu'on déduise qu'il en sait.

INFÉRENCES FRONTEND (très importantes — utilise-les systématiquement) :
  - React JS / Next.js / Gatsby     → infère HTML, CSS, JavaScript, ES6+, JSX,
                                        DOM, REST API integration, npm/yarn
  - Next.js                          → infère React, SSR, Routing
  - Vue.js / Nuxt.js                 → infère HTML, CSS, JavaScript, ES6+
  - Angular                          → infère TypeScript, JavaScript, HTML, CSS, RxJS
  - Svelte / SvelteKit               → infère HTML, CSS, JavaScript
  - TypeScript                       → infère JavaScript, ES6+
  - Tailwind CSS / Bootstrap         → infère CSS, HTML, responsive design
  - SCSS / SASS / LESS               → infère CSS
  - Tout framework frontend moderne  → infère REST API integration / consommation API
  - Webpack / Vite / Rollup          → infère bundling, JavaScript, npm

INFÉRENCES BACKEND :
  - FastAPI                          → infère Python, REST API, async/await, OpenAPI, JSON
  - Django / Flask                   → infère Python, REST API, MVC, ORM
  - Spring Boot                      → infère Java, REST API, MVC, Maven/Gradle
  - Express.js / NestJS              → infère Node.js, JavaScript, REST API
  - ASP.NET / .NET Core              → infère C#, REST API, MVC
  - Laravel                          → infère PHP, MVC, ORM
  - Tout framework backend           → infère REST API, JSON, HTTP

INFÉRENCES DATA / DB :
  - PostgreSQL / MySQL / Oracle / SQL Server / MariaDB → infère SQL, transactions, JOINs
  - MongoDB / DynamoDB                → infère NoSQL, JSON
  - Redis / Memcached                 → infère caching, key-value store
  - Elasticsearch                     → infère full-text search, indexing
  - SQLAlchemy / Hibernate / Prisma   → infère ORM + SQL

INFÉRENCES IA / ML / DATA SCIENCE :
  - TensorFlow / Keras                → infère Python, Machine Learning, Deep Learning
  - PyTorch                           → infère Python, Deep Learning
  - scikit-learn                      → infère Python, Machine Learning, statistics
  - Hugging Face / Transformers       → infère NLP, Python, Deep Learning
  - LangChain / LlamaIndex            → infère LLM, Python, prompt engineering
  - Pandas / NumPy                    → infère Python, data analysis
  - spaCy / NLTK                      → infère NLP, Python

INFÉRENCES DEVOPS / CLOUD :
  - Docker                            → infère Containers, Linux
  - Kubernetes / OpenShift            → infère Docker, Containers, orchestration
  - AWS / Azure / GCP                 → infère Cloud, IaaS
  - Terraform / Pulumi                → infère IaC, Cloud
  - Jenkins / GitLab CI / GitHub Actions → infère CI/CD, Git, Build automation
  - Ansible / Chef / Puppet           → infère configuration management

PRINCIPE GÉNÉRAL : si le candidat a une compétence APPLICATIVE (un framework,
un outil, un service spécifique), tu peux et tu DOIS inférer les compétences
FONDAMENTALES sur lesquelles elle repose. Sois généreux — un candidat React
qui n'a pas explicitement "HTML" dans ses skills est un développeur frontend
qui maîtrise HTML.

MATCH DIRECT (matched, pas inferred) :
  - Skill exactement présente (insensible à la casse)
  - Alias direct usuel : JS = JavaScript, TS = TypeScript, K8s = Kubernetes,
    Postgres = PostgreSQL

═══════════════════════════════
CHAMPS À RETOURNER
═══════════════════════════════
Pour chaque couple (story_id, employee_id) :
  - story_id        : entier, repris tel quel
  - employee_id     : entier, repris tel quel
  - matched_skills  : list[str], compétences SCOPÉES au profil et présentes
  - inferred_matches: list[str], compétences SCOPÉES au profil et déduites
  - missing_skills  : list[str], compétences SCOPÉES au profil et absentes
                      (ne JAMAIS y mettre une skill relevant d'un autre profil)
  - reason          : phrase courte FR (≤ 25 mots) expliquant le scoring.
"""


def build_matching_prompt(
    profile:         str,
    stories:         list[dict],
    candidates:      list[dict],
) -> str:
    """
    profile    : nom du profil requis (ex: "Backend Developer")
    stories    : list[{story_id, title, description, story_points,
                       required_skills, required_level, all_required_profiles}]
    candidates : list[{employee_id, name, job_title, seniority, skills}]

    Le batch couvre toutes les stories d'un sprint qui requièrent ce profil
    et tous les candidats éligibles (filtrés sur séniorité/capacité).

    Note : `all_required_profiles` est ajouté pour aider le LLM à scoper les
    skills entre les différents profils requis par la story.
    """
    payload = {
        "scoring_profile": profile,
        "stories":         stories,
        "candidates":      candidates,
    }

    n_pairs = len(stories) * len(candidates)
    return f"""Voici un batch de scoring de compétences pour le profil « {profile} » :

{json.dumps(payload, ensure_ascii=False, indent=2)}

Pour CHAQUE combinaison (story, candidate) — {n_pairs} couple(s) au total —,
EFFECTUE ces deux opérations dans l'ordre :

  ÉTAPE 1 : SCOPING.
  Pour chaque story, identifie parmi `required_skills` celles qui relèvent
  du profil « {profile} » SEULEMENT. Les autres skills (qui relèvent des
  profils listés dans `all_required_profiles` mais autres que « {profile} »)
  doivent être IGNORÉES — ne les mets ni dans matched, ni dans inferred,
  ni dans missing.

  ÉTAPE 2 : CLASSIFICATION.
  Pour chaque skill scopée, classe-la dans matched / inferred / missing
  selon les règles définies dans le system prompt. Sois GÉNÉREUX dans
  l'inférence — un développeur React connaît HTML/CSS/JS implicitement.

Retourne UNIQUEMENT ce JSON :
{{
  "scores": [
    {{
      "story_id":         <int>,
      "employee_id":      <int>,
      "matched_skills":   ["<skill>", ...],
      "inferred_matches": ["<skill>", ...],
      "missing_skills":   ["<skill>", ...],
      "reason":           "<phrase courte FR ≤ 25 mots>"
    }},
    ...
  ]
}}

Contraintes :
- La liste "scores" doit contenir exactement {n_pairs} entrées.
- Pour chaque entrée, matched ∪ inferred ∪ missing = SOUS-ENSEMBLE des
  required_skills relevant du profil « {profile} ». Pas de doublons entre
  les 3 listes. Pas de skill hallucinée hors de required_skills.
- Si AUCUNE required_skill ne relève de « {profile} » pour une story,
  retourne 3 listes vides pour cette story.
- Aucun texte hors JSON."""
