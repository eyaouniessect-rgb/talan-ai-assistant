# agents/pm/jira/actions.py
# ═══════════════════════════════════════════════════════════════
# Actions CRUD Jira — une fonction par type d'objet
#
# Mapping pipeline → Jira :
#   Epic (phase 2)     → Issue type "Epic"
#   Story (phase 3)    → Issue type "Story", lié à son Epic
#   Sprint (phase 7)   → Sprint Jira + affectation des stories
#   Staffing (phase 8) → assignee sur chaque issue
# ═══════════════════════════════════════════════════════════════

import os
from dotenv import load_dotenv
from agents.pm.jira import client as jira

load_dotenv()
# _PROJECT_KEY n'est plus une constante globale.
# Chaque fonction reçoit project_key depuis le state du pipeline (1 clé par projet).


# ──────────────────────────────────────────────────────────────
# Helpers — résolution des types d'issue dans le projet
# ──────────────────────────────────────────────────────────────

_TYPE_CACHE: dict[str, str] = {}   # { "Epic" → "10000", ... }

def _get_issue_type_id(name: str) -> str:
    """Résout le nom d'un type d'issue vers son ID numérique."""
    if name in _TYPE_CACHE:
        return _TYPE_CACHE[name]
    types = jira.get("issuetype")
    for t in types:
        _TYPE_CACHE[t["name"]] = t["id"]
    return _TYPE_CACHE.get(name, name)


# ──────────────────────────────────────────────────────────────
# PHASE 2 — Epics
# ──────────────────────────────────────────────────────────────

def create_epic(title: str, description: str, project_key: str) -> str:
    """
    Crée un Epic dans Jira dans le projet identifié par project_key.
    Retourne la clé Jira (ex: "TALAN-1").
    """
    print(f"[Jira] create_epic : {title} → projet {project_key}")
    body = {
        "fields": {
            "project":     {"key": project_key},
            "summary":     title,
            "description": _text_doc(description),
            "issuetype":   {"name": "Epic"},
        }
    }
    result = jira.post("issue", body)
    key = result["key"]
    print(f"[Jira] Epic cree : {key}")
    return key


# ──────────────────────────────────────────────────────────────
# PHASE 3 — Stories
# ──────────────────────────────────────────────────────────────

def create_story(
    title:               str,
    description:         str,
    acceptance_criteria: list[str],
    project_key:         str,
    epic_key:            str | None = None,
    story_points:        int | None = None,
) -> str:
    """
    Crée une User Story dans Jira dans le projet project_key, liée à son Epic.
    Retourne la clé Jira (ex: "TALAN-5").

    Stratégie d'epic link (essaie dans cet ordre) :
      1. customfield_10014  → projets Classic/Company-managed
      2. parent.key         → projets NextGen/Team-managed
      3. sans epic link     → fallback garanti pour créer la story quand même
    """
    print(f"[Jira] create_story : {title[:60]} → projet {project_key} (epic={epic_key})")
    ac_text   = "\n".join(f"- {c}" for c in (acceptance_criteria or []))
    full_desc = description
    if ac_text:
        full_desc += f"\n\n*Critères d'acceptation :*\n{ac_text}"

    # Champs de base — summary tronqué à 250 chars (limite Jira = 255)
    base_fields: dict = {
        "project":     {"key": project_key},
        "summary":     title[:250],
        "description": _text_doc(full_desc),
        "issuetype":   {"name": "Story"},
    }
    if story_points:
        sp_field = jira.get_story_points_field_id()
        base_fields[sp_field] = float(story_points)

    # Séquence de tentatives pour le lien Epic
    attempts: list[dict] = []
    if epic_key:
        attempts.append({**base_fields, "customfield_10014": epic_key})   # Classic
        attempts.append({**base_fields, "parent": {"key": epic_key}})     # NextGen
    attempts.append(base_fields)   # Sans lien epic (fallback garanti)

    last_err: Exception | None = None
    for attempt_fields in attempts:
        try:
            result = jira.post("issue", {"fields": attempt_fields})
            key = result["key"]
            linked = "epic_link" if "customfield_10014" in attempt_fields \
                else ("parent" if "parent" in attempt_fields else "sans_epic")
            print(f"[Jira] Story creee : {key} (stratégie={linked})")
            return key
        except RuntimeError as e:
            last_err = e
            err_str = str(e)
            # Réessayer seulement sur une erreur 400 liée au champ epic
            if "400" in err_str and epic_key:
                print(f"[Jira]   ⚠ Tentative échouée ({err_str[:120]}) → essai suivant")
                continue
            raise   # Autre erreur HTTP → ne pas réessayer

    raise RuntimeError(f"[Jira] create_story échoué sur toutes les tentatives : {last_err}")


