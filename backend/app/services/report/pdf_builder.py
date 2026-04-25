# app/services/report/pdf_builder.py
# ═══════════════════════════════════════════════════════════════
# Génération du PDF backlog avec ReportLab.
# Responsabilité unique : mise en page et rendu PDF.
# Aucun accès DB, aucune logique métier.
# ═══════════════════════════════════════════════════════════════

import io
import os
from datetime import date, datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether, Image,
)


# ── Palette couleurs ──────────────────────────────────────────
NAVY      = colors.HexColor("#0F1D3A")
CYAN      = colors.HexColor("#00B4D8")
AMBER     = colors.HexColor("#F59E0B")
GREEN     = colors.HexColor("#10B981")
RED       = colors.HexColor("#EF4444")
SLATE_100 = colors.HexColor("#F1F5F9")
SLATE_200 = colors.HexColor("#E2E8F0")
SLATE_500 = colors.HexColor("#64748B")
SLATE_700 = colors.HexColor("#334155")
WHITE     = colors.white

# Chemin absolu du logo (même répertoire que le backend)
_LOGO_PATH = os.path.join(
    os.path.dirname(__file__),   # .../app/services/report/
    "..", "..", "..",             # remonte à backend/
    "images", "logo talan.png",
)
_LOGO_PATH = os.path.normpath(_LOGO_PATH)


# ── Styles typographiques ─────────────────────────────────────
def _styles() -> dict:
    return {
        "company": ParagraphStyle(
            "company", fontName="Helvetica-Bold",
            fontSize=11, textColor=CYAN,
        ),
        "project_title": ParagraphStyle(
            "project_title", fontName="Helvetica-Bold",
            fontSize=26, textColor=NAVY,
            leading=30,       # ligne haute — pas de spaceAfter ici
            spaceAfter=0,
        ),
        "meta_label": ParagraphStyle(
            "meta_label", fontName="Helvetica",
            fontSize=10, textColor=SLATE_500,
        ),
        "meta_value": ParagraphStyle(
            "meta_value", fontName="Helvetica-Bold",
            fontSize=10, textColor=SLATE_700,
        ),
        "section_title": ParagraphStyle(
            "section_title", fontName="Helvetica-Bold",
            fontSize=15, textColor=NAVY, spaceBefore=16, spaceAfter=8,
        ),
        "epic_title": ParagraphStyle(
            "epic_title", fontName="Helvetica-Bold",
            fontSize=12, textColor=WHITE,
        ),
        "epic_desc": ParagraphStyle(
            "epic_desc", fontName="Helvetica",
            fontSize=10, textColor=SLATE_500,
            spaceBefore=5, spaceAfter=4, leading=14,
        ),
        "epic_strategy": ParagraphStyle(
            "epic_strategy", fontName="Helvetica-Oblique",
            fontSize=9, textColor=SLATE_500,
            spaceAfter=8,
        ),
        "story_title": ParagraphStyle(
            "story_title", fontName="Helvetica-Bold",
            fontSize=10, textColor=SLATE_700, leading=14,
        ),
        "story_desc": ParagraphStyle(
            "story_desc", fontName="Helvetica",
            fontSize=9, textColor=SLATE_500, leading=12,
        ),
        "ac_item": ParagraphStyle(
            "ac_item", fontName="Helvetica",
            fontSize=9, textColor=SLATE_700, leading=12,
            leftIndent=10,
        ),
        "coverage_warn": ParagraphStyle(
            "coverage_warn", fontName="Helvetica-Bold",
            fontSize=9, textColor=AMBER,
        ),
        "coverage_gap": ParagraphStyle(
            "coverage_gap", fontName="Helvetica",
            fontSize=9, textColor=SLATE_700, leading=12,
            leftIndent=10,
        ),
    }


# ── Helpers ───────────────────────────────────────────────────

def _fmt_date(d) -> str:
    if d is None:
        return "—"
    if isinstance(d, (date, datetime)):
        return d.strftime("%d/%m/%Y")
    return str(d)


def _sp_color(pts: int | None) -> colors.Color:
    if not pts:
        return SLATE_500
    if pts <= 2:  return GREEN
    if pts <= 5:  return CYAN
    if pts <= 8:  return AMBER
    return RED


