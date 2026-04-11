# agents/pm/jira/client.py
# ═══════════════════════════════════════════════════════════════
# Singleton JiraClient — connexion à l'API Jira REST v3
# Lit JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN depuis .env
# ═══════════════════════════════════════════════════════════════

import os
import requests
from dotenv import load_dotenv

load_dotenv()

_BASE_URL  = os.getenv("JIRA_BASE_URL", "").rstrip("/")
_EMAIL     = os.getenv("JIRA_EMAIL", "")
_TOKEN     = os.getenv("JIRA_API_TOKEN", "")
_AUTH      = (_EMAIL, _TOKEN)
_HEADERS   = {"Accept": "application/json", "Content-Type": "application/json"}


def _request(method: str, path: str, **kwargs) -> dict:
    """Wrapper HTTP avec gestion d'erreur simple."""
    url = f"{_BASE_URL}/rest/api/3/{path.lstrip('/')}"
    r = requests.request(method, url, auth=_AUTH, headers=_HEADERS, timeout=15, **kwargs)
    if not r.ok:
        raise RuntimeError(
            f"[Jira] {method} {path} → HTTP {r.status_code} : {r.text[:300]}"
        )
    return r.json() if r.text else {}


def get(path: str) -> dict:
    return _request("GET", path)

def post(path: str, body: dict) -> dict:
    return _request("POST", path, json=body)

def put(path: str, body: dict) -> dict:
    return _request("PUT", path, json=body)
