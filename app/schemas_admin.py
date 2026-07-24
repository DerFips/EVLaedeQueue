from pydantic import BaseModel, field_validator


class LocationCreate(BaseModel):
    name: str
    address: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name ist zu kurz")
        if len(v) > 255:
            raise ValueError("Name darf maximal 255 Zeichen lang sein")
        return v

    @field_validator("address")
    @classmethod
    def check_address(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 5:
            raise ValueError("Adresse ist zu kurz")
        if len(v) > 500:
            raise ValueError("Adresse darf maximal 500 Zeichen lang sein")
        return v

    @field_validator("description")
    @classmethod
    def check_description(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 5000:
            raise ValueError("Beschreibung darf maximal 5000 Zeichen lang sein")
        return v


class LocationUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    description: str | None = None
    is_active: bool | None = None


class LocationOut(BaseModel):
    id: str
    name: str
    address: str
    description: str | None
    is_active: bool

    model_config = {"from_attributes": True}


class ChargingPointCreate(BaseModel):
    label: str
    connector_type: str | None = None
    max_power_kw: int | None = None

    @field_validator("label")
    @classmethod
    def check_label(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 1:
            raise ValueError("Label darf nicht leer sein")
        if len(v) > 100:
            raise ValueError("Label darf maximal 100 Zeichen lang sein")
        return v

    @field_validator("max_power_kw")
    @classmethod
    def check_power(cls, v: int | None) -> int | None:
        if v is not None and (v <= 0 or v > 1000):
            raise ValueError("Ladeleistung muss zwischen 1 und 1000 kW liegen")
        return v


class ChargingPointUpdate(BaseModel):
    label: str | None = None
    connector_type: str | None = None
    max_power_kw: int | None = None
    is_active: bool | None = None


class ChargingPointOut(BaseModel):
    id: str
    location_id: str
    label: str
    connector_type: str | None
    max_power_kw: int | None
    is_active: bool

    model_config = {"from_attributes": True}


class LocationDetailOut(LocationOut):
    charging_points: list[ChargingPointOut] = []