# ──────────────────────────────────────────────────────────────
# PHASE 7 — Sprints
# ──────────────────────────────────────────────────────────────

def get_board_id(project_key: str) -> int | None:
    """Récupère l'ID du board Jira du projet identifié par project_key."""
    try:
        import requests
        url   = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        r = requests.get(
            f"{url}/rest/agile/1.0/board",
            auth=(email, token),
            headers={"Accept": "application/json"},
            params={"projectKeyOrId": project_key},
            timeout=10,
        )
        if r.ok:
            boards = r.json().get("values", [])
            if boards:
                return boards[0]["id"]
    except Exception as e:
        print(f"[Jira] get_board_id erreur : {e}")
    return None


def create_sprint(board_id: int, name: str, start_date: str, end_date: str) -> int | None:
    """
    Crée un Sprint Jira. Retourne l'ID du sprint créé.
    """
    print(f"[Jira] create_sprint : {name}")
    try:
        import requests, os
        url   = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        r = requests.post(
            f"{url}/rest/agile/1.0/sprint",
            auth=(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={
                "name":          name,
                "startDate":     start_date,
                "endDate":       end_date,
                "originBoardId": board_id,
            },
            timeout=10,
        )
        if r.ok:
            sprint_id = r.json()["id"]
            print(f"[Jira] Sprint cree : id={sprint_id}")
            return sprint_id
        else:
            print(f"[Jira] create_sprint HTTP {r.status_code} : {r.text[:200]}")
    except Exception as e:
        print(f"[Jira] create_sprint erreur : {e}")
    return None


def add_issues_to_sprint(sprint_id: int, issue_keys: list[str]) -> None:
    """Ajoute des issues à un sprint existant."""
    if not issue_keys:
        return
    print(f"[Jira] add_to_sprint sprint={sprint_id} issues={issue_keys}")
    try:
        import requests, os
        url   = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        requests.post(
            f"{url}/rest/agile/1.0/sprint/{sprint_id}/issue",
            auth=(email, token),
            headers={"Content-Type": "application/json"},
            json={"issues": issue_keys},
            timeout=10,
        )
    except Exception as e:
        print(f"[Jira] add_issues_to_sprint erreur : {e}")


def start_sprint(sprint_id: int, actual_start: str, planned_end: str) -> bool:
    """
    Démarre un Sprint Jira (state: future → active).

    actual_start : date réelle de démarrage (clic PM, format ISO YYYY-MM-DD).
                   C'est cette date que Jira utilise pour le burndown.
    planned_end  : date de fin planifiée (engagement initial).
    """
    print(f"[Jira] start_sprint id={sprint_id} actual_start={actual_start} planned_end={planned_end}")
    try:
        import requests, os
        url   = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        r = requests.post(
            f"{url}/rest/agile/1.0/sprint/{sprint_id}",
            auth=(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={
                "state":     "active",
                "startDate": actual_start,
                "endDate":   planned_end,
            },
            timeout=10,
        )
        if r.ok:
            print(f"[Jira] Sprint {sprint_id} démarré (active)")
            return True
        print(f"[Jira] start_sprint HTTP {r.status_code} : {r.text[:200]}")
    except Exception as e:
        print(f"[Jira] start_sprint erreur : {e}")
    return False


def complete_sprint(sprint_id: int) -> bool:
    """Clôture un Sprint Jira (state: active → closed)."""
    print(f"[Jira] complete_sprint id={sprint_id}")
    try:
        import requests, os
        url   = os.getenv("JIRA_BASE_URL", "").rstrip("/")
        email = os.getenv("JIRA_EMAIL", "")
        token = os.getenv("JIRA_API_TOKEN", "")
        r = requests.post(
            f"{url}/rest/agile/1.0/sprint/{sprint_id}",
            auth=(email, token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            json={"state": "closed"},
            timeout=10,
        )
        if r.ok:
            print(f"[Jira] Sprint {sprint_id} clôturé (closed)")
            return True
        print(f"[Jira] complete_sprint HTTP {r.status_code} : {r.text[:200]}")
    except Exception as e:
        print(f"[Jira] complete_sprint erreur : {e}")
    return False


# ──────────────────────────────────────────────────────────────
# PHASE 4 — Dépendances (Issue Links)
# ──────────────────────────────────────────────────────────────

# Mapping relation_type → nom du lien Jira
# FS (Finish-to-Start) = la story "from" bloque la story "to"
_RELATION_TO_LINK_TYPE: dict[str, str] = {
    "FS": "Blocks",
    "SS": "Relates",
    "FF": "Relates",
    "SF": "Relates",
}

def create_issue_link(
    inward_key:  str,
    outward_key: str,
    relation_type: str = "FS",
) -> None:
    """
    Crée un Issue Link Jira entre deux stories.
    FS → inward_key "blocks" outward_key.
    Autres types → "Relates to".
    """
    link_type = _RELATION_TO_LINK_TYPE.get(relation_type, "Relates")
    print(f"[Jira] issue_link : {inward_key} --{link_type}--> {outward_key}")
    try:
        jira.post(
            "issueLink",
            {
                "type":          {"name": link_type},
                "inwardIssue":   {"key": inward_key},
                "outwardIssue":  {"key": outward_key},
            },
        )
    except Exception as e:
        print(f"[Jira] create_issue_link erreur ({inward_key}→{outward_key}) : {e}")
        raise


# ──────────────────────────────────────────────────────────────
# Mise à jour d'un champ sur une issue existante
# ──────────────────────────────────────────────────────────────

def update_story_points(issue_key: str, story_points: int) -> None:
    """
    Met à jour les story points sur une issue Jira déjà créée.
    Envoie la valeur sur tous les champs story-points détectés en une seule requête PUT
    (couvre customfield_10016 "Story point estimate" ET customfield_10028 "Story Points").
    """
    if not story_points:
        return
    sp_fields = jira.get_story_points_field_ids()
    value = int(story_points)
    fields_payload = {f: value for f in sp_fields}
    print(f"[Jira] update_story_points {issue_key} → {fields_payload}")
    try:
        jira.put(f"issue/{issue_key}", {"fields": fields_payload})
        print(f"[Jira] update_story_points OK ({issue_key})")
    except Exception as e:
        # Jira rejette parfois les champs inexistants dans le projet — retry champ par champ
        print(f"[Jira] update_story_points bulk échoué ({e}), retry champ par champ")
        last_err: Exception | None = None
        for sp_field in sp_fields:
            try:
                jira.put(f"issue/{issue_key}", {"fields": {sp_field: value}})
                print(f"[Jira] update_story_points OK ({issue_key} {sp_field}={value})")
            except Exception as e2:
                last_err = e2
                print(f"[Jira] update_story_points SKIP {sp_field} : {e2}")
        if last_err and len(sp_fields) == 1:
            raise RuntimeError(f"update_story_points {issue_key} échoué : {last_err}")


# ──────────────────────────────────────────────────────────────
# PHASE 8 — Staffing (assignation)
# ──────────────────────────────────────────────────────────────

def add_label(issue_key: str, label: str) -> None:
    """Ajoute un label sur une issue Jira sans écraser les labels existants."""
    print(f"[Jira] add_label {issue_key} ← '{label}'")
    try:
        current = jira.get(f"issue/{issue_key}?fields=labels")
        existing = [l["name"] for l in (current.get("fields", {}).get("labels") or [])]
        if label in existing:
            print(f"[Jira] add_label SKIP — label '{label}' déjà présent sur {issue_key}")
            return
        jira.put(f"issue/{issue_key}", {"fields": {"labels": existing + [label]}})
        print(f"[Jira] add_label OK {issue_key} → {existing + [label]}")
    except Exception as e:
        print(f"[Jira] add_label erreur ({issue_key}) : {e}")
        raise


def assign_issue(issue_key: str, account_id: str) -> None:
    """Assigne une issue Jira à un utilisateur via son accountId."""
    print(f"[Jira] assign {issue_key} -> {account_id}")
    try:
        jira.put(f"issue/{issue_key}/assignee", {"accountId": account_id})
    except Exception as e:
        print(f"[Jira] assign_issue erreur : {e}")


# ──────────────────────────────────────────────────────────────
# Helper — format texte pour l'API Jira v3 (Atlassian Document Format)
# ──────────────────────────────────────────────────────────────

def _text_doc(text: str) -> dict:
    """Convertit un texte brut en Atlassian Document Format (ADF)."""
    return {
        "type":    "doc",
        "version": 1,
        "content": [
            {
                "type":    "paragraph",
                "content": [{"type": "text", "text": text or " "}],
            }
        ],
    }
