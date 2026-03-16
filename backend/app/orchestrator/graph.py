# Définition du graphe LangGraph principal.
# Assemble les 3 nodes dans un StateGraph et compile le graphe.
# Configure aussi le PostgreSQL Checkpointer pour la long-term memory.
# 
# Flux : Node1 (intention) → Node2 (RBAC) → Node3 (dispatch A2A)
#                                          ↘ blocked (si non autorisé)
# app/orchestrator/graph.py
# app/orchestrator/graph.py
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from app.orchestrator.state import AssistantState
from app.orchestrator.nodes.node1_intent import node1_detect_intent
from app.orchestrator.nodes.node2_rbac import node2_check_permission
from app.orchestrator.nodes.node3_dispatch import node3_dispatch
from dotenv import load_dotenv
import psycopg
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

def build_base_graph():
    graph = StateGraph(AssistantState)

    graph.add_node("node1_intent",   node1_detect_intent)
    graph.add_node("node2_rbac",     node2_check_permission)
    graph.add_node("node3_dispatch", node3_dispatch)
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
    graph.add_edge("node3_dispatch", END)
    graph.add_edge("blocked", END)

    return graph


_base_graph = build_base_graph()


async def get_graph():
    """
    Retourne le graphe compilé avec AsyncPostgresSaver.
    Utilise psycopg async directement.
    """
    # connexion async psycopg avec autocommit
    conn = await psycopg.AsyncConnection.connect(
        DB_URI,
        autocommit=True
    )
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()
    return _base_graph.compile(checkpointer=checkpointer)