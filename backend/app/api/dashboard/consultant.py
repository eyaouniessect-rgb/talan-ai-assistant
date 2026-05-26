# app/api/dashboard/consultant.py
# ═══════════════════════════════════════════════════════════════
# Dashboard Consultant — endpoints réservés au rôle "consultant".
#
# GET /dashboard/consultant
#   - Liste des projets où le consultant a au moins une story affectée
#     dans un sprint ACTIF.
#   - Pour chaque projet : compteurs to_do / in_progress / done (sprint actif),
#     dates sprint, jours restants, allocation SP et pourcentage d'allocation.
# ═══════════════════════════════════════════════════════════════

from collections import Counter, defaultdict
from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user
from app.database.connection import get_db
from app.database.models.crm.project              import Project
from app.database.models.pm.sprint                import Sprint
from app.database.models.pm.staffing_assignment   import StaffingAssignment
from app.database.models.pm.user_story            import UserStory
from agents.pm.db import get_employee_id_by_user

# Statuts autorisés pour progress_status (aligné avec le modèle).
_ALLOWED_PROGRESS_STATUSES = {"to_do", "in_progress", "done"}

# Rang énorme = stories pas encore prioritisées (les pousse en fin de tri).
_UNRANKED = 10**9

router = APIRouter(prefix="/dashboard/consultant", tags=["Dashboard Consultant"])

# Capacité SP par niveau de séniorité (aligné avec matching/selection.py)
_CAPACITY_BY_SENIORITY: dict[str, int] = {
    "JUNIOR": 6,
    "MID":    8,
    "SENIOR": 10,
}


