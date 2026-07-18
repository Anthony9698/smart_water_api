import os

from io import BytesIO
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Plant, Room
from app.schemas import RoomCreate, RoomResponse
from app.schemas import PlantCreate, PlantResponse

from fastapi.responses import FileResponse

Path("data").mkdir(exist_ok=True)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Water API",
    version="0.2.0",
)

register_heif_opener()

IMAGE_DIRECTORY = Path(
    os.getenv(
        "SMART_WATER_IMAGE_DIR",
        "./data/images",
    )
)

IMAGE_DIRECTORY.mkdir(
    parents=True,
    exist_ok=True,
)

MAX_IMAGE_SIZE = 8 * 1024 * 1024


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


@app.put(
    "/api/plants/{plant_id}/photo",
    response_model=PlantResponse,
)
async def update_plant_photo(
    plant_id: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    plant = db.get(Plant, plant_id)

    if not plant:
        raise HTTPException(
            status_code=404,
            detail="Plant not found",
        )

    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/heic",
        "image/heif",
    }

    if photo.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Photo must be JPEG, PNG, HEIC, or HEIF",
        )

    contents = await photo.read(MAX_IMAGE_SIZE + 1)

    if len(contents) > MAX_IMAGE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Photo must be 8 MB or smaller",
        )

    new_filename = f"{uuid4()}.jpg"
    new_path = IMAGE_DIRECTORY / new_filename

    try:
        with Image.open(BytesIO(contents)) as source:
            image = ImageOps.exif_transpose(source)
            image = image.convert("RGB")

            image.thumbnail((1600, 1600))

            image.save(
                new_path,
                format="JPEG",
                quality=85,
                optimize=True,
            )
    except (UnidentifiedImageError, OSError, ValueError) as error:
        new_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The uploaded photo could not be decoded",
        ) from error

    old_filename = plant.photo_filename
    plant.photo_filename = new_filename

    try:
        db.commit()
        db.refresh(plant)
    except Exception:
        db.rollback()
        new_path.unlink(missing_ok=True)
        raise

    if old_filename:
        old_path = IMAGE_DIRECTORY / old_filename
        old_path.unlink(missing_ok=True)

    return plant_response(plant)


@app.get(
    "/api/plants/{plant_id}/photo",
    response_class=FileResponse,
)
def get_plant_photo(
    plant_id: str,
    db: Session = Depends(get_db),
):
    plant = db.get(Plant, plant_id)

    if not plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant not found",
        )

    if not plant.photo_filename:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant does not have a photo",
        )

    photo_path = (IMAGE_DIRECTORY / plant.photo_filename).resolve()

    image_directory = IMAGE_DIRECTORY.resolve()

    if image_directory not in photo_path.parents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid photo path",
        )

    if not photo_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo file was not found",
        )

    return FileResponse(
        path=photo_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache",
        },
    )


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
