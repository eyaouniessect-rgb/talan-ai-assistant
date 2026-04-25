# app/api/report.py
# ═══════════════════════════════════════════════════════════════
# Endpoint FastAPI pour l'export PDF du backlog d'un projet.
#
# Route :
#   GET /report/{project_id}/export/backlog
#       → retourne un fichier PDF (application/pdf) en téléchargement
#
# Dépendances :
#   app/services/report/service.py    → assembly des données
#   app/services/report/pdf_builder.py → génération PDF
#
# Accès : réservé au rôle "pm" (RBAC).
# ═══════════════════════════════════════════════════════════════

import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.services.report.service import build_report_data
from app.services.report.pdf_builder import generate_pdf

router = APIRouter(prefix="/report", tags=["Report"])


async def require_pm(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "pm":
        raise HTTPException(status_code=403, detail="Accès réservé aux Project Managers.")
    return current_user


@router.get("/{project_id}/export/backlog")
async def export_backlog_pdf(
    project_id: int,
    _user: dict = Depends(require_pm),
):
    """
    Génère et retourne le rapport backlog complet (epics + user stories)
    au format PDF pour le projet donné.
    """
    data = await build_report_data(project_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Projet {project_id} introuvable.")

    pdf_bytes = generate_pdf(data)

    filename = f"backlog_{project_id}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