async def _require_consultant(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "consultant":
        raise HTTPException(403, "Accès réservé aux consultants.")
    return current_user


@router.get("")
async def get_consultant_dashboard(
    current_user: dict         = Depends(_require_consultant),
    db:           AsyncSession = Depends(get_db),
):
    """
    Dashboard du consultant connecté.

    Retourne :
      {
        "projects": [
          {
            "id", "name", "client_name", "project_status",
            "current_sprint_number",
            "sprint": {
              "start_date",        # actual_start_date si dispo, sinon start_date planifié
              "end_date",          # end_date planifié
              "days_remaining",    # >0 = dans les temps, <0 = en débordement
              "is_overdue"         # bool
            },
            "allocation": {
              "allocated_sp",      # SP consommés par le consultant sur ce sprint
              "capacity_sp",       # capacité totale selon séniorité (JUNIOR=6, MID=8, SENIOR=10)
              "allocation_pct"     # allocated_sp / capacity_sp * 100 (arrondi)
            },
            "tickets": {
              "to_do", "in_progress", "done", "total"
            }
          }, ...
        ]
      }
    """
    employee_id = await get_employee_id_by_user(current_user["user_id"])
    if not employee_id:
        return {"projects": []}

    # ── 1. Toutes les staffing_assignments du consultant (tous sprints) ──
    all_asgn = (await db.execute(
        select(StaffingAssignment)
        .where(StaffingAssignment.employee_id == employee_id)
    )).scalars().all()

    if not all_asgn:
        return {"projects": []}

    # ── 2. Sprints actifs des projets concernés — objets complets ────────
    project_ids_all = {a.project_id for a in all_asgn}
    active_sprints = (await db.execute(
        select(Sprint)
        .where(
            Sprint.project_id.in_(project_ids_all),
            Sprint.status == "active",
        )
    )).scalars().all()

    active_sprint_by_proj: dict[int, Sprint] = {
        s.project_id: s for s in active_sprints
    }

    # On ne garde que les projets où le consultant a une story dans le sprint actif
    asgn_keys = {(a.project_id, a.sprint_number) for a in all_asgn}
    visible_project_ids = {
        pid for pid, sprint in active_sprint_by_proj.items()
        if (pid, sprint.sprint_number) in asgn_keys
    }

    if not visible_project_ids:
        return {"projects": []}

    # ── 3. Charger les Project (nom + client) ─────────────────────────
    projects = (await db.execute(
        select(Project)
        .where(Project.id.in_(visible_project_ids))
        .options(selectinload(Project.client))
        .order_by(Project.name)
    )).scalars().all()

    # ── 4. Filtrer les assignments du sprint actif + collecter story_ids ──
    active_asgn: list[StaffingAssignment] = []
    for a in all_asgn:
        if a.project_id not in visible_project_ids:
            continue
        active_sprint = active_sprint_by_proj.get(a.project_id)
        if not active_sprint or a.sprint_number != active_sprint.sprint_number:
            continue
        active_asgn.append(a)

    # ── 5. Charger les UserStory (rank, priority_score, is_critical, jira_key) ──
    story_ids = {a.story_id for a in active_asgn if a.story_id}
    story_map: dict[int, UserStory] = {}
    if story_ids:
        story_rows = (await db.execute(
            select(UserStory).where(UserStory.id.in_(story_ids))
        )).scalars().all()
        story_map = {s.id: s for s in story_rows}

    # ── 6. Agréger compteurs + allocation + liste stories par projet ──
    counters_by_proj:  dict[int, Counter] = defaultdict(Counter)
    allocated_by_proj: dict[int, float]   = defaultdict(float)
    seniority_by_proj: dict[int, str]     = {}
    stories_by_proj:   dict[int, list]    = defaultdict(list)

    for a in active_asgn:
        counters_by_proj[a.project_id][a.progress_status or "to_do"] += 1
        allocated_by_proj[a.project_id] += a.allocated_sp or 0.0
        if a.project_id not in seniority_by_proj and a.employee_seniority:
            seniority_by_proj[a.project_id] = a.employee_seniority

        us = story_map.get(a.story_id) if a.story_id else None
        stories_by_proj[a.project_id].append({
            "assignment_id":    a.id,
            "story_id":         a.story_id,
            "title":            a.story_title or (us.title if us else "—"),
            "story_points":     a.story_points or (us.story_points if us else 0),
            "allocated_sp":     round(a.allocated_sp or 0.0, 2),
            "progress_status":  a.progress_status or "to_do",
            "rank":             us.rank if (us and us.rank is not None) else None,
            "priority_score":   round(us.priority_score, 2) if (us and us.priority_score is not None) else None,
            "is_critical":      bool(us.is_critical) if us else False,
            "jira_issue_key":   us.jira_issue_key if us else None,
            "required_profile": a.required_profile,
            "required_level":   a.required_level,
            "match_level":      a.match_level,
        })

    # Tri par rank ASC (les non-rankées en fin), puis story_id + profil pour stabilité.
    for pid in stories_by_proj:
        stories_by_proj[pid].sort(
            key=lambda s: (
                s["rank"] if s["rank"] is not None else _UNRANKED,
                s["story_id"] or 0,
                s["required_profile"] or "",
            )
        )

    # ── 7. Construire la réponse ──────────────────────────────────────
    today = date.today()
    out = []
    for p in projects:
        sprint = active_sprint_by_proj[p.id]
        c      = counters_by_proj.get(p.id, Counter())

        to_do       = c.get("to_do", 0)
        in_progress = c.get("in_progress", 0)
        done        = c.get("done", 0)
        total       = to_do + in_progress + done

        # Dates sprint
        sprint_start   = sprint.actual_start_date or sprint.start_date
        sprint_end     = sprint.end_date
        days_remaining = (sprint_end - today).days   # négatif si débordement
        is_overdue     = days_remaining < 0

        # Allocation SP
        seniority    = seniority_by_proj.get(p.id, "MID")
        capacity_sp  = _CAPACITY_BY_SENIORITY.get(seniority, 8)
        allocated_sp = round(allocated_by_proj.get(p.id, 0.0), 2)
        allocation_pct = round(allocated_sp / capacity_sp * 100) if capacity_sp else 0

        out.append({
            "id":                    p.id,
            "name":                  p.name,
            "client_name":           p.client.name if p.client else "—",
            "project_status":        p.status,
            "current_sprint_number": sprint.sprint_number,
            "sprint": {
                "start_date":     sprint_start.isoformat() if sprint_start else None,
                "end_date":       sprint_end.isoformat()   if sprint_end   else None,
                "days_remaining": days_remaining,
                "is_overdue":     is_overdue,
            },
            "allocation": {
                "allocated_sp":   allocated_sp,
                "capacity_sp":    capacity_sp,
                "allocation_pct": allocation_pct,
                "seniority":      seniority,
            },
            "tickets": {
                "to_do":       to_do,
                "in_progress": in_progress,
                "done":        done,
                "total":       total,
            },
            "stories": stories_by_proj.get(p.id, []),
        })

    return {"projects": out}


# ══════════════════════════════════════════════════════════════════
# GET /dashboard/consultant/tickets
# Liste TOUS les tickets du consultant, groupés par projet → sprint.
# Différent de GET /dashboard/consultant qui ne renvoie que le sprint
# actif. Utilisé par la page "Mes tickets" (sidebar).
# ══════════════════════════════════════════════════════════════════

@router.get("/tickets")
async def get_consultant_tickets(
    current_user: dict         = Depends(_require_consultant),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne tous les tickets du consultant, structurés en arborescence
    projet → sprint → tickets.

    Réponse :
      {
        "projects": [
          {
            "id", "name", "client_name",
            "sprints": [
              {
                "sprint_number", "name", "status",
                "start_date", "end_date",
                "is_active",   # status == "active"
                "tickets": [
                  {
                    "story_id", "title", "story_points",
                    "allocated_sp", "progress_status",
                    "rank", "is_critical", "jira_issue_key"
                  }, ...
                ]
              }, ...
            ]
          }, ...
        ]
      }
    """
    employee_id = await get_employee_id_by_user(current_user["user_id"])
    if not employee_id:
        return {"projects": []}

    # 1. Toutes les staffing_assignments du consultant
    all_asgn = (await db.execute(
        select(StaffingAssignment)
        .where(StaffingAssignment.employee_id == employee_id)
    )).scalars().all()
    if not all_asgn:
        return {"projects": []}

    # 2. Sprints des projets concernés (tous statuts)
    project_ids = {a.project_id for a in all_asgn}
    sprints = (await db.execute(
        select(Sprint)
        .where(Sprint.project_id.in_(project_ids))
        .order_by(Sprint.project_id, Sprint.sprint_number)
    )).scalars().all()
    sprint_by_key: dict[tuple[int, int], Sprint] = {
        (s.project_id, s.sprint_number): s for s in sprints
    }

    # 3. UserStory (rank, jira_key, is_critical)
    story_ids = {a.story_id for a in all_asgn if a.story_id}
    story_map: dict[int, UserStory] = {}
    if story_ids:
        rows = (await db.execute(
            select(UserStory).where(UserStory.id.in_(story_ids))
        )).scalars().all()
        story_map = {s.id: s for s in rows}

    # 4. Projects (nom + client)
    projects = (await db.execute(
        select(Project)
        .where(Project.id.in_(project_ids))
        .options(selectinload(Project.client))
        .order_by(Project.name)
    )).scalars().all()

    # 5. Regrouper assignments en projet → sprint → tickets
    # IMPORTANT : un ticket = une StaffingAssignment (pas une UserStory).
    # Si la même story est splittée en 2 profils (frontend + backend), on aura
    # 2 lignes distinctes avec des assignment_id différents — chacune avec son
    # propre progress_status, son profil et son allocation.
    tickets_by_proj_sprint: dict[tuple[int, int], list] = defaultdict(list)
    for a in all_asgn:
        us = story_map.get(a.story_id) if a.story_id else None
        tickets_by_proj_sprint[(a.project_id, a.sprint_number)].append({
            "assignment_id":    a.id,
            "story_id":         a.story_id,
            "title":            a.story_title or (us.title if us else "—"),
            "story_points":     a.story_points or (us.story_points if us else 0),
            "allocated_sp":     round(a.allocated_sp or 0.0, 2),
            "progress_status":  a.progress_status or "to_do",
            "rank":             us.rank if (us and us.rank is not None) else None,
            "is_critical":      bool(us.is_critical) if us else False,
            "jira_issue_key":   us.jira_issue_key if us else None,
            "required_profile": a.required_profile,
            "required_level":   a.required_level,
        })

    # Tri tickets par rank ASC (rank 1 = plus prioritaire), puis profil pour stabilité
    for key in tickets_by_proj_sprint:
        tickets_by_proj_sprint[key].sort(
            key=lambda t: (
                t["rank"] if t["rank"] is not None else _UNRANKED,
                t["story_id"] or 0,
                t["required_profile"] or "",
            )
        )

    # 6. Construire la réponse
    out = []
    for p in projects:
        # Sprints où le consultant a au moins un ticket
        proj_sprints = []
        for s in sprints:
            if s.project_id != p.id:
                continue
            tickets = tickets_by_proj_sprint.get((p.id, s.sprint_number), [])
            if not tickets:
                continue
            proj_sprints.append({
                "sprint_number": s.sprint_number,
                "name":          s.name,
                "status":        s.status,
                "is_active":     s.status == "active",
                "start_date":    (s.actual_start_date or s.start_date).isoformat() if (s.actual_start_date or s.start_date) else None,
                "end_date":      s.end_date.isoformat() if s.end_date else None,
                "tickets":       tickets,
            })
        if not proj_sprints:
            continue
        out.append({
            "id":          p.id,
            "name":        p.name,
            "client_name": p.client.name if p.client else "—",
            "sprints":     proj_sprints,
        })

    return {"projects": out}


# ══════════════════════════════════════════════════════════════════
# PATCH /dashboard/consultant/tickets/{assignment_id}
# Met à jour le progress_status d'UNE seule StaffingAssignment.
# Sécurité : on vérifie que l'assignment appartient bien au consultant
# connecté (un consultant ne peut pas modifier celle d'un autre).
#
# Pourquoi assignment_id et non story_id ?
#   Une UserStory peut être splittée en plusieurs assignments (ex :
#   frontend + backend) éventuellement sur le même consultant ou sur
#   deux consultants différents. Filtrer par story_id mettrait à jour
#   les deux d'un coup → incorrect. assignment_id est l'unité de
#   progression réelle.
# ══════════════════════════════════════════════════════════════════

@router.patch("/tickets/{assignment_id}")
async def update_consultant_ticket_status(
    assignment_id: int          = Path(..., gt=0),
    payload:       dict         = Body(...),
    current_user:  dict         = Depends(_require_consultant),
    db:            AsyncSession = Depends(get_db),
):
    """
    Body : { "progress_status": "to_do" | "in_progress" | "done" }
    """
    new_status = (payload.get("progress_status") or "").strip()
    if new_status not in _ALLOWED_PROGRESS_STATUSES:
        raise HTTPException(
            400,
            f"progress_status invalide : '{new_status}'. "
            f"Valeurs autorisées : {sorted(_ALLOWED_PROGRESS_STATUSES)}",
        )

    employee_id = await get_employee_id_by_user(current_user["user_id"])
    if not employee_id:
        raise HTTPException(403, "Aucun employé associé à cet utilisateur.")

    asgn = (await db.execute(
        select(StaffingAssignment).where(
            StaffingAssignment.id          == assignment_id,
            StaffingAssignment.employee_id == employee_id,
        )
    )).scalar_one_or_none()

    if not asgn:
        raise HTTPException(404, "Ticket introuvable ou non assigné à ce consultant.")

    # ── Contrainte : le sprint parent doit être ACTIVE ─────────────
    sprint = (await db.execute(
        select(Sprint).where(
            Sprint.project_id    == asgn.project_id,
            Sprint.sprint_number == asgn.sprint_number,
        )
    )).scalar_one_or_none()

    if not sprint:
        raise HTTPException(404, "Sprint introuvable pour ce ticket.")
    if sprint.status != "active":
        label = {"planned": "n'est pas encore démarré", "completed": "est déjà clôturé"}.get(
            sprint.status, f"a le statut '{sprint.status}'"
        )
        raise HTTPException(
            409,
            f"Impossible de modifier ce ticket : le sprint {label}. "
            f"Le statut ne peut être modifié que pendant un sprint actif.",
        )

    asgn.progress_status = new_status
    await db.commit()

    return {
        "assignment_id":   asgn.id,
        "story_id":        asgn.story_id,
        "progress_status": new_status,
    }
