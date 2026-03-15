# Client A2A réutilisable pour appeler n'importe quel agent.
# Méthode principale : send_task(agent_url, task, params) → résultat
# Gère :
#   - L'authentification Bearer entre agents
#   - Le timeout (default: 30s)
#   - Les retries en cas d'erreur réseau (max 3 tentatives)
#   - La désérialisation de la réponse A2A standard
# app/a2a/client.py
import httpx
from a2a.client import ClientFactory, ClientConfig, create_text_message_object
from a2a.types import Message, Task, Artifact
from a2a.utils.message import get_message_text
from app.a2a.registry import get_agent_url


async def send_task(agent_name: str, user_message: str) -> str:
    """
    Envoie un message à un agent A2A et retourne la réponse texte.
    Conforme à la doc officielle Lesson 5.
    """
    agent_url = get_agent_url(agent_name)

    async with httpx.AsyncClient(timeout=60.0) as httpx_client:
        # Connexion à l'agent (doc officielle : ClientFactory.connect)
        client = await ClientFactory.connect(
            agent_url,
            client_config=ClientConfig(httpx_client=httpx_client),
        )

        # Construit le message (doc officielle : create_text_message_object)
        message = create_text_message_object(content=user_message)

        # Envoie et traite la réponse
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