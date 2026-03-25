# Insère les règles RBAC initiales dans la table `permissions`.
# Définit qui peut faire quoi :
#   consultant : create_leave, get_my_leaves, get_my_projects, get_tickets...
#   pm         : get_all_projects, get_team_availability, create_ticket, upload_cdc...
# scripts/seed_permissions.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal
from app.database.models.permissions import Permission

PERMISSIONS = [
    # ── CONSULTANT ──────────────────────────────────────
    {"role": "consultant", "action": "create_leave",          "allowed": True},
    {"role": "consultant", "action": "get_my_leaves",         "allowed": True},
    {"role": "consultant", "action": "get_team_availability", "allowed": True},
    {"role": "consultant", "action": "get_my_projects",       "allowed": True},
    {"role": "consultant", "action": "get_tickets",           "allowed": True},
    {"role": "consultant", "action": "create_ticket",         "allowed": True},
    {"role": "consultant", "action": "update_ticket",         "allowed": True},
    {"role": "consultant", "action": "get_calendar",          "allowed": True},
    {"role": "consultant", "action": "create_event",          "allowed": True},
    {"role": "consultant", "action": "update_event",          "allowed": True},
    {"role": "consultant", "action": "delete_event",          "allowed": True},
    {"role": "consultant", "action": "check_availability",    "allowed": True},
    {"role": "consultant", "action": "search_events",         "allowed": True},
    {"role": "consultant", "action": "send_message",          "allowed": True},
    {"role": "consultant", "action": "search_docs",           "allowed": True},

    # ── PM — tout ce que le consultant peut faire + plus ─
    {"role": "pm", "action": "create_leave",          "allowed": True},
    {"role": "pm", "action": "get_my_leaves",         "allowed": True},
    {"role": "pm", "action": "get_team_availability", "allowed": True},
    {"role": "pm", "action": "get_my_projects",       "allowed": True},
    {"role": "pm", "action": "get_all_projects",      "allowed": True},
    {"role": "pm", "action": "generate_report",       "allowed": True},
    {"role": "pm", "action": "get_tickets",           "allowed": True},
    {"role": "pm", "action": "create_ticket",         "allowed": True},
    {"role": "pm", "action": "update_ticket",         "allowed": True},
    {"role": "pm", "action": "get_calendar",          "allowed": True},
    {"role": "pm", "action": "create_event",          "allowed": True},
    {"role": "pm", "action": "update_event",          "allowed": True},
    {"role": "pm", "action": "delete_event",          "allowed": True},
    {"role": "pm", "action": "check_availability",    "allowed": True},
    {"role": "pm", "action": "search_events",         "allowed": True},
    {"role": "pm", "action": "send_message",          "allowed": True},
    {"role": "pm", "action": "search_docs",           "allowed": True},
]

async def seed():
    async with AsyncSessionLocal() as db:
        for p in PERMISSIONS:
            db.add(Permission(**p))
        await db.commit()
        print(f"✅ {len(PERMISSIONS)} permissions créées !")
        print("   consultant → 15 actions autorisées")
        print("   pm         → 17 actions autorisées")

asyncio.run(seed())