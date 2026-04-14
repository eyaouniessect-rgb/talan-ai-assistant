"""
clean_projects.py
─────────────────
Vide les tables de test pour repartir sur des données propres.

Modes :
  --projects   Vide uniquement les tables projets PM (défaut)
  --rh         Vide uniquement les tables RH (congés, logs)
  --chat       Vide les conversations et messages du chat
  --all        Vide tout (projets + RH + chat)
  --yes / -y   Sans confirmation

Exemples :
  cd backend
  python -m scripts.clean_projects --all --yes
  python -m scripts.clean_projects --rh
  python -m scripts.clean_projects --projects
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text
from app.database.connection import AsyncSessionLocal


TABLES_PROJECTS = [
    ("project_management", "task_dependencies"),
    ("project_management", "story_dependencies"),
    ("project_management", "tasks"),
    ("project_management", "user_stories"),
    ("project_management", "sprints"),
    ("project_management", "epics"),
    ("project_management", "pipeline_state"),
    ("project_management", "project_documents"),
    ("crm",                "projects"),
]

TABLES_RH = [
    ("hris", "leave_logs"),
    ("hris", "leaves"),
]

TABLES_CHAT = [
    ("public", "messages"),
    ("public", "conversations"),
]


async def clean(tables: list, label: str, auto_yes: bool = False) -> None:
    print("=" * 60)
    print(f"  NETTOYAGE — {label}")
    print("=" * 60)
    print()
    print("Tables qui seront vidées :")
    for schema, table in tables:
        print(f"  - {schema}.{table}")
    print()

    if not auto_yes:
        confirm = input("Confirmer ? [oui/N] : ").strip().lower()
        if confirm not in ("oui", "o", "yes", "y"):
            print("Annulé.")
            return

    async with AsyncSessionLocal() as session:
        async with session.begin():
            for schema, table in tables:
                await session.execute(
                    text(f'TRUNCATE TABLE "{schema}"."{table}" RESTART IDENTITY CASCADE')
                )
                print(f"  OK  {schema}.{table}")

    print()
    print(f"Nettoyage [{label}] terminé.")


if __name__ == "__main__":
    args = sys.argv[1:]
    auto_yes = "--yes" in args or "-y" in args

    do_projects = "--projects" in args or "--all" in args
    do_rh       = "--rh"       in args or "--all" in args
    do_chat     = "--chat"     in args or "--all" in args

    # Par défaut (aucun flag) → projets seulement
    if not (do_projects or do_rh or do_chat):
        do_projects = True

    async def run():
        if do_projects:
            await clean(TABLES_PROJECTS, "PROJETS PM",  auto_yes)
        if do_rh:
            await clean(TABLES_RH,       "CONGES RH",   auto_yes)
        if do_chat:
            await clean(TABLES_CHAT,     "CHAT / CONV.", auto_yes)

    asyncio.run(run())
