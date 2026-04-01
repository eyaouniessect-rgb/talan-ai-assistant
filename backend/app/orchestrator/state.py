from typing import TypedDict, Optional, Annotated, List, Dict, Any
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class PlanStep(TypedDict):
    step_id: str
    agent: str
    task: str
    depends_on: List[str]
    status: str          # "pending", "running", "waiting_input", "done", "failed"
    result: Optional[Any]

class AssistantState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: int
    role: str
    plan: Optional[List[PlanStep]]          # plan complet
    plan_results: Optional[Dict[str, Any]]  # résultats par step_id
    waiting_step: Optional[str]             # step_id en attente d’input
    final_response: Optional[str]
    last_agent: Optional[str]               # pour continuation simple (si utilisé)