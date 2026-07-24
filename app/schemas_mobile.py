from pydantic import BaseModel, field_validator


class DeviceTokenRegister(BaseModel):
    platform: str
    push_token: str

    @field_validator("platform")
    @classmethod
    def check_platform(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in ("ios", "android"):
            raise ValueError("platform muss 'ios' oder 'android' sein")
        return v

    @field_validator("push_token")
    @classmethod
    def check_token(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("push_token ist ungueltig")
        if len(v) > 500:
            raise ValueError("push_token ist zu lang")
        return v


class DeviceTokenOut(BaseModel):
    id: str
    platform: str
    is_active: bool

    model_config = {"from_attributes": True}


class MobileDashboardOut(BaseModel):
    active_session: dict | None = None
    queue_status: dict | None = None
    locations_summary: list[dict] = []
