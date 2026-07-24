from pydantic import BaseModel, field_validator
from app.models.models import ParkingOfferType


class QueueJoinRequest(BaseModel):
    parking_offer: ParkingOfferType = ParkingOfferType.NONE

    @field_validator("parking_offer", mode="before")
    @classmethod
    def normalize(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


class QueueEntryOut(BaseModel):
    id: str
    charging_point_id: str
    user_id: str
    parking_offer: str
    status: str
    position: int
    created_at: str

    model_config = {"from_attributes": True}


class MyQueueStatusOut(BaseModel):
    queue_entry_id: str
    charging_point_id: str
    charging_point_label: str
    location_id: str
    location_name: str
    position: int
    people_ahead: int
    parking_offer: str
    status: str
