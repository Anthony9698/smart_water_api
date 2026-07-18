from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Plant, Room
from app.schemas import RoomCreate, RoomResponse
from app.schemas import PlantCreate, PlantResponse

Path("data").mkdir(exist_ok=True)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Water API",
    version="0.2.0",
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post(
    "/api/rooms",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_room(
    payload: RoomCreate,
    db: Session = Depends(get_db),
):
    room = Room(name=payload.name.strip())

    db.add(room)
    db.commit()
    db.refresh(room)

    return RoomResponse(
        id=room.id,
        name=room.name,
        plant_count=0,
    )


@app.get("/api/rooms", response_model=list[RoomResponse])
def list_rooms(db: Session = Depends(get_db)):
    statement = (
        select(
            Room.id,
            Room.name,
            func.count(Plant.id).label("plant_count"),
        )
        .outerjoin(Plant)
        .group_by(Room.id)
        .order_by(Room.name)
    )

    rooms = db.execute(statement).all()

    return [
        RoomResponse(
            id=room.id,
            name=room.name,
            plant_count=room.plant_count,
        )
        for room in rooms
    ]


@app.delete(
    "/api/rooms/{room_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_room(
    room_id: str,
    db: Session = Depends(get_db),
):
    room = db.get(Room, room_id)

    if not room:
        raise HTTPException(
            status_code=404,
            detail="Room not found",
        )

    db.delete(room)
    db.commit()


def plant_response(plant: Plant) -> PlantResponse:
    photo_url = None

    if plant.photo_filename:
        photo_url = f"/api/plants/{plant.id}/photo"

    return PlantResponse(
        id=plant.id,
        name=plant.name,
        species=plant.species,
        room_id=plant.room_id,
        moisture_entity_id=plant.moisture_entity_id,
        pump_entity_id=plant.pump_entity_id,
        photo_url=photo_url,
    )


@app.post(
    "/api/plants",
    response_model=PlantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_plant(
    payload: PlantCreate,
    db: Session = Depends(get_db),
):
    room = db.get(Room, payload.room_id)

    if not room:
        raise HTTPException(
            status_code=404,
            detail="Room not found",
        )

    plant = Plant(**payload.model_dump())

    db.add(plant)
    db.commit()
    db.refresh(plant)

    return plant_response(plant)


@app.put("/api/plants/{plant_id}/photo")
async def update_plant_photo(
    plant_id: str,
    photo: UploadFile = File(...),
):
    return {
        "plant_id": plant_id,
        "filename": photo.filename,
        "content_type": photo.content_type,
    }


@app.get("/api/plants", response_model=list[PlantResponse])
def list_plants(
    room_id: str | None = None,
    db: Session = Depends(get_db),
):
    statement = select(Plant).order_by(Plant.name)

    if room_id:
        statement = statement.where(Plant.room_id == room_id)

    plants = db.scalars(statement).all()

    return [plant_response(plant) for plant in plants]
