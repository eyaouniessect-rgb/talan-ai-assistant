# app/api/rh.py
# Endpoints RH — accessibles uniquement au rôle "rh"
import datetime
import secrets
import string
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.security import get_current_user, hash_password
from app.database.connection import get_db
from app.database.models.user import User
from app.database.models.hris import (
    Department, Team, Employee, Skill, EmployeeSkill,
    Leave, LeaveLog, LeaveStatusEnum,
    SeniorityEnum, SkillLevelEnum,
)
from app.database.models.crm import Assignment
from utils.email import send_credentials_email

router = APIRouter(prefix="/rh", tags=["RH"])
logger = logging.getLogger(__name__)


# ── Dépendance : rôle rh uniquement ──────────────────────
async def require_rh(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "rh":
        raise HTTPException(status_code=403, detail="Accès réservé au rôle RH")
    return current_user


def _generate_password(length: int = 12) -> str:
    chars = string.ascii_letters + string.digits + "!@#$"
    return "".join(secrets.choice(chars) for _ in range(length))


# ═══════════════════════════════════════════════════
# Schémas Pydantic
# ═══════════════════════════════════════════════════

class SkillInput(BaseModel):
    name: str
    level: str = "intermediate"  # beginner | intermediate | advanced | expert


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    role: str  # consultant | pm | rh
    # Profil employé
    team_id: int
    job_title: Optional[str] = None
    seniority: Optional[str] = None      # junior | mid | senior | lead | principal
    hire_date: Optional[str] = None      # ISO date YYYY-MM-DD, défaut = aujourd'hui
    skills: List[SkillInput] = []


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    role: str
    is_active: bool
    employee_id: Optional[int] = None
    created_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True


class TeamOut(BaseModel):
    id: int
    name: str
    department: str
    manager_name: Optional[str] = None

    class Config:
        from_attributes = True


class DepartmentOut(BaseModel):
    id: int
    name: str
    team_count: int

    class Config:
        from_attributes = True


class SkillOut(BaseModel):
    name: str
    level: str


class EmployeeOut(BaseModel):
    id: int
    user_id: int
    name: str
    email: str
    role: str
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    hire_date: Optional[str] = None
    leave_balance: int
    team: Optional[str] = None
    department: Optional[str] = None
    manager: Optional[str] = None
    skills: List[SkillOut] = []


# ═══════════════════════════════════════════════════
# POST /rh/users — Créer un compte utilisateur
# ═══════════════════════════════════════════════════

@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserRequest,
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in ("consultant", "pm", "rh"):
        raise HTTPException(status_code=400, detail="Rôle invalide (consultant | pm | rh)")

    # Vérifier que l'email n'existe pas déjà
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email déjà utilisé")

    # Vérifier que le team existe et récupérer son manager_id
    team_result = await db.execute(select(Team).where(Team.id == body.team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe introuvable")

    # ── Créer le compte User ─────────────────────────────
    password = _generate_password()
    user = User(
        name=body.name,
        email=body.email,
        password=hash_password(password),
        role=body.role,
        is_active=True,
    )
    db.add(user)
    await db.flush()  # génère user.id sans commit

    # ── Date d'embauche : aujourd'hui si non fournie ─────
    hire_date = (
        datetime.date.fromisoformat(body.hire_date)
        if body.hire_date
        else datetime.date.today()
    )

    # ── Seniority enum ───────────────────────────────────
    seniority = None
    if body.seniority and body.seniority in [e.value for e in SeniorityEnum]:
        seniority = SeniorityEnum(body.seniority)

    # ── Créer l'employé (manager = manager de l'équipe) ──
    employee = Employee(
        user_id=user.id,
        team_id=body.team_id,
        manager_id=team.manager_id,   # déduit de l'équipe
        job_title=body.job_title,
        seniority=seniority,
        hire_date=hire_date,
        leave_balance=22,
    )
    db.add(employee)
    await db.flush()  # génère employee.id

    # ── Créer les skills ─────────────────────────────────
    for skill_input in body.skills:
        skill_name = skill_input.name.strip()
        if not skill_name:
            continue
        skill_result = await db.execute(select(Skill).where(Skill.name == skill_name))
        skill = skill_result.scalar_one_or_none()
        if not skill:
            skill = Skill(name=skill_name)
            db.add(skill)
            await db.flush()

        level = (
            skill_input.level
            if skill_input.level in [e.value for e in SkillLevelEnum]
            else "intermediate"
        )
        db.add(EmployeeSkill(
            employee_id=employee.id,
            skill_id=skill.id,
            level=SkillLevelEnum(level),
        ))

    await db.commit()
    await db.refresh(user)

    try:
        send_credentials_email(to_email=body.email, name=body.name, password=password)
    except Exception as exc:
        logger.error(f"Erreur envoi email à {body.email}: {exc}")

    logger.info(f"Compte créé : {body.email} (rôle={body.role}, employé={employee.id}, équipe={body.team_id})")
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        employee_id=employee.id,
        created_at=user.created_at,
    )


# ═══════════════════════════════════════════════════
# GET /rh/users — Liste des utilisateurs
# ═══════════════════════════════════════════════════

@router.get("/users", response_model=List[UserOut])
async def list_users(
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).order_by(User.name))
    users = result.scalars().all()
    return [
        UserOut(
            id=u.id,
            name=u.name,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


# ═══════════════════════════════════════════════════
# GET /rh/departments — Liste des départements
# ═══════════════════════════════════════════════════

@router.get("/departments", response_model=List[DepartmentOut])
async def list_departments(
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Department).options(selectinload(Department.teams))
    )
    departments = result.scalars().all()
    return [
        DepartmentOut(
            id=d.id,
            name=d.name.value if hasattr(d.name, "value") else d.name,
            team_count=len(d.teams),
        )
        for d in departments
    ]


# ═══════════════════════════════════════════════════
# GET /rh/teams — Liste des équipes
# ═══════════════════════════════════════════════════

@router.get("/teams", response_model=List[TeamOut])
async def list_teams(
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Team)
        .options(
            selectinload(Team.department),
            selectinload(Team.manager).selectinload(Employee.user),
        )
    )
    teams = result.scalars().all()
    out = []
    for t in teams:
        dept_name = (
            t.department.name.value if hasattr(t.department.name, "value") else t.department.name
        ) if t.department else None
        manager_name = t.manager.user.name if t.manager and t.manager.user else None
        out.append(TeamOut(
            id=t.id,
            name=t.name,
            department=dept_name,
            manager_name=manager_name,
        ))
    return out


# ═══════════════════════════════════════════════════
# GET /rh/employees — Liste des employés avec skills
# ═══════════════════════════════════════════════════

@router.get("/employees", response_model=List[EmployeeOut])
async def list_employees(
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Employee)
        .options(
            selectinload(Employee.user),
            selectinload(Employee.team).selectinload(Team.department),
            selectinload(Employee.manager).selectinload(Employee.user),
            selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
        )
    )
    employees = result.scalars().all()
    out = []
    for e in employees:
        team_name = e.team.name if e.team else None
        dept_name = None
        if e.team and e.team.department:
            dept_name = (
                e.team.department.name.value
                if hasattr(e.team.department.name, "value")
                else e.team.department.name
            )
        manager_name = e.manager.user.name if e.manager and e.manager.user else None
        skills = [
            SkillOut(
                name=es.skill.name,
                level=es.level.value if hasattr(es.level, "value") else es.level,
            )
            for es in e.employee_skills
        ]
        out.append(EmployeeOut(
            id=e.id,
            user_id=e.user_id,
            name=e.user.name if e.user else "",
            email=e.user.email if e.user else "",
            role=e.user.role if e.user else "",
            job_title=e.job_title,
            seniority=e.seniority.value if e.seniority and hasattr(e.seniority, "value") else e.seniority,
            hire_date=str(e.hire_date) if e.hire_date else None,
            leave_balance=e.leave_balance or 0,
            team=team_name,
            department=dept_name,
            manager=manager_name,
            skills=skills,
        ))
    return out


