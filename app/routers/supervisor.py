import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import os
import jwt
from app.routers.auth import create_token, decode_supervisor_from_cookie
import bcrypt

from app.database import get_db
from app.config import JWT_SECRET, TWILIO_VERIFY_SERVICE_SID
from app.services.twilio_client import TwilioClientSingleton

# Namespace the routes to avoid collisions with existing /auth endpoints
router = APIRouter(prefix="/supervisor", tags=["Supervisor"])

if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET not set in environment")


class SupervisorLoginBody(BaseModel):
    email: EmailStr
    password: str


class PhoneNumber(BaseModel):
    phone: str


class VerifyOTP(BaseModel):
    phone: str
    code: str


class TaskFilter(BaseModel):
    ward: Optional[str] = None
    driver_id: Optional[str] = None
    vehicle_id: Optional[int] = None
    status: Optional[str] = None


def _normalize_phone(phone: str) -> str:
    cleaned = phone.replace(" ", "").replace("-", "")
    if cleaned.startswith("+91"):
        cleaned = cleaned[3:]
    return cleaned.lstrip("0") or cleaned


def decode_supervisor_from_cookie(authorization: str = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")

    token = authorization.replace("Bearer ", "")
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/login")
def supervisor_login(body: dict, response: Response):
    phone = body.get("phone")

    if not phone:
        raise HTTPException(400, "Phone number is required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name FROM supervisors WHERE phone=%s LIMIT 1",
            (phone,)
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(404, "Driver not registered")
    supervisor_id = row[0]

    supervisor_id, name = row

    # Compare plain password with hashed password
    # if not bcrypt.checkpw(body.password.encode("utf-8"), password_hash.encode("utf-8")):
    #     raise HTTPException(status_code=401, detail="Invalid credentials")

    token_payload = {
        "supervisor_id": supervisor_id,
        "name": name,
        # "zone": zone,
        # "ward_number": ward_number,
        # "ward_name": ward_name,
        "role": "supervisor",
    }

    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
    try:
        httpx.post(
            f"{os.getenv('BACKEND_URL')}/otp/send",
            json={"phone": phone},
            timeout=3  # short timeout, fire-and-forget
        )
        return {"message": "OTP sent successfully", "token": token }

    except Exception as e:
        print("OTP SEND WARNING (ignored):", e)
        # ❗ Do NOT fail here

    return {
        "message": "OTP sent successfully", "token": token
    }

    max_age = 60 * 60 * 8  # 8 hours

    response.set_cookie(
        "supervisor_logged_in",
        "true",
        max_age=max_age,
    )
    response.set_cookie(
        "sessionToken-supervisor",
        token,
        httponly=True,
        max_age=max_age,
        path="/",
        secure=os.getenv("NODE_ENV") == "production",
    )

    return {
        "message": "Login successful",
        "token": token,
        "supervisor": {
            "id": supervisor_id,
            "name": name,
            "zone": zone,
            "ward_number": ward_number,
            "ward_name": ward_name,
        },
    }


@router.post("/auth/logout")
def supervisor_logout(response: Response):
    try:
        response.delete_cookie("supervisor_logged_in")
        response.delete_cookie("sessionToken-supervisor")
        return {"message": "Logout successful"}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/auth/send-otp")
def send_otp(data: PhoneNumber):
    phone = _normalize_phone(data.phone)

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name FROM supervisors 
            WHERE phone = %s OR phone LIKE %s OR phone LIKE %s
            """,
            (phone, f"%{phone.replace('+', '').replace('91', '')}%", phone.replace('+91', "")),
        )
        supervisor = cur.fetchone()

    #token = create_token({"supervisor_id": supervisor[0], "phone": phone, "role": "supervisor" })
    try:
        httpx.post(
            f"{os.getenv('BACKEND_URL')}/otp/send",
            json={"phone": phone},
            timeout=3  # short timeout, fire-and-forget
        )
        #return {"message": "OTP sent successfully", "token": token }

    except Exception as e:
        print("OTP SEND WARNING (ignored):", e)

    if not supervisor:
        raise HTTPException(status_code=404, detail="Supervisor not found. Contact admin to add your number.")

    # Testing mode: bypass Twilio and accept any OTP
    return {"status": "pending", "message": "Testing mode: OTP bypassed (use any code)"}


@router.post("/auth/verify-otp")
def verify_otp(data: VerifyOTP):
    phone = _normalize_phone(data.phone)
    
    # Verify OTP first
    try:
        response = httpx.post(
            f"{os.getenv('BACKEND_URL')}/otp/verify",
            json={"phone": phone, "code": data.code},
            timeout=10
        )
        
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")
            
        result = response.json()
        if result.get("status") != "approved":
            raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    
    except httpx.RequestError as e:
        print("OTP VERIFY ERROR:", e)
        raise HTTPException(status_code=503, detail="OTP verification service unavailable")
    except HTTPException:
        raise
    except Exception as e:
        print("OTP VERIFY WARNING:", e)
        raise HTTPException(status_code=400, detail="OTP verification failed")

    # OTP verified, now get supervisor details
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, name, zone, ward_number, ward_name, driver_assigned, vehicle_assigned, phone 
            FROM supervisors 
            WHERE phone = %s OR phone LIKE %s OR phone LIKE %s
            """,
            (phone, f"%{phone.replace('+', '').replace('91', '')}%", phone.replace('+91', "")),
        )
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Supervisor not found")

    supervisor_id, name, zone, ward_number, ward_name, driver_assigned, vehicle_assigned, phone_number = row

    token_payload = {
        "supervisor_id": supervisor_id,
        "name": name,
        "zone": zone,
        "ward_number": ward_number,
        "ward_name": ward_name,
        "role": "SUPERVISOR",
    }

    token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")

    return {
        "message": "Login successful",
        "token": token,
        "supervisor": {
            "id": supervisor_id,
            "name": name,
            "zone": zone,
            "ward_number": ward_number,
            "ward_name": ward_name,
        },
    }


@router.get("/dashboard/stats")
def get_dashboard_stats(supervisor_data: dict = Depends(decode_supervisor_from_cookie)):
    supervisor_id = supervisor_data["supervisor_id"]

    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT COUNT(*) FROM pickups p
                JOIN trips t ON p.trip_id = t.trip_id
                WHERE t.supervisor_id = %s 
                AND DATE(p.scheduled_date) = CURRENT_DATE
                """,
                (supervisor_id,),
            )
            todays_pickups = cur.fetchone()[0] or 0

            cur.execute(
                """
                SELECT COUNT(*) FROM pickups p
                JOIN trips t ON p.trip_id = t.trip_id
                WHERE t.supervisor_id = %s 
                AND p.status = 'DONE'
                AND DATE(p.scheduled_date) = CURRENT_DATE
                """,
                (supervisor_id,),
            )
            completed_tasks = cur.fetchone()[0] or 0

            cur.execute(
                """
                SELECT COUNT(*) FROM pickups p
                JOIN trips t ON p.trip_id = t.trip_id
                WHERE t.supervisor_id = %s 
                AND p.status = 'PENDING'
                AND DATE(p.scheduled_date) = CURRENT_DATE
                """,
                (supervisor_id,),
            )
            pending_tasks = cur.fetchone()[0] or 0

            cur.execute(
                """
                SELECT COUNT(DISTINCT t.driver_id) FROM trips t
                WHERE t.supervisor_id = %s 
                AND DATE(t.trip_date) = CURRENT_DATE
                """,
                (supervisor_id,),
            )
            drivers_on_duty = cur.fetchone()[0] or 0

            cur.execute(
                """
                SELECT COUNT(*) as total_vehicles
                FROM vehicles 
                WHERE supervisor_id = %s
                """,
                (supervisor_id,),
            )
            vehicle_count = cur.fetchone()[0] or 0
            active_vehicles = vehicle_count
            inactive_vehicles = 0

        return {
            "todays_pickups": todays_pickups,
            "completed_tasks": completed_tasks,
            "pending_tasks": pending_tasks,
            "drivers_on_duty": drivers_on_duty,
            "active_vehicles": active_vehicles,
            "inactive_vehicles": inactive_vehicles,
        }
    except Exception:
        return {
            "todays_pickups": 0,
            "completed_tasks": 0,
            "pending_tasks": 0,
            "drivers_on_duty": 0,
            "active_vehicles": 0,
            "inactive_vehicles": 0,
        }


@router.post("/tasks/list")
def get_tasks(filters: TaskFilter, supervisor_data: dict = Depends(decode_supervisor_from_cookie)):
    supervisor_id = supervisor_data.get("supervisor_id")

    query = """
       SELECT 
    p.pickup_id,
    p.bwg_id,

    /* BWG / Pickup name */
    CASE 
        WHEN p.source_type = 'MAIN_BWG' THEN b.organization
        WHEN p.source_type = 'ADDITIONAL_PICKUP' THEN pa.organization_name
    END AS bwg_name,

    t.driver_id,
    d.name AS driver_name,
    t.vehicle_id,
    v.registration_number AS vehicle_number,
    p.status,
    p.scheduled_date,
    p.updated_at AS completed_at,

    /* Ward number */
    CASE 
        WHEN p.source_type = 'MAIN_BWG' THEN b.ward_number
        WHEN p.source_type = 'ADDITIONAL_PICKUP' THEN w.ward_number
    END AS ward_number,

    /* Ward name */
    CASE 
        WHEN p.source_type = 'MAIN_BWG' THEN b.ward_name
        WHEN p.source_type = 'ADDITIONAL_PICKUP' THEN w.ward_name
    END AS ward_name,

    /* Zone */
    CASE 
        WHEN p.source_type = 'MAIN_BWG' THEN b.zone
        WHEN p.source_type = 'ADDITIONAL_PICKUP' THEN w.zone_name
    END AS zone_name

FROM pickups p

/* MAIN BWG */
LEFT JOIN bwg b
  ON p.source_type = 'MAIN_BWG'
 AND p.bwg_id = b.id

/* ADDITIONAL PICKUP */
LEFT JOIN pickup_address pa
  ON p.source_type = 'ADDITIONAL_PICKUP'
 AND p.bwg_id = pa.id

/* WARD LOOKUP */
LEFT JOIN wards w
  ON p.source_type = 'ADDITIONAL_PICKUP'
 AND CAST(pa.ward AS INTEGER) = w.ward_number
 AND pa.zone_id = w.zone_id

LEFT JOIN trips t ON p.trip_id = t.trip_id
LEFT JOIN driver d ON t.driver_id = d.id
LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id

WHERE t.supervisor_id = %s
AND p.scheduled_date <= CURRENT_DATE
ORDER BY p.scheduled_date DESC
    """

    params = [supervisor_id]

    if filters.ward:
        query += " AND b.ward_number = %s"
        params.append(filters.ward)

    if filters.driver_id:
        query += " AND t.driver_id = %s"
        params.append(filters.driver_id)

    if filters.vehicle_id:
        query += " AND t.vehicle_id = %s"
        params.append(filters.vehicle_id)

    if filters.status:
        query += " AND p.status = %s"
        params.append(filters.status)

    # query += " ORDER BY p.scheduled_date DESC LIMIT 100"

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()

    tasks = []
    for row in rows:
        tasks.append(
            {
                "pickup_id": row[0],
                "bwg_id": row[1],
                "bwg_name": row[2],
                "driver_id": row[3],
                "driver_name": row[4],
                "vehicle_id": row[5],
                "vehicle_number": row[6],
                "status": row[7],
                "scheduled_date": row[8].isoformat() if row[8] else None,
                "completed_at": row[9].isoformat() if row[9] else None,
                "ward_number": row[10],
                "ward_name": row[11],
            }
        )

    return {"tasks": tasks}


@router.get("/tasks/filters")
def get_task_filters(supervisor_data: dict = Depends(decode_supervisor_from_cookie)):
    supervisor_id = supervisor_data.get("supervisor_id")

    try:
        with get_db() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT DISTINCT
    CASE 
        WHEN p.source_type = 'MAIN BWG' THEN b.ward_number
        WHEN p.source_type = 'ADDITIONAL PICKUP' THEN pa.ward_number
    END AS ward_number,

    CASE 
        WHEN p.source_type = 'MAIN BWG' THEN b.ward_name
        WHEN p.source_type = 'ADDITIONAL PICKUP' THEN pa.ward_name
    END AS ward_name

FROM pickups p
LEFT JOIN bwg b ON p.bwg_id = b.id
LEFT JOIN pickup_address pa ON p.pickup_address_id = pa.id
JOIN trips t ON p.trip_id = t.trip_id
WHERE t.supervisor_id = %s
ORDER BY ward_number

                """,
                (supervisor_id,),
            )
            wards = [{"number": row[0], "name": row[1]} for row in cur.fetchall()]

            try:
                cur.execute(
                    """
                    SELECT DISTINCT d.id, d.name 
                    FROM pickups p
                    JOIN trips t ON p.trip_id = t.trip_id
                    JOIN driver d ON t.driver_id = d.id
                    WHERE t.supervisor_id = %s
                    ORDER BY d.name
                    """,
                    (supervisor_id,),
                )
                drivers = [{"id": row[0], "name": row[1]} for row in cur.fetchall()]
            except Exception:
                drivers = []

            try:
                cur.execute(
                    """
                    SELECT DISTINCT v.vehicle_id, v.registration_number 
                    FROM pickups p
                    JOIN trips t ON p.trip_id = t.trip_id
                    JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                    WHERE t.supervisor_id = %s
                    ORDER BY v.registration_number
                    """,
                    (supervisor_id,),
                )
                vehicles = [{"id": row[0], "number": row[1]} for row in cur.fetchall()]
            except Exception:
                vehicles = []

        return {
            "wards": wards,
            "drivers": drivers,
            "vehicles": vehicles,
            "statuses": ["PENDING", "DONE", "MISSED"],
        }
    except Exception:
        return {
            "wards": [],
            "drivers": [],
            "vehicles": [],
            "statuses": ["PENDING", "DONE", "MISSED"],
        }


