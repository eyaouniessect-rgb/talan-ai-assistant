# app/core/groq_client.py
# ═══════════════════════════════════════════════════════════
# Gestion des providers LLM avec fallback :
#   1. NVIDIA NIM (openai/gpt-oss-120b — 128k context)  ← primaire
#   2. Groq (openai/gpt-oss-120b — 8k TPM)              ← fallback (9 clés)
#
# Deux modes d'utilisation :
#   1. invoke_with_fallback() → pour Node 1 et Node 3 (appels directs)
#   2. build_llm()            → pour l'agent RH ReAct (objet ChatOpenAI)
# ═══════════════════════════════════════════════════════════

import os
import asyncio
import logging
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL   = "https://api.groq.com/openai/v1"


# ══════════════════════════════════════════════════════
# Chargement des clés
# ══════════════════════════════════════════════════════

def _load_nvidia_key() -> str | None:
    load_dotenv()
    return os.getenv("NVIDIA_API_KEY") or None


def _load_keys(agent_offset: int = 0) -> list[str]:
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

    # Rotation basée sur PID + offset fixe par agent.
    if len(keys) > 1:
        offset = (os.getpid() + agent_offset) % len(keys)
        keys = keys[offset:] + keys[:offset]

    logger.info(f"Groq : {len(keys)} clé(s) | PID={os.getpid()} agent_offset={agent_offset} → clé #{(os.getpid() + agent_offset) % len(keys) + 1}")
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

# Erreurs TPM (tokens-per-minute) — rotation de clé + attente peut aider
TPM_ERRORS = (
    "tokens per minute",
    "rate_limit_exceeded",
    "quota_exceeded",
    "insufficient_quota",
)

# Erreurs de contexte trop long — rotation inutile, contexte identique
CONTEXT_ERRORS = (
    "request too large",
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

FRIENDLY_CONTEXT_MSG = (
    "⚠️ La conversation est trop longue pour être traitée.\n"
    "**Que faire ?**\n"
    "- Démarrez une nouvelle conversation (bouton ✚ en haut à gauche)\n"
    "- Ou reformulez votre demande de façon plus concise"
)


def _is_fallback_error(error: Exception) -> bool:
    error_str = str(error).lower()
    return any(code in error_str for code in FALLBACK_ERRORS)


def _is_tpm_error(error: Exception) -> bool:
    """Retourne True si c'est une limite TPM (rotation + attente peut aider).
    Retourne False si c'est en réalité une erreur de taille de requête."""
    error_str = str(error).lower()
    # "request too large" prend la priorité — c'est une erreur de taille, pas de quota
    if "request too large" in error_str:
        return False
    return any(code in error_str for code in TPM_ERRORS)


def _is_context_error(error: Exception) -> bool:
    """Retourne True si la requête est trop grande (413 / request too large)."""
    error_str = str(error).lower()
    if "request too large" in error_str:
        return True
    return any(code in error_str for code in CONTEXT_ERRORS)


# ══════════════════════════════════════════════════════
# Extraction du texte depuis une réponse LangChain
# ══════════════════════════════════════════════════════

def _extract_text(response) -> str:
    """
    Extrait le texte d'une réponse LangChain.

    response.content peut être :
      - str  : cas normal → retourné tel quel
      - list : blocs de contenu [{"type":"text","text":"..."}]
               → concatène les blocs "text"
      - ""   : réponse vide ("No message content") → retourne ""
    """
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts)
    return ""


# ══════════════════════════════════════════════════════
# Mode 1 : invoke_with_fallback (Node 1 + Node 3)
# ══════════════════════════════════════════════════════

