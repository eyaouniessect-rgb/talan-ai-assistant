# scripts/seed_permissions.py
# ═══════════════════════════════════════════════════════════
# RBAC par TOOL — les permissions sont maintenant par nom d'outil
# Rôles : consultant | pm | rh
# ═══════════════════════════════════════════════════════════
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal
from app.database.models.permissions import Permission

PERMISSIONS = [
    # ═══════════════════════════════════════════════════
    # CONSULTANT — actions sur son propre périmètre
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
    {"role": "consultant", "action": "delete_leave",             "allowed": True},
    {"role": "consultant", "action": "get_my_leaves",            "allowed": True},
    {"role": "consultant", "action": "check_leave_balance",      "allowed": True},
    {"role": "consultant", "action": "get_team_availability",    "allowed": True},
    {"role": "consultant", "action": "get_team_stack",           "allowed": True},
    {"role": "consultant", "action": "notify_manager",           "allowed": True},

    # Pas d'accès RH admin
    {"role": "consultant", "action": "approve_leave",            "allowed": False},
    {"role": "consultant", "action": "reject_leave",             "allowed": False},
    {"role": "consultant", "action": "get_all_leaves",           "allowed": False},
    {"role": "consultant", "action": "create_user_account",      "allowed": False},
    {"role": "consultant", "action": "deactivate_user",          "allowed": False},

    # ═══════════════════════════════════════════════════
    # PM — tout consultant + vision équipe
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
    {"role": "pm", "action": "delete_leave",             "allowed": True},
    {"role": "pm", "action": "get_my_leaves",            "allowed": True},
    {"role": "pm", "action": "check_leave_balance",      "allowed": True},
    {"role": "pm", "action": "get_team_availability",    "allowed": True},
    {"role": "pm", "action": "get_team_stack",           "allowed": True},
    {"role": "pm", "action": "notify_manager",           "allowed": True},
    {"role": "pm", "action": "get_all_leaves",           "allowed": True},   # voir congés équipe

    # Pas de création de comptes
    {"role": "pm", "action": "approve_leave",            "allowed": False},
    {"role": "pm", "action": "reject_leave",             "allowed": False},
    {"role": "pm", "action": "create_user_account",      "allowed": False},
    {"role": "pm", "action": "deactivate_user",          "allowed": False},

    # ═══════════════════════════════════════════════════
    # RH — administration RH complète
    # ═══════════════════════════════════════════════════

    # ── Calendar Agent tools ──────────────────────────
    {"role": "rh", "action": "check_calendar_conflicts", "allowed": True},
    {"role": "rh", "action": "get_calendar_events",      "allowed": True},
    {"role": "rh", "action": "create_meeting",           "allowed": True},
    {"role": "rh", "action": "update_meeting",           "allowed": True},
    {"role": "rh", "action": "delete_meeting",           "allowed": True},
    {"role": "rh", "action": "search_meetings",          "allowed": True},

    # ── RH Agent tools — accès complet ───────────────
    {"role": "rh", "action": "create_leave",             "allowed": True},
    {"role": "rh", "action": "delete_leave",             "allowed": True},
    {"role": "rh", "action": "get_my_leaves",            "allowed": True},
    {"role": "rh", "action": "check_leave_balance",      "allowed": True},
    {"role": "rh", "action": "get_team_availability",    "allowed": True},
    {"role": "rh", "action": "get_team_stack",           "allowed": True},
    {"role": "rh", "action": "notify_manager",           "allowed": True},
    {"role": "rh", "action": "get_all_leaves",           "allowed": True},

    # ── RH Admin tools — exclusif RH ─────────────────
    {"role": "rh", "action": "approve_leave",            "allowed": True},
    {"role": "rh", "action": "reject_leave",             "allowed": True},
    {"role": "rh", "action": "create_user_account",      "allowed": True},
    {"role": "rh", "action": "deactivate_user",          "allowed": True},
]


async def seed():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import delete
        await db.execute(delete(Permission))
        await db.commit()

        for p in PERMISSIONS:
            db.add(Permission(**p))
        await db.commit()

        for role in ("consultant", "pm", "rh"):
            count = sum(1 for p in PERMISSIONS if p["role"] == role)
            allowed = sum(1 for p in PERMISSIONS if p["role"] == role and p["allowed"])
            print(f"   {role:12} → {allowed} autorisés / {count} total")

        print(f"\n✅ {len(PERMISSIONS)} permissions créées (3 rôles : consultant, pm, rh)")


asyncio.run(seed())
