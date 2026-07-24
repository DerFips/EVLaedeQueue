from pydantic import BaseModel


class CheckoutInitiateResponse(BaseModel):
    action: str
    message: str
    pending_entry_id: str | None = None
    pending_user_parking_offer: str | None = None
    notified_user_email: str | None = None


class CheckoutActionResponse(BaseModel):
    action: str
    message: str
    pending_entry_id: str | None = None
    pending_user_parking_offer: str | None = None
    notified_user_email: str | None = None
