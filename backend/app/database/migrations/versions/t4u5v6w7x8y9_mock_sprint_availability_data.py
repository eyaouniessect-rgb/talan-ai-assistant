"""mock_sprint_availability_data

Revision ID: t4u5v6w7x8y9
Revises: s3t4u5v6w7x8
Create Date: 2026-05-09

Données de test pour la phase Staffing — projet "Eya Project Management" (id=12).

  1. Met à jour les dates du projet id=12 :
       start_date = 2026-06-01, end_date = 2026-08-28
     -> 65 jours ouvrables -> 6 sprints de 10 jours ouvrables chacun.

  2. Crée un "Projet Bloquant Mock" (id distinct) pour porter
     les affectations qui bloqueront certains candidats.

  3. Insère des crm.assignments et hris.leaves sur des employés
     dont le job_title est parmi :
       Backend Developer | ML Engineer | Frontend Developer | Full Stack Developer

Scénario de disponibilité :
  Sprint 1  (2026-06-01 -> 2026-06-12) :
    [X] Backend Dev #2 (affectation autre projet)
    [X] Frontend Dev #2 (congé annuel approuvé)
    [X] ML Engineer #2 (affectation autre projet sprint 1+2)
    [V] tous les autres

  Sprint 2  (2026-06-15 -> 2026-06-26) :
    [X] Backend Dev #3 (congé annuel approuvé)
    [X] ML Engineer #2 (affectation autre projet sprint 1+2)
    [V] Backend Dev #2 libéré, Frontend Dev #2 libérée, tous les autres

  Sprint 3+ (2026-06-29 -> …) :
    [X] Full Stack Dev #2 (affectation open-ended)
    [V] tous les autres libérés
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision:      str                             = 't4u5v6w7x8y9'
down_revision: Union[str, None]                = 's3t4u5v6w7x8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on:    Union[str, Sequence[str], None] = None

TARGET_PROJECT_ID   = 12
PROJECT_START       = "2026-06-01"
PROJECT_END         = "2026-08-28"

SPRINT_1_START, SPRINT_1_END = "2026-06-01", "2026-06-12"
SPRINT_2_START, SPRINT_2_END = "2026-06-15", "2026-06-26"
SPRINT_3_START               = "2026-06-29"

BLOCKER_PROJECT_NAME = "Projet Bloquant Mock (Staffing Test)"


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Mettre à jour les dates du projet cible ────────────
    conn.execute(sa.text("""
        UPDATE crm.projects
        SET start_date = CAST(:start AS date),
            end_date   = CAST(:end AS date)
        WHERE id = :pid
    """), {"start": PROJECT_START, "end": PROJECT_END, "pid": TARGET_PROJECT_ID})
    print(f"[mock] Projet {TARGET_PROJECT_ID} : dates mises à jour {PROJECT_START} -> {PROJECT_END}")

    # ── 2. Créer le projet bloquant (porteur des conflits) ────
    existing_blocker = conn.execute(sa.text(
        "SELECT id FROM crm.projects WHERE name = :name LIMIT 1"
    ), {"name": BLOCKER_PROJECT_NAME}).scalar()

    if not existing_blocker:
        # Récupérer le client_id du projet cible pour la FK
        client_id = conn.execute(sa.text(
            "SELECT client_id FROM crm.projects WHERE id = :pid"
        ), {"pid": TARGET_PROJECT_ID}).scalar()

        if not client_id:
            print("[mock] [WARN]  Projet cible introuvable ou sans client — migration annulée.")
            return

        conn.execute(sa.text("""
            INSERT INTO crm.projects (name, client_id, status, start_date, end_date)
            VALUES (:name, :cid, 'in_progress', '2026-01-01', '2026-12-31')
        """), {"name": BLOCKER_PROJECT_NAME, "cid": client_id})
        print(f"[mock] Projet bloquant créé : '{BLOCKER_PROJECT_NAME}'")

    blocker_id = conn.execute(sa.text(
        "SELECT id FROM crm.projects WHERE name = :name LIMIT 1"
    ), {"name": BLOCKER_PROJECT_NAME}).scalar()

    # ── 3. Récupérer les employés par job_title (ORDER BY id) ─
    def get_employees(job_title: str, limit: int = 4) -> list[int]:
        rows = conn.execute(sa.text("""
            SELECT id FROM hris.employees
            WHERE job_title = :jt
            ORDER BY id
            LIMIT :lim
        """), {"jt": job_title, "lim": limit}).fetchall()
        ids = [r[0] for r in rows]
        print(f"[mock]   {job_title} ({len(ids)}) : {ids}")
        return ids

    backend_devs   = get_employees("Backend Developer",    4)
    ml_engineers   = get_employees("ML Engineer",          3)
    frontend_devs  = get_employees("Frontend Developer",   3)
    fullstack_devs = get_employees("Full Stack Developer", 3)

    # ── 4. Helpers ────────────────────────────────────────────
    def add_assignment(emp_id: int, start: str, end: str | None, role: str) -> None:
        conn.execute(sa.text("""
            INSERT INTO crm.assignments
                (project_id, employee_id, role_in_project, start_date, end_date)
            VALUES (:pid, :eid, :role, CAST(:start AS date), CAST(:end AS date))
        """), {"pid": blocker_id, "eid": emp_id, "role": role, "start": start, "end": end})
        label = f"{start} -> {end or 'inf (open-ended)'}"
        print(f"[mock]   assignment emp#{emp_id} ({role}) : {label}")

    def add_leave(emp_id: int, start: str, end: str, days: int) -> None:
        conn.execute(sa.text("""
            INSERT INTO hris.leaves
                (employee_id, leave_type, start_date, end_date, status, days_count)
            VALUES (:eid, 'annual', CAST(:start AS date), CAST(:end AS date), 'approved', :days)
        """), {"eid": emp_id, "start": start, "end": end, "days": days})
        print(f"[mock]   congé     emp#{emp_id} : {start} -> {end}")

    # ── 5. Backend Developers ─────────────────────────────────
    # #1 -> toujours disponible (aucun conflit)
    # #2 -> bloqué Sprint 1 par affectation
    # #3 -> bloqué Sprint 2 par congé
    # #4 -> toujours disponible
    if len(backend_devs) >= 2:
        add_assignment(backend_devs[1], SPRINT_1_START, SPRINT_1_END, "Backend Developer")
    if len(backend_devs) >= 3:
        add_leave(backend_devs[2], SPRINT_2_START, SPRINT_2_END, days=10)

    # ── 6. ML Engineers ───────────────────────────────────────
    # #1 -> toujours disponible
    # #2 -> bloqué Sprints 1+2 par affectation
    # #3 -> toujours disponible
    if len(ml_engineers) >= 2:
        add_assignment(ml_engineers[1], SPRINT_1_START, SPRINT_2_END, "ML Engineer")

    # ── 7. Frontend Developers ────────────────────────────────
    # #1 -> toujours disponible
    # #2 -> bloqué Sprint 1 par congé
    # #3 -> toujours disponible
    if len(frontend_devs) >= 2:
        add_leave(frontend_devs[1], SPRINT_1_START, SPRINT_1_END, days=10)

    # ── 8. Full Stack Developers ──────────────────────────────
    # #1 -> toujours disponible
    # #2 -> bloqué Sprint 3+ (affectation open-ended, end_date = NULL)
    # #3 -> toujours disponible
    if len(fullstack_devs) >= 2:
        add_assignment(fullstack_devs[1], SPRINT_3_START, None, "Full Stack Developer")

    print("\n[mock] [OK] Données de test sprint/disponibilité insérées avec succès.")
    print(f"[mock]    Sprint 1 ({SPRINT_1_START} -> {SPRINT_1_END}) : certains bloqués")
    print(f"[mock]    Sprint 2 ({SPRINT_2_START} -> {SPRINT_2_END}) : certains bloqués")
    print(f"[mock]    Sprint 3+ ({SPRINT_3_START} -> …)             : Full Stack #2 bloqué")


def downgrade() -> None:
    conn = op.get_bind()

    # Supprimer les assignments du projet bloquant
    blocker_id = conn.execute(sa.text(
        "SELECT id FROM crm.projects WHERE name = :name LIMIT 1"
    ), {"name": BLOCKER_PROJECT_NAME}).scalar()

    if blocker_id:
        conn.execute(sa.text(
            "DELETE FROM crm.assignments WHERE project_id = :pid"
        ), {"pid": blocker_id})
        conn.execute(sa.text(
            "DELETE FROM crm.projects WHERE id = :pid"
        ), {"pid": blocker_id})
        print(f"[mock] Projet bloquant supprimé (id={blocker_id})")

    # Supprimer les congés créés dans la fenêtre sprint 1-2 2026
    conn.execute(sa.text("""
        DELETE FROM hris.leaves
        WHERE leave_type = 'annual'
          AND status     = 'approved'
          AND start_date >= '2026-06-01'
          AND end_date   <= '2026-06-30'
    """))

    # Remettre les dates du projet cible à NULL
    conn.execute(sa.text("""
        UPDATE crm.projects
        SET start_date = NULL,
            end_date   = NULL
        WHERE id = :pid
    """), {"pid": TARGET_PROJECT_ID})

    print("[mock] [OK] Données mock supprimées, dates projet réinitialisées.")
