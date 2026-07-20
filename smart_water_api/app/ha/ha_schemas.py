from pydantic import BaseModel


class MoistureSensorResponse(BaseModel):
    entity_id: str
    name: str
    state: float | None
    unit: str | None
    available: bool

    # Computed by Smart Water API
    assigned_plant_id: str | None = None
    assigned_plant_name: str | None = None


class PumpSwitchResponse(BaseModel):
    entity_id: str
    name: str
    domain: str
    state: str | None
    available: bool

    # Computed by Smart Water API
    assigned_plant_id: str | None = None
    assigned_plant_name: str | None = None
