# api/rh/rh.py
# Schéma : hris + public
#
# Endpoints RH — accessibles uniquement au rôle "rh".
# Gestion des utilisateurs, employés, départements, équipes, congés, compétences.
# POST   /rh/users                          → créer un compte utilisateur + profil employé
# GET    /rh/users                          → liste des utilisateurs
# PATCH  /rh/users/{id}/toggle-active       → activer/désactiver un compte
# GET    /rh/departments                    → liste des départements avec HEAD
# GET    /rh/director                       → directeur général (PRINCIPAL)
# GET    /rh/teams                          → liste des équipes
# GET    /rh/employees                      → liste des employés (filtrable)
# GET    /rh/employees/{id}                 → fiche d'un employé
# PATCH  /rh/employees/{id}                 → modifier un employé
# POST   /rh/employees/{id}/contact         → envoyer un email à un employé
# GET    /rh/skills                         → liste des compétences
# GET    /rh/leaves                         → toutes les demandes de congé
# POST   /rh/leaves/{id}/approve            → approuver un congé
# POST   /rh/leaves/{id}/reject             → rejeter un congé

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
from app.database.models.public.user import User
from app.database.models.hris import (
    Department, Team, Employee, Skill, EmployeeSkill,
    Leave, LeaveLog, LeaveStatusEnum,
    SeniorityEnum, SkillLevelEnum,
)
from app.database.models.crm import Assignment
from utils.email import send_credentials_email, send_generic_email

router = APIRouter(prefix="/rh", tags=["RH"])
logger = logging.getLogger(__name__)


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
    level: str = "intermediate"


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    role: str
    team_id: int
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    hire_date: Optional[str] = None
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
    manager_employee_id: Optional[int] = None

    class Config:
        from_attributes = True


class DepartmentOut(BaseModel):
    id: int
    name: str
    team_count: int
    head_name: Optional[str] = None
    head_job_title: Optional[str] = None
    head_employee_id: Optional[int] = None

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
    is_active: bool = True
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    phone: Optional[str] = None
    hire_date: Optional[str] = None
    leave_balance: int
    team: Optional[str] = None
    department: Optional[str] = None
    manager: Optional[str] = None
    manager_employee_id: Optional[int] = None
    manager_email: Optional[str] = None
    manager_phone: Optional[str] = None
    manager_job_title: Optional[str] = None
    manager_seniority: Optional[str] = None
    skills: List[SkillOut] = []


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


class UpdateEmployeeRequest(BaseModel):
    job_title:  Optional[str] = None
    seniority:  Optional[str] = None
    team_id:    Optional[int] = None
    manager_id: Optional[int] = None


class ContactEmailRequest(BaseModel):
    subject:   str
    body:      str
    cc_emails: List[str] = []


class SkillListOut(BaseModel):
    id: int
    name: str


# ═══════════════════════════════════════════════════
# POST /rh/users
# ═══════════════════════════════════════════════════

@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserRequest,
    _rh: dict = Depends(require_rh),
    db: AsyncSession = Depends(get_db),
):
    if body.role not in ("consultant", "pm", "rh"):
        raise HTTPException(status_code=400, detail="Rôle invalide (consultant | pm | rh)")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email déjà utilisé")

    team_result = await db.execute(select(Team).where(Team.id == body.team_id))
    team = team_result.scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe introuvable")

    password = _generate_password()
    user = User(name=body.name, email=body.email, password=hash_password(password), role=body.role, is_active=True)
    db.add(user)
    await db.flush()

    hire_date = datetime.date.fromisoformat(body.hire_date) if body.hire_date else datetime.date.today()
    seniority = SeniorityEnum(body.seniority) if body.seniority and body.seniority in [e.value for e in SeniorityEnum] else None

    employee = Employee(
        user_id=user.id, team_id=body.team_id, manager_id=team.manager_id,
        job_title=body.job_title, seniority=seniority, hire_date=hire_date, leave_balance=22,
    )
    db.add(employee)
    await db.flush()

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
        level = skill_input.level if skill_input.level in [e.value for e in SkillLevelEnum] else "intermediate"
        db.add(EmployeeSkill(employee_id=employee.id, skill_id=skill.id, level=SkillLevelEnum(level)))

    await db.commit()
    await db.refresh(user)

    try:
        send_credentials_email(to_email=body.email, name=body.name, password=password)
    except Exception as exc:
        logger.error(f"Erreur envoi email à {body.email}: {exc}")

    return UserOut(id=user.id, name=user.name, email=user.email, role=user.role, is_active=user.is_active, employee_id=employee.id, created_at=user.created_at)


