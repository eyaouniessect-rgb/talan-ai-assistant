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
from agents.pm.graph import init_pm_graph

# Imports des routers depuis la nouvelle structure api/ (sous-dossiers par domaine)
from app.api.auth.login import router as auth_router
from app.api.auth.google_oauth import router as google_oauth_router
from app.api.chat.chat import router as chat_router
from app.api.rh.rh import router as rh_router
from app.api.events.events import router as events_router
from app.api.crm.crm import router as crm_router
from app.api.documents.documents import router as documents_router
from app.api.pipeline.pipeline import router as pipeline_router
from app.api.dashboard.pm      import router as dashboard_pm_router
from app.api.report            import router as report_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Démarrage ──────────────────────────────────────
    await init_graph()       # orchestrateur conversationnel
    await init_pm_graph()    # pipeline PM (12 phases)
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
app.include_router(rh_router)
app.include_router(google_oauth_router)
app.include_router(crm_router)
app.include_router(documents_router)
app.include_router(pipeline_router)
app.include_router(dashboard_pm_router)
app.include_router(report_router)

@app.get("/health")
async def health():
    return {"status": "ok", "app": "Talan Assistant"}