_STRATEGY_COLORS: dict[str, tuple[str, colors.Color]] = {
    "by_feature":       ("Par feature",           colors.HexColor("#1D4ED8")),
    "by_user_role":     ("Par role utilisateur",  colors.HexColor("#15803D")),
    "by_workflow_step": ("Par etape de workflow", colors.HexColor("#B45309")),
    "by_component":     ("Par composant",         colors.HexColor("#7E22CE")),
}
_STRATEGY_DEFAULT_COLOR = ("Par feature", colors.HexColor("#1D4ED8"))


def _strategy_paragraph(strategy: str) -> Paragraph:
    label, fg = _STRATEGY_COLORS.get(strategy, _STRATEGY_DEFAULT_COLOR)
    return Paragraph(
        f"Decoupage : <b>{label}</b>",
        ParagraphStyle(
            "strat", fontName="Helvetica", fontSize=9,
            textColor=fg, spaceAfter=6,
        ),
    )


# ── Bloc en-tête du document ──────────────────────────────────

def _build_header(data: dict, styles: dict) -> list:
    project = data["project"]
    client  = data["client"]
    pm      = data["pm"]
    summary = data["summary"]
    elements = []

    # ── En-tête : logo à gauche (grand), titre centré, fond blanc ──
    logo_size = 2.2 * cm   # logo carré 225×225, agrandi
    if os.path.exists(_LOGO_PATH):
        try:
            logo_cell = Image(_LOGO_PATH, width=logo_size, height=logo_size)
        except Exception:
            logo_cell = Paragraph("TALAN", styles["company"])
    else:
        logo_cell = Paragraph("TALAN", styles["company"])

    header_table = Table(
        [[
            logo_cell,
            Paragraph("BACKLOG REPORT", ParagraphStyle(
                "br", fontName="Helvetica-Bold", fontSize=16,
                textColor=NAVY, alignment=TA_CENTER,
            )),
            Paragraph("", ParagraphStyle("empty", fontSize=1)),  # équilibre droite
        ]],
        colWidths=[2.8 * cm, 12.4 * cm, 2.8 * cm],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), WHITE),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(header_table)
    elements.append(HRFlowable(width="100%", thickness=2, color=NAVY, spaceAfter=8))
    elements.append(Spacer(1, 0.3 * cm))

    # ── Titre projet + séparateur cyan (avec espace explicite) ──
    elements.append(Paragraph(project["name"], styles["project_title"]))
    elements.append(Spacer(1, 0.25 * cm))          # espace AVANT la ligne
    elements.append(HRFlowable(width="100%", thickness=2, color=CYAN, spaceAfter=10))

    # ── Métadonnées 2 colonnes ────────────────────────────────
    def _meta_row(label, value):
        return [
            Paragraph(label, styles["meta_label"]),
            Paragraph(str(value) if value else "—", styles["meta_value"]),
        ]

    meta_left = [
        _meta_row("Client",         client["name"]),
        _meta_row("Secteur",        client["industry"] or "—"),
        _meta_row("Contact",        client["contact_email"] or "—"),
        _meta_row("Chef de projet", pm["name"]),
        _meta_row("Email PM",       pm["email"]),
    ]
    meta_right = [
        _meta_row("Date debut",  _fmt_date(project["start_date"])),
        _meta_row("Deadline",    _fmt_date(project["end_date"])),
        _meta_row("Jira",        project["jira_key"] or "—"),
        _meta_row("Statut",      project["status"] or "—"),
        ["", ""],
    ]

    combined = []
    for i in range(len(meta_left)):
        combined.append(meta_left[i] + [Spacer(0.4 * cm, 1)] + meta_right[i])

    meta_table = Table(combined, colWidths=[3.2 * cm, 5.3 * cm, 0.4 * cm, 3.2 * cm, 5.9 * cm])
    meta_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 0.5 * cm))

    # ── Bandeau résumé — 4 stats ──────────────────────────────
    stats = [
        ("Epics",        str(summary["nb_epics"]),           NAVY),
        ("Stories",      str(summary["nb_stories"]),          CYAN),
        ("Story Points", str(summary["total_points"]),        GREEN),
        ("Couv. KO",     str(summary["nb_coverage_issues"]),  AMBER),
    ]
    stats_cells = []
    for label, value, col in stats:
        cell = Table(
            [[Paragraph(value, ParagraphStyle(
                "sv", fontName="Helvetica-Bold", fontSize=22,
                textColor=col, alignment=TA_CENTER,
            ))],
             [Paragraph(label, ParagraphStyle(
                "sl", fontName="Helvetica", fontSize=9,
                textColor=SLATE_500, alignment=TA_CENTER,
            ))]],
            colWidths=[4.25 * cm],
        )
        cell.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), SLATE_100),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("ROUNDEDCORNERS", [4]),
        ]))
        stats_cells.append(cell)

    summary_table = Table([stats_cells], colWidths=[4.25 * cm] * 4)
    summary_table.setStyle(TableStyle([
        ("LEFTPADDING",  (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.6 * cm))

    return elements


# ── Bloc couverture d'un epic ─────────────────────────────────

def _build_coverage_block(coverage: dict, styles: dict) -> list:
    if coverage["ok"]:
        return []

    items = []
    gaps         = coverage.get("gaps", [])
    suggestions  = coverage.get("suggestions", [])
    scope_issues = coverage.get("scope_creep_issues", [])
    quality      = coverage.get("quality_issues", [])

    items.append(Paragraph("Couverture incomplete", styles["coverage_warn"]))

    if gaps:
        items.append(Paragraph("Fonctionnalites manquantes :", ParagraphStyle(
            "cl", fontName="Helvetica-Bold", fontSize=9, textColor=SLATE_700,
        )))
        for g in gaps:
            items.append(Paragraph(f"- {g}", styles["coverage_gap"]))

    if scope_issues:
        items.append(Paragraph("Scope creep :", ParagraphStyle(
            "cl", fontName="Helvetica-Bold", fontSize=9, textColor=SLATE_700,
        )))
        for s in scope_issues:
            items.append(Paragraph(f"- {s}", styles["coverage_gap"]))

    if quality:
        items.append(Paragraph("Qualite :", ParagraphStyle(
            "cl", fontName="Helvetica-Bold", fontSize=9, textColor=SLATE_700,
        )))
        for q in quality:
            items.append(Paragraph(f"- {q}", styles["coverage_gap"]))

    if suggestions:
        items.append(Paragraph("Suggestions :", ParagraphStyle(
            "cl", fontName="Helvetica-Bold", fontSize=9, textColor=SLATE_700,
        )))
        for s in suggestions:
            items.append(Paragraph(f"- {s}", styles["coverage_gap"]))

    block_table = Table([[items]], colWidths=[17 * cm])
    block_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX",           (0, 0), (-1, -1), 0.5, AMBER),
        ("ROUNDEDCORNERS", [4]),
    ]))
    return [block_table, Spacer(1, 0.25 * cm)]


