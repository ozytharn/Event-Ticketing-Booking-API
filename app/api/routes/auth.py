from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBSession
from app.core.config import settings
from app.core.errors import APIError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.schemas.auth import TokenRead, UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: DBSession) -> User:
    if payload.role == UserRole.ORGANIZER:
        provided_code = payload.organizer_registration_code or ""
        configured_code = settings.organizer_registration_code or ""
        if not configured_code or not compare_digest(provided_code, configured_code):
            raise APIError(
                403,
                "organizer_registration_denied",
                "A valid organizer registration code is required",
            )
    email = str(payload.email).lower()
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise APIError(409, "email_already_registered", "An account with this email already exists")
    user = User(
        email=email,
        full_name=payload.full_name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(
            409, "email_already_registered", "An account with this email already exists"
        ) from exc
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenRead)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: DBSession,
) -> TokenRead:
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise APIError(401, "invalid_credentials", "Email or password is incorrect")
    return TokenRead(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserRead)
def read_me(user: CurrentUser) -> User:
    return user
