# orchestrator/utils/routing.py
#
# Utilitaires de routage partagés entre node1 et node3.
#
# Contenu :
#   - AGENT_DISPLAY_NAMES    : noms affichables pour les messages UI/fallback
#   - AGENT_KEYWORD_MAP      : mots-clés par agent (utilisé par _keyword_fallback)
#   - _keyword_fallback      : routage par mots-clés (dernier recours si LLM échoue)
#   - _parse_llm_json        : extraction robuste du JSON depuis la réponse LLM brute

import json
import re
from app.orchestrator.utils.text import _normalize_french


# ─────────────────────────────────────────────
# Noms affichables des agents (UI & messages de fallback)
# ─────────────────────────────────────────────

AGENT_DISPLAY_NAMES: dict[str, str] = {
    "rh":       "RH (gestion des congés)",
    "calendar": "Calendrier",
    "jira":     "Jira",
    "slack":    "Slack",
    "crm":      "CRM",
    "chat":     "Assistant",
}


# ─────────────────────────────────────────────
# Mots-clés par agent (fallback keyword routing)
# ─────────────────────────────────────────────
# Chaque set contient des mots-clés simples ou des expressions (plusieurs mots).
# Les expressions multi-mots ont un poids doublé → moins de faux positifs.

AGENT_KEYWORD_MAP: dict[str, set[str]] = {
    "slack": {
        "slack", "notifie", "notifier", "notifier sur",
        "message à", "préviens", "previens", "envoie à",
        "envoyer un message",
    },
    "calendar": {
        "réunion", "reunion", "meeting", "agenda",
        "calendrier", "créneau", "creneau",
        "horaire", "rendez-vous", "rendez vous",
        "disponibilité", "disponibilite",
    },
    "rh": {
        "congé", "conge", "conges", "congés",
        "solde", "absence", "absences",
        "équipe", "equipe", "collaborateur",
        "poser un congé", "poser un conge",
        "compétence", "competence",
    },
    "jira": {
        "jira", "ticket", "tickets", "issue", "issues",
        "sprint", "backlog", "story", "bug", "tâche jira",
    },
    "crm": {
        "client", "clients", "projet crm", "contact",
        "contrat", "opportunité", "opportunite",
    },
}


# ─────────────────────────────────────────────
# Routage par mots-clés (fallback)
# ─────────────────────────────────────────────

def _keyword_fallback(text: str, keyword_map: dict[str, set[str]] = None) -> str | None:
    """
    Détermine l'agent le plus probable par correspondance de mots-clés.
    Utilisée dans node1 comme dernier recours quand le LLM échoue.

    Algorithme de scoring :
      - Expression multi-mots → poids x2 (plus spécifique)
      - Mot-clé long (> 8 chars) → bonus +1
      - Si l'écart entre le meilleur et le 2ème < 25 % → ambigu → retourne None

    Retourne le nom de l'agent, ou None si ambiguïté ou aucun match.
    """
    if keyword_map is None:
        keyword_map = AGENT_KEYWORD_MAP

    t = text.lower()
    t_norm = _normalize_french(t)
    t_words = set(re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ]+", t))
    t_norm_words = set(re.findall(r"[a-zàâäéèêëïîôùûüÿçœæ]+", t_norm))

    scores: dict[str, float] = {}
    for agent, tags in keyword_map.items():
        score = 0.0
        for kw in tags:
            kw_lower = kw.lower()
            # Correspondance directe (sous-chaîne) ou normalisée
            matched = kw_lower in t or kw_lower in t_norm
            if not matched and " " in kw_lower:
                # Correspondance par ensemble de mots pour les expressions
                kw_words = set(kw_lower.split())
                matched = kw_words.issubset(t_words) or kw_words.issubset(t_norm_words)
            if matched:
                word_count = len(kw_lower.split())
                # Expressions multi-mots = poids double
                weight = word_count * 2.0 if word_count > 1 else 1.0
                # Bonus pour les mots-clés longs (très spécifiques)
                if len(kw_lower) > 8:
                    weight += 1.0
                score += weight
        if score > 0:
            scores[agent] = score

    if not scores:
        return None

    # Tri décroissant par score
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Si le meilleur et le 2ème sont trop proches → ambiguïté → None
    if len(ranked) >= 2:
        best, second = ranked[0][1], ranked[1][1]
        if best > 0 and (best - second) / best < 0.25:
            return None

    return ranked[0][0]


# ─────────────────────────────────────────────
# Extraction du JSON depuis la réponse LLM brute
# ─────────────────────────────────────────────

def _parse_llm_json(raw: str) -> dict | None:
    """
    Extrait et parse le JSON de la réponse brute du LLM planificateur.
    Gère trois cas :
      1. Réponse JSON pure
      2. JSON encapsulé dans un bloc ```json ... ```
      3. JSON tronqué (max_tokens atteint) → récupération partielle des steps valides

    Retourne un dict {"steps": [...]} ou None si impossible à parser.
    """
    content = raw.strip()

    # ── Cas 2 : bloc markdown ```json ─────────────────────────
    if "```" in content:
        start_idx = content.find("```")
        end_idx = content.rfind("```")
        if start_idx != -1 and end_idx > start_idx:
            block = content[start_idx + 3:end_idx].strip()
            # Enlever le tag "json" si présent
            if block.startswith("json"):
                block = block[4:].strip()
            content = block

    # ── Cas 1 : extraire les accolades ────────────────────────
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1 or end == 0:
        return None
    json_str = content[start:end]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # ── Cas 3 : récupération partielle (JSON tronqué) ─────────
    # Tente d'extraire les steps déjà complets (objets { } fermés)
    print("JSON tronqué detecte, tentative de recuperation partielle...")
    steps_start = json_str.find('"steps"')
    if steps_start == -1:
        return None
    arr_start = json_str.find("[", steps_start)
    if arr_start == -1:
        return None

    steps = []
    i = arr_start + 1
    depth = 0
    step_start_idx = None

    while i < len(json_str):
        c = json_str[i]
        if c == "{":
            if depth == 0:
                step_start_idx = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and step_start_idx is not None:
                step_str = json_str[step_start_idx:i + 1]
                try:
                    step_obj = json.loads(step_str)
                    # Valide les champs minimaux obligatoires
                    if "agent" in step_obj and "task" in step_obj:
                        steps.append(step_obj)
                except json.JSONDecodeError:
                    pass
                step_start_idx = None
        i += 1

    if steps:
        print(f"   Recuperation partielle : {len(steps)} step(s) extraits")
        return {"steps": steps}

    return None
