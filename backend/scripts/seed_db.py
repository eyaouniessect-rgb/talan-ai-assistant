# scripts/seed_db.py
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database.connection import AsyncSessionLocal
from app.database.models.user import User
from app.database.models.hris import Employee, Team
from app.core.security import hash_password

async def seed():
    async with AsyncSessionLocal() as db:

        # ── Users ──────────────────────────────────────
        eya = User(
            name="Eya Ben Ali",
            email="eya@talan.com",
            password=hash_password("password"),
            role="consultant",
        )
        ahmed = User(
            name="Ahmed Karim",
            email="ahmed@talan.com",
            password=hash_password("password"),
            role="pm",
        )
        db.add(eya)
        db.add(ahmed)
        await db.flush()  # pour avoir les IDs

        # ── Team ───────────────────────────────────────
        team = Team(
            name="Team TalanConnect",
            manager_id=ahmed.id,
        )
        db.add(team)
        await db.flush()

        # ── Employees ──────────────────────────────────
        emp_eya = Employee(
            user_id=eya.id,
            team_id=team.id,
            skills="Python, React, FastAPI, LangChain",
        )
        emp_ahmed = Employee(
            user_id=ahmed.id,
            team_id=team.id,
            skills="Project Management, Jira, Agile, Scrum",
        )
        db.add(emp_eya)
        db.add(emp_ahmed)

        await db.commit()
        print("✅ Users créés !")
        print("✅ Team créée !")
        print("✅ Employees créés !")

asyncio.run(seed())