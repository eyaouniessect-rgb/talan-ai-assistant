"""
Script de suppression complète d'un ou plusieurs projets PM.

Supprime dans l'ordre correct (respect des FK) :
  project_management.task_dependencies
  project_management.story_dependencies
  project_management.tasks
  project_management.user_stories
  project_management.sprints
  project_management.epics
  project_management.pipeline_state
  project_management.project_documents
  crm.projects

Utilisation :
  python scripts/delete_project.py                   → liste tous les projets
  python scripts/delete_project.py 5                 → supprime le projet id=5
  python scripts/delete_project.py 5 12 17           → supprime les projets 5, 12, 17
  python scripts/delete_project.py --all             → supprime TOUS les projets (confirmation requise)
  python scripts/delete_project.py 5 --dry-run       → simule sans supprimer

Exécuter depuis le dossier backend/ :
  cd backend && python scripts/delete_project.py
"""

import asyncio
import sys
import os

# Ajoute backend/ au path pour importer les modules du projet
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host":     os.getenv("POSTGRES_HOST",     "localhost"),
    "port":     int(os.getenv("POSTGRES_PORT", "5432")),
    "user":     os.getenv("POSTGRES_USER",     "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", "password"),
    "database": os.getenv("POSTGRES_DB",       "talan_assistant"),
}

# ──────────────────────────────────────────────────────────────
# Helpers affichage
# ──────────────────────────────────────────────────────────────

def _sep(char="─", width=60):
    print(char * width)

def _header(text):
    _sep("═")
    print(f"  {text}")
    _sep("═")

def _ok(text):   print(f"  ✓  {text}")
def _skip(text): print(f"  -  {text}")
def _warn(text): print(f"  ⚠  {text}")
def _err(text):  print(f"  ✗  {text}")


# ──────────────────────────────────────────────────────────────
# Listing des projets
# ──────────────────────────────────────────────────────────────

async def list_projects(conn) -> list[dict]:
    rows = await conn.fetch("""
        SELECT
            p.id,
            p.name,
            p.status,
            p.archived,
            p.created_at,
            COUNT(DISTINCT e.id)   AS nb_epics,
            COUNT(DISTINCT us.id)  AS nb_stories,
            COUNT(DISTINCT t.id)   AS nb_tasks,
            COUNT(DISTINCT ps.id)  AS nb_pipeline_phases,
            COUNT(DISTINCT pd.id)  AS nb_documents
        FROM crm.projects p
        LEFT JOIN project_management.epics          e  ON e.project_id  = p.id
        LEFT JOIN project_management.user_stories   us ON us.epic_id    = e.id
        LEFT JOIN project_management.tasks          t  ON t.user_story_id = us.id
        LEFT JOIN project_management.pipeline_state ps ON ps.project_id = p.id
        LEFT JOIN project_management.project_documents pd ON pd.project_id = p.id
        GROUP BY p.id
        ORDER BY p.id
    """)
    return [dict(r) for r in rows]


def print_projects(projects: list[dict]):
    if not projects:
        print("  Aucun projet trouvé.")
        return

    print(f"\n  {'ID':>4}  {'Nom':<35} {'Statut':<18} {'Arch':>4}  "
          f"{'Epics':>5}  {'Stories':>7}  {'Tasks':>5}  {'Phases':>6}  {'Docs':>4}")
    _sep()
    for p in projects:
        arch = "oui" if p["archived"] else "non"
        print(f"  {p['id']:>4}  {str(p['name']):<35} {str(p['status']):<18} {arch:>4}  "
              f"{p['nb_epics']:>5}  {p['nb_stories']:>7}  {p['nb_tasks']:>5}  "
              f"{p['nb_pipeline_phases']:>6}  {p['nb_documents']:>4}")
    _sep()
    print(f"  Total : {len(projects)} projet(s)\n")


# ──────────────────────────────────────────────────────────────
# Suppression d'un projet
# ──────────────────────────────────────────────────────────────

