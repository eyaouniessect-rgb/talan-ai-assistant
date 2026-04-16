# agents/pm/agents/extraction/vlm_service.py
# ═══════════════════════════════════════════════════════════════
# Service VLM — Détection d'architecture dans le CDC
#
# Flux :
#   1. Détecte si le document contient des images
#      - PDF  : pages avec images embarquées OU dessins vectoriels
#      - DOCX : images embarquées via les relations du document
#      - TXT  : impossible → retourne résultat vide directement
#   2. Vérifie la taille de chaque image vs limite VLM (_MAX_IMAGE_BYTES)
#      - Image trop grande → ignorée, consignée dans doc_info["oversized_pages"]
#   3. Si images analysables → envoie à Groq llama-4-scout (vision)
#   4. Retourne (detected, description, details, doc_info)
#      doc_info = { page_count, image_count, analyzed_count, oversized_pages }
#
# Non-bloquant : toute erreur → (False, None, None, doc_info vide)
# Tracé dans LangSmith via @traceable
# ═══════════════════════════════════════════════════════════════

import os
import io
import json
import re
import base64
import asyncio
import logging

from langsmith import traceable

logger = logging.getLogger(__name__)

_VLM_MODEL         = "meta-llama/llama-4-scout-17b-16e-instruct"
_IMAGE_DPI         = 250   # Résolution rendu PDF → image (250 dpi requis pour lisibilité des petits labels)
_MAX_OUTPUT_TOKENS = 3000

# Taille maximale d'une image envoyée au VLM (en octets, avant encodage base64)
# À 250 DPI, un A4 PDF génère ~5-7 MB PNG — limite portée à 8 MB
_MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB

# ──────────────────────────────────────────────────────────────
# PROMPT VLM — Analyseur d'architecture exhaustif
# ──────────────────────────────────────────────────────────────

_VLM_PROMPT = """Tu es un expert en architecture logicielle. Analyse cette image extraite d'un cahier des charges.

══════════════════════════════════════════════════════════════
RÈGLE ABSOLUE — ANTI-HALLUCINATION
══════════════════════════════════════════════════════════════
- Rapporte UNIQUEMENT ce que tu peux lire ou voir clairement dans l'image.
- N'invente RIEN. N'infère RIEN. Ne complète pas avec tes connaissances générales.
- Si un label est illisible ou trop petit, écris exactement ce que tu vois (même partiel).
- Si tu n'es pas sûr d'un texte, préfixe-le avec "?" (ex: "?Redis").
- Ne suppose JAMAIS qu'un composant existe s'il n'est pas visuellement présent.

══════════════════════════════════════════════════════════════
ÉTAPE 1 — DÉTECTER LE TYPE D'ARCHITECTURE
══════════════════════════════════════════════════════════════
Identifie le pattern architectural visible parmi :
  • multi-agent          (agents LLM, orchestrateur, supervisor)
  • microservices        (services indépendants, API Gateway, conteneurs)
  • monolithique         (application unique, MVC, N-tiers)
  • event-driven         (event bus, message broker, publish/subscribe)
  • serverless           (functions, lambdas, triggers)
  • pipeline / ETL       (flux de données séquentiel)
  • client-serveur       (frontend, backend, API REST)
  • SOA                  (services SOAP/XML, ESB)
  • développement        (CI/CD, DevOps, build pipeline, branches git)
  • hybride              (combinaison de plusieurs patterns)
  • autre                (décrire ce qui est visible)

══════════════════════════════════════════════════════════════
ÉTAPE 2 — SCANNER EXHAUSTIVEMENT TOUTE L'IMAGE
══════════════════════════════════════════════════════════════
Pour CHAQUE zone visible dans l'image (de haut en bas, de gauche à droite) :
  □ Lis le titre/label de la zone
  □ Lis CHAQUE boîte, rectangle, cercle, icône à l'intérieur
  □ Lis CHAQUE flèche et le texte porté par la flèche (protocole, type de message)
  □ Lis les bases de données (cylindres), files de messages, caches
  □ Lis les services externes (nuages, logos tiers)
  □ Lis les mécanismes de sécurité (cadenas, JWT, OAuth, API Key)

══════════════════════════════════════════════════════════════
ÉTAPE 3 — REMPLIR LE JSON EXHAUSTIVEMENT
══════════════════════════════════════════════════════════════
Réponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou après :

{
  "architecture_detected": true,
  "architecture_type": "type exact parmi la liste ci-dessus",
  "layers": [
    {
      "name": "texte EXACT du titre de la zone/couche visible — SI AUCUN TITRE N'EST VISIBLE, déduis un nom court depuis le contenu (ex: 'Agent Layer', 'Processing', 'Input', 'Output') — ne laisse JAMAIS ce champ vide",
      "technologies": ["noms exacts des technologies lisibles dans cette zone"],
      "components": ["noms exacts des boîtes/composants visibles dans cette zone"],
      "role": "rôle déduit uniquement de ce qui est visible"
    }
  ],
  "agents": [
    {
      "name": "nom EXACT de l'agent tel qu'écrit",
      "role": "rôle écrit dans l'image, sinon null"
    }
  ],
  "orchestration": "outil d'orchestration visible (LangGraph, Kafka, Kubernetes...), null si absent",
  "apis": ["endpoints, routes ou APIs dont le texte est lisible"],
  "data_sources": ["TOUTES les bases de données, fichiers, caches, data lakes visibles — NOM EXACT"],
  "external_services": ["TOUS les services externes, SaaS, cloud providers visibles — NOM EXACT"],
  "mcp_servers": ["noms EXACTS des MCP servers visibles"],
  "security_mechanisms": ["JWT, OAuth2, API Key, TLS, firewall... visibles dans l'image"],
  "communication_protocols": ["HTTP, REST, gRPC, WebSocket, AMQP, Kafka, GraphQL... lisibles sur les flèches ou labels"],
  "deployment": ["Docker, Kubernetes, AWS, Azure, GCP, CI/CD... visibles"],
  "description": "description en 4-6 phrases basée UNIQUEMENT sur ce qui est visible — mentionne le type d'architecture, les couches principales, les protocoles, les sources de données et les services externes"
}

══════════════════════════════════════════════════════════════
RAPPEL CRITIQUE pour data_sources, external_services et communication_protocols
══════════════════════════════════════════════════════════════
Ces trois champs sont SOUVENT manqués. Avant de répondre :
  • Cherche les cylindres (bases de données) → data_sources
  • Cherche les nuages, logos (AWS, Slack, GitHub, Stripe...) → external_services
  • Cherche le texte sur les flèches (HTTP, REST, gRPC, TCP...) → communication_protocols
Si ces éléments ne sont pas visibles, laisse les listes vides [].

══════════════════════════════════════════════════════════════
Si l'image ne contient PAS de diagramme d'architecture :
══════════════════════════════════════════════════════════════
{
  "architecture_detected": false,
  "architecture_type": null,
  "layers": [], "agents": [], "orchestration": null,
  "apis": [], "data_sources": [], "mcp_servers": [],
  "external_services": [], "security_mechanisms": [],
  "communication_protocols": [], "deployment": [],
  "description": null
}"""


