# app/a2a/discovery.py
# ═══════════════════════════════════════════════════════════
# DYNAMIC DISCOVERY — avec authentification A2A
# ═══════════════════════════════════════════════════════════

import httpx
import asyncio
import time
import os
import logging
from typing import Optional
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ── Configuration ──────────────────────────────────────────
CACHE_TTL_SECONDS = int(os.getenv("DISCOVERY_CACHE_TTL", "300"))
DISCOVERY_TIMEOUT = int(os.getenv("DISCOVERY_TIMEOUT", "5"))

# ── Token secret pour l'authentification inter-agents ──────
A2A_SECRET = os.getenv("A2A_SECRET_TOKEN", "")

# ── URLs des agents potentiels ─────────────────────────────
AGENT_ENDPOINTS = {
    "rh":       os.getenv("AGENT_RH_URL",       "http://localhost:8001"),
    "crm":      os.getenv("AGENT_CRM_URL",      "http://localhost:8002"),
    "jira":     os.getenv("AGENT_JIRA_URL",      "http://localhost:8003"),
    "slack":    os.getenv("AGENT_SLACK_URL",      "http://localhost:8004"),
    "calendar": os.getenv("AGENT_CALENDAR_URL",  "http://localhost:8005"),
}

# ── Mapping intent → skill ID ─────────────────────────────
INTENT_TO_SKILL = {
    "create_leave":          "create_leave",
    "check_leave_balance":   "check_leave_balance",
    "get_my_leaves":         "get_my_leaves",
    "get_team_availability": "get_team_availability",
    "get_team_stack":        "get_team_stack",
    "get_my_projects":       "get_my_projects",
    "get_all_projects":      "get_all_projects",
    "generate_report":       "generate_report",
    "get_tickets":           "get_tickets",
    "create_ticket":         "create_ticket",
    "update_ticket":         "update_ticket",
    "send_message":          "send_message",
    "get_calendar":          "get_calendar",
    "create_event":          "create_event",
    "search_docs":           "search_docs",
}


def _build_auth_headers() -> dict:
    """Construit les headers d'authentification pour les requêtes A2A."""
    if A2A_SECRET:
        return {"Authorization": f"Bearer {A2A_SECRET}"}
    return {}


class DiscoveredAgent:
    """Représente un agent découvert avec ses métadonnées."""
    def __init__(self, name: str, url: str, card: dict):
        self.name = name
        self.url = url
        self.card = card
        self.skills = [s.get("id", "") for s in card.get("skills", [])]
        self.description = card.get("description", "")
        self.version = card.get("version", "unknown")

    def has_skill(self, skill_id: str) -> bool:
        return skill_id in self.skills

    def __repr__(self):
        return f"Agent({self.name}, skills={self.skills}, url={self.url})"


class AgentDiscovery:
    """
    Service de découverte dynamique des agents A2A.
    Authentifié via Bearer token partagé.
    """

    def __init__(self):
        self._cache: dict[str, DiscoveredAgent] = {}
        self._last_scan: float = 0
        self._lock = asyncio.Lock()

    async def scan_agents(self, force: bool = False) -> dict[str, DiscoveredAgent]:
        """Scanne tous les agents configurés avec authentification."""
        async with self._lock:
            now = time.time()

            if not force and self._cache and (now - self._last_scan) < CACHE_TTL_SECONDS:
                logger.debug(f"🔄 Discovery cache hit ({len(self._cache)} agents)")
                return self._cache

            # ── Log sécurité ───────────────────────────────
            auth_status = "🔒 avec token" if A2A_SECRET else "⚠️ sans token (mode ouvert)"
            logger.info(f"🔍 Scanning des agents A2A ({auth_status})...")

            tasks = {
                name: self._fetch_agent_card(name, url)
                for name, url in AGENT_ENDPOINTS.items()
            }

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            new_cache = {}
            for name, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    error_type = type(result).__name__
                    # ── Distingue les erreurs d'auth des erreurs réseau ──
                    if "401" in str(result) or "403" in str(result):
                        logger.warning(f"   🔐 {name} — AUTH FAILED ({error_type})")
                    else:
                        logger.warning(f"   ❌ {name} — DOWN ({error_type})")
                elif result is not None:
                    new_cache[name] = result
                    logger.info(f"   ✅ {name} — UP (skills: {result.skills})")

            self._cache = new_cache
            self._last_scan = now

            logger.info(f"📊 Discovery terminé : {len(new_cache)}/{len(AGENT_ENDPOINTS)} agents actifs")
            return self._cache

    async def _fetch_agent_card(self, name: str, base_url: str) -> Optional[DiscoveredAgent]:
        """Récupère l'AgentCard avec authentification Bearer."""
        url = f"{base_url}/.well-known/agent.json"
        headers = _build_auth_headers()

        try:
            async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT) as client:
                response = await client.get(url, headers=headers)

                # ── Gère les erreurs d'auth explicitement ──────
                if response.status_code == 401:
                    raise Exception(f"401 Unauthorized — token manquant ou invalide")
                if response.status_code == 403:
                    raise Exception(f"403 Forbidden — token rejeté par l'agent")

                response.raise_for_status()
                card = response.json()
                return DiscoveredAgent(name=name, url=base_url, card=card)
        except Exception as e:
            raise e

    async def find_agent_for_intent(self, intent: str) -> Optional[DiscoveredAgent]:
        """Trouve l'agent capable de traiter un intent donné."""
        skill_id = INTENT_TO_SKILL.get(intent)
        if not skill_id:
            logger.warning(f"⚠️ Pas de mapping skill pour intent '{intent}'")
            return None

        agents = await self.scan_agents()

        for agent in agents.values():
            if agent.has_skill(skill_id):
                logger.info(f"🎯 Intent '{intent}' → Agent '{agent.name}' (skill: {skill_id})")
                return agent

        logger.warning(f"⚠️ Aucun agent actif avec le skill '{skill_id}' pour intent '{intent}'")
        return None

    async def get_all_active_agents(self) -> dict[str, DiscoveredAgent]:
        return await self.scan_agents()

    def get_cached_agents(self) -> dict[str, DiscoveredAgent]:
        return self._cache

    async def force_refresh(self) -> dict[str, DiscoveredAgent]:
        return await self.scan_agents(force=True)


# ── Instance globale ───────────────────────────────────────
discovery = AgentDiscovery()