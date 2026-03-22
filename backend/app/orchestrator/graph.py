# app/orchestrator/graph.py
# ═══════════════════════════════════════════════════════════
# Graphe LangGraph avec Dynamic Discovery A2A
# ═══════════════════════════════════════════════════════════
# 
# Flux : Node1 (intent) → Node2 (RBAC) → Node3 (discovery + dispatch) → Node4 (save AI msg) → END
#                                       ↘ blocked → Node4 → END
#
# Au démarrage :
# 1. Initialise le checkpointer PostgreSQL
# 2. Lance un premier scan des agents A2A (discovery)
# 3. Compile le graphe

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import AIMessage
from app.orchestrator.state import AssistantState
from app.orchestrator.nodes.node1_intent import node1_detect_intent
from app.orchestrator.nodes.node2_rbac import node2_check_permission
from app.orchestrator.nodes.node3_dispatch import node3_dispatch
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

# ── Instance globale ───────────────────────────────────
assistant_graph = None


# ══════════════════════════════════════════════════════
# NODE 4 — Sauvegarde l'AIMessage dans le state
# ══════════════════════════════════════════════════════
def node4_save_ai_message(state: AssistantState) -> AssistantState:
    """
    Injecte la final_response comme AIMessage dans state["messages"].
    Nettoie le JSON des agents (react_steps) pour ne garder que le texte propre.
    """
    final_response = state.get("final_response", "")

    clean_response = final_response
    try:
        parsed = json.loads(final_response)
        if isinstance(parsed, dict) and "response" in parsed:
            clean_response = parsed["response"]
    except (json.JSONDecodeError, TypeError):
        pass

    print(f"💾 NODE 4 — Sauvegarde AIMessage dans state['messages']")
    print(f"   Contenu : {clean_response[:150]}")

    return {
        **state,
        "messages": [AIMessage(content=clean_response)],
    }


def build_base_graph():
    graph = StateGraph(AssistantState)

    graph.add_node("node1_intent",      node1_detect_intent)
    graph.add_node("node2_rbac",        node2_check_permission)
    graph.add_node("node3_dispatch",    node3_dispatch)
    graph.add_node("node4_save_ai_msg", node4_save_ai_message)
    graph.add_node("blocked", lambda state: {
        **state,
        "final_response": "Accès refusé — vous n'avez pas la permission."
    })

    graph.set_entry_point("node1_intent")
    graph.add_edge("node1_intent", "node2_rbac")

    graph.add_conditional_edges(
        "node2_rbac",
        lambda state: "node3_dispatch" if state["is_authorized"] else "blocked",
        {"node3_dispatch": "node3_dispatch", "blocked": "blocked"}
    )

    graph.add_edge("node3_dispatch", "node4_save_ai_msg")
    graph.add_edge("blocked",        "node4_save_ai_msg")
    graph.add_edge("node4_save_ai_msg", END)

    return graph


async def init_graph():
    """
    Initialise le graphe + discovery au démarrage.
    """
    global assistant_graph
    print("⚡ Initialisation du graphe LangGraph...")

    # ── 1. Checkpointer PostgreSQL ─────────────────────────
    conn = await psycopg.AsyncConnection.connect(
        DB_URI, autocommit=True
    )
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()

    # ── 2. Premier scan des agents A2A ─────────────────────
    print("🔍 Premier scan des agents A2A (discovery)...")
    agents = await discovery.scan_agents(force=True)
    print(f"📊 Agents actifs au démarrage : {list(agents.keys())}")

    # ── 3. Compile le graphe ───────────────────────────────
    assistant_graph = build_base_graph().compile(
        checkpointer=checkpointer
    )
    print("✅ Graphe prêt.")
    print("📊 Flux : Node1 → Node2 → Node3 (discovery) → Node4 → END")


def get_graph():
    return assistant_graph