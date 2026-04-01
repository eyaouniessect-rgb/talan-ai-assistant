# app/orchestrator/graph.py
# ═══════════════════════════════════════════════════════════
# Graphe LangGraph avec planificateur et exécuteur de plan
# Flux : Node1 (planner) → Node3 (executor) → Node4 (save) → END
# ═══════════════════════════════════════════════════════════

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import AIMessage
from app.orchestrator.state import AssistantState
from app.orchestrator.nodes.node1_intent import node1_detect_intent
from app.orchestrator.nodes.node3_executor import node3_executor   # remplace node3_dispatch
from app.a2a.discovery import discovery
from dotenv import load_dotenv
import psycopg
import json
import os

load_dotenv()

DB_URI = (
    f"postgresql://{os.getenv('POSTGRES_USER', 'postgres')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'password')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'talan_assistant')}"
    f"?sslmode=disable"
)

assistant_graph = None


# ══════════════════════════════════════════════════════
# NODE 4 — Sauvegarde l'AIMessage dans le state
# ══════════════════════════════════════════════════════
def node4_save_ai_message(state: AssistantState) -> AssistantState:
    final_response = state.get("final_response", "")

    clean_response = final_response
    try:
        parsed = json.loads(final_response)
        if isinstance(parsed, dict) and "response" in parsed:
            clean_response = parsed["response"]
    except (json.JSONDecodeError, TypeError):
        pass

    print(f"\n💾 NODE 4 — Sauvegarde AIMessage dans state['messages']")
    print(f"   Contenu : {clean_response[:150]}")

    return {
        **state,
        "messages": [AIMessage(content=clean_response)],
    }


def build_base_graph():
    graph = StateGraph(AssistantState)

    graph.add_node("node1_router",     node1_detect_intent)   # node1 reste tel quel
    graph.add_node("node3_executor",   node3_executor)       # remplace node3_dispatch
    graph.add_node("node4_save_ai_msg", node4_save_ai_message)

    # Flux : Node1 → Node3 → Node4 → END
    graph.set_entry_point("node1_router")
    graph.add_edge("node1_router",      "node3_executor")
    graph.add_edge("node3_executor",    "node4_save_ai_msg")
    graph.add_edge("node4_save_ai_msg", END)

    return graph


async def init_graph():
    global assistant_graph
    print("⚡ Initialisation du graphe LangGraph...")

    conn = await psycopg.AsyncConnection.connect(
        DB_URI, autocommit=True
    )
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()

    print("🔍 Premier scan des agents A2A (discovery)...")
    agents = await discovery.scan_agents(force=True)
    print(f"📊 Agents actifs au démarrage : {list(agents.keys())}")

    assistant_graph = build_base_graph().compile(
        checkpointer=checkpointer
    )
    print("✅ Graphe prêt.")
    print("📊 Flux : Node1 (routeur/planner) → Node3 (executor) → Node4 (save) → END")


def get_graph():
    return assistant_graph