# Route principale du chat.
# POST /chat           → reçoit message + user_id + role → envoie à l'orchestrateur LangGraph
# GET  /chat/stream    → SSE endpoint → streame la réponse token par token vers le frontend React


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from langchain_core.messages import HumanMessage
from app.orchestrator.graph import assistant_graph
from app.core.security import get_current_user
from typing import Optional
router = APIRouter(prefix="/chat", tags=["Chat"])

class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None  # ← Optional

class ChatResponse(BaseModel):
    response: str
    intent: str
    target_agent: str

@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Route principale du chat.
    Reçoit un message → passe par LangGraph → retourne la réponse.
    """
    initial_state = {
        "messages":      [HumanMessage(content=request.message)],
        "user_id":       current_user["user_id"],
        "role":          current_user["role"],
        "intent":        None,
        "target_agent":  None,
        "entities":      {},
        "is_authorized": None,
        "final_response": None,
    }

    result = await assistant_graph.ainvoke(initial_state)

    return ChatResponse(
        response=result["final_response"],
        intent=result["intent"],
        target_agent=result["target_agent"],
    )