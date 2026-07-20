import os
import httpx

from sqlalchemy.orm import Session
from sqlalchemy import select

from fastapi import APIRouter, HTTPException, status, Depends
from app.ha.ha_schemas import MoistureSensorResponse, PumpSwitchResponse
from app.database import get_db
from app.models import Plant

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
async def list_moisture_sensors(
    unassigned_only: bool = False,
    plant_id: str | None = None,
    db: Session = Depends(get_db),
):
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

    assignment_rows = db.execute(
        select(
            Plant.moisture_entity_id,
            Plant.id,
            Plant.name,
        ).where(Plant.moisture_entity_id.isnot(None))
    ).all()

    assignments = {
        row.moisture_entity_id: {
            "plant_id": row.id,
            "plant_name": row.name,
        }
        for row in assignment_rows
    }
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

        assignment = assignments.get(entity_id)

        if unassigned_only:
            assigned_to_different_plant = (
                assignment is not None and assignment["plant_id"] != plant_id
            )

            if assigned_to_different_plant:
                continue

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
                assigned_plant_id=(assignment["plant_id"] if assignment else None),
                assigned_plant_name=(assignment["plant_name"] if assignment else None),
            )
        )

    sensors.sort(key=lambda sensor: sensor.name.lower())

    return sensors


@router.get(
    "/pump-switches",
    response_model=list[PumpSwitchResponse],
)
async def list_pump_switches(
    unassigned_only: bool = False,
    plant_id: str | None = None,
    db: Session = Depends(get_db),
):
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
            detail="Could not retrieve pump switches from Home Assistant",
        ) from error

    assignment_rows = db.execute(
        select(
            Plant.pump_entity_id,
            Plant.id,
            Plant.name,
        ).where(Plant.pump_entity_id.isnot(None))
    ).all()

    assignments = {
        row.pump_entity_id: {
            "plant_id": row.id,
            "plant_name": row.name,
        }
        for row in assignment_rows
    }

    pump_switches = []

    for entity in response.json():
        entity_id = entity.get("entity_id", "")
        domain = entity_id.partition(".")[0]

        if domain not in {"switch", "valve"} and "pump" not in entity_id:
            continue

        raw_state = entity.get("state")
        attributes = entity.get("attributes", {})

        available = raw_state not in {
            None,
            "unknown",
            "unavailable",
        }

        assignment = assignments.get(entity_id)

        if unassigned_only:
            assigned_to_different_plant = (
                assignment is not None and assignment["plant_id"] != plant_id
            )

            if assigned_to_different_plant:
                continue

        pump_switches.append(
            PumpSwitchResponse(
                entity_id=entity_id,
                name=attributes.get(
                    "friendly_name",
                    entity_id,
                ),
                domain=domain,
                state=raw_state if available else None,
                available=available,
                assigned_plant_id=(assignment["plant_id"] if assignment else None),
                assigned_plant_name=(assignment["plant_name"] if assignment else None),
            )
        )

    pump_switches.sort(key=lambda pump_switch: pump_switch.name.lower())

    return pump_switches
