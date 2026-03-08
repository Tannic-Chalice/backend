# app/router/driver.py
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr
from typing import Optional

from app.database import get_db
from app.services.password_utils import hash_password
from app.routers.auth import decode_driver_id_from_cookie

router = APIRouter(tags=["Driver"])


# ---------------------------
# Location schemas
# ---------------------------

class DriverLocationBody(BaseModel):
    lat: float
    lng: float
    speed: Optional[float] = None
    heading: Optional[float] = None


# ---------------------------
# 1) DRIVER SIGNUP  (POST /driver/signup)
# ---------------------------

class DriverSignupBody(BaseModel):
    name: str
    email: EmailStr
    phone: str
    license: str
    password: str


@router.post("/signup")
async def driver_signup(data: DriverSignupBody):
    hashed = hash_password(data.password)

    query = """
        INSERT INTO drivers (name, email, phone, license, password_hash, status)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, email, status
    """

    with get_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute(
                query,
                (
                    data.name,
                    data.email,
                    data.phone,
                    data.license,
                    hashed,
                    "pending",
                ),
            )
            row = cur.fetchone()
        except Exception as e:
            raise HTTPException(status_code=500, detail="Error creating driver account.")

    driver = {
        "id": row[0],
        "email": row[1],
        "status": row[2],
    }

    return {
        "message": "Signup successful! Wait for admin approval.",
        "driver": driver,
    }


# ---------------------------
# 1b) UPDATE LIVE LOCATION  (POST /driver/location)
# ---------------------------

@router.post("/location")
async def upsert_driver_location(request: Request, data: DriverLocationBody):
    driver_id = decode_driver_id_from_cookie(request)
    print("LIVE LOCATION driver_id =", driver_id)

    if not driver_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = """
        INSERT INTO driver_live_location (
            driver_id, latitude, longitude, speed, heading, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (driver_id)
        DO UPDATE SET
            latitude = EXCLUDED.latitude,
            longitude = EXCLUDED.longitude,
            speed = EXCLUDED.speed,
            heading = EXCLUDED.heading,
            updated_at = NOW()
        RETURNING driver_id, latitude, longitude, speed, heading, updated_at;
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            query,
            (driver_id, data.lat, data.lng, data.speed, data.heading),
        )
        row = cur.fetchone()
        conn.commit()

    return {
        "driver_id": row[0],
        "lat": float(row[1]),
        "lng": float(row[2]),
        "speed": float(row[3]) if row[3] is not None else None,
        "heading": float(row[4]) if row[4] is not None else None,
        "updated_at": row[5],
    }


@router.put("/location")
async def update_driver_location_only(request: Request, data: DriverLocationBody):
    driver_id = decode_driver_id_from_cookie(request)

    if not driver_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    query = """
        UPDATE driver_live_location
        SET
            latitude = %s,
            longitude = %s,
            speed = %s,
            heading = %s,
            updated_at = NOW()
        WHERE driver_id = %s
        RETURNING driver_id, latitude, longitude, speed, heading, updated_at;
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            query,
            (data.lat, data.lng, data.speed, data.heading, driver_id),
        )
        row = cur.fetchone()
        conn.commit()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Driver location not found. Use POST /location first."
        )

    return {
        "driver_id": row[0],
        "lat": float(row[1]),
        "lng": float(row[2]),
        "speed": float(row[3]) if row[3] is not None else None,
        "heading": float(row[4]) if row[4] is not None else None,
        "updated_at": row[5],
    }


# ---------------------------
# 2) DRIVER TASKS TODAY  (GET /driver/tasks)
# ---------------------------

