import re
from pydantic import BaseModel, EmailStr, field_validator


PASSWORD_MIN_LENGTH = 10


PASSWORD_MAX_LENGTH = 128


def validate_password_strength(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Passwort muss mindestens {PASSWORD_MIN_LENGTH} Zeichen lang sein")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValueError(f"Passwort darf maximal {PASSWORD_MAX_LENGTH} Zeichen lang sein")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Passwort muss mindestens einen Grossbuchstaben enthalten")
    if not re.search(r"[a-z]", password):
        raise ValueError("Passwort muss mindestens einen Kleinbuchstaben enthalten")
    if not re.search(r"\d", password):
        raise ValueError("Passwort muss mindestens eine Ziffer enthalten")
    return password


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    phone: str | None = None

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name ist zu kurz")
        if len(v) > 255:
            raise ValueError("Name darf maximal 255 Zeichen lang sein")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    is_verified: bool
    reward_points: int = 0
    leaderboard_opt_in: bool = False
    avatar_path: str | None = None
    nickname: str | None = None
    leaderboard_display: str = "user"

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    full_name: str | None = None
    nickname: str | None = None

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name muss mindestens 2 Zeichen lang sein")
        if len(v) > 255:
            raise ValueError("Name darf maximal 255 Zeichen lang sein")
        return v

    @field_validator("nickname")
    @classmethod
    def validate_nickname(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if len(v) == 0:
            return None
        if len(v) > 100:
            raise ValueError("Spitzname darf maximal 100 Zeichen lang sein")
        return v


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)
