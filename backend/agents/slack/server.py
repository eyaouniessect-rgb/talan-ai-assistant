# agents/slack/server.py
# ═══════════════════════════════════════════════════════════
# Serveur A2A de l'Agent Slack
# Port : AGENT_SLACK_PORT (défaut 8005)
# ═══════════════════════════════════════════════════════════

from dotenv import load_dotenv
import os
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from agents.slack.agent import SlackAgentExecutor
from agents.slack.schemas import build_agent_card
from agents.shared.auth_middleware import A2AAuthMiddleware
from app.core.groq_client import set_agent_offset


def main() -> None:
    print("Starting SlackAgent A2A Server...")
    load_dotenv()
    set_agent_offset(4)  # Slack agent : décalage sur les clés Groq

    HOST = os.getenv("AGENT_HOST", "localhost")
    PORT = int(os.getenv("AGENT_SLACK_PORT", 8005))

    agent_card = build_agent_card(host=HOST, port=PORT)

    request_handler = DefaultRequestHandler(
        agent_executor=SlackAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    app = server.build()
    app.add_middleware(A2AAuthMiddleware)

    token_configured = bool(os.getenv("A2A_SECRET_TOKEN", ""))
    slack_configured = bool(os.getenv("SLACK_BOT_TOKEN") or os.getenv("SLACK_USER_TOKEN"))

    security_status = "🔒 Authentification A2A activée" if token_configured else "⚠️ Pas de token A2A — mode ouvert"
    slack_status    = "✅ Token Slack configuré" if slack_configured else "⚠️ SLACK_USER_TOKEN manquant dans .env"

    print(f"SlackAgent running on http://{HOST}:{PORT}")
    print(f"Agent Card : http://{HOST}:{PORT}/.well-known/agent.json")
    print(f"Sécurité   : {security_status}")
    print(f"Slack MCP  : {slack_status}")

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