# ═══════════════════════════════════════════════════
# GET /rh/users
# ═══════════════════════════════════════════════════

@router.get("/users", response_model=List[UserOut])
async def list_users(_rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.name))
    return [UserOut(id=u.id, name=u.name, email=u.email, role=u.role, is_active=u.is_active, created_at=u.created_at) for u in result.scalars().all()]


# ═══════════════════════════════════════════════════
# GET /rh/departments
# ═══════════════════════════════════════════════════

@router.get("/departments", response_model=List[DepartmentOut])
async def list_departments(_rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Department).options(selectinload(Department.teams)))
    departments = result.scalars().all()

    heads_result = await db.execute(
        select(Employee, Team.department_id)
        .join(Team, Employee.team_id == Team.id)
        .where(Employee.seniority == SeniorityEnum.HEAD)
        .options(selectinload(Employee.user))
    )
    head_by_dept: dict[int, Employee] = {}
    for h, dept_id in heads_result.all():
        if dept_id not in head_by_dept:
            head_by_dept[dept_id] = h

    return [
        DepartmentOut(
            id=d.id,
            name=d.name.value if hasattr(d.name, "value") else d.name,
            team_count=len(d.teams),
            head_name=head_by_dept.get(d.id) and head_by_dept[d.id].user.name,
            head_job_title=head_by_dept.get(d.id) and head_by_dept[d.id].job_title,
            head_employee_id=head_by_dept.get(d.id) and head_by_dept[d.id].id,
        )
        for d in departments
    ]


# ═══════════════════════════════════════════════════
# GET /rh/director
# ═══════════════════════════════════════════════════

@router.get("/director", response_model=EmployeeOut)
async def get_director(_rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee)
        .where(Employee.seniority == SeniorityEnum.PRINCIPAL)
        .options(
            selectinload(Employee.user),
            selectinload(Employee.team).selectinload(Team.department),
            selectinload(Employee.manager).selectinload(Employee.user),
            selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
        )
        .limit(1)
    )
    e = result.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Directeur introuvable")

    skills = [SkillOut(name=es.skill.name, level=es.level.value if hasattr(es.level, "value") else es.level) for es in e.employee_skills]
    return EmployeeOut(
        id=e.id, user_id=e.user_id,
        name=e.user.name if e.user else "", email=e.user.email if e.user else "", role=e.user.role if e.user else "",
        is_active=e.user.is_active if e.user else True,
        job_title=e.job_title, seniority=e.seniority.value if e.seniority and hasattr(e.seniority, "value") else e.seniority,
        phone=e.phone, hire_date=str(e.hire_date) if e.hire_date else None, leave_balance=e.leave_balance or 0,
        team=e.team.name if e.team else None, department=None, manager=None,
        manager_employee_id=None, manager_email=None, manager_phone=None, manager_job_title=None, manager_seniority=None,
        skills=skills,
    )


# ═══════════════════════════════════════════════════
# GET /rh/teams
# ═══════════════════════════════════════════════════

@router.get("/teams", response_model=List[TeamOut])
async def list_teams(_rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Team).options(selectinload(Team.department), selectinload(Team.manager).selectinload(Employee.user))
    )
    out = []
    for t in result.scalars().all():
        dept_name = (t.department.name.value if hasattr(t.department.name, "value") else t.department.name) if t.department else None
        out.append(TeamOut(id=t.id, name=t.name, department=dept_name, manager_name=t.manager.user.name if t.manager and t.manager.user else None, manager_employee_id=t.manager.id if t.manager else None))
    return out


# ═══════════════════════════════════════════════════
# GET /rh/employees
# ═══════════════════════════════════════════════════

