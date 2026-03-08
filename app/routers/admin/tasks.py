from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from app.database import get_db

router = APIRouter()


@router.get("/tasks")
def get_tasks():
    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT 
    p.pickup_id,

    /* Source-aware organization name */
    CASE 
        WHEN p.source_type = 'MAIN_BWG' 
            THEN b.organization
        WHEN p.source_type = 'ADDITIONAL_PICKUP' 
            THEN pa.organization_name
        ELSE NULL
    END AS bwg_id,

    p.scheduled_date,
    p.scheduled_time_slot,
    p.location,
    p.status,
    p.created_at,
    p.updated_at,

    d.name AS driver_name,
    v.registration_number AS vehicle_registration,
    s.name AS supervisor_name

FROM pickups p

/* MAIN BWG */
LEFT JOIN bwg b 
    ON p.source_type = 'MAIN_BWG'
   AND p.bwg_id = b.id

/* ADDITIONAL PICKUP */
LEFT JOIN pickup_address pa
    ON p.source_type = 'ADDITIONAL_PICKUP'
   AND p.bwg_id = pa.id

LEFT JOIN trips t ON p.trip_id = t.trip_id
LEFT JOIN driver d ON t.driver_id = d.id
LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
LEFT JOIN supervisors s ON t.supervisor_id = s.id

ORDER BY p.scheduled_date DESC, p.scheduled_time_slot ASC;
                """
            )

            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
            tasks = [dict(zip(cols, r)) for r in rows]

        return {"tasks": tasks, "total": len(tasks)}

    except Exception as e:
        print("ERROR in /admin/tasks:", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/tasks")
async def update_status(request: Request):
    data = await request.json()

    pickup_id = data.get("pickupId")
    status = data.get("status")

    if not pickup_id or not status:
        raise HTTPException(400, "Missing pickupId or status")

    if status not in ["PENDING", "DONE", "MISSED"]:
        raise HTTPException(400, "Invalid status")

    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                UPDATE pickups
                SET status = %s, updated_at = NOW()
                WHERE pickup_id = %s
                RETURNING *
                """,
                (status, pickup_id),
            )

            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            task = dict(zip(cols, row)) if row else None

        if not task:
            raise HTTPException(404, "Task not found")

        return {"message": "Task status updated successfully", "task": task}

    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.put("/tasks")
async def update_task(request: Request):
    data = await request.json()

    pickup_id = data.get("pickupId")
    bwg_id = data.get("bwgId")
    driver_id = data.get("driverId")
    vehicle_id = data.get("vehicleId")
    supervisor_id = data.get("supervisorId")
    scheduled_date = data.get("scheduledDate")
    scheduled_time_slot = data.get("scheduledTimeSlot")
    location = data.get("location")

    if not pickup_id:
        raise HTTPException(400, "Missing pickupId")

    try:
        with get_db() as conn:
            cur = conn.cursor()
            conn.autocommit = False

            cur.execute(
                """
                SELECT trip_id FROM trips
                WHERE driver_id = %s AND vehicle_id = %s AND trip_date = %s
                """,
                (driver_id, vehicle_id, scheduled_date),
            )

            row = cur.fetchone()

            if row:
                trip_id = row[0]
                if supervisor_id:
                    cur.execute(
                        "UPDATE trips SET supervisor_id = %s WHERE trip_id = %s",
                        (supervisor_id, trip_id),
                    )
            else:
                cur.execute(
                    """
                    INSERT INTO trips (driver_id, vehicle_id, trip_date, supervisor_id, status)
                    VALUES (%s, %s, %s, %s, 'PENDING')
                    RETURNING trip_id
                    """,
                    (driver_id, vehicle_id, scheduled_date, supervisor_id),
                )
                trip_id = cur.fetchone()[0]

            cur.execute(
                """
                UPDATE pickups
                SET bwg_id = %s,
                    trip_id = %s,
                    scheduled_date = %s,
                    scheduled_time_slot = %s,
                    location = %s,
                    updated_at = NOW()
                WHERE pickup_id = %s
                RETURNING *
                """,
                (
                    bwg_id,
                    trip_id,
                    scheduled_date,
                    scheduled_time_slot,
                    location,
                    pickup_id,
                ),
            )

            row = cur.fetchone()
            cols = [d[0] for d in cur.description]
            task = dict(zip(cols, row)) if row else None

            if not task:
                conn.rollback()
                raise HTTPException(404, "Task not found")

            conn.commit()

        return {"message": "Task updated successfully", "task": task}

    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.delete("/tasks")
def delete_task(pickupId: Optional[str] = None):
    if not pickupId:
        raise HTTPException(400, "Missing pickupId")

    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                DELETE FROM pickups
                WHERE pickup_id = %s
                RETURNING pickup_id
                """,
                (pickupId,),
            )

            row = cur.fetchone()

        if not row:
            raise HTTPException(404, "Task not found")

        return {"message": "Task deleted successfully", "pickup_id": row[0]}

    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")
