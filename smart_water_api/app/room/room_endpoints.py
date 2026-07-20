from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Plant, Room
from app.room.room_schemas import RoomCreate, RoomResponse

router = APIRouter(
    prefix="/api/rooms",
    tags=["Rooms"],
)


# =============================================================================
# GET ENDPOINTS
# =============================================================================
@router.get("", response_model=list[RoomResponse])
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


# =============================================================================
# POST ENDPOINTS
# =============================================================================
@router.post(
    "",
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


# =============================================================================
# DELETE ENDPOINTS
# =============================================================================
@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
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