@router.get("/employees", response_model=List[EmployeeOut])
async def list_employees(
    department: Optional[str] = None, team: Optional[str] = None,
    seniority: Optional[str] = None, exclude_management: bool = False,
    _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db),
):
    query = select(Employee).options(
        selectinload(Employee.user),
        selectinload(Employee.team).selectinload(Team.department),
        selectinload(Employee.manager).selectinload(Employee.user),
        selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
    )
    if team:
        query = query.join(Employee.team).where(Team.name == team)
    elif department:
        query = query.join(Employee.team).join(Team.department).where(Department.name == department)
    if seniority:
        query = query.where(Employee.seniority == seniority)
    elif exclude_management:
        query = query.where(Employee.seniority.notin_([SeniorityEnum.HEAD, SeniorityEnum.PRINCIPAL]))

    result = await db.execute(query)
    out = []
    for e in result.scalars().all():
        team_name = e.team.name if e.team else None
        dept_name = (e.team.department.name.value if hasattr(e.team.department.name, "value") else e.team.department.name) if e.team and e.team.department else None
        out.append(EmployeeOut(
            id=e.id, user_id=e.user_id,
            name=e.user.name if e.user else "", email=e.user.email if e.user else "", role=e.user.role if e.user else "",
            is_active=e.user.is_active if e.user else True,
            job_title=e.job_title, seniority=e.seniority.value if e.seniority and hasattr(e.seniority, "value") else e.seniority,
            phone=e.phone, hire_date=str(e.hire_date) if e.hire_date else None, leave_balance=e.leave_balance or 0,
            team=team_name, department=dept_name,
            manager=e.manager.user.name if e.manager and e.manager.user else None,
            manager_employee_id=e.manager.id if e.manager else None,
            manager_email=e.manager.user.email if e.manager and e.manager.user else None,
            manager_phone=e.manager.phone if e.manager else None,
            manager_job_title=e.manager.job_title if e.manager else None,
            manager_seniority=(e.manager.seniority.value if hasattr(e.manager.seniority, "value") else e.manager.seniority) if e.manager else None,
            skills=[SkillOut(name=es.skill.name, level=es.level.value if hasattr(es.level, "value") else es.level) for es in e.employee_skills],
        ))
    return out


# ═══════════════════════════════════════════════════
# GET /rh/employees/{employee_id}
# ═══════════════════════════════════════════════════

@router.get("/employees/{employee_id}", response_model=EmployeeOut)
async def get_employee(employee_id: int, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Employee).where(Employee.id == employee_id).options(
            selectinload(Employee.user), selectinload(Employee.team).selectinload(Team.department),
            selectinload(Employee.manager).selectinload(Employee.user),
            selectinload(Employee.employee_skills).selectinload(EmployeeSkill.skill),
        )
    )
    e = result.scalar_one_or_none()
    if not e:
        raise HTTPException(status_code=404, detail="Employé introuvable")

    dept_name = (e.team.department.name.value if hasattr(e.team.department.name, "value") else e.team.department.name) if e.team and e.team.department else None
    return EmployeeOut(
        id=e.id, user_id=e.user_id,
        name=e.user.name if e.user else "", email=e.user.email if e.user else "", role=e.user.role if e.user else "",
        is_active=e.user.is_active if e.user else True,
        job_title=e.job_title, seniority=e.seniority.value if e.seniority and hasattr(e.seniority, "value") else e.seniority,
        phone=e.phone, hire_date=str(e.hire_date) if e.hire_date else None, leave_balance=e.leave_balance or 0,
        team=e.team.name if e.team else None, department=dept_name,
        manager=e.manager.user.name if e.manager and e.manager.user else None,
        manager_employee_id=e.manager.id if e.manager else None,
        manager_email=e.manager.user.email if e.manager and e.manager.user else None,
        manager_phone=e.manager.phone if e.manager else None,
        manager_job_title=e.manager.job_title if e.manager else None,
        manager_seniority=(e.manager.seniority.value if hasattr(e.manager.seniority, "value") else e.manager.seniority) if e.manager else None,
        skills=[SkillOut(name=es.skill.name, level=es.level.value if hasattr(es.level, "value") else es.level) for es in e.employee_skills],
    )


# ═══════════════════════════════════════════════════
# GET /rh/skills
# ═══════════════════════════════════════════════════

@router.get("/skills", response_model=List[SkillListOut])
async def list_skills(_rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Skill).order_by(Skill.name))
    return [SkillListOut(id=s.id, name=s.name) for s in result.scalars().all()]


# ═══════════════════════════════════════════════════
# GET /rh/leaves
# ═══════════════════════════════════════════════════

