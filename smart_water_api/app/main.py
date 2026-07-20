import os

from fastapi import FastAPI

from app.database import Base, engine
from app.room.room_endpoints import router as room_router
from app.ha.ha_endpoints import router as ha_router
from app.plant.plant_endpoints import router as plant_router

APP_VERSION = os.getenv(
    "SMART_WATER_VERSION",
    "development",
)

APP_COMMIT = os.getenv(
    "SMART_WATER_COMMIT",
    "unknown",
)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Water API",
    version=APP_VERSION,
)

app.include_router(room_router)
app.include_router(ha_router)
app.include_router(plant_router)


@app.get("/health", tags=["Health"])
def health():
    commit = APP_COMMIT

    if commit != "unknown":
        commit = commit[:12]

    return {
        "status": "ok",
        "version": APP_VERSION,
        "commit": commit,
    }
