# app/core/groq_client.py
# ═══════════════════════════════════════════════════════════
# Gestion de la tolérance aux pannes pour les clés API Groq.
# Si une clé tombe (rate limit, invalidée...), la suivante prend le relais.
#
# Deux modes d'utilisation :
#   1. invoke_with_fallback() → pour Node 1 et Node 3 (appels directs)
#   2. build_llm()            → pour l'agent RH ReAct (objet ChatOpenAI)
# ═══════════════════════════════════════════════════════════

import os
import logging
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
# Chargement des clés
# ══════════════════════════════════════════════════════

def _load_keys() -> list[str]:
    load_dotenv()
    keys = []
    for i in range(1, 10):
        key = os.getenv(f"GROQ_API_KEY_{i}")
        if key:
            keys.append(key)
    if not keys:
        key = os.getenv("GROQ_API_KEY")
        if key:
            keys.append(key)
    if not keys:
        raise ValueError("Aucune clé API Groq trouvée dans le .env")
    logger.info(f"Groq : {len(keys)} clé(s) chargée(s)")
    return keys


# ══════════════════════════════════════════════════════
# Erreurs qui déclenchent le fallback
# ══════════════════════════════════════════════════════

FALLBACK_ERRORS = (
    "rate_limit_exceeded",
    "invalid_api_key",
    "authentication_error",
    "quota_exceeded",
    "insufficient_quota",
    "503",
    "502",
    "529",
)

# Erreurs de dépassement de quota/tokens (rotation de clé inutile — même limite)
QUOTA_ERRORS = (
    "request too large",
    "tokens per minute",
    "413",
    "context_length_exceeded",
    "maximum context length",
)

FRIENDLY_QUOTA_MSG = (
    "⚠️ Le service IA est temporairement indisponible : limite de tokens atteinte.\n"
    "Cela se produit lorsque la conversation est très longue ou que le quota minute est épuisé.\n"
    "**Que faire ?**\n"
    "- Patientez quelques secondes et réessayez\n"
    "- Ou démarrez une nouvelle conversation (bouton ✚ en haut à gauche)"
)


def _is_fallback_error(error: Exception) -> bool:
    error_str = str(error).lower()
    return any(code in error_str for code in FALLBACK_ERRORS)


def _is_quota_error(error: Exception) -> bool:
    """Retourne True si l'erreur est un dépassement de quota/tokens (rotation inutile)."""
    error_str = str(error).lower()
    return any(code in error_str for code in QUOTA_ERRORS)


# ══════════════════════════════════════════════════════
# Mode 1 : invoke_with_fallback (Node 1 + Node 3)
# ══════════════════════════════════════════════════════

async def invoke_with_fallback(
    model: str,
    messages: list,
    max_tokens: int = 512,
    temperature: float = 0,
) -> str:
    """
    Appelle le modèle Groq avec rotation automatique des clés.
    Utilisé par Node 1 (intent) et Node 3 (chat).
    """
    keys = _load_keys()
    last_error = None

    for i, key in enumerate(keys):
        try:
            logger.debug(f"Groq : tentative avec clé #{i+1}")
            llm = ChatOpenAI(
                base_url="https://api.groq.com/openai/v1",
                api_key=key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response = await llm.ainvoke(messages)
            if i > 0:
                logger.info(f"Groq : clé #{i+1} a pris le relais")
            return response.content

        except Exception as e:
            last_error = e
            if _is_quota_error(e):
                # Quota tokens/minute dépassé → inutile de tourner, on sort immédiatement
                logger.warning(f"Groq : quota tokens dépassé (clé #{i+1}) : {str(e)[:120]}")
                raise RuntimeError(FRIENDLY_QUOTA_MSG) from e
            elif _is_fallback_error(e):
                logger.warning(f"Groq : clé #{i+1} échouée ({type(e).__name__}: {str(e)[:80]}) → essai suivant")
                continue
            else:
                logger.error(f"Groq : erreur non-récupérable avec clé #{i+1} : {e}")
                raise

    logger.error(f"Groq : toutes les clés ont échoué. Dernière erreur : {last_error}")
    if last_error and _is_quota_error(last_error):
        raise RuntimeError(FRIENDLY_QUOTA_MSG) from last_error
    raise RuntimeError(f"Toutes les clés Groq sont épuisées. Dernière erreur : {last_error}")


# ══════════════════════════════════════════════════════
# Mode 2 : build_llm (Agent RH ReAct)
# ══════════════════════════════════════════════════════

# Index global de la clé active — partagé entre tous les appels
_current_key_index = 0

def build_llm(
    model: str = "openai/gpt-oss-120b",
    temperature: float = 0,
    max_tokens: int = 2048,
) -> ChatOpenAI:
    """
    Construit un ChatOpenAI avec la clé active.
    Utilisé par l'agent RH ReAct (create_react_agent).
    """
    global _current_key_index
    keys = _load_keys()
    _current_key_index = min(_current_key_index, len(keys) - 1)

    logger.info(f"Groq build_llm : utilise clé #{_current_key_index + 1}/{len(keys)}")

    return ChatOpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=keys[_current_key_index],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def rotate_llm_key() -> bool:
    """
    Passe à la clé suivante. Retourne True si une clé est disponible,
    False si toutes les clés ont été essayées.
    """
    global _current_key_index
    keys = _load_keys()
    _current_key_index += 1

    if _current_key_index >= len(keys):
        _current_key_index = 0  # reset pour la prochaine fois
        logger.error("Groq : toutes les clés ont été essayées")
        return False

    logger.warning(f"Groq : rotation vers clé #{_current_key_index + 1}/{len(keys)}")
    return True