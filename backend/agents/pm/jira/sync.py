# agents/pm/jira/sync.py
# ═══════════════════════════════════════════════════════════════
# Synchronisation Jira via Atlassian MCP Remote Server
#
# Ce noeud est appelé après chaque validation humaine approuvée.
# Il synchronise le résultat de la phase avec Jira via le
# serveur MCP officiel Atlassian (remote MCP, OAuth 2.0).
#
# Référence : https://www.atlassian.com/blog/announcements/remote-mcp-server
#
# Mapping phase → opération Jira :
#   epics           → create Epics (issue type: Epic)
#   stories         → create Issues (issue type: Story)
#   refinement      → update Issues (description + acceptance criteria)
#   story_deps      → create Issue Links (type: "is blocked by")
#   prioritization  → update Priority field sur chaque Issue
#   tasks           → create Sub-tasks
#   task_deps       → create Issue Links entre sub-tasks
#   cpm             → add label "critical-path" sur les tasks critiques
#   sprints         → create Sprints + move Issues dans les sprints
#   staffing        → assign Issues aux membres Jira
#
# ⚠ Ce fichier est un STUB — l'implémentation MCP sera faite
#   dans une prochaine étape (après validation du graph complet).
# ═══════════════════════════════════════════════════════════════

from agents.pm.state import PMPipelineState


# ──────────────────────────────────────────────────────────────
# MAPPING PHASE → OPÉRATION JIRA
# ──────────────────────────────────────────────────────────────

_PHASE_SYNC_MAP = {
    "epics":           "create_epics",
    "stories":         "create_stories",

    "story_deps":      "create_story_links",
    "prioritization":  "update_priority",
    "tasks":           "create_subtasks",
    "task_deps":       "create_task_links",
    "cpm":             "update_critical_labels",
    "sprints":         "create_sprints",
    "staffing":        "assign_issues",
}


# ──────────────────────────────────────────────────────────────
# NOEUD JIRA SYNC
# ──────────────────────────────────────────────────────────────

async def node_jira_sync(state: PMPipelineState) -> dict:
    """
    Synchronise le résultat de la phase courante avec Jira.
    Appelé uniquement après une validation humaine approuvée.

    Retourne un patch du state avec :
      - jira_*_map mis à jour (mapping local idx → clé Jira)
      - jira_synced_phases mis à jour (ajout de la phase courante)
    """
    phase = state.get("current_phase", "")
    operation = _PHASE_SYNC_MAP.get(phase)

    if not operation:
        # Phase sans sync Jira (extract, monitoring) → on passe
        print(f"[JIRA SYNC] Phase '{phase}' : pas de sync Jira pour cette phase")
        return {}

    # Éviter les doubles sync (reprise après crash)
    already_synced = state.get("jira_synced_phases") or []
    if phase in already_synced:
        print(f"[JIRA SYNC] Phase '{phase}' déjà synchronisée → skip")
        return {}

    print(f"[JIRA SYNC] Phase '{phase}' → opération '{operation}' (stub)")

    # ── TODO : appel MCP Atlassian ─────────────────────────────
    # L'implémentation MCP sera ajoutée ici :
    #   client = AtlassianMCPClient(oauth_token=...)
    #   result = await client.call_tool(operation, payload)
    #   return { "jira_epic_map": result.epic_map, ... }
    # ──────────────────────────────────────────────────────────

    # Pour l'instant, on marque juste la phase comme synchronisée
    return {
        "jira_synced_phases": already_synced + [phase],
    }
