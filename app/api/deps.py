from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import APIError
from app.core.security import decode_access_token
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
DBSession = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DBSession) -> User:
    try:
        subject = decode_access_token(token).get("sub")
        user_id = int(subject)
    except (jwt.PyJWTError, TypeError, ValueError) as exc:
        raise APIError(401, "invalid_token", "The access token is invalid or expired") from exc
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise APIError(401, "invalid_token", "The access token is invalid or expired")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(user: User, role: UserRole) -> None:
    if user.role != role:
        raise APIError(403, "forbidden", f"This action requires the {role.value} role")
