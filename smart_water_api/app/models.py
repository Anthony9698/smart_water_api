from uuid import uuid4

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )

    plants: Mapped[list["Plant"]] = relationship(
        back_populates="room",
        cascade="all, delete-orphan",
    )


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid4()),
    )

    name: Mapped[str] = mapped_column(String(100))
    species: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    room_id: Mapped[str] = mapped_column(
        ForeignKey("rooms.id"),
    )

    moisture_entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    pump_entity_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        unique=True,
    )

    photo_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    room: Mapped["Room"] = relationship(
        back_populates="plants",
    )
