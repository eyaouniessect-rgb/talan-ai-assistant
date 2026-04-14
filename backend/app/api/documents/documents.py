# app/api/documents/documents.py
# ═══════════════════════════════════════════════════════════════
# Endpoints de gestion documentaire CDC
#
# Règle métier : 1 projet = 1 seul CDC
#
# Routes :
#   POST /projects/{project_id}/document → upload (ou remplacement) du CDC
#   GET  /projects/{project_id}/document → lire les infos du CDC actuel
#
# Flux POST :
#   1. Projet existant et appartenant au PM connecté
#   2. Validation extension (PDF/DOCX/TXT) et taille (max 10 MB)
#   3. SHA-256 calculé → détection de re-upload identique
#   4. Suppression de l'ancien fichier disque si un CDC existait déjà
#   5. Sauvegarde dans data/documents/{project_id}/
#   6. INSERT ou UPDATE dans project_management.project_documents
#   7. Retourne document_id → utilisé dans POST /pipeline/{id}/start
# ═══════════════════════════════════════════════════════════════

import hashlib
import uuid
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.crm.project import Project
from app.database.models.pm.project_document import ProjectDocument
from agents.pm.db import get_employee_id_by_user

router = APIRouter(tags=["Documents"])

_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}
_MAX_FILE_SIZE       = 10 * 1024 * 1024   # 10 MB
_DOCS_ROOT           = Path(__file__).resolve().parent.parent.parent.parent / "data" / "documents"
_MIME_MAP            = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt":  "text/plain",
}


# ──────────────────────────────────────────────────────────────
# RBAC
# ──────────────────────────────────────────────────────────────

async def require_pm(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "pm":
        raise HTTPException(status_code=403, detail="Accès réservé aux Project Managers.")
    return current_user


# ──────────────────────────────────────────────────────────────
# POST /projects/{project_id}/document — Upload (ou remplacement) du CDC
# ──────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/document", status_code=201)
async def upload_document(
    project_id:   int,
    file:         UploadFile   = File(..., description="CDC (PDF, DOCX ou TXT, max 10 MB)"),
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """
    Upload du Cahier des Charges d'un projet.
    1 projet = 1 CDC. Si un CDC existe déjà, il est remplacé.

    Retourne le document_id à utiliser dans POST /pipeline/{id}/start.
    """
    user_id = current_user["user_id"]

    # ── 1. Vérifier projet + propriété ───────────────────────
    employee_id = await get_employee_id_by_user(user_id)
    if not employee_id:
        raise HTTPException(403, "Votre compte n'est pas lié à un profil employé.")

    proj = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise HTTPException(404, f"Projet {project_id} introuvable.")
    if proj.project_manager_id != employee_id:
        raise HTTPException(403, "Ce projet ne vous appartient pas.")

    # ── 2. Validation extension + taille ─────────────────────
    filename = file.filename or "cdc"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Format non supporté '{ext}'. Envoyez un PDF, DOCX ou TXT.")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Le fichier est vide.")
    if len(file_bytes) > _MAX_FILE_SIZE:
        raise HTTPException(400, f"Fichier trop volumineux ({len(file_bytes)//1024} KB). Maximum : 10 MB.")

    # ── 3. SHA-256 + vérification re-upload identique ────────
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = (await db.execute(
        select(ProjectDocument).where(ProjectDocument.project_id == project_id)
    )).scalar_one_or_none()

    if existing and existing.file_hash == file_hash:
        # Même fichier déjà uploadé → pas besoin de remplacer
        return {
            "document_id": existing.id,
            "project_id":  project_id,
            "file_name":   existing.file_name,
            "replaced":    False,
            "message":     "Ce fichier est déjà le CDC actuel de ce projet (hash identique).",
        }

    # ── 4. Suppression de l'ancien CDC (fichier + ligne DB) ──
    if existing:
        try:
            if os.path.exists(existing.file_path):
                os.remove(existing.file_path)
        except OSError:
            pass
        await db.execute(
            delete(ProjectDocument).where(ProjectDocument.id == existing.id)
        )

    # ── 5. Sauvegarde sur disque ──────────────────────────────
    cdc_dir = _DOCS_ROOT / "cdc"
    cdc_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path     = str(cdc_dir / safe_filename)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # ── 6. Enregistrement en base ─────────────────────────────
    doc = ProjectDocument(
        project_id  = project_id,
        file_name   = filename,
        file_path   = file_path,
        file_hash   = file_hash,
        file_size   = len(file_bytes),
        mime_type   = _MIME_MAP.get(ext),
        uploaded_by = employee_id,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "document_id": doc.id,
        "project_id":  project_id,
        "file_name":   doc.file_name,
        "file_size":   doc.file_size,
        "replaced":    existing is not None,
        "message":     (
            "CDC remplacé. Utilisez document_id pour lancer le pipeline."
            if existing else
            "CDC uploadé. Utilisez document_id pour lancer le pipeline."
        ),
    }


# ──────────────────────────────────────────────────────────────
# GET /projects/{project_id}/document — Infos du CDC actuel
# ──────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/document")
async def get_document(
    project_id:   int,
    current_user: dict         = Depends(require_pm),
    db:           AsyncSession = Depends(get_db),
):
    """Retourne les métadonnées du CDC actuellement associé au projet."""
    doc = (await db.execute(
        select(ProjectDocument).where(ProjectDocument.project_id == project_id)
    )).scalar_one_or_none()

    if not doc:
        raise HTTPException(404, "Aucun CDC uploadé pour ce projet.")

    return {
        "document_id": doc.id,
        "file_name":   doc.file_name,
        "file_size":   doc.file_size,
        "mime_type":   doc.mime_type,
        "uploaded_by": doc.uploaded_by,
        "created_at":  doc.created_at.isoformat() if doc.created_at else None,
    }
