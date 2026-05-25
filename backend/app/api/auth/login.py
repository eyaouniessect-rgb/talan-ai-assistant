# api/auth/login.py
# Schéma : public
#
# Routes d'authentification.
# POST /auth/login    → vérifie email+password → retourne JWT
# POST /auth/register → crée un compte + retourne JWT

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from app.database.connection import get_db
from app.database.models.public.user import User
from app.database.models.hris.employee import Employee
from app.database.models.hris.team     import Team
from app.database.models.hris.leave    import Leave
from app.database.schemas.user import UserCreate, TokenResponse, UserResponse
from app.core.security import verify_password, hash_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Solde de congés annuel par défaut quand Employee.leave_balance est NULL
# (cohérent avec agents/rh/tools.py:check_leave_balance)
_DEFAULT_LEAVE_BALANCE = 26


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Connexion utilisateur.
    Accepte form-data OAuth2 (Swagger) — username = email.
    Retourne un JWT token + infos utilisateur.
    """
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email ou mot de passe incorrect"
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte désactivé")

    token = create_access_token(data={
        "sub": str(user.id),
        "role": user.role,
        "name": user.name,
    })

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
        )
    )


@router.get("/me/profile")
async def get_my_profile(
    current_user: dict         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """
    Retourne les infos RH de l'utilisateur connecté pour affichage sidebar :
      - seniority    (JUNIOR | MID | SENIOR)
      - job_title    (ex: "Frontend Developer")
      - team_name
      - department_name

    Champs nuls si l'utilisateur n'a pas de fiche employé (admin, etc.).
    """
    user_id = int(current_user["user_id"])

    employee = (await db.execute(
        select(Employee)
        .where(Employee.user_id == user_id)
        .options(selectinload(Employee.team).selectinload(Team.department))
    )).scalar_one_or_none()

    if not employee:
        return {
            "seniority":       None,
            "job_title":       None,
            "team_name":       None,
            "department_name": None,
            "leave_balance":   None,
        }

    dept = employee.team.department if (employee.team and employee.team.department) else None
    dept_name = None
    if dept:
        dept_name = dept.name.value if hasattr(dept.name, "value") else dept.name

    # Solde effectif = (leave_balance ou défaut 26) - jours en attente (pending)
    pending_rows = (await db.execute(
        select(Leave).where(
            and_(Leave.employee_id == employee.id, Leave.status == "pending")
        )
    )).scalars().all()
    jours_pending = sum((l.days_count or 0) for l in pending_rows)
    solde_total    = employee.leave_balance if employee.leave_balance is not None else _DEFAULT_LEAVE_BALANCE
    solde_effectif = solde_total - jours_pending

    return {
        "seniority":         employee.seniority.value if employee.seniority else None,
        "job_title":         employee.job_title,
        "team_name":         employee.team.name if employee.team else None,
        "department_name":   dept_name,
        "leave_balance":     solde_effectif,    # solde effectif (utilisé par la carte dashboard)
        "leave_total":       solde_total,       # solde brut
        "leave_pending":     jours_pending,     # jours en attente d'approbation
    }


@router.post("/register", response_model=TokenResponse)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Inscription d'un nouvel utilisateur."""
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")

    user = User(
        name=data.name,
        email=data.email,
        password=hash_password(data.password),
        role=data.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(data={
        "sub": str(user.id),
        "role": user.role,
        "name": user.name,
    })

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
        )
    )