# ──────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ──────────────────────────────────────────────────────────────

@traceable(name="vlm_detect_architecture", run_type="chain")
async def detect_architecture_vlm(
    file_bytes: bytes,
    ext: str,
) -> tuple[bool, str | None, dict | None, dict]:
    """
    Détecte une architecture dans le document en deux étapes :
      1. Extraction + validation taille des images (PDF ou DOCX)
      2. Analyse VLM si des images analysables sont trouvées

    Retourne (detected, description, details, doc_info) :
      detected    — bool
      description — texte global (4-6 phrases) ou None
      details     — dict structuré (layers, apis, agents...) ou None
      doc_info    — { page_count, image_count, analyzed_count, oversized_pages }

    Non-bloquant : toute erreur retourne (False, None, None, doc_info).
    """
    _empty_info = {"page_count": 0, "image_count": 0, "analyzed_count": 0, "oversized_pages": []}

    print(f"\n[VLM] {'='*55}")
    print(f"[VLM] Démarrage détection d'architecture")
    print(f"[VLM]   Format : {ext} | Taille : {len(file_bytes) / 1024:.1f} KB")

    if ext == ".txt":
        print(f"[VLM] Format TXT → pas d'images possibles, analyse ignorée")
        print(f"[VLM] {'='*55}\n")
        return False, None, None, _empty_info

    groq_api_key = _pick_groq_key()
    if not groq_api_key:
        logger.warning("[VLM] Aucune clé Groq disponible — analyse VLM ignorée")
        print(f"[VLM] ⚠ Pas de clé Groq disponible → VLM ignoré")
        print(f"[VLM] {'='*55}\n")
        return False, None, None, _empty_info

    try:
        result = await asyncio.to_thread(
            _run_vlm_pipeline, file_bytes, ext, groq_api_key
        )
        print(f"[VLM] {'='*55}\n")
        return result
    except Exception as e:
        logger.error(f"[VLM] Erreur inattendue : {e}")
        print(f"[VLM] ✗ Erreur VLM (non-bloquant) : {e}")
        print(f"[VLM] {'='*55}\n")
        return False, None, None, _empty_info


