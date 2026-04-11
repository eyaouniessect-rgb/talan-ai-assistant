# scripts/seed_crm.py
# Insère des clients CRM de test dans crm.clients

import asyncio, sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv; load_dotenv()
from app.database.connection import AsyncSessionLocal
from app.database.models.crm.client import Client

CLIENTS = [
    {"name": "Talan Tunisie",     "industry": "Conseil IT",    "contact_email": "contact@talan.tn"},
    {"name": "Talan France",      "industry": "Conseil IT",    "contact_email": "contact@talan.fr"},
    {"name": "BFI Group",         "industry": "Finance",       "contact_email": "dsi@bfi.tn"},
    {"name": "STEG",              "industry": "Energie",       "contact_email": "dsi@steg.com.tn"},
    {"name": "Tunisie Telecom",   "industry": "Telecom",       "contact_email": "it@tunisietelecom.tn"},
    {"name": "Banque Zitouna",    "industry": "Banque",        "contact_email": "it@banquezitouna.tn"},
    {"name": "EduGroup",          "industry": "Education",     "contact_email": "tech@edugroup.tn"},
    {"name": "HealthTech SA",     "industry": "Santé",         "contact_email": "cto@healthtech.tn"},
]

async def seed():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        existing = (await db.execute(select(Client.name))).scalars().all()
        existing_names = set(existing)
        to_insert = [c for c in CLIENTS if c["name"] not in existing_names]
        if not to_insert:
            print(f"[seed_crm] Rien a inserer ({len(existing_names)} clients deja en base).")
            return
        for c in to_insert:
            db.add(Client(**c))
        await db.commit()
        print(f"[seed_crm] {len(to_insert)} clients inseres ({len(existing_names)} existaient deja).")

asyncio.run(seed())
