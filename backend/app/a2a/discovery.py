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
from langsmith import traceable

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
        # ── Capacité de streaming ──────────────────────────
        self.supports_streaming = card.get("capabilities", {}).get("streaming", False)

    def has_skill(self, skill_id: str) -> bool:
        return skill_id in self.skills

    def __repr__(self):
        return f"Agent({self.name}, skills={self.skills}, streaming={self.supports_streaming}, url={self.url})"


class AgentDiscovery:

    def __init__(self):
        self._cache: dict[str, DiscoveredAgent] = {}
        self._last_scan: float = 0
        self._lock = asyncio.Lock()

    @traceable(name="discovery.scan_agents", tags=["a2a", "discovery"])
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
                    print(f"   ✅ {name} — UP skills={result.skills} streaming={result.supports_streaming}")
                    logger.info(f"   ✅ {name} — UP (skills: {result.skills}, streaming: {result.supports_streaming})")

            self._cache = new_cache
            self._last_scan = now

            logger.info(f"📊 Discovery : {len(new_cache)}/{len(AGENT_ENDPOINTS)} agents actifs")
            return self._cache

    @traceable(name="discovery.fetch_card", tags=["a2a", "http"])
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

    @traceable(name="discovery.find_agent", tags=["a2a", "discovery"])
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


# ══════════════════════════════════════════════════════════
# ROUTING MANIFEST — auto-généré depuis les Agent Cards
# ══════════════════════════════════════════════════════════

class RoutingManifest:
    """
    Construit un manifest de routage à partir des Agent Cards A2A.
    - routing_prompt : prompt LLM auto-généré avec descriptions + skills + examples
    - keyword_map    : {agent_name: set(tags)} extrait automatiquement des skills
    """

    def __init__(self):
        self._prompt: str = ""
        self._keyword_map: dict[str, set[str]] = {}
        self._agent_names: set[str] = set()
        self._last_build: float = 0

    @property
    def routing_prompt(self) -> str:
        return self._prompt

    @property
    def keyword_map(self) -> dict[str, set[str]]:
        return self._keyword_map

    @property
    def agent_names(self) -> set[str]:
        return self._agent_names

    def is_stale(self) -> bool:
        import time
        return (time.time() - self._last_build) > CACHE_TTL_SECONDS or not self._prompt

    async def build(self, force: bool = False) -> "RoutingManifest":
        """Reconstruit le manifest depuis les Agent Cards découvertes."""
        import time

        if not force and not self.is_stale():
            return self

        agents = await discovery.scan_agents(force=force)

        if not agents:
            logger.warning("⚠️ Aucun agent découvert — manifest vide")
            return self

        prompt_lines = []
        keyword_map = {}
        agent_names = set()

        for name, agent in sorted(agents.items()):
            agent_names.add(name)
            card = agent.card

            # ── En-tête agent (description complète) ────────────
            desc = card.get("description", "Pas de description")
            prompt_lines.append(f"\n## AGENT: {name}")
            prompt_lines.append(f"   Description: {desc}")

            skills = card.get("skills", [])
            all_tags = set()

            for skill in skills:
                skill_id   = skill.get("id", "?")
                skill_name = skill.get("name", skill_id)
                skill_desc = skill.get("description", "")
                examples   = skill.get("examples", [])
                tags       = skill.get("tags", [])

                all_tags.update(t.lower() for t in tags)

                # Skill complet : id + nom + description complète
                prompt_lines.append(f"  • {skill_id} ({skill_name})")
                if skill_desc:
                    prompt_lines.append(f"    → {skill_desc}")
                # Exemples représentatifs : max 2 par skill pour rester compact
                if examples:
                    for ex in examples[:2]:
                        prompt_lines.append(f"    Ex: \"{ex}\"")

            # --- Enrichir les tags avec des mots extraits des examples ---
            # On filtre les mots génériques (verbes d'action, temporels, pronoms)
            # pour éviter que des mots comme "supprimer", "demain" créent des
            # collisions entre agents.
            _GENERIC_WORDS = {
                # Pronoms / déterminants / prépositions
                "dans", "avec", "pour", "quel", "quels", "quelle", "quelles",
                "cette", "mon", "mes", "mes", "sont", "est-ce", "votre", "vous",
                "moi", "nous", "leur", "leurs", "tous", "tout", "toute", "toutes",
                # Temporels (partagés entre agents)
                "prochaine", "prochain", "semaine", "mois", "demain", "aujourd'hui",
                "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche",
                "matin", "après-midi", "soir", "jour", "jours", "heure", "heures",
                "date", "dates",
                # Verbes d'action génériques (partagés entre agents)
                "créer", "creer", "supprimer", "supprime", "modifier", "modifie",
                "annuler", "annule", "consulter", "consulte", "voir", "montre",
                "affiche", "cherche", "chercher", "trouver", "trouve", "montrer",
                "vérifier", "verifie", "vérifie",
                # Mots de liaison
                "comment", "combien", "quand", "peut", "veux", "voudrais",
                "souhaite", "besoin", "faire", "fait",
            }
            for skill in skills:
                for ex in skill.get("examples", []):
                    words = ex.lower().split()
                    for w in words:
                        clean = w.strip(".,?!\"'()[]")
                        if len(clean) > 3 and clean not in _GENERIC_WORDS:
                            all_tags.add(clean)

            keyword_map[name] = all_tags

        self._prompt = (
            f"AGENTS DISPONIBLES ({len(agents)} agents actifs):\n"
            + "\n".join(prompt_lines)
        )
        self._keyword_map = keyword_map
        self._agent_names = agent_names
        self._last_build = time.time()

        logger.info(f"📋 Routing manifest construit : {len(agents)} agents, "
                     f"{sum(len(t) for t in keyword_map.values())} keywords total")

        return self


routing_manifest = RoutingManifest()