@router.get("/leaves", response_model=List[LeaveOut])
async def list_leaves(status: Optional[str] = None, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    query = (
        select(Leave)
        .options(selectinload(Leave.employee).selectinload(Employee.user), selectinload(Leave.employee).selectinload(Employee.team))
        .order_by(Leave.created_at.desc())
    )
    if status:
        query = query.where(Leave.status == status)

    result = await db.execute(query)
    out = []
    for lv in result.scalars().all():
        emp = lv.employee
        out.append(LeaveOut(
            id=lv.id, employee_id=lv.employee_id,
            employee_name=emp.user.name if emp and emp.user else "—",
            employee_email=emp.user.email if emp and emp.user else "—",
            team=emp.team.name if emp and emp.team else None,
            leave_type=lv.leave_type.value if hasattr(lv.leave_type, "value") else lv.leave_type,
            start_date=str(lv.start_date), end_date=str(lv.end_date), days_count=lv.days_count,
            status=lv.status.value if hasattr(lv.status, "value") else lv.status,
            justification_url=lv.justification_url, created_at=str(lv.created_at) if lv.created_at else None,
        ))
    return out


# ═══════════════════════════════════════════════════
# POST /rh/leaves/{id}/approve
# ═══════════════════════════════════════════════════

@router.post("/leaves/{leave_id}/approve")
async def approve_leave(leave_id: int, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Leave).where(Leave.id == leave_id))
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Congé introuvable")
    if leave.status != LeaveStatusEnum.PENDING:
        raise HTTPException(status_code=400, detail="Ce congé n'est pas en attente")

    leave.status = LeaveStatusEnum.APPROVED
    db.add(LeaveLog(employee_id=leave.employee_id, leave_id=leave.id, action="approved", description="Congé approuvé par le responsable RH"))
    await db.commit()
    return {"success": True, "status": "approved"}


# ═══════════════════════════════════════════════════
# POST /rh/leaves/{id}/reject
# ═══════════════════════════════════════════════════

@router.post("/leaves/{leave_id}/reject")
async def reject_leave(leave_id: int, body: RejectBody, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Leave).where(Leave.id == leave_id))
    leave = result.scalar_one_or_none()
    if not leave:
        raise HTTPException(status_code=404, detail="Congé introuvable")
    if leave.status != LeaveStatusEnum.PENDING:
        raise HTTPException(status_code=400, detail="Ce congé n'est pas en attente")

    leave.status = LeaveStatusEnum.REJECTED
    db.add(LeaveLog(employee_id=leave.employee_id, leave_id=leave.id, action="rejected", description=f"Congé rejeté : {body.reason or 'Aucune raison précisée'}"))
    await db.commit()
    return {"success": True, "status": "rejected"}


# ═══════════════════════════════════════════════════
# PATCH /rh/employees/{employee_id}
# ═══════════════════════════════════════════════════

@router.patch("/employees/{employee_id}")
async def update_employee(employee_id: int, body: UpdateEmployeeRequest, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).options(selectinload(Employee.user), selectinload(Employee.team)).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee:
        raise HTTPException(status_code=404, detail="Employé introuvable")

    if body.job_title is not None:
        employee.job_title = body.job_title
    if body.seniority is not None:
        try:
            employee.seniority = SeniorityEnum(body.seniority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Seniority invalide : {body.seniority}")
    if body.team_id is not None:
        if not (await db.execute(select(Team).where(Team.id == body.team_id))).scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Équipe introuvable")
        employee.team_id = body.team_id
    if body.manager_id is not None:
        if not (await db.execute(select(Employee).where(Employee.id == body.manager_id))).scalar_one_or_none():
            raise HTTPException(status_code=404, detail="Manager introuvable")
        employee.manager_id = body.manager_id

    db.add(employee)
    await db.commit()
    await db.refresh(employee)
    return {"success": True, "employee_id": employee.id}


# ═══════════════════════════════════════════════════
# POST /rh/employees/{employee_id}/contact
# ═══════════════════════════════════════════════════

@router.post("/employees/{employee_id}/contact")
async def contact_employee(employee_id: int, body: ContactEmailRequest, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Employee).options(selectinload(Employee.user)).where(Employee.id == employee_id))
    employee = result.scalar_one_or_none()
    if not employee or not employee.user:
        raise HTTPException(status_code=404, detail="Employé introuvable")

    try:
        send_generic_email(to_email=employee.user.email, subject=body.subject, body=body.body, cc_emails=body.cc_emails)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur envoi email : {str(e)}")

    return {"success": True, "sent_to": employee.user.email}


# ═══════════════════════════════════════════════════
# PATCH /rh/users/{user_id}/toggle-active
# ═══════════════════════════════════════════════════

@router.patch("/users/{user_id}/toggle-active")
async def toggle_user_active(user_id: int, _rh: dict = Depends(require_rh), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    user.is_active = not user.is_active
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"success": True, "user_id": user.id, "is_active": user.is_active}
