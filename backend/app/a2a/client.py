# app/a2a/client.py
# ═══════════════════════════════════════════════════════════
# Client A2A — avec authentification Bearer
# ═══════════════════════════════════════════════════════════

import httpx
import logging
import os
from a2a.client import ClientFactory, ClientConfig, create_text_message_object
from a2a.types import Message, Task, Artifact
from a2a.utils.message import get_message_text
from dotenv import load_dotenv
from langsmith import traceable
from typing import AsyncGenerator, Tuple

load_dotenv()
logger = logging.getLogger(__name__)

# ── Token secret partagé ──────────────────────────────────
A2A_SECRET = os.getenv("A2A_SECRET_TOKEN", "")


@traceable(name="a2a.send_task", tags=["a2a", "dispatch"])
async def send_task_to_url(agent_url: str, user_message: str) -> str:
    """
    Envoie un message à un agent A2A via son URL directe.
    Inclut le Bearer token si configuré.
    """
    # ── Construit les headers d'auth ───────────────────────
    headers = {}
    if A2A_SECRET:
        headers["Authorization"] = f"Bearer {A2A_SECRET}"

    async with httpx.AsyncClient(timeout=300, headers=headers) as httpx_client:
        client = await ClientFactory.connect(
            agent_url,
            client_config=ClientConfig(httpx_client=httpx_client),
        )
        message = create_text_message_object(content=user_message)

        text_content = ""
        async for response in client.send_message(message):
            if isinstance(response, Message):
                text_content = get_message_text(response)
            elif isinstance(response, tuple):
                task: Task = response[0]
                if task.artifacts:
                    artifact: Artifact = task.artifacts[0]
                    text_content = get_message_text(artifact)

    return text_content or "L'agent n'a pas retourné de réponse."


async def send_task_to_url_streaming(
    agent_url: str, user_message: str
) -> AsyncGenerator[Tuple[str, str], None]:
    """
    Générateur asynchrone qui envoie un message à un agent A2A et
    yield des événements intermédiaires au fur et à mesure.

    Yields tuples of (event_type, text):
      - ('message', text)    : message intermédiaire de l'agent
      - ('status', text)     : mise à jour de statut de la tâche
      - ('artifact', text)   : artefact produit par la tâche
      - ('done', text)       : événement final avec le texte complet collecté
    """
    headers = {}
    if A2A_SECRET:
        headers["Authorization"] = f"Bearer {A2A_SECRET}"

    print(f"   [A2A STREAM] Connexion à {agent_url}...")

    async with httpx.AsyncClient(timeout=300, headers=headers) as httpx_client:
        client = await ClientFactory.connect(
            agent_url,
            client_config=ClientConfig(httpx_client=httpx_client),
        )
        message = create_text_message_object(content=user_message)

        last_collected_text = ""

        async for response in client.send_message(message):
            if isinstance(response, Message):
                text = get_message_text(response)
                if text:
                    last_collected_text = text
                    print(f"   [A2A STREAM] message: {text[:80]}")
                    yield ("message", text)

            elif isinstance(response, tuple):
                task: Task = response[0]

                # Mise à jour de statut
                if task.status and task.status.message:
                    status_text = get_message_text(task.status.message)
                    if status_text:
                        last_collected_text = status_text
                        print(f"   [A2A STREAM] status: {status_text[:80]}")
                        yield ("status", status_text)

                # Artefacts produits
                if task.artifacts:
                    artifact: Artifact = task.artifacts[0]
                    artifact_text = get_message_text(artifact)
                    if artifact_text:
                        last_collected_text = artifact_text
                        print(f"   [A2A STREAM] artifact: {artifact_text[:80]}")
                        yield ("artifact", artifact_text)

        # Événement final avec le dernier texte collecté
        final_text = last_collected_text or "L'agent n'a pas retourné de réponse."
        print(f"   [A2A STREAM] done: {final_text[:80]}")
        yield ("done", final_text)


async def send_task(agent_name: str, user_message: str) -> str:
    """
    Envoie un message à un agent A2A.
    Discovery → fallback registry.
    """
    from app.a2a.discovery import discovery

    agents = await discovery.scan_agents()
    if agent_name in agents:
        agent = agents[agent_name]
        logger.info(f"🔍 Discovery : agent '{agent_name}' trouvé à {agent.url}")
        return await send_task_to_url(agent.url, user_message)

    logger.warning(f"⚠️ Discovery : agent '{agent_name}' non trouvé, fallback registry")
    from app.a2a.registry import get_agent_url
    agent_url = get_agent_url(agent_name)
    return await send_task_to_url(agent_url, user_message)
