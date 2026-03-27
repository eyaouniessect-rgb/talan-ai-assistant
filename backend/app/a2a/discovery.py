# app/a2a/discovery.py
# ═══════════════════════════════════════════════════════════
# DYNAMIC DISCOVERY — simplifié
# Plus de mapping intent→skill. Node 1 fournit directement le
# target_agent, et discovery trouve l'agent par son nom.
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

CACHE_TTL_SECONDS = int(os.getenv("DISCOVERY_CACHE_TTL", "300"))
DISCOVERY_TIMEOUT = int(os.getenv("DISCOVERY_TIMEOUT", "5"))
A2A_SECRET = os.getenv("A2A_SECRET_TOKEN", "")

AGENT_ENDPOINTS = {
    "rh":       os.getenv("AGENT_RH_URL",       "http://localhost:8001"),
    "calendar": os.getenv("AGENT_CALENDAR_URL",  "http://localhost:8002"),
    "crm":      os.getenv("AGENT_CRM_URL",      "http://localhost:8003"),
    "jira":     os.getenv("AGENT_JIRA_URL",      "http://localhost:8004"),
    "slack":    os.getenv("AGENT_SLACK_URL",      "http://localhost:8005"),
}


def _build_auth_headers() -> dict:
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

    def __init__(self):
        self._cache: dict[str, DiscoveredAgent] = {}
        self._last_scan: float = 0
        self._lock = asyncio.Lock()

    async def scan_agents(self, force: bool = False) -> dict[str, DiscoveredAgent]:
        """Scanne tous les agents configurés."""
        async with self._lock:
            now = time.time()

            if not force and self._cache and (now - self._last_scan) < CACHE_TTL_SECONDS:
                return self._cache

            auth_status = "🔒 avec token" if A2A_SECRET else "⚠️ sans token"
            logger.info(f"🔍 Scanning des agents A2A ({auth_status})...")

            tasks = {
                name: self._fetch_agent_card(name, url)
                for name, url in AGENT_ENDPOINTS.items()
            }

            results = await asyncio.gather(*tasks.values(), return_exceptions=True)

            new_cache = {}
            for name, result in zip(tasks.keys(), results):
                if isinstance(result, Exception):
                    if "401" in str(result) or "403" in str(result):
                        logger.warning(f"   🔐 {name} — AUTH FAILED")
                    else:
                        logger.warning(f"   ❌ {name} — DOWN ({type(result).__name__})")
                elif result is not None:
                    new_cache[name] = result
                    logger.info(f"   ✅ {name} — UP (skills: {result.skills})")

            self._cache = new_cache
            self._last_scan = now

            logger.info(f"📊 Discovery : {len(new_cache)}/{len(AGENT_ENDPOINTS)} agents actifs")
            return self._cache

    async def _fetch_agent_card(self, name: str, base_url: str) -> Optional[DiscoveredAgent]:
        url = f"{base_url}/.well-known/agent.json"
        headers = _build_auth_headers()

        try:
            async with httpx.AsyncClient(timeout=DISCOVERY_TIMEOUT) as client:
                response = await client.get(url, headers=headers)
                if response.status_code == 401:
                    raise Exception("401 Unauthorized")
                if response.status_code == 403:
                    raise Exception("403 Forbidden")
                response.raise_for_status()
                card = response.json()
                return DiscoveredAgent(name=name, url=base_url, card=card)
        except Exception as e:
            raise e

    async def find_agent_by_name(self, agent_name: str) -> Optional[DiscoveredAgent]:
        """Trouve un agent par son nom (rh, calendar, etc.)."""
        agents = await self.scan_agents()
        agent = agents.get(agent_name)
        if agent:
            logger.info(f"🎯 Agent '{agent_name}' trouvé à {agent.url}")
        else:
            logger.warning(f"⚠️ Agent '{agent_name}' non disponible")
        return agent

    async def get_all_active_agents(self) -> dict[str, DiscoveredAgent]:
        return await self.scan_agents()

    def get_cached_agents(self) -> dict[str, DiscoveredAgent]:
        return self._cache

    async def force_refresh(self) -> dict[str, DiscoveredAgent]:
        return await self.scan_agents(force=True)


discovery = AgentDiscovery()