async def invoke_with_fallback(
    model: str,
    messages: list,
    max_tokens: int = 512,
    temperature: float = 0,
    agent_offset: int = 0,
) -> str:
    """
    Appelle le modèle avec fallback :
      1. NVIDIA NIM (128k context) — si NVIDIA_API_KEY présente
      2. Groq keys (9 clés en rotation) — si NVIDIA échoue ou absent
    """
    # ── Tentative NVIDIA ───────────────────────────────
    nvidia_key = _load_nvidia_key()
    if nvidia_key:
        try:
            print(f"🟢 [NVIDIA] Tentative avec {model} (128k context)")
            llm = ChatOpenAI(
                base_url=NVIDIA_BASE_URL,
                api_key=nvidia_key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response = await llm.ainvoke(messages)
            print(f"✅ [NVIDIA] Succès")
            return _extract_text(response)
        except Exception as e:
            if _is_context_error(e):
                # Même avec 128k, si le contexte est dépassé → message direct
                logger.warning(f"NVIDIA : contexte trop long : {str(e)[:120]}")
                raise RuntimeError(FRIENDLY_CONTEXT_MSG) from e
            # Toute autre erreur NVIDIA → fallback Groq
            print(f"⚠️ [NVIDIA] Échec ({type(e).__name__}: {str(e)[:80]}) → fallback Groq")
            logger.warning(f"NVIDIA échec → fallback Groq : {str(e)[:120]}")

    # ── Fallback Groq (9 clés en rotation) ────────────
    keys = _load_keys(agent_offset)
    last_error = None

    for i, key in enumerate(keys):
        try:
            key_preview = key[:8] + "..."
            print(f"🔑 [Groq] Tentative avec clé #{i+1}/{len(keys)} ({key_preview})")
            llm = ChatOpenAI(
                base_url=GROQ_BASE_URL,
                api_key=key,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response = await llm.ainvoke(messages)
            if i > 0:
                print(f"✅ [Groq] Clé #{i+1} a pris le relais avec succès")
            return _extract_text(response)

        except Exception as e:
            last_error = e
            if _is_context_error(e):
                logger.warning(f"Groq : contexte trop long (clé #{i+1}) : {str(e)[:120]}")
                raise RuntimeError(FRIENDLY_CONTEXT_MSG) from e
            elif _is_tpm_error(e):
                print(f"⚠️ [Groq] TPM dépassé (clé #{i+1}) → rotation vers clé #{i+2} + attente 3s")
                await asyncio.sleep(3)
                continue
            elif _is_fallback_error(e):
                logger.warning(f"Groq : clé #{i+1} échouée ({type(e).__name__}: {str(e)[:80]}) → essai suivant")
                continue
            else:
                logger.error(f"Groq : erreur non-récupérable avec clé #{i+1} : {e}")
                raise

    logger.error(f"Tous les providers ont échoué. Dernière erreur : {last_error}")
    raise RuntimeError(FRIENDLY_QUOTA_MSG) from last_error


# ══════════════════════════════════════════════════════
# Mode 2 : build_llm (Agent RH ReAct)
# ══════════════════════════════════════════════════════

# Index global de la clé Groq active (fallback)
_current_key_index = 0
_agent_offset: int = 0


def set_agent_offset(offset: int):
    """À appeler au démarrage de chaque agent avec son offset fixe."""
    global _agent_offset
    _agent_offset = offset


def build_llm(
    model: str = "openai/gpt-oss-120b",
    temperature: float = 0,
    max_tokens: int = 2048,
    force_groq: bool = False,
) -> ChatOpenAI:
    """
    Construit un ChatOpenAI :
      - NVIDIA NIM en priorité (si NVIDIA_API_KEY présente et force_groq=False)
      - Groq (clé active) en fallback
    """
    nvidia_key = _load_nvidia_key()

    if nvidia_key and not force_groq:
        print(f"🟢 [NVIDIA] build_llm → {model} (128k context)")
        logger.info(f"build_llm : utilise NVIDIA NIM ({model})")
        return ChatOpenAI(
            base_url=NVIDIA_BASE_URL,
            api_key=nvidia_key,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    # Fallback Groq
    global _current_key_index
    keys = _load_keys(_agent_offset)
    _current_key_index = min(_current_key_index, len(keys) - 1)

    key_preview = keys[_current_key_index][:8] + "..."
    print(f"🔑 [Groq] build_llm → clé #{_current_key_index + 1}/{len(keys)} ({key_preview})")
    logger.info(f"build_llm : utilise Groq clé #{_current_key_index + 1}/{len(keys)}")

    return ChatOpenAI(
        base_url=GROQ_BASE_URL,
        api_key=keys[_current_key_index],
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


def rotate_llm_key() -> bool:
    """
    Passe à la clé Groq suivante. Retourne True si une clé est disponible,
    False si toutes les clés ont été essayées.
    """
    global _current_key_index
    keys = _load_keys(_agent_offset)
    prev = _current_key_index + 1
    _current_key_index += 1

    if _current_key_index >= len(keys):
        _current_key_index = 0
        print(f"❌ [Groq] Toutes les clés épuisées ({len(keys)}/{len(keys)}) — reset à #1")
        logger.error("Groq : toutes les clés ont été essayées")
        return False

    key_preview = keys[_current_key_index][:8] + "..."
    print(f"🔄 [Groq] Rotation : clé #{prev} → clé #{_current_key_index + 1}/{len(keys)} ({key_preview})")
    logger.warning(f"Groq : rotation vers clé #{_current_key_index + 1}/{len(keys)}")
    return True


def build_llm_groq_fallback(
    model: str = "openai/gpt-oss-120b",
    temperature: float = 0,
    max_tokens: int = 2048,
) -> ChatOpenAI:
    """Force Groq (utilisé par l'agent RH quand NVIDIA échoue et qu'on tourne les clés)."""
    return build_llm(model=model, temperature=temperature, max_tokens=max_tokens, force_groq=True)
