# Définition du LangGraph State (short-term memory en RAM).
# TypedDict contenant :
#   - messages       : list[BaseMessage] — historique de la conversation en cours
#   - user_id        : str
#   - role           : str (consultant | pm)
#   - intent         : str — intention détectée par Node 1
#   - target_agent   : str — agent cible détecté par Node 1
#   - entities       : dict — entités extraites (dates, IDs, etc.)
#   - is_authorized  : bool — résultat du Node 2 RBAC
#   - final_response : str — réponse finale à streamer
from typing import TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AssistantState(TypedDict):
    # add_messages → ajoute au lieu d'écraser à chaque requête
    messages: Annotated[list[BaseMessage], add_messages]

    user_id: int
    role: str
    intent: Optional[str]
    target_agent: Optional[str]
    entities: Optional[dict]
    is_authorized: Optional[bool]
    final_response: Optional[str]