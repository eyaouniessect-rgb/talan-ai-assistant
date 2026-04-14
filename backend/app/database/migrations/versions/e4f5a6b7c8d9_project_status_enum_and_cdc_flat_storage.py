"""project status enum + cdc flat storage

Revision ID: e4f5a6b7c8d9
Revises: bc01acf87cbe
Create Date: 2026-04-12

Deux changements :
1. crm.projects.status — anciens strings FR → valeurs enum ProjectGlobalStatus
2. project_management.project_documents.file_path — sous-dossiers {project_id}/ → dossier plat cdc/
   + déplace les fichiers physiquement
"""

import os
import shutil
from pathlib import Path

from alembic import op
import sqlalchemy as sa

# ── identifiants ──────────────────────────────────────────────
revision = "e4f5a6b7c8d9"
down_revision = "bc01acf87cbe"
branch_labels = None
depends_on = None

# Racine data/documents/ — chemin absolu depuis ce fichier
_DOCS_ROOT = Path(__file__).resolve().parents[5] / "data" / "documents"


# ──────────────────────────────────────────────────────────────
# UPGRADE
# ──────────────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Migrer crm.projects.status ─────────────────────────
    #   "En cours"  → "in_progress"
    #   "Terminé"   → "completed"
    #   "En attente"→ "not_started"
    #   tout autre  → "not_started"
    conn.execute(sa.text("""
        UPDATE crm.projects
        SET status = CASE
            WHEN status = 'En cours'   THEN 'in_progress'
            WHEN status = 'Terminé'    THEN 'completed'
            WHEN status = 'En attente' THEN 'not_started'
            ELSE 'not_started'
        END
    """))

    # Nouveau défaut colonne
    conn.execute(sa.text("""
        ALTER TABLE crm.projects
            ALTER COLUMN status SET DEFAULT 'not_started'
    """))

    # ── 2. Migrer les chemins de documents ─────────────────────
    cdc_dir = _DOCS_ROOT / "cdc"
    cdc_dir.mkdir(parents=True, exist_ok=True)

    # Récupérer tous les documents qui ont encore un chemin avec sous-dossier project_id
    rows = conn.execute(sa.text("""
        SELECT id, file_path
        FROM project_management.project_documents
        WHERE file_path IS NOT NULL
    """)).fetchall()

    for doc_id, old_path in rows:
        old = Path(old_path)

        # Ignorer si le fichier est déjà dans cdc/
        if old.parent.name == "cdc":
            continue

        new_path = cdc_dir / old.name

        # Déplacer le fichier physique s'il existe
        if old.exists():
            # Éviter les collisions de noms
            if new_path.exists():
                stem = old.stem
                suffix = old.suffix
                new_path = cdc_dir / f"{stem}_{doc_id}{suffix}"
            shutil.move(str(old), str(new_path))

        # Mettre à jour le chemin en base
        conn.execute(sa.text("""
            UPDATE project_management.project_documents
            SET file_path = :new_path
            WHERE id = :doc_id
        """), {"new_path": str(new_path), "doc_id": doc_id})

    # Nettoyer les sous-dossiers vides {project_id}/
    if _DOCS_ROOT.exists():
        for entry in _DOCS_ROOT.iterdir():
            if entry.is_dir() and entry.name != "cdc":
                try:
                    entry.rmdir()   # ne supprime que si vide
                except OSError:
                    pass            # dossier non vide → on laisse


# ──────────────────────────────────────────────────────────────
# DOWNGRADE
# ──────────────────────────────────────────────────────────────

def downgrade() -> None:
    conn = op.get_bind()

    # ── 1. Remettre les anciens statuts FR ────────────────────
    conn.execute(sa.text("""
        UPDATE crm.projects
        SET status = CASE
            WHEN status = 'in_progress'   THEN 'En cours'
            WHEN status = 'completed'     THEN 'Terminé'
            WHEN status = 'pending_human' THEN 'En cours'
            ELSE 'En attente'
        END
    """))

    conn.execute(sa.text("""
        ALTER TABLE crm.projects
            ALTER COLUMN status SET DEFAULT 'En cours'
    """))

    # ── 2. Les fichiers restent dans cdc/ (downgrade partiel) ─
    # On ne recrée pas les sous-dossiers pour éviter les pertes de données.
    # Les chemins en base pointent toujours vers cdc/ après downgrade.
