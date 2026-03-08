from fastapi import APIRouter, HTTPException, Request
from app.database import get_db
from datetime import datetime, timedelta
from typing import List

router = APIRouter()


def generate_recurring_dates_by_weekday(
    start_date: str,
    weekdays: List[str],
    duration_days: int = 30  # 🔁 default = 1 month (editable later)
):
    """
    weekdays example: ["monday", "wednesday", "friday"]
    """
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = start + timedelta(days=duration_days)

    weekday_map = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }

    selected_days = {
        weekday_map[d.lower()]
        for d in weekdays
        if d.lower() in weekday_map
    }

    dates = []
    current = start

    while current <= end:
        if current.weekday() in selected_days:
            dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates


@router.post("/create-task")
async def admin_create_task(request: Request):
    data = await request.json()

    # Use the ID exactly as it comes from the frontend
    bwg_id = data.get("bwgId") 
    driver_id = str(data.get("driverId"))
    vehicle_id = data.get("vehicleId")
    supervisor_id = data.get("supervisorId")
    scheduled_date = data.get("scheduledDate")
    scheduled_time_slot = data.get("scheduledTimeSlot")
    location = data.get("location")
    recurring = data.get("recurring")

    # Validation
    missing = [f for f in ["bwgId", "driverId", "vehicleId", "scheduledDate", "scheduledTimeSlot", "location"] if not data.get(f)]
    if missing:
        raise HTTPException(status_code=400, detail={"message": f"Missing: {', '.join(missing)}"})

    try:
        with get_db() as conn:
            cur = conn.cursor()
            conn.autocommit = False

            # Determine source type based on ID format
            source_type = "ADDITIONAL_PICKUP" if "-P" in str(bwg_id) else "MAIN_BWG"

            # 1. Handle Trip Creation/Retrieval
            def get_or_create_trip(d_id, v_id, t_date, s_id):
                cur.execute(
                    "SELECT trip_id FROM trips WHERE driver_id = %s AND vehicle_id = %s AND trip_date = %s LIMIT 1",
                    (d_id, v_id, t_date)
                )
                row = cur.fetchone()
                if row:
                    if s_id: # Update supervisor if provided
                        cur.execute("UPDATE trips SET supervisor_id = %s WHERE trip_id = %s", (s_id, row[0]))
                    return row[0]
                
                cur.execute(
                    "INSERT INTO trips (driver_id, vehicle_id, trip_date, supervisor_id) VALUES (%s, %s, %s, %s) RETURNING trip_id",
                    (d_id, v_id, t_date, s_id)
                )
                return cur.fetchone()[0]

            insert_query = """
                INSERT INTO pickups (
                    bwg_id, trip_id, scheduled_date, scheduled_time_slot, 
                    location, status, source_type
                )
                VALUES (%s, %s, %s, %s, %s, 'PENDING', %s)
            """

            # 2. Process Task(s)
            if recurring and isinstance(recurring, list) and len(recurring) > 0:
                dates = generate_recurring_dates_by_weekday(scheduled_date, recurring)
                for date in dates:
                    t_id = get_or_create_trip(driver_id, vehicle_id, date, supervisor_id)
                    cur.execute(insert_query, (bwg_id, t_id, date, scheduled_time_slot, location, source_type))
            else:
                t_id = get_or_create_trip(driver_id, vehicle_id, scheduled_date, supervisor_id)
                cur.execute(insert_query, (bwg_id, t_id, scheduled_date, scheduled_time_slot, location, source_type))

            conn.commit()
            
            # Fetch BWG address from bwg table
            cur.execute(
                """
                SELECT b.address, b.organization
                FROM pickups p
                JOIN bwg b ON p.bwg_id = b.id
                WHERE p.trip_id = %s
                LIMIT 1
                """,
                (t_id,)
            )
            bwg_data = cur.fetchone()
            bwg_address = bwg_data[0] if bwg_data else None
            bwg_organization = bwg_data[1] if bwg_data else None
            
        return {
            "message": "Task created successfully",
            "bwg_address": bwg_address,
            "bwg_organization": bwg_organization,
            "trip_id": t_id
        }

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/tasks")
async def admin_update_task(request: Request):
    data = await request.json()

    # The UI might send a new bwgId if the user changed the location/entity
    pickup_id = data.get("pickupId")
    raw_bwg_id = data.get("bwgId")  # e.g., 'ORI0046-P1' or 'ORI0046'
    driver_id = str(data.get("driverId"))
    vehicle_id = data.get("vehicleId")
    supervisor_id = data.get("supervisorId")
    scheduled_date = data.get("scheduledDate")
    scheduled_time_slot = data.get("scheduledTimeSlot")
    location = data.get("location")

    if not all([pickup_id, raw_bwg_id, driver_id, vehicle_id, scheduled_date, scheduled_time_slot, location]):
        raise HTTPException(status_code=400, detail="Missing required fields")

    try:
        with get_db() as conn:
            cur = conn.cursor()
            conn.autocommit = False

            # --- START ID RESOLUTION (Same as Create Task) ---
            resolved_bwg_id = None
            source_type = "MAIN_BWG"

            # 1. Check if it's a primary BWG
            cur.execute("SELECT id FROM bwg WHERE id = %s", (raw_bwg_id,))
            if cur.fetchone():
                resolved_bwg_id = raw_bwg_id
            else:
                # 2. Check if it's an additional pickup address
                cur.execute("SELECT bwg_id FROM pickup_address WHERE id = %s", (raw_bwg_id,))
                pa_row = cur.fetchone()
                if pa_row:
                    resolved_bwg_id = pa_row[0]  # The parent (e.g., ORI0046)
                    source_type = "ADDITIONAL_PICKUP"
                else:
                    # If you dropped the FK constraint as discussed previously, 
                    # you can just use raw_bwg_id. If not, this check is mandatory.
                    resolved_bwg_id = raw_bwg_id 
            # --- END ID RESOLUTION ---

            # 1. Ensure pickup exists
            cur.execute("SELECT pickup_id FROM pickups WHERE pickup_id = %s", (pickup_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Pickup not found")

            # 2. Create/Update Trip (Creating a new trip for the specific edit)
            if supervisor_id:
                cur.execute(
                    """
                    INSERT INTO trips (driver_id, vehicle_id, trip_date, supervisor_id)
                    VALUES (%s, %s, %s, %s)
                    RETURNING trip_id
                    """,
                    (driver_id, vehicle_id, scheduled_date, supervisor_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO trips (driver_id, vehicle_id, trip_date)
                    VALUES (%s, %s, %s)
                    RETURNING trip_id
                    """,
                    (driver_id, vehicle_id, scheduled_date),
                )

            new_trip_id = cur.fetchone()[0]

            # 3. Update the pickup record
            # We update bwg_id to the resolved parent ID and store the specific source_type
            cur.execute(
                """
                UPDATE pickups
                SET
                    bwg_id = %s,
                    trip_id = %s,
                    scheduled_date = %s,
                    scheduled_time_slot = %s,
                    location = %s,
                    source_type = %s
                WHERE pickup_id = %s
                """,
                (
                    resolved_bwg_id,
                    new_trip_id,
                    scheduled_date,
                    scheduled_time_slot,
                    location,
                    source_type,
                    pickup_id,
                ),
            )

            conn.commit()

        return {"message": "Task updated successfully"}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))