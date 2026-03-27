# scripts/seed_permissions.py
# ═══════════════════════════════════════════════════════════
# RBAC par TOOL — les permissions sont maintenant par nom d'outil
# (tel que déclaré dans les agents), pas par intent.
# ═══════════════════════════════════════════════════════════
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal
from app.database.models.permissions import Permission

PERMISSIONS = [
    # ═══════════════════════════════════════════════════
    # CONSULTANT
    # ═══════════════════════════════════════════════════

    # ── Calendar Agent tools ──────────────────────────
    {"role": "consultant", "action": "check_calendar_conflicts", "allowed": True},
    {"role": "consultant", "action": "get_calendar_events",      "allowed": True},
    {"role": "consultant", "action": "create_meeting",           "allowed": True},
    {"role": "consultant", "action": "update_meeting",           "allowed": True},
    {"role": "consultant", "action": "delete_meeting",           "allowed": True},
    {"role": "consultant", "action": "search_meetings",          "allowed": True},

    # ── RH Agent tools ────────────────────────────────
    {"role": "consultant", "action": "create_leave",             "allowed": True},
    {"role": "consultant", "action": "get_my_leaves",            "allowed": True},
    {"role": "consultant", "action": "check_leave_balance",      "allowed": True},
    {"role": "consultant", "action": "get_team_availability",    "allowed": True},
    {"role": "consultant", "action": "get_team_stack",           "allowed": True},
    {"role": "consultant", "action": "notify_manager",           "allowed": True},

    # ═══════════════════════════════════════════════════
    # PM — tout ce que le consultant peut + plus
    # ═══════════════════════════════════════════════════

    # ── Calendar Agent tools ──────────────────────────
    {"role": "pm", "action": "check_calendar_conflicts", "allowed": True},
    {"role": "pm", "action": "get_calendar_events",      "allowed": True},
    {"role": "pm", "action": "create_meeting",           "allowed": True},
    {"role": "pm", "action": "update_meeting",           "allowed": True},
    {"role": "pm", "action": "delete_meeting",           "allowed": True},
    {"role": "pm", "action": "search_meetings",          "allowed": True},

    # ── RH Agent tools ────────────────────────────────
    {"role": "pm", "action": "create_leave",             "allowed": True},
    {"role": "pm", "action": "get_my_leaves",            "allowed": True},
    {"role": "pm", "action": "check_leave_balance",      "allowed": True},
    {"role": "pm", "action": "get_team_availability",    "allowed": True},
    {"role": "pm", "action": "get_team_stack",           "allowed": True},
    {"role": "pm", "action": "notify_manager",           "allowed": True},

    # ── PM-only tools (futurs) ────────────────────────
    # {"role": "pm", "action": "generate_report",       "allowed": True},
    # {"role": "pm", "action": "get_all_projects",      "allowed": True},
]

async def seed():
    async with AsyncSessionLocal() as db:
        # Supprime les anciennes permissions
        from sqlalchemy import delete
        await db.execute(delete(Permission))
        await db.commit()

        for p in PERMISSIONS:
            db.add(Permission(**p))
        await db.commit()

        consultant_count = sum(1 for p in PERMISSIONS if p["role"] == "consultant")
        pm_count = sum(1 for p in PERMISSIONS if p["role"] == "pm")
        print(f"✅ {len(PERMISSIONS)} permissions créées !")
        print(f"   consultant → {consultant_count} tools autorisés")
        print(f"   pm         → {pm_count} tools autorisés")

asyncio.run(seed())