# ── Bloc d'une story ──────────────────────────────────────────

def _build_story_row(story: dict, idx: int, styles: dict) -> list:
    pts    = story["story_points"]
    pt_col = _sp_color(pts)
    pt_str = str(pts) if pts else "?"

    # Colonne gauche : numéro + SP
    left_content = Table(
        [[Paragraph(f"{idx}", ParagraphStyle(
            "si", fontName="Helvetica-Bold", fontSize=11,
            textColor=WHITE, alignment=TA_CENTER,
        ))],
         [Paragraph(f"{pt_str} pts", ParagraphStyle(
            "sp", fontName="Helvetica-Bold", fontSize=9,
            textColor=pt_col, alignment=TA_CENTER,
         ))]],
        colWidths=[1.4 * cm],
    )
    left_content.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
    ]))

    # Colonne droite : titre + description + AC
    right_items = [Paragraph(story["title"], styles["story_title"])]

    if story.get("description"):
        right_items.append(Paragraph(story["description"], styles["story_desc"]))

    ac = story.get("acceptance_criteria", [])
    if ac:
        right_items.append(Paragraph("Criteres d'acceptation :", ParagraphStyle(
            "acl", fontName="Helvetica-Bold", fontSize=9,
            textColor=SLATE_700, spaceBefore=4,
        )))
        for criterion in ac:
            # &#8226; = bullet •  (supporte par ReportLab WinAnsiEncoding)
            right_items.append(Paragraph(f"&#8226;  {criterion}", styles["ac_item"]))

    row_table = Table(
        [[left_content, right_items]],
        colWidths=[1.5 * cm, 15.5 * cm],
    )
    row_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("BACKGROUND",    (1, 0), (1, 0), WHITE),
        ("BOX",           (0, 0), (-1, -1), 0.3, SLATE_200),
    ]))

    return [row_table, Spacer(1, 0.2 * cm)]


