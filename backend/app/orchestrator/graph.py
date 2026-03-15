# Définition du graphe LangGraph principal.
# Assemble les 3 nodes dans un StateGraph et compile le graphe.
# Configure aussi le PostgreSQL Checkpointer pour la long-term memory.
# 
# Flux : Node1 (intention) → Node2 (RBAC) → Node3 (dispatch A2A)
#                                          ↘ blocked (si non autorisé)
from langgraph.graph import StateGraph, END
from app.orchestrator.state import AssistantState
from app.orchestrator.nodes.node1_intent import node1_detect_intent
from app.orchestrator.nodes.node2_rbac import node2_check_permission
from app.orchestrator.nodes.node3_dispatch import node3_dispatch


def build_graph():
    """
    Assemble les 3 nodes dans un StateGraph LangGraph.
    
    Flux :
    node1 → node2 → node3 → END
                  ↘ blocked → END
    """
    graph = StateGraph(AssistantState)

    # Ajoute les nodes
    graph.add_node("node1_intent",     node1_detect_intent)
    graph.add_node("node2_rbac",       node2_check_permission)
    graph.add_node("node3_dispatch",   node3_dispatch)
    graph.add_node("blocked",          lambda state: {
        **state,
        "final_response": "Accès refusé — vous n'avez pas la permission d'effectuer cette action."
    })

    # Point d'entrée
    graph.set_entry_point("node1_intent")

    # Node1 → Node2 (toujours)
    graph.add_edge("node1_intent", "node2_rbac")

    # Node2 → Node3 ou Blocked (selon permission)
    graph.add_conditional_edges(
        "node2_rbac",
        lambda state: "node3_dispatch" if state["is_authorized"] else "blocked",
        {
            "node3_dispatch": "node3_dispatch",
            "blocked": "blocked",
        }
    )

    # Node3 → END
    graph.add_edge("node3_dispatch", END)
    graph.add_edge("blocked", END)

    return graph.compile()


# Instance globale du graphe
assistant_graph = build_graph()