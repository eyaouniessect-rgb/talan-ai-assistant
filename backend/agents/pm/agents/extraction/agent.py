# agents/pm/agents/extraction/agent.py
# ═══════════════════════════════════════════════════════════════
# Agent d'extraction — Phase 1 du pipeline PM
#
# Flux :
#   1. Récupère le document depuis project_management.project_documents
#   2. Lit le fichier depuis file_path (data/documents/{project_id}/)
#   3. Valide extension + taille
#   4. Extrait le texte brut (PDF/DOCX/TXT)
#   5. Retourne validation_status="pending_human"
#      → node_validate persiste PENDING_VALIDATION + interrupt()
# ═══════════════════════════════════════════════════════════════

import os

from sqlalchemy import select

from agents.pm.state import PMPipelineState
from agents.pm.agents.extraction.service import validate_file, extract_text
from app.database.connection import AsyncSessionLocal
from app.database.models.pm.project_document import ProjectDocument


async def node_extraction(state: PMPipelineState) -> dict:
    """
    Noeud LangGraph — Phase 1 : extraction du texte CDC.
    Lit le fichier via document_id → file_path en DB.
    Passe ensuite par node_validate (validation humaine).
    """
    project_id  = state.get("project_id")
    document_id = state.get("document_id")

    print(f"\n{'='*60}")
    print(f"[EXTRACTION] Démarrage Phase 1")
    print(f"[EXTRACTION]   project_id  = {project_id}")
    print(f"[EXTRACTION]   document_id = {document_id}")
    print(f"{'='*60}")

    # ── 1. Récupérer le document en base ─────────────────────
    print(f"[EXTRACTION] Récupération du document en base...")
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ProjectDocument).where(ProjectDocument.id == document_id)
        )
        doc = result.scalar_one_or_none()

    if not doc:
        error_msg = f"Document {document_id} introuvable dans project_documents."
        print(f"[EXTRACTION] ERREUR : {error_msg}")
        return {"error": error_msg, "current_phase": "extract"}

    file_path = doc.file_path
    filename  = doc.file_name
    file_size = doc.file_size or 0
    ext       = os.path.splitext(filename)[1].lower()

    print(f"[EXTRACTION] Document trouvé :")
    print(f"[EXTRACTION]   filename  = {filename}")
    print(f"[EXTRACTION]   extension = {ext}")
    print(f"[EXTRACTION]   taille    = {file_size} octets ({file_size / 1024:.1f} KB)")
    print(f"[EXTRACTION]   file_path = {file_path}")

    # ── 2. Lire le fichier depuis le disque ──────────────────
    print(f"[EXTRACTION] Lecture du fichier sur le disque...")
    if not os.path.exists(file_path):
        error_msg = f"Fichier introuvable sur le disque : {file_path}"
        print(f"[EXTRACTION] ERREUR : {error_msg}")
        return {"error": error_msg, "current_phase": "extract"}

    with open(file_path, "rb") as f:
        file_bytes = f.read()
    print(f"[EXTRACTION] Fichier lu : {len(file_bytes)} octets")

    # ── 3. Validation extension + taille ─────────────────────
    print(f"[EXTRACTION] Validation extension et taille...")
    error_msg = validate_file(ext, file_bytes)
    if error_msg:
        print(f"[EXTRACTION] ERREUR validation : {error_msg}")
        return {"error": error_msg, "current_phase": "extract"}
    print(f"[EXTRACTION] Validation OK")

    # ── 4. Extraction du texte ────────────────────────────────
    print(f"[EXTRACTION] Extraction du texte ({ext})...")
    cdc_text, error_msg = extract_text(file_bytes, ext)
    if error_msg:
        print(f"[EXTRACTION] ERREUR extraction : {error_msg}")
        return {"error": error_msg, "current_phase": "extract"}

    nb_chars    = len(cdc_text)
    nb_lines    = cdc_text.count('\n') + 1
    nb_words    = len(cdc_text.split())
    pages_est   = max(1, nb_chars // 2000)

    print(f"\n[EXTRACTION] ✓ Extraction réussie :")
    print(f"[EXTRACTION]   Caractères : {nb_chars:,}")
    print(f"[EXTRACTION]   Mots       : {nb_words:,}")
    print(f"[EXTRACTION]   Lignes     : {nb_lines:,}")
    print(f"[EXTRACTION]   Pages est. : {pages_est}")
    print(f"\n[EXTRACTION] --- Aperçu (500 premiers caractères) ---")
    print(cdc_text[:500])
    print(f"[EXTRACTION] --- Fin aperçu ---\n")

    # ── 5. Log JSON (visible dans les logs backend) ──────────
    import json
    print(f"[EXTRACTION] Résultat JSON :")
    print(json.dumps({
        "filename":  filename,
        "extension": ext,
        "file_size": file_size,
        "pages_est": pages_est,
        "preview":   cdc_text[:200],
    }, ensure_ascii=False, indent=2))

    # ── 6. Passe en attente de validation humaine ─────────────
    # node_validate lit cdc_text depuis le state pour calculer les stats
    # et persiste PENDING_VALIDATION + interrupt()
    print(f"\n[EXTRACTION] → Passage à node_validate (validation humaine requise)")
    print(f"{'='*60}\n")

    return {
        "cdc_text":          cdc_text,   # texte complet — lu par epics/stories/...
        "current_phase":     "extract",
        "validation_status": "pending_human",
        "error":             None,
    }
