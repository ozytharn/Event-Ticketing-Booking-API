from secrets import token_urlsafe

from fastapi import APIRouter, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DBSession
from app.core.errors import APIError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.schemas.auth import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
def read_profile(user: CurrentUser) -> User:
    return user


@router.get("/{user_id}", response_model=UserRead)
def read_user(user_id: int, user: CurrentUser) -> User:
    if user_id != user.id:
        raise APIError(404, "user_not_found", "User not found")
    return user


@router.patch("/me", response_model=UserRead)
def update_profile(payload: UserUpdate, user: CurrentUser, db: DBSession) -> User:
    changes = payload.model_dump(exclude_unset=True)
    new_password = changes.pop("new_password", None)
    current_password = changes.pop("current_password", None)
    if new_password is not None:
        if not verify_password(current_password, user.password_hash):
            raise APIError(403, "current_password_incorrect", "Current password is incorrect")
        user.password_hash = hash_password(new_password)
    if "email" in changes and changes["email"] is not None:
        email = str(changes["email"]).lower()
        duplicate = db.scalar(select(User.id).where(User.email == email, User.id != user.id))
        if duplicate is not None:
            raise APIError(
                409,
                "email_already_registered",
                "An account with this email already exists",
            )
        user.email = email
    if changes.get("full_name") is not None:
        user.full_name = changes["full_name"].strip()
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(
            409, "email_already_registered", "An account with this email already exists"
        ) from exc
    db.refresh(user)
    return user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_profile(user: CurrentUser, db: DBSession) -> Response:
    user.is_active = False
    user.email = f"deleted-{user.id}@deactivated.invalid"
    user.full_name = "Deleted account"
    user.password_hash = hash_password(token_urlsafe(48))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
