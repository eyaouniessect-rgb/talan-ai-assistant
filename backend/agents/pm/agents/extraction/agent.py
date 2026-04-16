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
from langsmith import traceable

from agents.pm.state import PMPipelineState
from agents.pm.agents.extraction.service import validate_file, extract_text
from agents.pm.agents.extraction.vlm_service import detect_architecture_vlm
from app.core.anti_injection import scan_text, scan_filename
from app.database.connection import AsyncSessionLocal
from app.database.models.pm.project_document import ProjectDocument


@traceable(name="node_extraction_phase1", run_type="chain")
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

    # ── 5. Scan de sécurité ───────────────────────────────────
    print(f"[EXTRACTION] Scan de sécurité (prompt/SQL/MCP/code injection)...")

    # Double extension sur le nom de fichier
    fname_scan = scan_filename(filename)

    # Contenu du document
    content_scan = scan_text(cdc_text)

    # Fusionner les deux résultats (worst-case severity)
    all_threats = fname_scan.threats + content_scan.threats
    if all_threats:
        from app.core.anti_injection import ScanResult, _SEVERITY_RANK, clean_text
        max_rank     = max(_SEVERITY_RANK[t.severity] for t in all_threats)
        max_severity = next(s for s, r in _SEVERITY_RANK.items() if r == max_rank)
        security_result = ScanResult(is_safe=False, severity=max_severity.value, threats=all_threats)
    else:
        security_result = content_scan  # is_safe=True

    if security_result.is_safe:
        print(f"[EXTRACTION] ✓ Scan sécurité OK — aucune menace détectée")
    else:
        print(f"[EXTRACTION] ⚠ {len(security_result.threats)} menace(s) détectée(s) — sévérité : {security_result.severity.upper()}")
        for t in security_result.threats:
            print(f"[EXTRACTION]   [{t.severity.upper()}] {t.pattern} : {t.description}")

        # Nettoyage du texte : suppression des patterns d'injection
        print(f"[EXTRACTION] → Nettoyage du texte (suppression des patterns détectés)...")
        cdc_text = clean_text(cdc_text, security_result.threats)
        security_result.was_cleaned  = True
        security_result.cleaned_text = cdc_text[:500]
        print(f"[EXTRACTION] ✓ Texte nettoyé — traitement continue avec le texte assaini")

    # ── 6. Analyse VLM — détection d'architecture ────────────
    print(f"\n[EXTRACTION] Analyse VLM (détection d'architecture dans le document)...")
    architecture_detected, architecture_description, architecture_details, doc_info = (
        await detect_architecture_vlm(file_bytes=file_bytes, ext=ext)
    )

    page_count  = doc_info.get("page_count")  or max(1, len(cdc_text) // 2000)
    image_count = doc_info.get("image_count") or 0

    if architecture_detected:
        print(f"[EXTRACTION] ✓ Architecture détectée par VLM")
        layers = (architecture_details or {}).get("layers", [])
        print(f"[EXTRACTION]   {len(layers)} couche(s) identifiée(s)")
    else:
        print(f"[EXTRACTION] ✗ Aucune architecture dans le document — sera générée en phase 8")

    # ── 7. Passe en attente de validation humaine ─────────────
    print(f"\n[EXTRACTION] → Passage à node_validate (validation humaine requise)")
    print(f"{'='*60}\n")

    return {
        "cdc_text":                  cdc_text,
        "security_scan":             security_result.to_dict(),
        "architecture_detected":     architecture_detected,
        "architecture_description":  architecture_description,
        "architecture_details":      architecture_details,
        "page_count":                page_count,
        "image_count":               image_count,
        "vlm_doc_info":              doc_info,
        "current_phase":             "extract",
        "validation_status":         "pending_human",
        "error":                     None,
    }
