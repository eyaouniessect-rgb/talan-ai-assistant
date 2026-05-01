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


# ──────────────────────────────────────────────────────────────
# Résolution dynamique du champ "Story Points"
# ──────────────────────────────────────────────────────────────

_STORY_POINTS_FIELD_IDS: list[str] | None = None   # cache in-process

# Jira Cloud expose deux champs distincts selon le type de projet :
#   customfield_10016 = "Story point estimate" (next-gen / sprint planning)
#   customfield_10028 = "Story Points"         (classic / colonne backlog)
# On met les deux à jour pour couvrir tous les cas.
_STORY_POINTS_NAMES = {
    "story points", "story point estimate", "estimation", "points",
    "story point", "sp", "complexity",
}

def get_story_points_field_ids() -> list[str]:
    """
    Retourne la liste de tous les IDs de champs Jira correspondant aux story points.
    Jira Cloud peut avoir deux champs (customfield_10016 ET customfield_10028) ;
    les deux sont mis à jour pour que la valeur apparaisse partout (backlog + ticket detail).
    """
    global _STORY_POINTS_FIELD_IDS
    if _STORY_POINTS_FIELD_IDS is not None:
        return _STORY_POINTS_FIELD_IDS

    found: list[str] = []
    try:
        fields = _request("GET", "field")
        if isinstance(fields, list):
            for f in fields:
                name = (f.get("name") or "").strip().lower()
                if name in _STORY_POINTS_NAMES:
                    found.append(f["id"])
                    print(f"[Jira] Story Points field trouvé : '{f['name']}' → id={f['id']}")
    except Exception as e:
        print(f"[Jira] Impossible de résoudre les champs Story Points : {e}")

    if not found:
        found = ["customfield_10016"]
        print("[Jira] Story Points field non trouvé → fallback customfield_10016")

    _STORY_POINTS_FIELD_IDS = found
    return _STORY_POINTS_FIELD_IDS


def get_story_points_field_id() -> str:
    """Retourne le premier champ story points détecté (compatibilité)."""
    return get_story_points_field_ids()[0]
