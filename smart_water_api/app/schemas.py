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
    species: str | None = None
    room_id: str
    moisture_entity_id: str | None = None
    pump_entity_id: str | None = None


class PlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    species: str | None
    room_id: str
    moisture_entity_id: str | None
    pump_entity_id: str | None
    photo_url: str | None = None
