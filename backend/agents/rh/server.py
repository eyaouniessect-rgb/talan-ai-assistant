# agents/rh/server.py
# ═══════════════════════════════════════════════════════════
# Serveur A2A de l'Agent RH — avec authentification
# ═══════════════════════════════════════════════════════════

from dotenv import load_dotenv
import os
import uvicorn

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore

from agents.rh.agent import RHAgentExecutor
from agents.rh.schemas import build_agent_card
from agents.shared.auth_middleware import A2AAuthMiddleware
from app.core.groq_client import set_agent_offset


def main() -> None:
    print("Starting RHAgent A2A Server...")
    load_dotenv()
    set_agent_offset(0)  # RH agent : clés 1-8 (offset 0)

    HOST = os.getenv("AGENT_HOST", "localhost")
    PORT = int(os.getenv("AGENT_RH_PORT", 8001))

    agent_card = build_agent_card(host=HOST, port=PORT)

    request_handler = DefaultRequestHandler(
        agent_executor=RHAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )

    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )

    # ── Build l'app Starlette et ajoute le middleware auth ──
    app = server.build()
    app.add_middleware(A2AAuthMiddleware)

    # ── Log sécurité ────────────────────────────────────────
    token_configured = bool(os.getenv("A2A_SECRET_TOKEN", ""))
    security_status = "🔒 Authentification A2A activée" if token_configured else "⚠️ Pas de token A2A — mode ouvert"

    print(f"RHAgent running on http://{HOST}:{PORT}")
    print(f"Agent Card : http://{HOST}:{PORT}/.well-known/agent.json")
    print(f"Sécurité : {security_status}")

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()