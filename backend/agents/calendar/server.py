# Serveur FastAPI de l'Agent Calendar.

from dotenv import load_dotenv
import os
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from agents.calendar.agent import CalendarAgentExecutor
from agents.calendar.schemas import build_agent_card
from app.core.groq_client import set_agent_offset


def main():
    load_dotenv()
    set_agent_offset(4)  # Calendar agent : décalé de 4 → clés 5-8-1-2-3-4

    HOST = os.getenv("AGENT_HOST", "localhost")
    PORT = int(os.getenv("AGENT_CALENDAR_PORT", 8002))

    agent_card = build_agent_card(HOST, PORT)

    request_handler = DefaultRequestHandler(
        agent_executor=CalendarAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build()

    print(f"CalendarAgent running on http://{HOST}:{PORT}")

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()