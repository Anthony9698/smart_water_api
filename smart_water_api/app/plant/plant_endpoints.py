import os

from io import BytesIO
from uuid import uuid4
from datetime import UTC, datetime

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Plant, Room
from app.plant.plant_schemas import PlantCreate, PlantUpdate, PlantResponse

from fastapi.responses import FileResponse

router = APIRouter(
    prefix="/api/plants",
    tags=["Plants"],
)

MAX_IMAGE_SIZE = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
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


# =============================================================================
# VALIDATION HELPERS
# =============================================================================
def normalize_utc(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    # SQLite may remove timezone information when reading it.
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC).replace(microsecond=0)


# =============================================================================
# RESPONSE BUILDERS
# =============================================================================
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
        last_watered_at=normalize_utc(plant.last_watered_at),
    )


# =============================================================================
# GET ENDPOINTS
# =============================================================================
@router.get(
    "/{plant_id}/photo",
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


@router.get("", response_model=list[PlantResponse])
def list_plants(
    room_id: str | None = None,
    db: Session = Depends(get_db),
):
    statement = select(Plant).order_by(Plant.name)

    if room_id:
        statement = statement.where(Plant.room_id == room_id)

    plants = db.scalars(statement).all()

    return [plant_response(plant) for plant in plants]


# =============================================================================
# POST ENDPOINTS
# =============================================================================
@router.post(
    "",
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


@router.post(
    "/{plant_id}/watered",
    response_model=PlantResponse,
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

    plant.last_watered_at = datetime.now(UTC).replace(microsecond=0)

    db.commit()
    db.refresh(plant)

    return plant_response(plant)


# =============================================================================
# PATCH ENDPOINTS
# =============================================================================
@router.patch(
    "/{plant_id}",
    response_model=PlantResponse,
    status_code=status.HTTP_200_OK,
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


# =============================================================================
# PUT ENDPOINTS
# =============================================================================
@router.put("/{plant_id}/photo", response_model=PlantResponse)
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
