from pydantic import BaseModel, field_validator, model_validator


def _clean(value: str | None, field: str, min_len: int, max_len: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) < min_len:
        raise ValueError(f"{field} ist zu kurz")
    if len(value) > max_len:
        raise ValueError(f"{field} darf maximal {max_len} Zeichen lang sein")
    return value


def _optional_text(value: str | None, field: str, max_len: int) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if len(value) > max_len:
        raise ValueError(f"{field} darf maximal {max_len} Zeichen lang sein")
    return value or None


def _reject_explicit_null(model: BaseModel, fields: tuple[str, ...]) -> None:
    # PATCH: weggelassen = unveraendert. Ein ausdrueckliches null wuerde dagegen in eine
    # NOT-NULL-Spalte geschrieben und als Fehler 500 enden.
    for name in fields:
        if name in model.model_fields_set and getattr(model, name) is None:
            raise ValueError(f"{name} darf nicht null sein")


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

    @field_validator("name")
    @classmethod
    def check_name(cls, v):
        return _clean(v, "Name", 2, 255)

    @field_validator("address")
    @classmethod
    def check_address(cls, v):
        return _clean(v, "Adresse", 5, 500)

    @field_validator("description")
    @classmethod
    def check_description(cls, v):
        return _optional_text(v, "Beschreibung", 5000)

    @model_validator(mode="after")
    def check_nulls(self):
        _reject_explicit_null(self, ("name", "address", "is_active"))
        return self


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

    @field_validator("connector_type")
    @classmethod
    def check_connector(cls, v):
        return _optional_text(v, "Steckertyp", 50)

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

    @field_validator("label")
    @classmethod
    def check_label(cls, v):
        return _clean(v, "Label", 1, 100)

    @field_validator("connector_type")
    @classmethod
    def check_connector(cls, v):
        return _optional_text(v, "Steckertyp", 50)

    @field_validator("max_power_kw")
    @classmethod
    def check_power(cls, v):
        if v is not None and (v <= 0 or v > 1000):
            raise ValueError("Ladeleistung muss zwischen 1 und 1000 kW liegen")
        return v

    @model_validator(mode="after")
    def check_nulls(self):
        _reject_explicit_null(self, ("label", "is_active"))
        return self


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
