from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.user import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.ATTENDEE
    organizer_registration_code: str | None = Field(default=None, exclude=True)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    created_at: datetime
    is_active: bool


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    current_password: str | None = Field(default=None, min_length=8, max_length=128)
    new_password: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def require_update_fields(self) -> "UserUpdate":
        if all(
            value is None
            for value in (self.email, self.full_name, self.current_password, self.new_password)
        ):
            raise ValueError("at least one field must be supplied")
        if (self.current_password is None) != (self.new_password is None):
            raise ValueError("current_password and new_password must be provided together")
        return self


class TokenRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
