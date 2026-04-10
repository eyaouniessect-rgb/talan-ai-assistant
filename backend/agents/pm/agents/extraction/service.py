# agents/pm/agents/extraction/service.py
# ═══════════════════════════════════════════════════════════════
# Service d'extraction de texte — logique métier pure
#
# Responsabilités :
#   - Valider l'extension et la taille du fichier
#   - Extraire le texte brut d'un PDF (pypdf) ou DOCX (python-docx)
#
# Formats supportés : PDF (pypdf), DOCX (python-docx), TXT (builtin)
# Pas de dépendances LLM ni DB : fonctions synchrones pures.
# ═══════════════════════════════════════════════════════════════

import io

_MAX_FILE_SIZE      = 10 * 1024 * 1024          # 10 MB
_ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")


def validate_file(ext: str, file_bytes: bytes) -> str | None:
    """
    Valide l'extension et la taille du fichier.
    Retourne un message d'erreur, ou None si tout est OK.
    """
    if ext not in _ALLOWED_EXTENSIONS:
        return f"Extension non supportée : '{ext}'. Envoyez un PDF, DOCX ou TXT."
    if len(file_bytes) > _MAX_FILE_SIZE:
        return f"Fichier trop volumineux ({len(file_bytes) // 1024} KB). Maximum : 10 MB."
    return None


def extract_text(file_bytes: bytes, ext: str) -> tuple[str, str | None]:
    """
    Extrait le texte brut d'un PDF, DOCX ou TXT.
    Retourne (texte, None) en cas de succès, ("", message_erreur) sinon.
    """
    if ext == ".pdf":
        return _extract_pdf(file_bytes)
    if ext == ".docx":
        return _extract_docx(file_bytes)
    if ext == ".txt":
        return _extract_txt(file_bytes)
    return "", f"Format non supporté : '{ext}'"


def _extract_pdf(file_bytes: bytes) -> tuple[str, str | None]:
    """Extraction PDF via pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        pages  = [page.extract_text() or "" for page in reader.pages]
        text   = "\n".join(pages).strip()
        if not text:
            return "", "Le PDF ne contient pas de texte extractible (PDF scanné non supporté)."
        return text, None
    except ImportError:
        return "", "Librairie pypdf manquante — pip install pypdf"
    except Exception as e:
        return "", f"Erreur lors de la lecture du PDF : {e}"


def _extract_docx(file_bytes: bytes) -> tuple[str, str | None]:
    """Extraction DOCX via python-docx."""
    try:
        from docx import Document
        doc        = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text       = "\n".join(paragraphs).strip()
        if not text:
            return "", "Le fichier DOCX ne contient pas de texte."
        return text, None
    except ImportError:
        return "", "Librairie python-docx manquante — pip install python-docx"
    except Exception as e:
        return "", f"Erreur lors de la lecture du DOCX : {e}"


def _extract_txt(file_bytes: bytes) -> tuple[str, str | None]:
    """Extraction TXT — décode en UTF-8 avec fallback latin-1."""
    try:
        text = file_bytes.decode("utf-8").strip()
    except UnicodeDecodeError:
        try:
            text = file_bytes.decode("latin-1").strip()
        except Exception as e:
            return "", f"Impossible de décoder le fichier TXT : {e}"
    if not text:
        return "", "Le fichier TXT est vide."
    return text, None
