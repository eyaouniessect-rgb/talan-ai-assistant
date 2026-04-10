# api/chat/chat.py
# Schéma : public
#
# Routes du chat conversationnel avec l'orchestrateur LangGraph.
# POST /chat/stream                              → SSE streaming (réponse en temps réel)
# POST /chat/                                    → endpoint non-streaming
# GET  /chat/conversations                       → liste des conversations de l'utilisateur
# GET  /chat/conversations/{id}/messages         → messages d'une conversation

from typing import Optional, List
import json
import re
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from langchain_core.messages import HumanMessage

from app.orchestrator.graph import get_graph
from app.core.security import get_current_user
from app.database.connection import get_db, AsyncSessionLocal
from app.database.models.public.conversation import Conversation
from app.database.models.public.message import Message
from app.orchestrator.nodes.node3_executor import _stream_queue

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalise les caractères Unicode exotiques produits par le LLM."""
    return (
        text.lower()
        .replace("\u2011", "-")
        .replace("\u2010", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u202f", " ")
        .replace("\u00a0", " ")
        .replace("\u00ab", '"')
        .replace("\u00bb", '"')
    )


def _detect_ui_hint(text: str) -> "dict | None":
    t = _normalize(text)
    _needs_datetime = bool(re.search(
        r"quelle heure|a quelle heure|heure.*(debut|fin)|debut et fin"
        r"|date.{0,15}(horaire|heure)|horaire.{0,15}souhait"
        r"|nouvelle date.{0,15}heur|preciser.{0,20}(date|heure|horaire)",
        t,
    ))
    _needs_emails = bool(re.search(
        r"e-mail|email|adresse mail|adresses mail|coordonnees|pouvez.vous me communiquer",
        t,
    ))
    if _needs_datetime and _needs_emails:
        return {"type": "event_datetime_with_emails"}
    if _needs_datetime:
        return {"type": "event_datetime"}
    if re.search(r"dates de (d.but|fin)|p.riode souhait.e|date de debut.*date de fin", t):
        return {"type": "date_range"}
    if re.search(r"quelle date|a quelle date|precisez la date|choisissez une date|nouvelle date", t):
        return {"type": "date_picker"}
    return None


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[int] = None


class ReActStep(BaseModel):
    status: str
    text: str


class ChatResponse(BaseModel):
    response: str
    intent: str
    target_agent: str
    conversation_id: int
    steps: List[ReActStep] = []
    ui_hint: Optional[dict] = None


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["user_id"]
    role = current_user["role"]

    print(f"\n{'='*60}")
    print(f"🌊 STREAMING REQUEST — user_id={user_id} msg={request.message[:60]}")
    print(f"{'='*60}")

    is_real_id = request.conversation_id is not None and request.conversation_id < 1_000_000_000_000
    conversation = None
    if is_real_id:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == request.conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conversation = result.scalar_one_or_none()

    if not conversation:
        conversation = Conversation(user_id=user_id, title=request.message[:40])
        db.add(conversation)
        await db.flush()
        await db.commit()
        print(f"   🆕 [CHAT] Nouvelle conversation créée : conv_id={conversation.id}")
    else:
        print(f"   ♻️  [CHAT] Conversation EXISTANTE réutilisée : conv_id={conversation.id}")

    thread_id = str(conversation.id)
    conversation_id = conversation.id

    graph = get_graph()
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "user_id": user_id,
        "role": role,
        "plan": None,
        "plan_results": None,
        "waiting_step": None,
        "final_response": None,
        "last_agent": None,
    }
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"stream:user_{user_id}",
        "metadata": {"user_id": user_id, "conversation_id": conversation_id},
    }

    queue: asyncio.Queue = asyncio.Queue()
    _stream_queue.set(queue)

    result_holder: dict = {}

    async def run_graph():
        try:
            print("   🚀 [BG] Lancement graph.ainvoke...")
            result = await graph.ainvoke(initial_state, config)
            result_holder["result"] = result
            print("   ✅ [BG] graph.ainvoke terminé")
        except Exception as e:
            print(f"   ❌ [BG] Erreur : {e}")
            result_holder["error"] = str(e)
        finally:
            await queue.put(None)

    bg_task = asyncio.create_task(run_graph())

    async def event_generator():
        print("   📡 [SSE] Générateur démarré")
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    print("   ⏰ [SSE] Timeout")
                    yield f"data: {json.dumps({'type': 'error', 'text': 'Timeout du serveur.'})}\n\n"
                    break

                if event is None:
                    print("   🏁 [SSE] Sentinel reçu — graph terminé")
                    break

                print(f"   📤 [SSE] → {event.get('type')} step={event.get('step_id','')}")
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            try:
                await asyncio.wait_for(asyncio.shield(bg_task), timeout=5.0)
            except Exception:
                pass

            if "error" in result_holder:
                err_msg = result_holder["error"]
                print(f"   ❌ [SSE] Erreur graph : {err_msg}")
                yield f"data: {json.dumps({'type': 'error', 'text': err_msg})}\n\n"
            else:
                result = result_holder.get("result", {})
                raw_response = result.get("final_response", "")
                last_agent = result.get("last_agent", "chat")

                try:
                    parsed = json.loads(raw_response)
                    final_text = parsed.get("response", raw_response)
                    ui_hint = parsed.get("ui_hint")
                except (json.JSONDecodeError, TypeError):
                    final_text = raw_response
                    ui_hint = None

                if ui_hint is None and final_text:
                    ui_hint = _detect_ui_hint(final_text)

                try:
                    async with AsyncSessionLocal() as session:
                        session.add(Message(conversation_id=conversation_id, role="user", content=request.message))
                        session.add(Message(conversation_id=conversation_id, role="assistant", content=final_text, intent=last_agent, target_agent=last_agent))
                        await session.commit()
                    print(f"   💾 [SSE] Messages sauvegardés")
                except Exception as e:
                    print(f"   ⚠️ [SSE] Erreur sauvegarde DB : {e}")

                print(f"   ✅ [SSE] done event → conv_id={conversation_id}")
                yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id, 'ui_hint': ui_hint}, ensure_ascii=False)}\n\n"

        except Exception as e:
            print(f"   💥 [SSE] Exception générateur : {e}")
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["user_id"]
    role    = current_user["role"]

    logger.info(f"Nouvelle requête - user_id={user_id} conv_id={request.conversation_id} msg={request.message[:50]}")

    is_real_id = (
        request.conversation_id is not None and
        request.conversation_id < 1_000_000_000_000
    )

    if is_real_id:
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
        conversation = Conversation(user_id=user_id, title=request.message[:40])
        db.add(conversation)
        await db.flush()

    thread_id = str(conversation.id)

    graph = get_graph()
    if graph is None:
        raise HTTPException(status_code=503, detail="Graph not initialized")

    initial_state = {
        "messages": [HumanMessage(content=request.message)],
        "user_id": user_id,
        "role": role,
        "plan": None,
        "plan_results": None,
        "waiting_step": None,
        "final_response": None,
        "last_agent": None,
    }
    config = {
        "configurable": {"thread_id": thread_id},
        "run_name": f"chat:user_{user_id}",
        "metadata": {"user_id": user_id, "role": role, "conversation_id": conversation.id, "message_preview": request.message[:100]},
    }
    result = await graph.ainvoke(initial_state, config)

    plan = result.get("plan")
    last_agent = result.get("last_agent")
    if plan and len(plan) > 0:
        intent_agent = plan[0]["agent"]
    elif last_agent:
        intent_agent = last_agent
    else:
        intent_agent = "chat"

    raw_response = result["final_response"]
    react_steps = []

    try:
        parsed = json.loads(raw_response)
        final_text = parsed.get("response", raw_response)
        react_steps = [ReActStep(status="done", text=step) for step in parsed.get("react_steps", [])]
        ui_hint = parsed.get("ui_hint")
    except (json.JSONDecodeError, TypeError):
        final_text = raw_response
        ui_hint = None

    if ui_hint is None:
        ui_hint = _detect_ui_hint(final_text)

    db.add(Message(conversation_id=conversation.id, role="user", content=request.message))
    db.add(Message(conversation_id=conversation.id, role="assistant", content=final_text, intent=intent_agent, target_agent=intent_agent))
    await db.commit()

    return ChatResponse(
        response=final_text,
        intent=intent_agent,
        target_agent=intent_agent,
        conversation_id=conversation.id,
        steps=react_steps,
        ui_hint=ui_hint,
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
    return [{"id": c.id, "title": c.title, "created_at": str(c.created_at)} for c in conversations]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"]
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

    result = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.timestamp.asc())
    )
    messages = result.scalars().all()
    return [
        {"id": m.id, "role": m.role, "content": m.content, "intent": m.intent, "target_agent": m.target_agent, "timestamp": str(m.timestamp)}
        for m in messages
    ]
