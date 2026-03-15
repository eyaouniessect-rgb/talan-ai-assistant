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
from typing import TypedDict, Optional, List
from langchain_core.messages import BaseMessage

class AssistantState(TypedDict):
    """
    SHORT-TERM MEMORY — partagée entre les 3 nodes.
    Réinitialisée à chaque nouvelle requête.
    """
    # Historique des messages de la conversation en cours
    messages: List[BaseMessage]

    # Infos utilisateur (injectées par FastAPI)
    user_id: int
    role: str              # consultant | pm

    # Résultat du Node 1
    intent: Optional[str]         # create_leave | get_projects | get_tickets...
    target_agent: Optional[str]   # rh | crm | jira | slack | calendar | rag
    entities: Optional[dict]      # ex: {"start_date": "2025-03-15", "end_date": "2025-03-21"}

    # Résultat du Node 2
    is_authorized: Optional[bool]

    # Résultat du Node 3
    final_response: Optional[str]