# ═══════════════════════════════════════════════════
# GET /rh/skills — Liste des compétences existantes
# ═══════════════════════════════════════════════════

class SkillListOut(BaseModel):
    id: int
    name: str


@router.get("/skills", response_model=List[SkillListOut])
async def list_skills(
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Skill).order_by(Skill.name))
    skills = result.scalars().all()
    return [SkillListOut(id=s.id, name=s.name) for s in skills]


# ═══════════════════════════════════════════════════
# Schémas Congés
# ═══════════════════════════════════════════════════

class LeaveOut(BaseModel):
    id: int
    employee_id: int
    employee_name: str
    employee_email: str
    team: Optional[str]
    leave_type: str
    start_date: str
    end_date: str
    days_count: Optional[int]
    status: str
    justification_url: Optional[str]
    created_at: Optional[str]


class RejectBody(BaseModel):
    reason: Optional[str] = None


# ═══════════════════════════════════════════════════
# GET /rh/leaves — Toutes les demandes de congé
# ═══════════════════════════════════════════════════

@router.get("/leaves", response_model=List[LeaveOut])
async def list_leaves(
    status: Optional[str] = None,
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Leave)
        .options(
            selectinload(Leave.employee).selectinload(Employee.user),
            selectinload(Leave.employee).selectinload(Employee.team),
        )
        .order_by(Leave.created_at.desc())
    )
    if status:
        query = query.where(Leave.status == status)

    result = await db.execute(query)
    leaves = result.scalars().all()

    out = []
    for lv in leaves:
        emp = lv.employee
        out.append(LeaveOut(
            id=lv.id,
            employee_id=lv.employee_id,
            employee_name=emp.user.name if emp and emp.user else "—",
            employee_email=emp.user.email if emp and emp.user else "—",
            team=emp.team.name if emp and emp.team else None,
            leave_type=lv.leave_type.value if hasattr(lv.leave_type, "value") else lv.leave_type,
            start_date=str(lv.start_date),
            end_date=str(lv.end_date),
            days_count=lv.days_count,
            status=lv.status.value if hasattr(lv.status, "value") else lv.status,
            justification_url=lv.justification_url,
            created_at=str(lv.created_at) if lv.created_at else None,
        ))
    return out