# ──────────────────────────────────────────────────────────────
# PIPELINE SYNCHRONE (exécuté dans asyncio.to_thread)
# ──────────────────────────────────────────────────────────────

@traceable(name="vlm_pipeline_sync", run_type="chain")
def _run_vlm_pipeline(
    file_bytes: bytes,
    ext: str,
    groq_api_key: str,
) -> tuple[bool, str | None, dict | None, dict]:
    """Orchestre : extraction images → validation taille → appel VLM → parsing résultat."""

    # ── Étape 1 : extraction des images ──────────────────────
    print(f"[VLM] Étape 1 : extraction des images depuis le document...")
    images_b64, doc_info = _extract_images(file_bytes, ext)

    if not images_b64:
        msg = "aucune image trouvée" if doc_info["image_count"] == 0 else "toutes les images sont trop grandes pour le VLM"
        print(f"[VLM] ✗ {msg} → VLM non lancé")
        return False, None, None, doc_info

    print(f"[VLM] ✓ {len(images_b64)} image(s) analysable(s) sur {doc_info['image_count']} trouvée(s)")
    if doc_info["oversized_pages"]:
        print(f"[VLM] ⚠ Pages ignorées (image trop grande) : {doc_info['oversized_pages']}")

    # ── Étape 2 : appel Groq Vision ───────────────────────────
    print(f"[VLM] Étape 2 : envoi des images à {_VLM_MODEL}...")
    raw_response = _call_groq_vision(images_b64, groq_api_key)

    if not raw_response:
        print(f"[VLM] ✗ Réponse vide du modèle VLM")
        return False, None, None, doc_info

    # ── Étape 3 : parsing JSON ────────────────────────────────
    print(f"[VLM] Étape 3 : parsing de la réponse...")
    detected, description, details = _parse_vlm_response(raw_response)
    doc_info["analyzed_count"] = len(images_b64)
    return detected, description, details, doc_info


# ──────────────────────────────────────────────────────────────
# EXTRACTION DES IMAGES
# ──────────────────────────────────────────────────────────────

def _extract_images(file_bytes: bytes, ext: str) -> tuple[list[str], dict]:
    """
    Dispatch vers l'extracteur approprié selon le format.
    Retourne (images_b64_analysables, doc_info).
    """
    if ext == ".pdf":
        return _extract_images_from_pdf(file_bytes)
    if ext == ".docx":
        return _extract_images_from_docx(file_bytes)
    return [], {"page_count": 0, "image_count": 0, "analyzed_count": 0, "oversized_pages": []}


# Seuil minimum de dessins vectoriels pour considérer une page comme "visuelle".
# Les pages texte contiennent souvent quelques traits (bordures, séparateurs, en-têtes)
# qui ne constituent pas un diagramme. Un vrai schéma d'architecture a >> 15 paths.
_MIN_DRAWINGS_THRESHOLD = 15


