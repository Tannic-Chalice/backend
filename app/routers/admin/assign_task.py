# app/routers/admin/assign_task.py
from fastapi import APIRouter, HTTPException, Request
from app.database import get_db

router = APIRouter()


@router.post("/assign-task")
async def admin_assign_task(request: Request):
    data = await request.json()

    pickup_id = data.get("pickupId")
    driver_id = data.get("driverId")
    vehicle_id = data.get("vehicleId")

    if not pickup_id or not driver_id or not vehicle_id:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: pickupId, driverId, vehicleId"
        )

    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute(
                'SELECT trip_id FROM "pickups" WHERE pickup_id = %s',
                (pickup_id,)
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(404, "Pickup not found")

            trip_id = row[0]

            cur.execute(
                'UPDATE "trips" SET driver_id = %s, vehicle_id = %s WHERE trip_id = %s',
                (driver_id, vehicle_id, trip_id)
            )
            conn.commit()

        return {"message": "Task assigned successfully"}

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(500, "Internal Server Error")
