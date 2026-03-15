# agents/rh/server.py
# Serveur A2A de l'Agent RH.


from dotenv import load_dotenv
import os
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from agents.rh.agent import RHAgentExecutor
from agents.rh.schemas import build_agent_card


def main() -> None:
    print("Starting RHAgent A2A Server...")
    load_dotenv()

    HOST = os.getenv("AGENT_HOST", "localhost")
    PORT = int(os.getenv("AGENT_RH_PORT", 8001))

    # AgentCard définie dans schemas.py
    agent_card = build_agent_card(host=HOST, port=PORT)

    # Handler A2A — exactement comme la doc officielle
    request_handler = DefaultRequestHandler(
        agent_executor=RHAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    # Application A2A Starlette
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    print(f"RHAgent running on http://{HOST}:{PORT}")
    print(f"Agent Card : http://{HOST}:{PORT}/.well-known/agent.json")

    uvicorn.run(server.build(), host=HOST, port=PORT)


if __name__ == "__main__":
    main()