# ── Bloc d'un epic ────────────────────────────────────────────

def _build_epic_block(epic: dict, epic_num: int, styles: dict) -> list:
    stories  = epic["stories"]
    coverage = epic["coverage"]

    nb_stories = len(stories)
    total_pts  = sum(s["story_points"] or 0 for s in stories)
    cov_ok     = coverage["ok"]
    cov_badge  = "Couverture OK" if cov_ok else "Couverture incomplete"
    cov_color  = GREEN if cov_ok else AMBER

    # ── En-tête de l'epic (bande navy) ────────────────────────
    header_left = Paragraph(
        f"<b>{epic_num}. {epic['title']}</b>",
        styles["epic_title"],
    )
    header_right = Table(
        [[
            Paragraph(cov_badge, ParagraphStyle(
                "cb", fontName="Helvetica-Bold", fontSize=9,
                textColor=cov_color,
            )),
            Paragraph(
                f"{nb_stories} stories  {total_pts} pts",
                ParagraphStyle("cs", fontName="Helvetica", fontSize=9, textColor=WHITE),
            ),
        ]],
        colWidths=[4.5 * cm, 3.5 * cm],
    )
    header_right.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    epic_header = Table(
        [[header_left, header_right]],
        colWidths=[9 * cm, 8 * cm],
    )
    epic_header.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (0, -1),  12),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 12),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))

    elements = [epic_header]

    # ── Description ───────────────────────────────────────────
    if epic.get("description"):
        elements.append(Paragraph(epic["description"], styles["epic_desc"]))

    # ── Stratégie de découpage ────────────────────────────────
    elements.append(_strategy_paragraph(epic.get("splitting_strategy", "")))

    # ── Bloc couverture si incomplète ─────────────────────────
    elements.extend(_build_coverage_block(coverage, styles))

    # ── Stories ───────────────────────────────────────────────
    for i, story in enumerate(stories, 1):
        elements.extend(_build_story_row(story, i, styles))

    elements.append(Spacer(1, 0.6 * cm))
    return elements


# ── Fonction publique principale ──────────────────────────────

def generate_pdf(data: dict) -> bytes:
    """
    Génère le PDF backlog en mémoire à partir du dict produit par service.py.
    Retourne les bytes du PDF.
    """
    buffer = io.BytesIO()
    styles = _styles()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.8 * cm,
        title=f"Backlog — {data['project']['name']}",
        author="Talan Assistant",
    )

    elements: list = []

    elements.extend(_build_header(data, styles))

    elements.append(Paragraph("Backlog — Epics & User Stories", styles["section_title"]))
    elements.append(HRFlowable(width="100%", thickness=1, color=SLATE_200, spaceAfter=10))

    for i, epic in enumerate(data["epics"], 1):
        block = _build_epic_block(epic, i, styles)
        elements.append(KeepTogether(block[:3]))
        elements.extend(block[3:])

    def _add_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(SLATE_500)
        now   = datetime.now().strftime("%d/%m/%Y %H:%M")
        pname = data["project"]["name"]
        canvas.drawString(1.5 * cm, 0.9 * cm, f"Talan Assistant — {pname}")
        canvas.drawRightString(
            A4[0] - 1.5 * cm, 0.9 * cm,
            f"Page {doc.page}  |  Genere le {now}",
        )
        canvas.restoreState()

    doc.build(elements, onFirstPage=_add_footer, onLaterPages=_add_footer)
    return buffer.getvalue()
