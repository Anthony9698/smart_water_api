from fastapi import FastAPI

from app.database import Base, engine
from app.room.room_endpoints import router as room_router
from app.ha.ha_endpoints import router as ha_router
from app.plant.plant_endpoints import router as plant_router

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Water API",
    version="0.2.0",
)

app.include_router(room_router)
app.include_router(ha_router)
app.include_router(plant_router)


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
