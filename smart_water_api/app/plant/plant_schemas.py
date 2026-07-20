from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class PlantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    species: str | None = Field(default=None, max_length=150)
    room_id: str
    moisture_entity_id: str | None = Field(
        default=None,
        max_length=255,
    )
    pump_entity_id: str | None = Field(
        default=None,
        max_length=255,
    )


class PlantUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    species: str | None = Field(default=None, max_length=150)
    room_id: str | None = None
    moisture_entity_id: str | None = Field(
        default=None,
        max_length=255,
    )
    pump_entity_id: str | None = Field(
        default=None,
        max_length=255,
    )


class PlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    species: str | None
    room_id: str
    moisture_entity_id: str | None
    pump_entity_id: str | None
    photo_url: str | None = None
    last_watered_at: datetime | None


class PumpSwitchStateUpdate(BaseModel):
    is_on: bool


class PumpSwitchStateResponse(BaseModel):
    plant_id: str
    entity_id: str
    is_on: bool
    last_watered_at: datetime | None