def _extract_images_from_pdf(file_bytes: bytes) -> tuple[list[str], dict]:
    """
    Pour chaque page PDF :
      - Détecte si la page contient :
          • des images embarquées (xobjects images PDF), OU
          • un nombre significatif de dessins vectoriels (>= _MIN_DRAWINGS_THRESHOLD)
            → évite de compter les simples bordures/séparateurs des pages texte
      - Vérifie que la taille du PNG rendu ne dépasse pas _MAX_IMAGE_BYTES
      - Si taille OK → ajoute à la liste des images analysables
      - Si taille trop grande → consigne dans oversized_pages
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        logger.error("[VLM] pymupdf non installé — pip install pymupdf")
        return [], {"page_count": 0, "image_count": 0, "analyzed_count": 0, "oversized_pages": []}

    doc        = fitz.open(stream=file_bytes, filetype="pdf")
    nb_pages   = len(doc)
    images_b64 = []
    image_count      = 0
    oversized_pages  = []

    print(f"[VLM]   PDF : {nb_pages} page(s) au total")

    matrix = fitz.Matrix(_IMAGE_DPI / 72, _IMAGE_DPI / 72)

    for i in range(nb_pages):
        page = doc[i]

        embedded_images = page.get_images(full=True)
        drawings        = page.get_drawings()

        # Une page est "visuelle" si elle contient une image embarquée
        # OU un nombre suffisant de dessins (seuil anti-bordures/séparateurs)
        has_visual = bool(embedded_images) or (len(drawings) >= _MIN_DRAWINGS_THRESHOLD)

        status = (
            f"✓ {len(embedded_images)} image(s) embarquée(s)"   if embedded_images else
            f"✓ {len(drawings)} dessins vectoriels (schéma)"     if has_visual else
            f"✗ {len(drawings)} dessin(s) — sous le seuil ({_MIN_DRAWINGS_THRESHOLD}), ignorée"
        )
        print(f"[VLM]   Page {i+1}/{nb_pages} → {status}")

        if not has_visual:
            continue

        image_count += 1
        pix       = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB)
        png_bytes = pix.tobytes("png")
        size_kb   = len(png_bytes) // 1024

        if len(png_bytes) > _MAX_IMAGE_BYTES:
            max_mb = _MAX_IMAGE_BYTES / (1024 * 1024)
            print(f"[VLM]   Page {i+1} → {size_kb} KB — ⚠ TROP GRANDE (limite {max_mb:.0f} MB) ignorée")
            oversized_pages.append(i + 1)
        else:
            images_b64.append(base64.b64encode(png_bytes).decode("utf-8"))
            print(f"[VLM]   Page {i+1} → {size_kb} KB PNG ✓ — "
                  f"{len(embedded_images)} image(s), {len(drawings)} dessin(s) vectoriel(s)")

    doc.close()

    doc_info = {
        "page_count":     nb_pages,
        "image_count":    image_count,
        "analyzed_count": 0,          # sera mis à jour après l'appel VLM
        "oversized_pages": oversized_pages,
    }
    return images_b64, doc_info


def _extract_images_from_docx(file_bytes: bytes) -> tuple[list[str], dict]:
    """
    Extrait les images embarquées dans un document DOCX.
    Vérifie la taille de chaque image avant envoi au VLM.
    """
    try:
        from docx import Document
    except ImportError:
        logger.error("[VLM] python-docx non installé — pip install python-docx")
        return [], {"page_count": 1, "image_count": 0, "analyzed_count": 0, "oversized_pages": []}

    doc            = Document(io.BytesIO(file_bytes))
    images_b64     = []
    image_count    = 0
    oversized_idxs = []

    print(f"[VLM]   DOCX : inspection des relations du document...")

    for rel_id, rel in doc.part.rels.items():
        if "image" not in rel.reltype:
            continue
        try:
            img_bytes = rel.target_part.blob
            image_count += 1
            size_kb = len(img_bytes) // 1024

            if len(images_b64) >= 10:
                print(f"[VLM]   Limite 10 images atteinte, reste ignoré")
                break

            if len(img_bytes) > _MAX_IMAGE_BYTES:
                max_mb = _MAX_IMAGE_BYTES / (1024 * 1024)
                print(f"[VLM]   Image {image_count} → {size_kb} KB — ⚠ TROP GRANDE (limite {max_mb:.0f} MB) ignorée")
                oversized_idxs.append(image_count)
            else:
                images_b64.append(base64.b64encode(img_bytes).decode("utf-8"))
                print(f"[VLM]   Image {image_count} extraite → {size_kb} KB ✓")
        except Exception as e:
            logger.warning(f"[VLM] Impossible de lire l'image {rel_id} : {e}")

    print(f"[VLM]   DOCX : {image_count} image(s) trouvée(s), {len(images_b64)} analysable(s)")

    doc_info = {
        "page_count":     1,           # DOCX n'a pas de pages structurées
        "image_count":    image_count,
        "analyzed_count": 0,
        "oversized_pages": oversized_idxs,
    }
    return images_b64, doc_info


# ──────────────────────────────────────────────────────────────
# APPEL GROQ VISION
# ──────────────────────────────────────────────────────────────

@traceable(name="vlm_groq_call", run_type="llm")
def _call_groq_vision(images_b64: list[str], groq_api_key: str) -> str | None:
    """
    Envoie uniquement les images (base64) au modèle Groq Vision.
    Le document complet n'est PAS envoyé — seules les images extraites le sont.
    Retourne le texte brut de la réponse, ou None si erreur.
    """
    try:
        from groq import Groq
    except ImportError:
        logger.error("[VLM] groq non installé — pip install groq")
        return None

    # Construction du message : images d'abord, prompt analytique ensuite
    content_parts = []
    for idx, b64 in enumerate(images_b64):
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{b64}"},
        })
        print(f"[VLM]   Image {idx+1}/{len(images_b64)} ajoutée au message")

    content_parts.append({"type": "text", "text": _VLM_PROMPT})

    print(f"[VLM]   Appel {_VLM_MODEL} avec {len(images_b64)} image(s) (texte document non envoyé)...")

    client = Groq(api_key=groq_api_key)
    completion = client.chat.completions.create(
        model=_VLM_MODEL,
        messages=[{"role": "user", "content": content_parts}],
        temperature=0,
        max_completion_tokens=_MAX_OUTPUT_TOKENS,
        top_p=1,
        stream=False,
        stop=None,
    )

    raw = completion.choices[0].message.content.strip()
    tokens_in  = completion.usage.prompt_tokens     if completion.usage else "?"
    tokens_out = completion.usage.completion_tokens if completion.usage else "?"
    print(f"[VLM]   ✓ Réponse reçue | tokens : {tokens_in} in / {tokens_out} out")
    print(f"[VLM]   Réponse brute : {raw[:300]}")
    return raw


# ──────────────────────────────────────────────────────────────
# PARSING
# ──────────────────────────────────────────────────────────────

def _parse_vlm_response(raw: str) -> tuple[bool, str | None, dict | None]:
    """
    Parse la réponse JSON du VLM.
    Retourne (detected, description_globale, details_structures).
    """
    clean = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    # Tenter d'extraire le premier bloc JSON si le modèle a ajouté du texte autour
    json_match = re.search(r'\{[\s\S]*\}', clean)
    if json_match:
        clean = json_match.group(0)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError as e:
        logger.warning(f"[VLM] Réponse non-JSON : {e} | contenu : {raw[:200]}")
        print(f"[VLM] ⚠ Impossible de parser la réponse JSON")
        return False, None, None

    detected    = bool(data.get("architecture_detected", False))
    description = data.get("description") or None
    arch_type   = data.get("architecture_type") or None

    if not detected:
        print(f"[VLM] ✗ Aucune architecture technique détectée dans les images")
        return False, None, None

    # ── Nettoyage des couches : remplir les noms vides ───────
    raw_layers = data.get("layers", [])
    for idx, layer in enumerate(raw_layers):
        if not layer.get("name"):
            components = layer.get("components", [])
            if components:
                layer["name"] = f"Zone {idx + 1} ({', '.join(components[:2])}{'...' if len(components) > 2 else ''})"
            else:
                layer["name"] = f"Zone {idx + 1}"

    # ── Détails structurés ────────────────────────────────────
    details = {
        "architecture_type":       arch_type,
        "layers":                  raw_layers,
        "agents":                  data.get("agents",                  []),
        "orchestration":           data.get("orchestration"),
        "apis":                    data.get("apis",                    []),
        "data_sources":            data.get("data_sources",            []),
        "mcp_servers":             data.get("mcp_servers",             []),
        "external_services":       data.get("external_services",       []),
        "security_mechanisms":     data.get("security_mechanisms",     []),
        "communication_protocols": data.get("communication_protocols", []),
        "deployment":              data.get("deployment",              []),
    }

    # ── Logs détaillés ────────────────────────────────────────
    print(f"[VLM] ✓ Architecture détectée")
    print(f"[VLM]   Type            : {arch_type}")
    print(f"[VLM]   Layers          : {len(details['layers'])} couche(s)")
    for layer in details["layers"]:
        print(f"[VLM]     - {layer.get('name', '?')} | techs: {layer.get('technologies', [])} | composants: {layer.get('components', [])}")
    if details["agents"]:
        print(f"[VLM]   Agents          : {[a.get('name') for a in details['agents']]}")
    if details["orchestration"]:
        print(f"[VLM]   Orchestration   : {details['orchestration']}")
    if details["apis"]:
        print(f"[VLM]   APIs            : {details['apis']}")
    if details["data_sources"]:
        print(f"[VLM]   Data sources    : {details['data_sources']}")
    if details["communication_protocols"]:
        print(f"[VLM]   Protocoles      : {details['communication_protocols']}")
    if details["mcp_servers"]:
        print(f"[VLM]   MCP servers     : {details['mcp_servers']}")
    if details["security_mechanisms"]:
        print(f"[VLM]   Sécurité        : {details['security_mechanisms']}")
    if details["external_services"]:
        print(f"[VLM]   Services ext.   : {details['external_services']}")
    if details["deployment"]:
        print(f"[VLM]   Déploiement     : {details['deployment']}")
    print(f"[VLM]   Description     : {(description or '')[:400]}")

    return True, description, details


# ──────────────────────────────────────────────────────────────
# UTILITAIRE
# ──────────────────────────────────────────────────────────────

def _pick_groq_key() -> str | None:
    """Retourne la première clé Groq disponible dans le .env."""
    from dotenv import load_dotenv
    load_dotenv()
    for i in range(1, 10):
        key = os.getenv(f"GROQ_API_KEY_{i}")
        if key:
            return key
    return os.getenv("GROQ_API_KEY") or None
