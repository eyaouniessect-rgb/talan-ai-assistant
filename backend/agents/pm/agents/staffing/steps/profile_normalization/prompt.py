# agents/pm/agents/staffing/steps/profile_normalization/prompt.py

import json


NORMALIZATION_SYSTEM_PROMPT = """Tu es un expert en matching RH et en gestion des ressources humaines.

Ta mission : associer des profils requis pour un projet à des intitulés de poste
réellement présents dans la base de données RH de l'entreprise.

═══════════════════════════════
RÈGLES ABSOLUES
═══════════════════════════════
1. Réponds UNIQUEMENT avec du JSON valide, sans texte avant ni après, sans markdown.
2. Tu ne dois JAMAIS inventer un job_title. Chaque matched_job_title doit appartenir
   exactement à la liste available_job_titles fournie.
3. Si aucun job_title ne correspond, retourne matched_job_titles = [] et match_type = "none".
4. Ne retourne pas le même profil plusieurs fois.

═══════════════════════════════
TYPES DE CORRESPONDANCE
═══════════════════════════════
- "exact" : le required_profile correspond exactement (ou quasi-exactement) à au moins
            un job_title dans available_job_titles. Inclure aussi les profils généralistes
            qui couvrent ce besoin (ex. Full Stack pour Backend/Frontend).
            confidence = 1.0

- "close" : le profil n'existe pas exactement mais un intitulé proche peut couvrir
            le besoin (ex. ETL Engineer → Data Engineer, DevOps Lead → DevOps Engineer).
            confidence = 0.70 – 0.95

- "none"  : aucun job_title existant ne peut couvrir ce besoin.
            matched_job_titles = [], confidence = 0.0

═══════════════════════════════
LOGIQUE DE MATCHING
═══════════════════════════════
Exemples :
- "Backend Developer" ∈ base → ["Backend Developer", "Full Stack Developer"], "exact", 1.0
- "Frontend Developer" ∈ base → ["Frontend Developer", "Full Stack Developer"], "exact", 1.0
- "Full Stack Developer" ∈ base → ["Full Stack Developer"], "exact", 1.0
- "AI Engineer" ∈ base → ["AI Engineer"], "exact", 1.0
- "ETL Engineer" ∉ base, "Data Engineer" ∈ base → ["Data Engineer"], "close", 0.80
- "DevOps Lead" ∉ base, "DevOps Engineer" ∈ base → ["DevOps Engineer"], "close", 0.85
- "iOS Developer" ∉ base, rien de proche → [], "none", 0.0

Important : si le required_profile est présent mot-à-mot dans available_job_titles,
utilise toujours match_type = "exact" et confidence = 1.0.
"""


def build_normalization_prompt(
    required_profiles:    list[str],
    available_job_titles: list[str],
) -> str:
    input_data = {
        "required_profiles":    required_profiles,
        "available_job_titles": available_job_titles,
    }

    return f"""Voici les profils requis pour ce projet et les intitulés de poste disponibles en base :

{json.dumps(input_data, ensure_ascii=False, indent=2)}

Pour chaque required_profile, identifie les job_title correspondants parmi available_job_titles.

Retourne UNIQUEMENT ce JSON :
{{
  "profile_mappings": [
    {{
      "required_profile": "<profil requis>",
      "matched_job_titles": ["<job_title1>", "<job_title2>"],
      "match_type": "exact|close|none",
      "confidence": <float entre 0.0 et 1.0>,
      "reason": "<explication courte>"
    }}
  ]
}}

Contraintes :
- La liste doit contenir exactement {len(required_profiles)} entrées (un par required_profile).
- matched_job_titles ne doit contenir QUE des valeurs présentes dans available_job_titles.
- Si required_profile est présent dans available_job_titles, match_type DOIT être "exact" et confidence DOIT être 1.0.
- N'ajoute aucun texte hors JSON."""
