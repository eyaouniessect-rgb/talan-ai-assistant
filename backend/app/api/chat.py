# Route principale du chat.
# POST /chat           → reçoit message + user_id + role → envoie à l'orchestrateur LangGraph
# GET  /chat/stream    → SSE endpoint → streame la réponse token par token vers le frontend React

# app/api/chat.py
from typing import Optional, List
import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_core.messages import HumanMessage

from app.orchestrator.graph import get_graph
from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.chat import Conversation, Message

router = APIRouter(prefix="/chat", tags=["Chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None


class ReActStep(BaseModel):
    status: str  # done | loading
    text: str


class ChatResponse(BaseModel):
    response: str
    intent: str
    target_agent: str
    conversation_id: int
    steps: List[ReActStep] = []


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["user_id"]
    role    = current_user["role"]

    # ── 1. Trouve ou crée la conversation ─────────────────
    if request.conversation_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()
    else:
        conversation = None

    if not conversation:
        conversation = Conversation(
            user_id=user_id,
            title=request.message[:40],
        )
        db.add(conversation)
        await db.flush()

    # ── 2. thread_id = conversation.id ────────────────────
    thread_id = str(conversation.id)

    # ── 3. Appelle LangGraph ──────────────────────────────
    graph = get_graph()
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    initial_state = {
        "messages":       [HumanMessage(content=request.message)],
        "user_id":        user_id,
        "role":           role,
        "intent":         None,
        "target_agent":   None,
        "entities":       {},
        "is_authorized":  None,
        "final_response": None,
    }

    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(initial_state, config)

    # ── 4. Parse la réponse — Agent RH retourne JSON ──────
    raw_response = result["final_response"]
    react_steps = []

    try:
        # Agent RH (ReAct) retourne un JSON avec response + react_steps
        parsed = json.loads(raw_response)
        final_text = parsed.get("response", raw_response)
        react_steps = [
            ReActStep(status="done", text=step)
            for step in parsed.get("react_steps", [])
        ]
    except (json.JSONDecodeError, TypeError):
        # Autres agents retournent du texte simple
        final_text = raw_response

    # ── 5. Sauvegarde dans tes tables ─────────────────────
    db.add(Message(
        conversation_id=conversation.id,
        role="user",
        content=request.message,
    ))
    db.add(Message(
        conversation_id=conversation.id,
        role="assistant",
        content=final_text,
        intent=result["intent"],
        target_agent=result["target_agent"],
    ))

    await db.commit()

    return ChatResponse(
        response=final_text,
        intent=result["intent"],
        target_agent=result["target_agent"],
        conversation_id=conversation.id,
        steps=react_steps,
    )


@router.get("/conversations")
async def get_conversations(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user["user_id"])
        .order_by(Conversation.created_at.desc())
    )
    conversations = result.scalars().all()
    return [
        {"id": c.id, "title": c.title, "created_at": str(c.created_at)}
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "intent": m.intent,
            "target_agent": m.target_agent,
            "timestamp": str(m.timestamp),
        }
        for m in messages
    ]