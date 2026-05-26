import asyncio, sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from agents.pm.agents.staffing.steps.matching.crm_repository import upsert_crm_assignments
from datetime import date

async def main():
    n = await upsert_crm_assignments(
        project_id   = 16,
        sprint_start = date(2026, 5, 23),
        sprint_end   = date(2026, 6, 12),
    )
    print(f"OK — {n} ligne(s) upsertees dans crm.assignments")

asyncio.run(main())
