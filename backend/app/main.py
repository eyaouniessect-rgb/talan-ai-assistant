# Point d'entrée FastAPI.
# Initialise l'app, enregistre les routers, configure CORS,
# rate limiting, middleware de sécurité et LangSmith.
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os

load_dotenv()

from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
app = FastAPI(
    title="Talan Assistant API",
    version="1.0.0",
)

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(chat_router)
@app.get("/health")
async def health():
    return {"status": "ok", "app": "Talan Assistant"}