@router.get("/tasks")
async def driver_tasks(request: Request):
    driver_id = decode_driver_id_from_cookie(request)

    query = """
      SELECT 
        t.trip_id,
        t.trip_date,
        t.status AS trip_status,
        v.registration_number AS vehicle_number,
        p.pickup_id,
        p.status AS pickup_status,
        p.scheduled_time_slot,
        p.actual_pickup_timestamp,
        b.organization AS bwg_organization_name,
        b.location AS bwg_address
      FROM trips t
      JOIN pickups p ON t.trip_id = p.trip_id
      JOIN vehicles v ON t.vehicle_id = v.vehicle_id
      JOIN bwg b ON p.bwg_id = b.id
      WHERE t.driver_id = %s AND t.trip_date = CURRENT_DATE
      ORDER BY p.scheduled_time_slot;
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (driver_id,))
        rows = cur.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="No trip assigned for you today.")

    first = rows[0]
    response = {
        "trip_id": first[0],
        "trip_date": first[1],
        "trip_status": first[2],
        "vehicle_number": first[3],
        "pickups": [
            {
                "pickup_id": r[4],
                "status": r[5],
                "scheduled_time_slot": r[6],
                "actual_pickup_timestamp": r[7],
                "bwg_organization_name": r[8],
                "bwg_address": r[9],
            }
            for r in rows
        ],
    }

    return response


# ---------------------------
# 3) UPDATE PICKUP  (POST /driver/update-pickup)
# ---------------------------

class UpdatePickupBody(BaseModel):
    pickupId: int
    status: str  # 'DONE' or 'MISSED'


@router.post("/update-pickup")
async def update_pickup(request: Request, data: UpdatePickupBody):
    if data.status not in ["DONE", "MISSED"]:
        raise HTTPException(
            status_code=400,
            detail="Valid Pickup ID and status (DONE or MISSED) are required.",
        )

    driver_id = decode_driver_id_from_cookie(request)

    with get_db() as conn:
        conn.autocommit = False
        cur = conn.cursor()
        try:
            update_pickup_query = """
              UPDATE pickups p
              SET status = %s, actual_pickup_timestamp = NOW()
              FROM trips t
              WHERE p.pickup_id = %s
                AND p.trip_id = t.trip_id
                AND t.driver_id = %s
                AND p.status = 'PENDING'
              RETURNING p.trip_id,
                p.pickup_id, p.status, p.scheduled_time_slot,
                p.actual_pickup_timestamp, 
                (SELECT organization FROM bwg WHERE bwg.id = p.bwg_id) as bwg_organization_name,
                (SELECT location FROM bwg WHERE bwg.id = p.bwg_id) as bwg_address;
            """
            cur.execute(
                update_pickup_query,
                (data.status, data.pickupId, driver_id),
            )
            pickup_row = cur.fetchone()

            if not pickup_row:
                conn.rollback()
                raise HTTPException(
                    status_code=404,
                    detail="Pickup not found, not assigned to you, or already completed.",
                )

            trip_id = pickup_row[0]

            cur.execute(
                "UPDATE trips SET status = 'PENDING' WHERE trip_id = %s AND status = 'SCHEDULED'",
                (trip_id,),
            )

            cur.execute(
                "SELECT COUNT(*) FROM pickups WHERE trip_id = %s AND status = 'PENDING'",
                (trip_id,),
            )
            remaining_count = int(cur.fetchone()[0])

            if remaining_count == 0:
                cur.execute(
                    "UPDATE trips SET status = 'COMPLETED' WHERE trip_id = %s",
                    (trip_id,),
                )

            conn.commit()
        except HTTPException:
            raise
        except Exception as e:
            conn.rollback()
            raise HTTPException(
                status_code=500, detail="Internal Server Error"
            )

    updated_pickup = {
        "trip_id": pickup_row[0],
        "pickup_id": pickup_row[1],
        "status": pickup_row[2],
        "scheduled_time_slot": pickup_row[3],
        "actual_pickup_timestamp": pickup_row[4],
        "bwg_organization_name": pickup_row[5],
        "bwg_address": pickup_row[6],
    }

    return updated_pickup


# ---------------------------
# 4) UPDATE TRIP  (POST /driver/update-trip)
# ---------------------------

class UpdateTripBody(BaseModel):
    tripId: int
    status: str  # 'PENDING' or 'COMPLETED'


@router.post("/update-trip")
async def update_trip(request: Request, data: UpdateTripBody):
    if data.status not in ["PENDING", "COMPLETED"]:
        raise HTTPException(
            status_code=400,
            detail="A valid status (PENDING, COMPLETED) is required.",
        )

    driver_id = decode_driver_id_from_cookie(request)

    query = """
      UPDATE trips
      SET status = %s
      WHERE trip_id = %s
      AND driver_id = %s
      AND status != 'COMPLETED'
      RETURNING trip_id, status;
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (data.status, data.tripId, driver_id))
        row = cur.fetchone()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Trip not found, not assigned to you, or already completed.",
        )

    updated_trip = {
        "trip_id": row[0],
        "status": row[1],
    }

    return updated_trip