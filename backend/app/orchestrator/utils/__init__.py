# orchestrator/utils/__init__.py
#
# Point d'entrée du package utilitaires de l'orchestrateur.
# Re-exporte les fonctions publiques utilisées par node1 et node3.
#
# Modules :
#   - text.py        : traitement de texte (historique, nettoyage, classification)
#   - routing.py     : routage par mots-clés, parsing JSON LLM, noms agents
#   - google_auth.py : vérification token Google Calendar

from app.orchestrator.utils.text import (
    _extract_clean_text,
    _strip_markdown_tables,
    _build_history,
    _build_history_for_llm,
    _is_chat_only,
    _is_gibberish,
    _normalize_french,
)

from app.orchestrator.utils.routing import (
    AGENT_DISPLAY_NAMES,
    AGENT_KEYWORD_MAP,
    _keyword_fallback,
    _parse_llm_json,
)

from app.orchestrator.utils.google_auth import (
    _check_google_token,
)

__all__ = [
    # text
    "_extract_clean_text",
    "_strip_markdown_tables",
    "_build_history",
    "_build_history_for_llm",
    "_is_chat_only",
    "_is_gibberish",
    "_normalize_french",
    # routing
    "AGENT_DISPLAY_NAMES",
    "AGENT_KEYWORD_MAP",
    "_keyword_fallback",
    "_parse_llm_json",
    # google_auth
    "_check_google_token",
]
