# Définition du graphe LangGraph principal.
# Assemble les nodes dans un StateGraph et compile le graphe.
# Configure aussi le PostgreSQL Checkpointer pour la long-term memory.
# 
# Flux : Node1 (intention) → Node2 (RBAC) → Node3 (dispatch A2A) → Node4 (save AI msg)
#                                          ↘ blocked → Node4 (save AI msg)
#
# ═══════════════════════════════════════════════════════════
# FIX MÉMOIRE : Node4 ajoute l'AIMessage dans state["messages"]
# pour que le checkpointer sauvegarde l'historique complet
# (Human + AI), et que les requêtes suivantes voient les
# réponses précédentes de l'assistant.
# ═══════════════════════════════════════════════════════════
# app/orchestrator/graph.py

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langchain_core.messages import AIMessage
from app.orchestrator.state import AssistantState
from app.orchestrator.nodes.node1_intent import node1_detect_intent
from app.orchestrator.nodes.node2_rbac import node2_check_permission
from app.orchestrator.nodes.node3_dispatch import node3_dispatch
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

# ── Instance globale — créée UNE SEULE FOIS ───────────
assistant_graph = None


# ══════════════════════════════════════════════════════
# NODE 4 — Sauvegarde l'AIMessage dans le state
# ══════════════════════════════════════════════════════
def node4_save_ai_message(state: AssistantState) -> AssistantState:
    """
    Injecte la final_response comme AIMessage dans state["messages"].
    
    POURQUOI :
    - Sans ça, seuls les HumanMessage sont dans state["messages"]
    - Le checkpointer ne sauvegarde que ce qui est dans le state
    - Les requêtes suivantes ne voient pas les réponses de l'assistant
    - L'historique envoyé aux agents ne contient que des "Utilisateur:"
    
    On nettoie aussi le JSON des agents (react_steps) pour ne garder
    que le texte propre dans l'historique.
    """
    final_response = state.get("final_response", "")

    # ── Nettoie : si c'est du JSON agent, extrait "response" ──
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

    # ── Nodes ──────────────────────────────────────────────
    graph.add_node("node1_intent",      node1_detect_intent)
    graph.add_node("node2_rbac",        node2_check_permission)
    graph.add_node("node3_dispatch",    node3_dispatch)
    graph.add_node("node4_save_ai_msg", node4_save_ai_message)
    graph.add_node("blocked", lambda state: {
        **state,
        "final_response": "Accès refusé — vous n'avez pas la permission."
    })

    # ── Edges ──────────────────────────────────────────────
    graph.set_entry_point("node1_intent")
    graph.add_edge("node1_intent", "node2_rbac")

    graph.add_conditional_edges(
        "node2_rbac",
        lambda state: "node3_dispatch" if state["is_authorized"] else "blocked",
        {"node3_dispatch": "node3_dispatch", "blocked": "blocked"}
    )

    # Node3 et blocked → Node4 (sauvegarde AI msg) → END
    graph.add_edge("node3_dispatch", "node4_save_ai_msg")
    graph.add_edge("blocked",        "node4_save_ai_msg")
    graph.add_edge("node4_save_ai_msg", END)

    return graph


async def init_graph():
    """
    Initialise le graphe UNE SEULE FOIS au démarrage.
    Appelé dans le lifespan de FastAPI.
    """
    global assistant_graph
    print("⚡ Initialisation du graphe LangGraph...")

    conn = await psycopg.AsyncConnection.connect(
        DB_URI, autocommit=True
    )
    checkpointer = AsyncPostgresSaver(conn)
    await checkpointer.setup()

    assistant_graph = build_base_graph().compile(
        checkpointer=checkpointer
    )
    print("✅ Graphe prêt.")
    print("📊 Flux : Node1 → Node2 → Node3/blocked → Node4 (save AI msg) → END")


def get_graph():
    """Retourne l'instance globale du graphe."""
    return assistant_graph