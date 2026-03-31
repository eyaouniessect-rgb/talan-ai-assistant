# Définition du LangGraph State.
# Simplifié : Node 1 ne détecte plus d'intent spécifique,
# juste le target_agent. Le RBAC est dans les agents.
# Support multi-agent : target_agents contient une liste de
# {"agent": "rh", "sub_task": "..."} pour le dispatch parallèle.
from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AssistantState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    user_id: int
    role: str
    target_agent: Optional[str]
    target_agents: Optional[list[dict]]   # multi-agent: [{"agent": "rh", "sub_task": "..."}]
    final_response: Optional[str]
