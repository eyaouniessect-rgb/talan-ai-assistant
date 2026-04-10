# orchestrator/utils/text.py
#
# Utilitaires de traitement de texte partagés entre node1 et node3.
# Regroupés ici pour éviter la duplication entre les deux nodes.
#
# Fonctions :
#   - _extract_clean_text     : extrait le texte lisible d'une réponse JSON ou brute
#   - _strip_markdown_tables  : supprime les tableaux Markdown (économie de tokens)
#   - _build_history          : formate l'historique de conversation pour le contexte LLM
#   - _is_chat_only           : détecte les messages de salutation / politesse
#   - _is_gibberish           : détecte les messages sans sens (pas de voyelles, etc.)
#   - _normalize_french       : normalise les fautes de frappe courantes en français

import json
import re
import unicodedata
from typing import Optional


# ─────────────────────────────────────────────
# Constantes partagées
# ─────────────────────────────────────────────

# Longueur max d'une réponse IA dans l'historique (économie de tokens)
MAX_AI_RESPONSE_CHARS = 300

# Préfixes des messages d'erreur système à exclure de l'historique
_ERROR_PREFIXES = ("⚠️", "Erreur lors du traitement", "Une erreur inattendue")

# Tokens de salutation/politesse → routage direct vers agent "chat" sans LLM
_CHAT_ONLY_TOKENS = {
    "bonjour", "salut", "hello", "bonsoir", "hi", "coucou",
    "merci", "ok merci", "super merci", "merci beaucoup",
    "au revoir", "bonne journée", "bonne journee", "à bientôt", "a bientot",
    "bonne soirée", "bonne soiree",
}

# Fautes de frappe fréquentes en français → correction avant analyse
_FRENCH_TYPOS = {
    "conje": "conge", "conjes": "conges", "conjer": "conger",
    "réuion": "reunion", "reunoin": "reunion",
    "absense": "absence", "absance": "absence",
}


# ─────────────────────────────────────────────
# Extraction de texte depuis une réponse agent
# ─────────────────────────────────────────────

def _extract_clean_text(content: str) -> str:
    """
    Extrait le texte lisible depuis une réponse agent.
    Si la réponse est un JSON avec un champ "response", retourne ce champ.
    Sinon retourne le contenu brut tel quel.
    Utilisée dans node1 (historique LLM) et node3 (assemblage réponse finale).
    """
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed.get("response", content)
        return content
    except (json.JSONDecodeError, TypeError):
        return content


# ─────────────────────────────────────────────
# Nettoyage des réponses pour l'historique
# ─────────────────────────────────────────────

def _strip_markdown_tables(text: str) -> str:
    """
    Supprime les lignes de tableau Markdown (| ... |) d'une réponse.
    Réduit le nombre de tokens envoyés au LLM dans l'historique.
    Exemple : "| col1 | col2 |" et "|---|---|" sont supprimées.
    """
    result = []
    for line in text.split("\n"):
        # Ignorer les lignes de tableau et les séparateurs (|---|)
        if line.strip().startswith("|"):
            continue
        result.append(line)
    return "\n".join(result).strip()


# ─────────────────────────────────────────────
# Construction de l'historique de conversation
# ─────────────────────────────────────────────

def _build_history(trimmed_messages: list) -> str:
    """
    Formate les derniers messages en un historique lisible pour le contexte des agents.
    Utilisée dans node3 pour injecter le contexte dans chaque appel A2A.
    - Exclut les messages d'erreur système
    - Tronque les réponses IA trop longues
    - Supprime les tableaux Markdown des réponses IA
    """
    lines = []
    for msg in trimmed_messages[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        clean = _extract_clean_text(msg.content)

        # Exclure les messages d'erreur système (quota, contexte trop long...)
        if msg.type != "human" and any(clean.startswith(p) for p in _ERROR_PREFIXES):
            continue

        # Supprimer les tableaux Markdown pour économiser des tokens
        if msg.type != "human":
            clean = _strip_markdown_tables(clean)

        # Tronquer les réponses IA trop longues
        if msg.type != "human" and len(clean) > MAX_AI_RESPONSE_CHARS:
            clean = clean[:MAX_AI_RESPONSE_CHARS] + "... [tronqué]"

        lines.append(f"{role}: {clean}")
    return "\n".join(lines)


def _build_history_for_llm(trimmed_messages: list, max_ai_chars: int = 200) -> str:
    """
    Formate les derniers messages en historique pour le prompt du LLM planificateur.
    Utilisée dans node1 pour fournir le contexte de continuation au planner.
    Version plus agressive que _build_history : tronque plus tôt (200 chars par défaut).
    """
    lines = []
    for msg in trimmed_messages[:-1]:
        role = "Utilisateur" if msg.type == "human" else "Assistant"
        content = msg.content if msg.type == "human" else _extract_clean_text(msg.content)

        # Exclure les messages d'erreur pour ne pas polluer le contexte LLM
        if msg.type != "human" and any(content.startswith(p) for p in _ERROR_PREFIXES):
            continue

        # Tronquer les longues réponses IA
        if msg.type != "human" and len(content) > max_ai_chars:
            content = content[:max_ai_chars] + "..."

        lines.append(f"{role}: {content}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# Classification du message entrant (fast paths)
# ─────────────────────────────────────────────

def _is_chat_only(text: str) -> bool:
    """
    Retourne True si le message est une salutation ou politesse pure.
    Permet d'éviter un appel LLM pour les messages triviaux (fast path node1).
    Exemple : "bonjour", "merci", "au revoir" → True
    """
    clean = text.lower().strip().rstrip("!?.,")
    clean = " ".join(clean.split())
    return clean in _CHAT_ONLY_TOKENS


def _is_gibberish(text: str) -> bool:
    """
    Détecte les messages sans sens (suites de consonnes, texte trop court...).
    Permet de router directement vers "chat" sans appel LLM (fast path node1).
    Critères :
      - Ratio voyelles < 15% sur un texte de 5+ caractères alphabétiques
      - Suite de 6+ consonnes consécutives
    """
    clean = text.lower().strip()
    if not clean:
        return True
    if _is_chat_only(clean):
        return False

    # Extraire uniquement les lettres alphabétiques
    alpha_only = re.sub(r"[^a-zàâäéèêëïîôùûüÿçœæ]", "", clean)
    if len(alpha_only) < 3:
        return False

    # Vérifier le ratio de voyelles
    voyelles = set("aeiouyàâäéèêëïîôùûüÿœæ")
    n_voyelles = sum(1 for c in alpha_only if c in voyelles)
    ratio = n_voyelles / len(alpha_only) if alpha_only else 0

    if len(alpha_only) >= 5 and ratio < 0.15:
        return True
    if re.search(r"[^aeiouyàâäéèêëïîôùûüÿœæ]{6,}", alpha_only):
        return True
    return False


# ─────────────────────────────────────────────
# Normalisation du français
# ─────────────────────────────────────────────

def _normalize_french(text: str) -> str:
    """
    Normalise les fautes de frappe courantes en français et supprime les accents.
    Utilisée dans _keyword_fallback (routing.py) pour améliorer la détection de mots-clés.
    Exemple : "conge" → "conge", "réuion" → "reunion"
    """
    # Supprimer les accents (NFD → filtrer les combining marks)
    nfkd = unicodedata.normalize("NFD", text)
    normalized = "".join(c for c in nfkd if unicodedata.category(c) != "Mn")

    # Corriger les fautes de frappe connues
    for typo, fix in _FRENCH_TYPOS.items():
        normalized = normalized.replace(typo, fix)

    return normalized
