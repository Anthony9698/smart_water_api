from pydantic import BaseModel, ConfigDict, Field


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RoomResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    plant_count: int


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


class MoistureSensorResponse(BaseModel):
    entity_id: str
    name: str
    state: float | None
    unit: str | None
    available: bool
    assigned_plant_id: str | None = None
    assigned_plant_name: str | None = None
