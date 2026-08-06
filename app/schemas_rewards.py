from pydantic import BaseModel, field_validator


class LeaderboardOptInRequest(BaseModel):
    leaderboard_opt_in: bool


class LeaderboardDisplayRequest(BaseModel):
    leaderboard_display: str

    @field_validator("leaderboard_display")
    @classmethod
    def validate_display(cls, v: str) -> str:
        if v not in ("user", "car"):
            raise ValueError("leaderboard_display muss 'user' oder 'car' sein")
        return v


class LeaderboardEntryOut(BaseModel):
    rank: int
    display_name: str
    reward_points: int
    avatar_path: str | None = None
    is_car: bool = False


class MyRewardsOut(BaseModel):
    reward_points: int
    leaderboard_opt_in: bool
    leaderboard_display: str
    leaderboard_rank: int | None = None


class AvatarUploadResponse(BaseModel):
    avatar_path: str


class CarCreateRequest(BaseModel):
    name: str
    brand: str | None = None
    model: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Name darf nicht leer sein")
        if len(v) > 100:
            raise ValueError("Name darf maximal 100 Zeichen lang sein")
        return v


class CarUpdateRequest(BaseModel):
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    is_primary: bool | None = None


class CarOut(BaseModel):
    id: str
    name: str
    brand: str | None = None
    model: str | None = None
    photo_path: str | None = None
    is_primary: bool

    model_config = {"from_attributes": True}


class CarPhotoUploadResponse(BaseModel):
    photo_path: str