@router.get("/grievances")
def get_grievances(supervisor_data: dict = Depends(decode_supervisor_from_cookie)):
    supervisor_id = supervisor_data.get("supervisor_id")

    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT 
                    g.id,
                    g.bwg_id,
                    b.organization as bwg_name,
                    b.phone as bwg_phone,
                    g.category,
                    g.description,
                    g.status,
                    g.created_at,
                    g.resolved_at,
                    b.ward_number,
                    b.ward_name
                FROM grievances g
                JOIN bwg b ON g.bwg_id = b.id
                WHERE g.supervisors_at_submission_id = %s
                ORDER BY g.created_at DESC
                LIMIT 100
                """,
                (supervisor_id,),
            )

            rows = cur.fetchall()
            grievances = []
            for row in rows:
                grievances.append(
                    {
                        "grievance_id": row[0],
                        "bwg_id": row[1],
                        "bwg_name": row[2],
                        "bwg_phone": row[3],
                        "category": row[4],
                        "description": row[5],
                        "status": row[6],
                        "submitted_at": row[7].isoformat() if row[7] else None,
                        "resolved_at": row[8].isoformat() if row[8] else None,
                        "ward_number": row[9],
                        "ward_name": row[10],
                    }
                )

        return {"grievances": grievances}
    except Exception:
        return {"grievances": []}


@router.get("/notifications")
def get_notifications(supervisor_data: dict = Depends(decode_supervisor_from_cookie)):
    supervisor_id = supervisor_data.get("supervisor_id")

    notifications = []

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT 
                p.pickup_id,
                b.organization as bwg_name,
                p.scheduled_date,
                'missed_pickup' as type
            FROM pickups p
            JOIN bwg b ON p.bwg_id = b.id
            JOIN trips t ON p.trip_id = t.trip_id
            WHERE t.supervisor_id = %s 
            AND p.status = 'MISSED'
            AND p.scheduled_date >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY p.scheduled_date DESC
            LIMIT 10
            """,
            (supervisor_id,),
        )

        for row in cur.fetchall():
            notifications.append(
                {
                    "id": f"pickup_{row[0]}",
                    "type": "missed_pickup",
                    "title": "Missed Pickup Alert",
                    "message": f"Pickup missed for {row[1]} on {row[2]}",
                    "timestamp": datetime.now().isoformat(),
                }
            )

        cur.execute(
            """
            SELECT 
                g.id,
                b.organization as bwg_name,
                g.category,
                g.created_at
            FROM grievances g
            JOIN bwg b ON g.bwg_id = b.id
            WHERE g.supervisors_at_submission_id = %s 
            AND g.status = 'Open'
            AND g.created_at >= CURRENT_DATE - INTERVAL '7 days'
            ORDER BY g.created_at DESC
            LIMIT 10
            """,
            (supervisor_id,),
        )

        for row in cur.fetchall():
            notifications.append(
                {
                    "id": f"grievance_{row[0]}",
                    "type": "new_grievance",
                    "title": "New Grievance",
                    "message": f"{row[1]} raised a {row[2]} grievance",
                    "timestamp": row[3].isoformat() if row[3] else None,
                }
            )

    notifications.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    return {"notifications": notifications[:50]}


@router.get("/profile")
def get_profile(supervisor_data: dict = Depends(decode_supervisor_from_cookie)):
    supervisor_id = supervisor_data.get("supervisor_id")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT 
                s.id,
                s.name,
                s.phone,
                s.gmail,
                s.zone,
                s.ward_number,
                s.ward_name,
                s.created_at
            FROM supervisors s
            WHERE s.id = %s
            """,
            (supervisor_id,),
        )

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Supervisor not found")

        cur.execute(
            """
            SELECT DISTINCT ward_number, ward_name 
            FROM bwg 
            WHERE supervisor_id = %s
            ORDER BY ward_number
            """,
            (supervisor_id,),
        )

        assigned_wards = [{"number": r[0], "name": r[1]} for r in cur.fetchall()]

    return {
        "id": row[0],
        "name": row[1],
        "contact_number": row[2],
        "email": row[3],
        "zone": row[4],
        "ward_number": row[5],
        "ward_name": row[6],
        "assigned_wards": assigned_wards,
        "joined_date": row[7].isoformat() if row[7] else None,
    }
