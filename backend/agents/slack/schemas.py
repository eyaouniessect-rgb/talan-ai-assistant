# agents/slack/schemas.py
# ═══════════════════════════════════════════════════════════
# AgentCard A2A + Modèles Pydantic — Agent Slack
# ═══════════════════════════════════════════════════════════
# IMPORTANT : les skill IDs doivent correspondre EXACTEMENT
# aux valeurs dans app/a2a/discovery.py → AGENT_ENDPOINTS["slack"]

import os
from a2a.types import AgentCard, AgentSkill, AgentCapabilities
from pydantic import BaseModel
from typing import Optional


# ══════════════════════════════════════════════════════
# PARTIE 1 — Identité A2A (AgentCard + AgentSkills)
# ══════════════════════════════════════════════════════

skill_send_message = AgentSkill(
    id="send_slack_message",
    name="Envoyer un message Slack",
    description=(
        "Envoie un message dans un channel Slack, une conversation privée "
        "ou en réponse à un thread. Peut notifier une équipe entière."
    ),
    tags=[
        "slack", "message", "envoyer", "send", "notifier", "notifie",
        "poste", "post", "channel", "canal", "équipe", "equipe", "team",
        "notifie", "notification", "alerte", "alert", "#general", "#dev",
        "envoie un message", "send message", "poster dans", "écrire dans",
    ],
    examples=[
        "Envoie un message dans #general pour annoncer la réunion",
        "Notifie l'équipe dev dans #dev-team",
        "Poste dans #projet-x que le déploiement est terminé",
        "Envoie une alerte à #incidents",
        "Écris à @ahmed sur Slack",
    ],
)

skill_read_channel = AgentSkill(
    id="read_slack_channel",
    name="Lire les messages d'un channel Slack",
    description=(
        "Récupère les derniers messages d'un channel Slack. "
        "Permet de voir les échanges récents d'une équipe ou d'un projet."
    ),
    tags=[
        "slack", "lire", "read", "messages", "channel", "canal",
        "derniers messages", "historique", "history", "voir messages",
        "quoi de neuf", "activité slack", "messages récents",
    ],
    examples=[
        "Montre-moi les derniers messages de #dev-team",
        "Lis les messages de #general aujourd'hui",
        "Quels sont les 10 derniers messages de #projet-x ?",
        "Quoi de neuf dans #infra ?",
    ],
)

skill_search_messages = AgentSkill(
    id="search_slack_messages",
    name="Rechercher des messages Slack",
    description=(
        "Recherche des messages dans Slack selon un mot-clé, une expression, "
        "un auteur ou dans un channel spécifique. "
        "Supporte les filtres avancés Slack."
    ),
    tags=[
        "slack", "recherche", "search", "cherche", "trouver", "find",
        "messages", "qui a dit", "mention", "a parlé de", "keyword",
        "mots-clés", "recherche dans slack", "slack search",
    ],
    examples=[
        "Cherche les messages qui mentionnent le projet Alpha",
        "Qui a parlé de déploiement dans #dev-team ?",
        "Trouve les messages de @sana sur le bug critique",
        "Recherche dans Slack les discussions sur la sprint review",
    ],
)

skill_notify_team = AgentSkill(
    id="notify_slack_team",
    name="Notifier une équipe sur Slack",
    description=(
        "Compose et envoie une notification structurée à une équipe "
        "ou un channel Slack. Utilisé pour les alertes, annonces et rappels."
    ),
    tags=[
        "slack", "notifier", "notification", "alerte", "alert", "équipe",
        "team", "annonce", "announce", "rappel", "reminder", "broadcast",
        "informer", "avertir", "prévenir",
    ],
    examples=[
        "Notifie l'équipe RH qu'un congé a été approuvé",
        "Envoie un rappel de la réunion dans #pm-team",
        "Informe #general que le serveur sera en maintenance",
        "Alerte #incidents d'une anomalie en production",
    ],
)


def build_agent_card(host: str, port: int) -> AgentCard:
    return AgentCard(
        name="SlackAgent",
        description=(
            "Agent spécialisé dans la communication Slack : "
            "envoi de messages dans des channels, lecture des échanges récents, "
            "recherche de messages par mot-clé, et notification d'équipes."
        ),
        url=f"http://{host}:{port}/",
        version="1.0.0",
        default_input_modes=["text"],
        default_output_modes=["text"],
        capabilities=AgentCapabilities(streaming=True),
        skills=[
            skill_send_message,
            skill_read_channel,
            skill_search_messages,
            skill_notify_team,
        ],
    )


# ══════════════════════════════════════════════════════
# PARTIE 2 — Modèles Pydantic
# ══════════════════════════════════════════════════════

class SendMessageRequest(BaseModel):
    channel: str
    text: str
    thread_ts: Optional[str] = None

class MessageResponse(BaseModel):
    ok: bool
    ts: Optional[str] = None
    channel: Optional[str] = None
    error: Optional[str] = None

class SearchResponse(BaseModel):
    messages: list[dict]
    total: Optional[int] = None
