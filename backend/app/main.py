# Point d'entrée FastAPI.
# Initialise l'app, enregistre les routers, configure CORS,
# rate limiting, middleware de sécurité et LangSmith.
# app/main.py
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.orchestrator.graph import init_graph
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.events import router as events_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Démarrage ──────────────────────────────────────
    await init_graph()
    yield
    # ── Arrêt ──────────────────────────────────────────
    print("🛑 Arrêt du serveur.")


app = FastAPI(
    title="Talan Assistant API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(events_router)

@app.get("/health")
async def health():
    return {"status": "ok", "app": "Talan Assistant"}