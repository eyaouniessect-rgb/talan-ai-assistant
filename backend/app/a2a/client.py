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

load_dotenv()
logger = logging.getLogger(__name__)

# ── Token secret partagé ──────────────────────────────────
A2A_SECRET = os.getenv("A2A_SECRET_TOKEN", "")


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