async def delete_one_project(conn, project_id: int, dry_run: bool = False) -> dict:
    """
    Supprime un projet et toutes ses données liées dans l'ordre correct des FK.
    Retourne un dict avec les compteurs de lignes supprimées.
    """
    stats = {}

    # Vérifie que le projet existe
    row = await conn.fetchrow(
        "SELECT id, name FROM crm.projects WHERE id = $1", project_id
    )
    if not row:
        _warn(f"Projet id={project_id} introuvable — ignoré.")
        return {}

    project_name = row["name"]
    print(f"\n  Projet  : [{project_id}] {project_name}")
    _sep("-")

    async def _delete(label: str, query: str, *args):
        if dry_run:
            # Compte sans supprimer
            count_q = query.replace("DELETE FROM", "SELECT COUNT(*) FROM", 1)
            # Retire la clause RETURNING si présente
            count_q = count_q.split(" RETURNING")[0]
            count = await conn.fetchval(count_q, *args)
            _skip(f"[DRY-RUN] {label} : {count} ligne(s)")
            stats[label] = count
        else:
            result = await conn.execute(query, *args)
            # result = "DELETE N"
            count = int(result.split()[-1]) if result else 0
            if count:
                _ok(f"{label} : {count} supprimé(s)")
            else:
                _skip(f"{label} : 0 ligne")
            stats[label] = count

    # ── 1. task_dependencies ─────────────────────────────────
    await _delete(
        "task_dependencies",
        """
        DELETE FROM project_management.task_dependencies
        WHERE task_id IN (
            SELECT t.id FROM project_management.tasks t
            JOIN project_management.user_stories us ON us.id = t.user_story_id
            JOIN project_management.epics e ON e.id = us.epic_id
            WHERE e.project_id = $1
        )
        """,
        project_id,
    )

    # ── 2. story_dependencies ────────────────────────────────
    await _delete(
        "story_dependencies",
        """
        DELETE FROM project_management.story_dependencies
        WHERE story_id IN (
            SELECT us.id FROM project_management.user_stories us
            JOIN project_management.epics e ON e.id = us.epic_id
            WHERE e.project_id = $1
        )
        """,
        project_id,
    )

    # ── 3. tasks ─────────────────────────────────────────────
    await _delete(
        "tasks",
        """
        DELETE FROM project_management.tasks
        WHERE user_story_id IN (
            SELECT us.id FROM project_management.user_stories us
            JOIN project_management.epics e ON e.id = us.epic_id
            WHERE e.project_id = $1
        )
        """,
        project_id,
    )

    # ── 4. user_stories ──────────────────────────────────────
    await _delete(
        "user_stories",
        """
        DELETE FROM project_management.user_stories
        WHERE epic_id IN (
            SELECT id FROM project_management.epics WHERE project_id = $1
        )
        """,
        project_id,
    )

    # ── 5. sprints ───────────────────────────────────────────
    await _delete(
        "sprints",
        "DELETE FROM project_management.sprints WHERE project_id = $1",
        project_id,
    )

    # ── 6. epics ─────────────────────────────────────────────
    await _delete(
        "epics",
        "DELETE FROM project_management.epics WHERE project_id = $1",
        project_id,
    )

    # ── 7. pipeline_state ────────────────────────────────────
    await _delete(
        "pipeline_state",
        "DELETE FROM project_management.pipeline_state WHERE project_id = $1",
        project_id,
    )

    # ── 8. project_documents ─────────────────────────────────
    await _delete(
        "project_documents",
        "DELETE FROM project_management.project_documents WHERE project_id = $1",
        project_id,
    )

    # ── 9. project (crm) ─────────────────────────────────────
    await _delete(
        "crm.projects",
        "DELETE FROM crm.projects WHERE id = $1",
        project_id,
    )

    total = sum(stats.values())
    mode = "[DRY-RUN] " if dry_run else ""
    print(f"  {mode}→ Total supprimé : {total} ligne(s)")
    return stats


# ──────────────────────────────────────────────────────────────
# Point d'entrée principal
# ──────────────────────────────────────────────────────────────

async def main():
    args = sys.argv[1:]
    dry_run  = "--dry-run"  in args
    delete_all = "--all"    in args
    args = [a for a in args if not a.startswith("--")]

    conn = await asyncpg.connect(**DB_CONFIG)

    try:
        # ── Mode liste : aucun argument ──────────────────────
        if not args and not delete_all:
            _header("Projets existants")
            projects = await list_projects(conn)
            print_projects(projects)
            print("  Usage : python scripts/delete_project.py <id> [id2 ...] [--dry-run]")
            print("          python scripts/delete_project.py --all\n")
            return

        # ── Mode --all ───────────────────────────────────────
        if delete_all:
            projects = await list_projects(conn)
            if not projects:
                print("  Aucun projet à supprimer.")
                return

            _header("Suppression de TOUS les projets")
            print_projects(projects)

            if not dry_run:
                confirm = input("  Tapez 'SUPPRIMER TOUT' pour confirmer : ").strip()
                if confirm != "SUPPRIMER TOUT":
                    print("  Annulé.")
                    return

            project_ids = [p["id"] for p in projects]

        # ── Mode ids spécifiques ─────────────────────────────
        else:
            try:
                project_ids = [int(a) for a in args]
            except ValueError:
                _err(f"IDs invalides : {args}")
                sys.exit(1)

            if not dry_run and len(project_ids) > 1:
                _header(f"Suppression de {len(project_ids)} projets")
                confirm = input(f"  Confirmer la suppression des projets {project_ids} ? [o/N] ").strip().lower()
                if confirm not in ("o", "oui", "y", "yes"):
                    print("  Annulé.")
                    return

        # ── Exécution ────────────────────────────────────────
        mode_label = " [DRY-RUN]" if dry_run else ""
        _header(f"Suppression{mode_label} — {len(project_ids)} projet(s)")

        total_all = {}
        for pid in project_ids:
            row_stats = await delete_one_project(conn, pid, dry_run=dry_run)
            for k, v in row_stats.items():
                total_all[k] = total_all.get(k, 0) + v

        # ── Bilan global ─────────────────────────────────────
        if len(project_ids) > 1:
            _sep("═")
            print("  BILAN GLOBAL")
            _sep()
            for table, count in total_all.items():
                print(f"  {table:<35} {count:>6} ligne(s)")
            _sep()
            print(f"  {'TOTAL':<35} {sum(total_all.values()):>6} ligne(s)")
            _sep("═")

        if dry_run:
            print("\n  Mode DRY-RUN : aucune donnée supprimée.\n")
        else:
            print("\n  Suppression terminée.\n")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
