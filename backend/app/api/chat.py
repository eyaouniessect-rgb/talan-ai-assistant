# app/api/chat.py
from typing import Optional, List
import json
import re
import logging
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
logger = logging.getLogger(__name__)


def _normalize(text: str) -> str:
    """Normalise les caractères Unicode exotiques produits par le LLM."""
    return (
        text.lower()
        .replace("\u2011", "-")   # non-breaking hyphen → -
        .replace("\u2010", "-")   # hyphen → -
        .replace("\u2013", "-")   # en-dash → -
        .replace("\u2014", "-")   # em-dash → -
        .replace("\u202f", " ")   # narrow no-break space → space
        .replace("\u00a0", " ")   # no-break space → space
        .replace("\u00ab", '"')   # «
        .replace("\u00bb", '"')   # »
    )


def _detect_ui_hint(text: str) -> "dict | None":
    """Détecte le composant UI interactif à afficher selon le texte de la réponse."""
    t = _normalize(text)

    # ── 1. Choix en ligne / présentiel ───────────────────
    if ("en ligne" in t or "presentiel" in t or "distanciel" in t) and "?" in t:
        return {
            "type": "choice",
            "options": [
                {"label": "En ligne (Google Meet)", "value": "oui, en ligne avec Google Meet", "icon": "video"},
                {"label": "Présentiel", "value": "non, en présentiel", "icon": "building"},
            ],
        }

    # ── 2. Boutons Oui / Non ─────────────────────────────
    is_oui_non = (
        "souhaitez-vous" in t or
        "voulez-vous" in t or
        "confirmez-vous" in t or
        bool(re.search(r"oui\s*/\s*non", t)) or
        bool(re.search(r"r.pondez.*oui", t)) or
        ("oui" in t and "non" in t and "?" in t)
    )
    is_time_or_detail = bool(re.search(r"quelle heure|quel titre|quel jour", t))
    if is_oui_non and not is_time_or_detail:
        return {"type": "confirm", "options": ["Oui", "Non"]}

    # ── 3. Date + heure début/fin (événements calendar) ──
    if re.search(r"quelle heure|a quelle heure|heure.*(debut|fin)|debut et fin|date.{0,15}(horaire|heure)|horaire.{0,15}souhait|nouvelle date.{0,15}heur|preciser.{0,20}(date|heure|horaire)", t):
        return {"type": "event_datetime"}

    # ── 4. Plage de dates (congés, disponibilités) ───────
    if re.search(r"dates de (d.but|fin)|p.riode souhait.e|date de debut.*date de fin", t):
        return {"type": "date_range"}

    # ── 5. Date simple ───────────────────────────────────
    if re.search(r"quelle date|a quelle date|precisez la date|choisissez une date|quel jour|nouvelle date", t):
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


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["user_id"]
    role    = current_user["role"]

    logger.info(f"Nouvelle requête - user_id={user_id} conv_id={request.conversation_id} msg={request.message[:50]}")

    # ── 1. Trouve ou crée la conversation ─────────────────
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
        logger.info(f"Conversation trouvée en base : {conversation is not None}")
    else:
        conversation = None
        logger.info("ID temporaire détecté → nouvelle conversation")

    if not conversation:
        conversation = Conversation(
            user_id=user_id,
            title=request.message[:40],
        )
        db.add(conversation)
        await db.flush()
        logger.info(f"Nouvelle conversation créée : id={conversation.id}")
    else:
        logger.info(f"Conversation existante utilisée : id={conversation.id}")

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

    logger.info(f"LangGraph terminé - intent={result['intent']} agent={result['target_agent']}")

    # ── 4. Parse la réponse ────────────────────────────────
    raw_response = result["final_response"]
    react_steps = []

    try:
        parsed = json.loads(raw_response)
        final_text = parsed.get("response", raw_response)
        react_steps = [
            ReActStep(status="done", text=step)
            for step in parsed.get("react_steps", [])
        ]
        ui_hint = parsed.get("ui_hint")
        logger.info("Réponse parsée (JSON) ✅")
    except (json.JSONDecodeError, TypeError):
        final_text = raw_response
        ui_hint = None
        logger.info("Réponse texte simple ✅")

    # ── Fallback : détecte ui_hint si l'agent n'en a pas fourni ──
    if ui_hint is None:
        ui_hint = _detect_ui_hint(final_text)
    logger.info(f"🎨 UI hint final : {ui_hint} | texte[:100] : {final_text[:100]}")

    # ── 5. Sauvegarde dans les tables ─────────────────────
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
    logger.info(f"Messages sauvegardés - conversation_id={conversation.id}")

    return ChatResponse(
        response=final_text,
        intent=result["intent"],
        target_agent=result["target_agent"],
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
    # ✅ FIX sécurité : vérifie que la conversation appartient bien à l'user
    conv_result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user["user_id"]
        )
    )
    if not conv_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Conversation non trouvée")

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