# app/core/groq_client.py
# ═══════════════════════════════════════════════════════════
# Gestion des providers LLM avec fallback :
#   1. NVIDIA NIM (openai/gpt-oss-120b — 128k context)  ← primaire
#      Plusieurs clés supportées : NVIDIA_API_KEY, NVIDIA_API_KEY2, ...
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


def _load_nvidia_keys() -> list[str]:
    """Charge toutes les clés NVIDIA disponibles (NVIDIA_API_KEY, NVIDIA_API_KEY2, ...)."""
    load_dotenv()
    keys = []
    key1 = os.getenv("NVIDIA_API_KEY")
    if key1:
        keys.append(key1)
    for i in range(2, 10):
        key = os.getenv(f"NVIDIA_API_KEY{i}")
        if key:
            keys.append(key)
    if keys:
        logger.info(f"NVIDIA : {len(keys)} clé(s) disponible(s)")
    return keys


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
    skip_nvidia: bool = False,
    nvidia_retries: int = 1,
    skip_groq: bool = False,
    nvidia_key_index: int = 0,
    nvidia_max_keys: int | None = None,
    nvidia_timeout: int = 90,
) -> str:
    """
    Appelle le modèle avec fallback :
      1. NVIDIA NIM (128k context) — clés en rotation
         nvidia_key_index : index de départ (0=clé principale, 1=NVIDIA_API_KEY2, etc.)
         nvidia_max_keys  : nombre max de clés à essayer (None = toutes)
                            Mettre 1 pour empêcher la rotation (utile en parallèle pour
                            ne pas saturer plusieurs clés simultanément).
         nvidia_retries   : tentatives par clé avec température variée
         nvidia_timeout   : timeout par tentative (secondes)
      2. Groq keys (9 clés en rotation) — si toutes les clés NVIDIA échouent
         Sauf si skip_groq=True (ex: prompt trop grand pour Groq)
    """
    NVIDIA_TIMEOUT_SEC = nvidia_timeout

    nvidia_keys = _load_nvidia_keys()
    if nvidia_keys and not skip_nvidia:
        all_nvidia_failed = False
        # Rotation des clés NVIDIA en démarrant depuis nvidia_key_index
        ordered_keys = nvidia_keys[nvidia_key_index:] + nvidia_keys[:nvidia_key_index]
        if nvidia_max_keys is not None:
            ordered_keys = ordered_keys[:max(1, nvidia_max_keys)]

        for key_idx, nvidia_key in enumerate(ordered_keys):
            key_label = f"clé #{(nvidia_key_index + key_idx) % len(nvidia_keys) + 1}/{len(nvidia_keys)}"
            nvidia_failed = False

            for attempt in range(nvidia_retries):
                temp = temperature + (0.05 * attempt if attempt > 0 else 0)
                try:
                    tag = f"#{attempt+1}/{nvidia_retries}" if nvidia_retries > 1 else ""
                    print(f"🟢 [NVIDIA] {key_label} Tentative {tag} avec {model} (128k context, temp={temp:.2f}, timeout={NVIDIA_TIMEOUT_SEC}s)")
                    llm = ChatOpenAI(
                        base_url=NVIDIA_BASE_URL,
                        api_key=nvidia_key,
                        model=model,
                        temperature=temp,
                        max_tokens=max_tokens,
                        timeout=NVIDIA_TIMEOUT_SEC,
                    )
                    response = await asyncio.wait_for(
                        llm.ainvoke(messages),
                        timeout=NVIDIA_TIMEOUT_SEC + 10,
                    )
                    text = _extract_text(response)
                    if not text or not text.strip():
                        print(f"⚠️ [NVIDIA] {key_label} Réponse vide (tentative {attempt+1}/{nvidia_retries}) — content={repr(response.content)[:80]}")
                        if attempt < nvidia_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        nvidia_failed = True
                        break
                    print(f"✅ [NVIDIA] {key_label} Succès ({len(text)} chars)")
                    return text
                except asyncio.TimeoutError:
                    print(f"⏱️ [NVIDIA] {key_label} Timeout après {NVIDIA_TIMEOUT_SEC}s (tentative {attempt+1}/{nvidia_retries})")
                    if attempt < nvidia_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    nvidia_failed = True
                    break
                except Exception as e:
                    if _is_context_error(e):
                        logger.warning(f"NVIDIA : contexte trop long : {str(e)[:120]}")
                        raise RuntimeError(FRIENDLY_CONTEXT_MSG) from e
                    if attempt < nvidia_retries - 1:
                        print(f"⚠️ [NVIDIA] {key_label} Erreur tentative {attempt+1}/{nvidia_retries} ({type(e).__name__}) → retry")
                        await asyncio.sleep(2)
                        continue
                    nvidia_failed = True
                    print(f"⚠️ [NVIDIA] {key_label} Échec après {nvidia_retries} tentative(s) ({type(e).__name__}: {str(e)[:80]})")
                    logger.warning(f"NVIDIA {key_label} échec final : {str(e)[:120]}")
                    break

            if nvidia_failed and key_idx < len(ordered_keys) - 1:
                print(f"🔄 [NVIDIA] {key_label} épuisée → rotation vers clé suivante")
                await asyncio.sleep(1)
                continue
            if nvidia_failed:
                all_nvidia_failed = True

        if all_nvidia_failed and skip_groq:
            print(f"❌ [NVIDIA] Toutes les clés échouées + skip_groq=True → retour vide")
            raise ValueError("NVIDIA failed and Groq is skipped (large prompt)")

    # ── Fallback Groq (9 clés en rotation) ────────────
    if skip_groq:
        raise RuntimeError("NVIDIA failed and Groq fallback is disabled (skip_groq=True)")

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
