# app/services/report/service.py
# ═══════════════════════════════════════════════════════════════
# Assemblage des données du rapport backlog.
# Responsabilité : appeler le repository, calculer les totaux,
# structurer le dict final passé à pdf_builder.
# Aucun accès DB direct, aucune logique PDF.
# ═══════════════════════════════════════════════════════════════

from app.services.report.repository import get_project_full, get_epics_with_stories


async def build_report_data(project_id: int) -> dict | None:
    """
    Construit le dictionnaire complet des données du rapport.
    Retourne None si le projet n'existe pas.
    """
    project = await get_project_full(project_id)
    if not project:
        return None

    epics = await get_epics_with_stories(project_id)

    nb_stories         = sum(len(e["stories"]) for e in epics)
    total_points       = sum(
        s["story_points"] or 0
        for e in epics
        for s in e["stories"]
    )
    nb_coverage_issues = sum(1 for e in epics if not e["coverage"]["ok"])

    return {
        "project": {
            "id":         project["id"],
            "name":       project["name"],
            "status":     project["status"],
            "start_date": project["start_date"],
            "end_date":   project["end_date"],
            "jira_key":   project["jira_key"],
            "created_at": project["created_at"],
        },
        "client": project["client"],
        "pm":     project["pm"],
        "summary": {
            "nb_epics":           len(epics),
            "nb_stories":         nb_stories,
            "total_points":       total_points,
            "nb_coverage_issues": nb_coverage_issues,
        },
        "epics": epics,
    }
