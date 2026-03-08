from fastapi import APIRouter, Request, HTTPException, Depends, status, UploadFile, File, Form
from pydantic import BaseModel, EmailStr
from jose import jwt, JWTError
from passlib.context import CryptContext
from psycopg2.extras import RealDictCursor
import os
from typing import Optional
import boto3
from uuid import uuid4
from app.database import get_db

router = APIRouter()
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_BUCKET_NAME = os.getenv("S3_BUCKET_NAME") or os.getenv("AWS_BUCKET_NAME")

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)
JWT_SECRET = os.getenv("JWT_SECRET")
ALGORITHM = "HS256"

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET not set")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_token(request: Request, cookie_name: str) -> Optional[str]:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        if token and token not in ("undefined", "null"):
            return token
    return request.cookies.get(cookie_name)

def get_driver_id(request: Request) -> int:
    token = get_token(request, "sessionToken-driver")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized: Token missing")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or expired token")
    driver_id = payload.get("driver_id")
    if not driver_id:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token payload")
    return str(driver_id)

class DriverSignupRequest(BaseModel):
    name: str
    email: EmailStr
    phone: str
    license: str
    password: str

@router.post("/signup", status_code=201)
def driver_signup(payload: DriverSignupRequest):
    try:
        hashed_password = pwd_context.hash(payload.password)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO drivers (name, email, phone, license, password_hash, status)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                    RETURNING id, email, status;
                """, (
                    payload.name,
                    payload.email,
                    payload.phone,
                    payload.license,
                    hashed_password
                ))
                driver = cur.fetchone()
        return {
            "message": "Signup successful! Wait for admin approval.",
            "driver": {
                "id": driver[0],
                "email": driver[1],
                "status": driver[2]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class PickupStatusUpdate(BaseModel):
    pickupId: int
    status: str

@router.post("/pickup/status")
def update_pickup_status(
    payload: PickupStatusUpdate,
    driver_id: str = Depends(get_driver_id)
):
    if payload.status not in ["DONE", "MISSED"]:
        raise HTTPException(400, "Status must be DONE or MISSED")
    try:
        with get_db() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE pickups p
SET status = %s, actual_pickup_timestamp = NOW()
FROM trips t
WHERE p.pickup_id = %s
  AND p.trip_id = t.trip_id
  AND t.driver_id = %s
  AND p.status = 'PENDING'
RETURNING p.trip_id, p.pickup_id, p.status,
          p.scheduled_time_slot, p.actual_pickup_timestamp,
          (SELECT organization FROM bwg WHERE id = p.bwg_id) AS bwg_organization_name,
          (SELECT location FROM bwg WHERE id = p.bwg_id) AS bwg_address;

                """, (payload.status, payload.pickupId, driver_id))
                pickup = cur.fetchone()
                if not pickup:
                    raise HTTPException(404, "Pickup not found or already completed")
                trip_id = pickup["trip_id"]
                cur.execute("""
                    UPDATE trips
                    SET status = 'PENDING'
                    WHERE trip_id = %s AND status = 'SCHEDULED'
                """, (trip_id,))
                cur.execute("""
                    SELECT COUNT(*) FROM pickups
                    WHERE trip_id = %s AND status = 'PENDING'
                """, (trip_id,))
                remaining = int(cur.fetchone()["count"])
                if remaining == 0:
                    cur.execute("""
                        UPDATE trips SET status = 'COMPLETED'
                        WHERE trip_id = %s
                    """, (trip_id,))
                # After updating pickup and possibly trip
                cur.execute("""
                    SELECT status FROM trips WHERE trip_id = %s
                """, (trip_id,))
                trip_status = cur.fetchone()["status"]

                pickup["trip_status"] = trip_status
                return pickup

    except Exception as e:
        print(f"Error in update_pickup_status: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class TripStatusUpdate(BaseModel):
    tripId: int
    status: str

@router.post("/trip/status")
def update_trip_status(
    payload: TripStatusUpdate,
    driver_id: str = Depends(get_driver_id)
):
    if payload.status not in ["PENDING", "COMPLETED"]:
        raise HTTPException(400, "Invalid trip status")

    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                UPDATE trips
                SET status = %s
                WHERE trip_id = %s AND driver_id = %s
                RETURNING trip_id, status;
            """, (payload.status, payload.tripId, driver_id))

            trip = cur.fetchone()

            if not trip:
                raise HTTPException(404, "Trip not found")

            return trip


@router.get("/tasks")
def get_today_driver_tasks(request: Request, driver_id: str = Depends(get_driver_id)):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:

            # 1️⃣ Fetch ALL trips for today
            cur.execute("""
                SELECT
                    t.trip_id,
                    t.trip_date,
                    t.status AS trip_status,
                    v.registration_number AS vehicle_number
                FROM trips t
                LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                WHERE t.driver_id = %s
                  AND t.trip_date = CURRENT_DATE
            """, (driver_id,))

            trips = cur.fetchall()

            if not trips:
                return []

            # 2️⃣ Attach pickups for each trip (SOURCE-AWARE)
            for trip in trips:
                cur.execute("""
                    SELECT
                        p.pickup_id, p.bwg_id,
                        p.status,
                        p.scheduled_time_slot,
                        p.actual_pickup_timestamp,

                        /* SAME FIELD NAMES FOR FRONTEND */
                        CASE
                            WHEN p.source_type = 'MAIN_BWG'
                                THEN b.organization
                            WHEN p.source_type = 'ADDITIONAL_PICKUP'
                                THEN pa.organization_name
                        END AS bwg_organization_name,
                            
                        /* DISPLAY ADDRESS (TEXT) */
                        CASE
                            WHEN p.source_type = 'MAIN_BWG'
                                THEN b.address
                            WHEN p.source_type = 'ADDITIONAL_PICKUP'
                                THEN pa.address
                        END AS display_address,

                        /* For Navigate (Coordinates) */
                        CASE
                            WHEN p.source_type = 'MAIN_BWG'
                                THEN b.location
                            WHEN p.source_type = 'ADDITIONAL_PICKUP'
                                THEN pa.location
                        END AS bwg_address

                    FROM pickups p

                    /* MAIN BWG */
                    LEFT JOIN bwg b
                        ON p.source_type = 'MAIN_BWG'
                       AND p.bwg_id = b.id

                    /* ADDITIONAL PICKUP */
                    LEFT JOIN pickup_address pa
                        ON p.source_type = 'ADDITIONAL_PICKUP'
                       AND p.bwg_id = pa.id

                    WHERE p.trip_id = %s
                    ORDER BY p.scheduled_time_slot;
                """, (trip["trip_id"],))

                trip["pickups"] = cur.fetchall()

            return trips


@router.get("/supervisor")
def get_assigned_supervisor(driver_id: str = Depends(get_driver_id)):
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    s.id,
                    s.name,
                    s.phone,
                    s.gmail,
                    s.zone,
                    s.ward_number,
                    s.ward_name
                FROM supervisors s
                WHERE s.driver_assigned = %s
                LIMIT 1
                """,
                (driver_id,),
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Supervisor not assigned")

    return {
        "supervisor": {
            "id": row["id"],
            "name": row["name"],
            "contact_number": row["phone"],
            "email": row["gmail"],
            "zone": row["zone"],
            "ward_number": row["ward_number"],
            "ward_name": row["ward_name"],
        }
    }


@router.get("/notifications")
def get_driver_notifications(driver_id: str = Depends(get_driver_id)):
    """Fetch notifications for the authenticated driver based on their trips and pickups"""
    with get_db() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            notifications = []
            
            # 1. Trip assignments
            cur.execute("""
                SELECT 
                    t.trip_id,
                    t.trip_date,
                    t.created_at,
                    COUNT(p.pickup_id) as pickup_count
                FROM trips t
                LEFT JOIN pickups p ON t.trip_id = p.trip_id
                WHERE t.driver_id = %s 
                  AND t.created_at >= NOW() - INTERVAL '7 days'
                GROUP BY t.trip_id, t.trip_date, t.created_at
                ORDER BY t.created_at DESC
            """, (driver_id,))
            
            trips = cur.fetchall()
            for trip in trips:
                notifications.append({
                    "id": f"trip_{trip['trip_id']}",
                    "message": f"New trip assigned for {trip['trip_date']} with {trip['pickup_count']} pickups",
                    "date": trip['created_at'].strftime('%Y-%m-%d'),
                    "read": False
                })
            
            # 2. Supervisor assignments
            cur.execute("""
                SELECT s.name, s.updated_at
                FROM supervisors s
                WHERE s.driver_assigned = %s
                  AND s.updated_at >= NOW() - INTERVAL '7 days'
                ORDER BY s.updated_at DESC
                LIMIT 5
            """, (driver_id,))
            
            supervisors = cur.fetchall()
            for sup in supervisors:
                notifications.append({
                    "id": f"supervisor_{sup['updated_at'].timestamp()}",
                    "message": f"Supervisor {sup['name']} assigned to you",
                    "date": sup['updated_at'].strftime('%Y-%m-%d'),
                    "read": True
                })
            
    notifications.sort(key=lambda x: x['date'], reverse=True)
    return {"notifications": notifications[:20]}



class DriverLocationBody(BaseModel):
    lat: float
    lng: float
    speed: Optional[float] = None
    heading: Optional[float] = None

@router.post("/location")
def update_driver_location(
    request: Request,
    data: DriverLocationBody,
    driver_id: str = Depends(get_driver_id)
):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO driver_live_location
                        (driver_id, latitude, longitude, speed, heading, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (driver_id)
                    DO UPDATE SET
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        speed = EXCLUDED.speed,
                        heading = EXCLUDED.heading,
                        updated_at = NOW()
                    RETURNING driver_id, latitude, longitude, speed, heading, updated_at;
                """, (
                    driver_id,
                    data.lat,
                    data.lng,
                    data.speed,
                    data.heading
                ))
                row = cur.fetchone()
        return {
            "driver_id": row[0],
            "lat": float(row[1]),
            "lng": float(row[2]),
            "speed": float(row[3]) if row[3] is not None else None,
            "heading": float(row[4]) if row[4] is not None else None,
            "updated_at": row[5],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/upload_photo")
def upload_driver_pickup_photo(
    driver_id: str = Form(...),
    trip_id: str = Form(...),
    bwg_id: str = Form(...),
    photo: UploadFile = File(...),
):
    try:
        if photo.content_type not in ["image/jpeg", "image/png", "image/jpg"]:
            raise HTTPException(status_code=400, detail="Invalid image format")

        # Convert trip_id to int
        try:
            trip_id_int = int(trip_id)
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid trip_id format")

        extension = photo.filename.split(".")[-1]
        filename = f"{uuid4()}.{extension}"
        s3_key = f"driver-uploads/{filename}"

        s3_client.upload_fileobj(
            photo.file,
            AWS_BUCKET_NAME,
            s3_key,
            ExtraArgs={"ContentType": photo.content_type},
        )

        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO driver_pickup_photo
                (driver_id, trip_id, bwg_id, s3_key)
                VALUES (%s, %s, %s, %s)
                RETURNING id;
                """,
                (driver_id, trip_id_int, bwg_id, s3_key),
            )
            record_id = cur.fetchone()[0]
            conn.commit()

        return {
            "message": "Photo uploaded successfully",
            "id": record_id,
            "s3_key": s3_key,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in upload_driver_pickup_photo: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))