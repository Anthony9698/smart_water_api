import os
import httpx

from fastapi import APIRouter, HTTPException, status
from app.ha.ha_schemas import MoistureSensorResponse

router = APIRouter(
    prefix="/api/ha",
    tags=["Home Assistant"],
)

HA_API_URL = os.getenv(
    "HA_API_URL",
    "http://supervisor/core/api",
)

HA_TOKEN = os.getenv("HA_TOKEN") or os.getenv("SUPERVISOR_TOKEN")


# =============================================================================
# GET ENDPOINTS
# =============================================================================
@router.get(
    "/moisture-sensors",
    response_model=list[MoistureSensorResponse],
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
