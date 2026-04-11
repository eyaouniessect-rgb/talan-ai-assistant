# app/api/crm/crm.py
# ═══════════════════════════════════════════════════════════════
# Endpoints CRM — Gestion des Clients et Projets
#
# Routes :
#   GET    /crm/clients              → liste des clients
#   POST   /crm/clients              → créer un nouveau client
#   GET    /crm/projects             → liste des projets du PM connecté
#   POST   /crm/projects             → créer un nouveau projet (client existant)
#
# Séparation des responsabilités :
#   Ces endpoints gèrent UNIQUEMENT les données métier (master data).
#   L'upload de CDC et le lancement du pipeline sont dans des endpoints séparés.
#
# Accès : réservé au rôle "pm" (RBAC).
# ═══════════════════════════════════════════════════════════════

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.crm.client import Client
from app.database.models.crm.project import Project
from agents.pm.db import get_employee_id_by_user

router = APIRouter(prefix="/crm", tags=["CRM"])


# ──────────────────────────────────────────────────────────────
# RBAC — réservé aux PM
# ──────────────────────────────────────────────────────────────

async def require_pm(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "pm":
        raise HTTPException(status_code=403, detail="Accès réservé aux Project Managers.")
    return current_user


# ──────────────────────────────────────────────────────────────
# SCHÉMAS PYDANTIC
# ──────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name:          str
    industry:      Optional[str]  = None
    contact_email: Optional[str]  = None


class ProjectCreate(BaseModel):
    name:      str
    client_id: int


# ──────────────────────────────────────────────────────────────
# CLIENTS
# ──────────────────────────────────────────────────────────────

@router.get("/clients")
async def list_clients(
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Retourne la liste de tous les clients CRM."""
    result = await db.execute(select(Client).order_by(Client.name))
    clients = result.scalars().all()
    return [
        {
            "id":            c.id,
            "name":          c.name,
            "industry":      c.industry,
            "contact_email": c.contact_email,
        }
        for c in clients
    ]


@router.post("/clients", status_code=201)
async def create_client(
    body:         ClientCreate,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Crée un nouveau client CRM.
    Création TOUJOURS explicite — jamais automatique depuis un document.
    """
    # Vérifier doublon sur le nom (insensible à la casse)
    existing = await db.execute(
        select(Client).where(Client.name.ilike(body.name))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Un client nommé '{body.name}' existe déjà.")

    client = Client(
        name          = body.name,
        industry      = body.industry,
        contact_email = body.contact_email,
    )
    db.add(client)
    await db.commit()
    await db.refresh(client)

    return {
        "id":            client.id,
        "name":          client.name,
        "industry":      client.industry,
        "contact_email": client.contact_email,
    }


# ──────────────────────────────────────────────────────────────
# PROJETS
# ──────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects(
    client_id:    Optional[int] = None,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Retourne les projets CRM du PM connecté. Filtre optionnel : ?client_id=X"""
    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(403, "Votre compte n'est pas lié à un profil employé.")

    q = select(Project).where(Project.project_manager_id == employee_id)
    if client_id is not None:
        q = q.where(Project.client_id == client_id)
    result = await db.execute(q.order_by(Project.created_at.desc()))
    projects = result.scalars().all()

    return [
        {
            "id":          p.id,
            "name":        p.name,
            "client_id":   p.client_id,
            "client_name": p.client.name if p.client else "—",
            "status":      p.status,
            "progress":    p.progress,
            "created_at":  p.created_at.isoformat() if p.created_at else None,
        }
        for p in projects
    ]


@router.post("/projects", status_code=201)
async def create_project(
    body:         ProjectCreate,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Crée un nouveau projet CRM.

    Le projet est toujours lié à un client EXISTANT (client_id obligatoire).
    Le PM connecté devient automatiquement project_manager_id.
    """
    user_id     = current_user["user_id"]
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(403, "Votre compte n'est pas lié à un profil employé.")

    # Vérifier que le client existe
    client_result = await db.execute(select(Client).where(Client.id == body.client_id))
    if not client_result.scalar_one_or_none():
        raise HTTPException(404, f"Client {body.client_id} introuvable.")

    # Vérifier doublon : même nom pour ce client + ce PM
    dup = await db.execute(
        select(Project).where(
            Project.name.ilike(body.name),
            Project.client_id          == body.client_id,
            Project.project_manager_id == employee_id,
        )
    )
    existing_project = dup.scalar_one_or_none()
    if existing_project:
        raise HTTPException(409, {
            "detail":     f"Un projet nommé '{body.name}' existe déjà pour ce client.",
            "project_id": existing_project.id,
            "project_name": existing_project.name,
        })

    project = Project(
        name               = body.name,
        client_id          = body.client_id,
        project_manager_id = employee_id,
        status             = "En cours",
        progress           = 0.0,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    return {
        "id":         project.id,
        "name":       project.name,
        "client_id":  project.client_id,
        "status":     project.status,
        "created_at": project.created_at.isoformat() if project.created_at else None,
    }
