from pydantic import BaseModel


class ChargingPointStatusOut(BaseModel):
    id: str
    label: str
    connector_type: str | None
    max_power_kw: int | None
    is_active: bool
    is_occupied: bool
    current_session_id: str | None = None
    queue_length: int = 0

    model_config = {"from_attributes": True}


class LocationWithStatusOut(BaseModel):
    id: str
    name: str
    address: str
    description: str | None
    is_active: bool
    charging_points: list[ChargingPointStatusOut] = []

    model_config = {"from_attributes": True}


class CheckInResponse(BaseModel):
    session_id: str
    charging_point_id: str
    checked_in_at: str


class MySessionOut(BaseModel):
    session_id: str
    charging_point_id: str
    charging_point_label: str
    location_id: str
    location_name: str
    checked_in_at: str