# ═══════════════════════════════════════════════════
# POST /rh/leaves/{id}/approve
# ═══════════════════════════════════════════════════

@router.post("/leaves/{leave_id}/approve")
async def approve_leave(
    leave_id: int,
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Leave).where(Leave.id == leave_id))
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Congé introuvable")
    if leave.status != LeaveStatusEnum.PENDING:
        raise HTTPException(status_code=400, detail="Ce congé n'est pas en attente")

    leave.status = LeaveStatusEnum.APPROVED
    db.add(LeaveLog(
        employee_id=leave.employee_id,
        leave_id=leave.id,
        action="approved",
        description=f"Congé approuvé par le responsable RH",
    ))
    await db.commit()
    return {"success": True, "status": "approved"}


# ═══════════════════════════════════════════════════
# POST /rh/leaves/{id}/reject
# ═══════════════════════════════════════════════════

@router.post("/leaves/{leave_id}/reject")
async def reject_leave(
    leave_id: int,
    body: RejectBody,
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Leave).where(Leave.id == leave_id))
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Congé introuvable")
    if leave.status != LeaveStatusEnum.PENDING:
        raise HTTPException(status_code=400, detail="Ce congé n'est pas en attente")

    leave.status = LeaveStatusEnum.REJECTED
    reason = body.reason or "Aucune raison précisée"
    db.add(LeaveLog(
        employee_id=leave.employee_id,
        leave_id=leave.id,
        action="rejected",
        description=f"Congé rejeté : {reason}",
    ))
    await db.commit()
    return {"success": True, "status": "rejected"}
