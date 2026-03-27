# Définition du LangGraph State.
# Simplifié : Node 1 ne détecte plus d'intent spécifique,
# juste le target_agent. Le RBAC est dans les agents.
from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AssistantState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]

    user_id: int
    role: str
    target_agent: Optional[str]
    final_response: Optional[str]
