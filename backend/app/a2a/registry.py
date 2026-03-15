# Registre des agents disponibles.
# Charge les URLs des agents depuis les variables d'environnement.
# Méthode : get_agent(name) → AgentCard
# Utilisé par Node 3 pour résoudre l'URL de l'agent cible.
import os

AGENT_REGISTRY = {
    "rh":       os.getenv("AGENT_RH_URL",       "http://localhost:8001"),
    "crm":      os.getenv("AGENT_CRM_URL",      "http://localhost:8002"),
    "jira":     os.getenv("AGENT_JIRA_URL",     "http://localhost:8003"),
    "slack":    os.getenv("AGENT_SLACK_URL",     "http://localhost:8004"),
    "calendar": os.getenv("AGENT_CALENDAR_URL", "http://localhost:8005"),
}

def get_agent_url(agent_name: str) -> str:
    url = AGENT_REGISTRY.get(agent_name)
    if not url:
        raise ValueError(f"Agent inconnu : '{agent_name}'")
    return url