import os
import httpx

from io import BytesIO
from uuid import uuid4
from datetime import UTC, datetime

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, status, File, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import Plant, Room
from app.schemas import RoomCreate, RoomResponse
from app.schemas import PlantCreate, PlantUpdate, PlantResponse
from app.schemas import MoistureSensorResponse

from fastapi.responses import FileResponse

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000

HA_API_URL = os.getenv(
    "HA_API_URL",
    "http://supervisor/core/api",
)

HA_TOKEN = os.getenv("HA_TOKEN") or os.getenv("SUPERVISOR_TOKEN")

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


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}


@app.post(
    "/api/rooms",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Rooms"],
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


@app.get("/api/rooms", response_model=list[RoomResponse], tags=["Rooms"])
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
    "/api/rooms/{room_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Rooms"]
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
        last_watered_at=plant.last_watered_at,
    )


@app.post(
    "/api/plants",
    response_model=PlantResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Plants"],
)
def create_plant(
    payload: PlantCreate,
    db: Session = Depends(get_db),
):
    room = db.get(Room, payload.room_id)

    if not room:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )

    if payload.moisture_entity_id:
        existing_plant = db.scalar(
            select(Plant).where(Plant.moisture_entity_id == payload.moisture_entity_id)
        )

        if existing_plant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("This moisture sensor is already assigned to another plant"),
            )

    plant = Plant(**payload.model_dump())

    db.add(plant)
    db.commit()
    db.refresh(plant)

    return plant_response(plant)


@app.patch(
    "/api/plants/{plant_id}",
    response_model=PlantResponse,
    status_code=status.HTTP_200_OK,
    tags=["Plants"],
)
def update_plant(
    plant_id: str,
    payload: PlantUpdate,
    db: Session = Depends(get_db),
):
    plant = db.get(Plant, plant_id)

    if not plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant not found",
        )

    updates = payload.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Plant name cannot be null",
        )

    if "room_id" in updates and updates["room_id"] is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Room ID cannot be null",
        )

    if "room_id" in updates:
        room = db.get(Room, updates["room_id"])

        if not room:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Room not found",
            )

    moisture_entity_id = updates.get("moisture_entity_id")

    if moisture_entity_id is not None:
        existing_plant = db.scalar(
            select(Plant).where(
                Plant.moisture_entity_id == moisture_entity_id,
                Plant.id != plant_id,
            )
        )

        if existing_plant:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=("This moisture sensor is already " "assigned to another plant"),
            )

    for field, value in updates.items():
        setattr(plant, field, value)

    db.commit()
    db.refresh(plant)

    return plant_response(plant)


@app.put("/api/plants/{plant_id}/photo", response_model=PlantResponse, tags=["Plants"])
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
            pixel_count = source.width * source.height

            if pixel_count > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="Photo dimensions are too large",
                )

            # Reduces memory usage for JPEG images.
            source.draft("RGB", (1600, 1600))

            image = ImageOps.exif_transpose(source)
            image.thumbnail((1600, 1600))

            if image.mode != "RGB":
                image = image.convert("RGB")

            image.save(
                new_path,
                format="JPEG",
                quality=85,
                optimize=True,
            )
    except HTTPException:
        new_path.unlink(missing_ok=True)
        raise
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


@app.get("/api/plants/{plant_id}/photo", response_class=FileResponse, tags=["Plants"])
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


@app.get("/api/plants", response_model=list[PlantResponse], tags=["Plants"])
def list_plants(
    room_id: str | None = None,
    db: Session = Depends(get_db),
):
    statement = select(Plant).order_by(Plant.name)

    if room_id:
        statement = statement.where(Plant.room_id == room_id)

    plants = db.scalars(statement).all()

    return [plant_response(plant) for plant in plants]


@app.get(
    "/api/ha/moisture-sensors",
    response_model=list[MoistureSensorResponse],
    tags=["Home Assistant"],
)
async def list_moisture_sensors():
    if not HA_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Home Assistant API token is unavailable",
        )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{HA_API_URL}/states",
                headers={
                    "Authorization": f"Bearer {HA_TOKEN}",
                    "Content-Type": "application/json",
                },
            )

            response.raise_for_status()

    except httpx.HTTPError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not retrieve sensors from Home Assistant",
        ) from error

    sensors = []

    for entity in response.json():
        entity_id = entity.get("entity_id", "")
        attributes = entity.get("attributes", {})

        if not entity_id.startswith("sensor."):
            continue

        if attributes.get("device_class") != "moisture":
            continue

        raw_state = entity.get("state")
        available = raw_state not in {
            None,
            "unknown",
            "unavailable",
        }

        try:
            reading = float(raw_state) if available else None
        except (TypeError, ValueError):
            reading = None
            available = False

        sensors.append(
            MoistureSensorResponse(
                entity_id=entity_id,
                name=attributes.get(
                    "friendly_name",
                    entity_id,
                ),
                state=reading,
                unit=attributes.get("unit_of_measurement"),
                available=available,
            )
        )

    return sensors


@app.post(
    "/api/plants/{plant_id}/watered", response_model=PlantResponse, tags=["Plants"]
)
def mark_plant_watered(
    plant_id: str,
    db: Session = Depends(get_db),
):
    plant = db.get(Plant, plant_id)

    if not plant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plant not found",
        )

    plant.last_watered_at = datetime.now(UTC)

    db.commit()
    db.refresh(plant)

    return plant_response(plant)
