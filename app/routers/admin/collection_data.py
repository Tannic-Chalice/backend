from fastapi import APIRouter, HTTPException
from app.database import get_db
from datetime import datetime
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel
from typing import Optional
import random
import logging

router = APIRouter(tags=["collection-data"])

logger = logging.getLogger("uvicorn.error")

# -------------------------------------------------------------------
# MODELS
# -------------------------------------------------------------------

class VehicleLookupRequest(BaseModel):
    vehicle_number: str


class VehicleLogRequest(BaseModel):
    vehicle_id: int
    log_date: Optional[str] = None
    shift: Optional[str] = None
    driver_id: Optional[str] = None
    supervisor_id: Optional[int] = None
    zone_id: Optional[int] = None
    ward_id: Optional[int] = None
    corporation: Optional[str] = None
    weigh_bridge_id: Optional[int] = None
    remarks: Optional[str] = None
    ward_number: Optional[int] = None
    ward_id: Optional[int] = None
    ward_name: Optional[str] = None


class WeighBridgeDataRequest(BaseModel):
    vehicle_number: str
    weigh_date: Optional[str] = None
    gross_weight: Optional[float] = None
    tare_weight: Optional[float] = None
    time: Optional[str] = None  # Added missing field
    ward_name: Optional[str] = None  # Added missing field
    ward_number: Optional[int] = None  # Added missing field
    zone_name: Optional[str] = None  # Added missing field
    # net_weight removed from request, will be auto-calculated


# -------------------------------------------------------------------
# BWG WISE COLLECTION REPORT
# -------------------------------------------------------------------

@router.get("/bwg-collection-reports")
def get_bwg_collection_reports():
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT 
                    vl.log_id,
                    vl.log_date,
                    vl.corporation,
                    vl.ward_id,
                    vl.vehicle_id,
                    v.registration_number AS vehicle_number,
                    w.ward_number,
                    w.ward_name
                FROM vehicle_logs vl
                LEFT JOIN vehicles v ON vl.vehicle_id = v.vehicle_id
                LEFT JOIN wards w ON vl.ward_id = w.id
                ORDER BY vl.log_date DESC
                LIMIT 100
            """)

            logs = cur.fetchall()
            print(f"[DEBUG] get_bwg_collection_reports: fetched {len(logs)} rows from vehicle_logs")
            result = []

            for log in logs:
                log_dict = dict(log)

                if log_dict.get("ward_number"):
                    cur.execute("""
                        SELECT id, organization
                        FROM bwg
                        WHERE CAST(ward_number AS TEXT) = %s
                        LIMIT 1
                    """, (str(log_dict["ward_number"]),))

                    bwg = cur.fetchone()
                    log_dict["bwg_id"] = bwg["id"] if bwg else None
                    log_dict["bwg_name"] = bwg["organization"] if bwg else None
                else:
                    log_dict["bwg_id"] = None
                    log_dict["bwg_name"] = None

                result.append(log_dict)

            print(f"[DEBUG] get_bwg_collection_reports: returning {len(result)} rows")
            cur.close()
            return result

    except Exception as e:
        print(f"[DEBUG] get_bwg_collection_reports: error {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# DEBUG – WEIGHT BRIDGE DATA
# -------------------------------------------------------------------

@router.get("/debug-weigh-data")
def debug_weigh_data():
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT 
                    wb.sl_no,
                    wb.vehicle_no,
                    wb.date AS weigh_date,
                    wb.time,
                    v.registration_number,
                    v.vehicle_id
                FROM weight_bridge wb
                LEFT JOIN vehicles v
                  ON LOWER(TRIM(wb.vehicle_no)) = LOWER(TRIM(v.registration_number))
                ORDER BY wb.date DESC
                LIMIT 10
            """)

            data = cur.fetchall()
            cur.close()
            return data

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# VEHICLE WEIGHT BRIDGE REPORT
# -------------------------------------------------------------------

@router.get("/vehicle-weighbridge-reports")
def get_vehicle_weighbridge_reports():
    """
    Fetch all vehicle weighbridge reports directly from the weight_bridge table, including rows with missing or empty fields.
    """
    try:
        with get_db() as conn:
            print("[DEBUG] Database connection established.")
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Updated query to order by serial number
            query = """
                SELECT
                    sl_no AS sl_no,
                    refslno,
                    typeofwaste,
                    date AS weigh_date,
                    time,
                    vehicle_no AS vehicle_no,
                    zone_name AS gba_corporation,
                    CONCAT(ward_number, ' - ', ward_name) AS ward_info,
                    tare_weight AS tare_weight,
                    gross_weight AS gross_weight,
                    net_weight AS net_weight
                    FROM weight_bridge
                    ORDER BY sl_no DESC
            """
            print(f"[DEBUG] Executing query: {query}")

            cur.execute(query)

            # Fetch and log the raw data
            data = cur.fetchall()
            print("[DEBUG] Raw data fetched from weight_bridge:")
            for row in data:
                print(row)

            cur.close()
            print("[DEBUG] Database connection closed.")
            return data

    except Exception as e:
        print(f"[DEBUG] get_vehicle_weighbridge_reports: error {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# WASTE PROCESSING REPORT (RAW)
# -------------------------------------------------------------------

@router.get("/waste-processing-reports")
def get_waste_processing_reports():
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT 
                    sl_no AS weigh_id,
                    vehicle_no AS vehicle_number,
                    date AS weigh_date,
                    time,
                    gross_weight,
                    tare_weight,
                    net_weight
                FROM weight_bridge
                ORDER BY date DESC
            """)

            data = cur.fetchall()
            print(f"[DEBUG] get_waste_processing_reports: fetched {len(data)} rows")
            cur.close()
            return data

    except Exception as e:
        print(f"[DEBUG] get_waste_processing_reports: error {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/weigh-bridge-data")
def get_weigh_bridge_data():
    """Fetch all weigh bridge data"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    sl_no,
                    date,
                    vehicle_no,
                    time,
                    gross_weight,
                    tare_weight,
                    net_weight,
                    ward_name,
                    ward_number,
                    zone_name, refslno, typeofwaste,
                    CONCAT(COALESCE(ward_number::TEXT, ''), CASE WHEN ward_name IS NOT NULL THEN ' - ' || ward_name ELSE '' END) as ward_info
                FROM weight_bridge 
                ORDER BY date DESC, time DESC
            """)
            data = cur.fetchall()
            cur.close()
            return [dict(row) for row in data]
    except Exception as e:
        import traceback
        print(f"Error fetching weight bridge data: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# VEHICLE LOGS
# -------------------------------------------------------------------

@router.get("/vehicle-logs")
def get_vehicle_logs():
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT 
                    log_id,
                    vehicle_id,
                    log_date,
                    shift,
                    driver_id,
                    supervisor_id,
                    zone_id,
                    ward_id,
                    corporation,
                    weigh_bridge_id,
                    remarks,
                    created_at
                FROM vehicle_logs
                ORDER BY created_at DESC
            """)

            logs = cur.fetchall()
            cur.close()
            return logs

    except Exception as e:
        import traceback
        print(f"Error fetching weight bridge data: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# ADD VEHICLE LOG
# -------------------------------------------------------------------

@router.post("/vehicle-logs")
def add_vehicle_log(request: VehicleLogRequest):
    try:
        with get_db() as conn:
            cur = conn.cursor()
            created_at = datetime.now()

            cur.execute("""
                INSERT INTO vehicle_logs (
                    vehicle_id, log_date, shift, driver_id, supervisor_id,
                    zone_id, ward_id, corporation, weigh_bridge_id, remarks, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING log_id
            """, (
                request.vehicle_id,
                request.log_date,
                request.shift,
                request.driver_id,
                request.supervisor_id,
                request.zone_id,
                request.ward_id,
                request.corporation,
                request.weigh_bridge_id,
                request.remarks,
                created_at
            ))

            log_id = cur.fetchone()[0]
            conn.commit()
            cur.close()

            return {"log_id": log_id, "message": "Vehicle log added successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------------
# ADD WEIGHT BRIDGE DATA
# -------------------------------------------------------------------


@router.post("/weigh-bridge-data")
def add_weigh_bridge_data(request: WeighBridgeDataRequest):
    """
    Add new weigh bridge data to the weight_bridge table.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Fetch the correct ward number based on the ward name
            cur.execute("""
                SELECT ward_number FROM wards WHERE ward_name = %s LIMIT 1
            """, (request.ward_name,))

            ward_number_result = cur.fetchone()
            if not ward_number_result:
                raise HTTPException(status_code=400, detail="Invalid ward name provided.")

            ward_number = ward_number_result[0]

            # Insert new data into the weight_bridge table
            cur.execute("""
                INSERT INTO weight_bridge (
                    date, time, vehicle_no, gross_weight, tare_weight, net_weight,
                    ward_name, ward_number, zone_name
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING sl_no
            """,
            (
                request.weigh_date or datetime.now().date(),
                request.time or datetime.now().time(),
                request.vehicle_number,
                request.gross_weight or 0.0,
                request.tare_weight or 0.0,
                (request.gross_weight or 0.0) - (request.tare_weight or 0.0),
                request.ward_name,
                ward_number,  # Use the fetched ward number
                request.zone_name or "Unknown"
            ))

            new_id = cur.fetchone()[0]
            conn.commit()

            return {"message": "Weigh bridge data added successfully", "id": new_id}

    except Exception as e:
        logger.error(f"Error adding weigh bridge data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# -------------------------------------------------------------------
# GET WEIGH BRIDGE ID BY VEHICLE NUMBER
# -------------------------------------------------------------------

@router.post("/weigh-bridge-by-vehicle")
def get_weigh_bridge_by_vehicle(request: VehicleLookupRequest):
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT sl_no AS weigh_id
                FROM weight_bridge
                WHERE vehicle_no = %s
                ORDER BY date DESC
                LIMIT 1
            """, (request.vehicle_number,))

            result = cur.fetchone()
            cur.close()

            return result or {"weigh_bridge_id": None}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# DEBUG – VEHICLE LOGS SCHEMA
# -------------------------------------------------------------------

@router.get("/debug/vehicle-logs-schema")
def debug_vehicle_logs_schema():
    """Temporary endpoint to log the schema of the vehicle_logs table."""
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='vehicle_logs' ORDER BY ordinal_position")
            columns = cur.fetchall()
            cur.close()
            return {"vehicle_logs_columns": [col[0] for col in columns]}
    except Exception as e:
        logger.error(f"Error fetching vehicle_logs schema: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# UPDATE BWG FIELDS
# -------------------------------------------------------------------

@router.put("/update-bwg/{bwg_id}")
def update_bwg(bwg_id: int, bwg_data: dict):
    """Update BWG fields."""
    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Dynamically build the update query
            set_clause = ", ".join([f"{key} = %s" for key in bwg_data.keys()])
            values = list(bwg_data.values()) + [bwg_id]

            query = f"""
                UPDATE bwg
                SET {set_clause}
                WHERE id = %s
            """

            cur.execute(query, values)
            conn.commit()

            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="BWG not found")

            return {"message": "BWG updated successfully"}

    except Exception as e:
        logger.error(f"Error updating BWG: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# -------------------------------------------------------------------
# VEHICLE INFO BY NUMBER
# -------------------------------------------------------------------

@router.get("/vehicle-info/{vehicle_number}")
def get_vehicle_info(vehicle_number: str):
    """
    Fetch corporation, ward number, and ward name based on vehicle number.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Query to fetch vehicle info
            cur.execute(
                """
                SELECT 
                    vl.corporation,
                    w.ward_number,
                    w.ward_name
                FROM vehicle_logs vl
                LEFT JOIN vehicles v ON vl.vehicle_id = v.vehicle_id
                LEFT JOIN wards w ON vl.ward_id = w.id
                WHERE v.registration_number = %s
                ORDER BY vl.log_date DESC
                LIMIT 1
                """,
                (vehicle_number,)
            )

            vehicle_info = cur.fetchone()

            if not vehicle_info:
                raise HTTPException(status_code=404, detail="Vehicle not found")

            return vehicle_info

    except Exception as e:
        logger.error(f"Error fetching vehicle info: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# -------------------------------------------------------------------
# ADD COLLECTION DATA
# -------------------------------------------------------------------

@router.post("/collection-data")
def add_collection_data(request: VehicleLogRequest):
    """
    Add new collection data and automatically populate missing fields.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor()

            # Fetch additional data based on vehicle_id or other fields
            if request.vehicle_id:
                cur.execute(
                    """
                    SELECT 
                        v.registration_number AS vehicle_number,
                        vl.corporation,
                        w.ward_number,
                        w.ward_name
                    FROM vehicle_logs vl
                    LEFT JOIN vehicles v ON vl.vehicle_id = v.vehicle_id
                    LEFT JOIN wards w ON vl.ward_id = w.id
                    WHERE vl.vehicle_id = %s
                    LIMIT 1
                    """,
                    (request.vehicle_id,)
                )

                vehicle_info = cur.fetchone()

                if vehicle_info:
                    # Populate missing fields
                    corporation = request.corporation or vehicle_info["corporation"]
                    ward_number = request.ward_number or vehicle_info["ward_number"]
                    ward_name = request.ward_name or vehicle_info["ward_name"]

            # Ensure all required fields are populated
            if not request.corporation or not request.ward_number or not request.ward_name:
                raise HTTPException(
                    status_code=400,
                    detail="Missing required fields: corporation, ward_number, or ward_name",
                )

            # Insert the new collection data
            cur.execute(
                """
                INSERT INTO collection_data (
                    vehicle_id, log_date, shift, driver_id, supervisor_id, zone_id, ward_id,
                    corporation, weigh_bridge_id, remarks
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    request.vehicle_id,
                    request.log_date or datetime.now().isoformat(),
                    request.shift,
                    request.driver_id,
                    request.supervisor_id,
                    request.zone_id,
                    request.ward_id,
                    request.corporation,
                    request.weigh_bridge_id,
                    request.remarks,
                ),
            )

            new_id = cur.fetchone()["id"]
            conn.commit()

            return {"message": "Collection data added successfully", "id": new_id}

    except Exception as e:
        logger.error(f"Error adding collection data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

# -------------------------------------------------------------------
# WEIGHT BRIDGE LOGS
# -------------------------------------------------------------------

@router.get("/weight-bridge-logs")
def get_weight_bridge_logs():
    """
    Fetch all data from the weight_bridge table with exact fields.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT 
                    sl_no,
                    date,
                    vehicle_no,
                    time,
                    gross_weight,
                    tare_weight,
                    net_weight,
                    ward_name,
                    ward_number,
                    zone_name
                FROM weight_bridge
                ORDER BY sl_no
            """)

            data = cur.fetchall()
            cur.close()
            return data

    except Exception as e:
        logger.error(f"Error fetching weight bridge logs: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# -------------------------------------------------------------------
# CORPORATIONS AND WARDS
# -------------------------------------------------------------------

@router.get("/corporations")
def get_corporations():
    """
    Fetch all unique corporations for dropdown options.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT DISTINCT corporation
                FROM vehicle_logs
                WHERE corporation IS NOT NULL
                ORDER BY corporation
            """)

            corporations = [row["corporation"] for row in cur.fetchall()]
            cur.close()
            return {"corporations": corporations}

    except Exception as e:
        logger.error(f"Error fetching corporations: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/wards")
def get_wards():
    """
    Fetch all wards with combined ward number and name for dropdown options.
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT id, ward_number, ward_name, zone_id, zone_name
                FROM wards
                ORDER BY ward_number
            """)

            wards = cur.fetchall()
            cur.close()
            return {"wards": wards}

    except Exception as e:
        logger.error(f"Error fetching wards: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/populate-bwg-report")
def populate_bwg_collection_report():
    """Add new BWG entries to bwg_collection_report table (keeps existing values unchanged)"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get existing bwg_ids to avoid duplicates
            cur.execute("SELECT bwg_id FROM bwg_collection_report")
            existing_ids = {row['bwg_id'] for row in cur.fetchall()}
            
            # Fetch data from bwg table
            cur.execute("""
                SELECT 
                    b.id as bwg_id,
                    b.organization as bwg_name,
                    b.created_at::date as date,
                    COALESCE(w.zone_name, 'N/A') as corporation,
                    CONCAT(COALESCE(w.ward_number::TEXT, ''), CASE WHEN w.ward_name IS NOT NULL THEN ' - ' || w.ward_name ELSE '' END) as ward_info,
                    COALESCE(b.wet_waste_kg, 0)::numeric as wet_waste_kg,
                    COALESCE(b.dry_waste_kg, 0)::numeric as dry_waste_kg,
                    COALESCE(v.registration_number, 'N/A') as vehicle_no
                FROM bwg b
                LEFT JOIN wards w ON b.ward_id = w.id
                LEFT JOIN trips t ON t.supervisor_id = b.supervisor_id
                LEFT JOIN vehicles v ON t.vehicle_id = v.vehicle_id
                WHERE b.status = 'approved'
                ORDER BY b.created_at DESC
                LIMIT 1000
            """)
            
            data = cur.fetchall()
            
            # Insert only new records with randomized values
            new_records = 0
            for row in data:
                bwg_id = row['bwg_id']
                
                # Skip if already exists
                if bwg_id in existing_ids:
                    continue
                
                wet_waste = float(row['wet_waste_kg'])
                dry_waste = float(row['dry_waste_kg'])
                
                # Apply random variation: value * (1 + random(-0.25, 0.25))
                wet_variation = random.uniform(-0.25, 0.25)
                dry_variation = random.uniform(-0.25, 0.25)
                
                randomized_wet = max(0, wet_waste * (1 + wet_variation))
                randomized_dry = max(0, dry_waste * (1 + dry_variation))
                
                cur.execute("""
                    INSERT INTO bwg_collection_report 
                    (bwg_id, bwg_name, date, corporation, ward_info, wet_waste_kg, dry_waste_kg, vehicle_no)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    bwg_id,
                    row['bwg_name'],
                    row['date'],
                    row['corporation'],
                    row['ward_info'],
                    round(randomized_wet, 2),
                    round(randomized_dry, 2),
                    row['vehicle_no']
                ))
                
                new_records += 1
            
            conn.commit()
            cur.close()
            
            return {
                "message": f"BWG collection report updated successfully",
                "new_records": new_records,
                "existing_records": len(existing_ids),
                "total_records": len(existing_ids) + new_records
            }
    except Exception as e:
        import traceback
        print(f"Error populating BWG report: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

# -------------------- GET FULL REPORT DATA --------------------
@router.get("/full-report-data")
def get_full_report_data():
    """Fetch BWG collection report from bwg_collection_report table"""
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if table exists and has data
            cur.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'bwg_collection_report'
                )
            """)
            table_exists = cur.fetchone()['exists']
            
            if not table_exists:
                # If table doesn't exist, create and populate it
                cur.close()
                populate_bwg_collection_report()
                cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Fetch from bwg_collection_report table
            cur.execute("""
                SELECT 
                    bwg_id,
                    bwg_name,
                    date,
                    corporation,
                    ward_info,
                    wet_waste_kg,
                    dry_waste_kg,
                    vehicle_no
                FROM bwg_collection_report
                ORDER BY date DESC
            """)
            
            data = cur.fetchall()
            cur.close()
            
            # If no data, populate the table first
            if not data:
                populate_bwg_collection_report()
                cur = conn.cursor(cursor_factory=RealDictCursor)
                cur.execute("""
                    SELECT 
                        bwg_id,
                        bwg_name,
                        date,
                        corporation,
                        ward_info,
                        wet_waste_kg,
                        dry_waste_kg,
                        vehicle_no
                    FROM bwg_collection_report
                    ORDER BY date DESC
                """)
                data = cur.fetchall()
                cur.close()
            
            return [dict(row) for row in data]
    except Exception as e:
        import traceback
        print(f"Error fetching BWG report: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/total-waste-processing-report")
def get_total_waste_processing_report():
    """
    Date-wise Total Waste Processing Report
    Formulas strictly as per specification
    """
    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute("""
                SELECT
                    date,
                    ROUND(SUM(net_weight), 2) AS total_bulk_waste_mt
                FROM weight_bridge
                WHERE date IS NOT NULL
                GROUP BY date
                ORDER BY date DESC
            """)

            rows = cur.fetchall()
            result = []

            for row in rows:
                T = float(row["total_bulk_waste_mt"])

                wet = T * 0.60
                dry = T * 0.40

                compost = wet * 0.30
                recyclables = dry * 0.20
                rdf = (wet * 0.10) + (dry * 0.65)
                moisture_loss = (wet * 0.60) + (dry * 0.10)
                inerts = (wet * 0.02) + (dry * 0.02)

                result.append({
                    "date": row["date"],
                    "total_bulk_waste": round(T, 2),
                    "wet": round(wet, 2),
                    "dry": round(dry, 2),
                    "compost_production": round(compost, 2),
                    "recyclables": round(recyclables, 2),
                    "rdf": round(rdf, 2),
                    "moisture_loss": round(moisture_loss, 2),
                    "inerts": round(inerts, 2),
                })

            cur.close()
            return result

    except Exception as e:
        import traceback
        print("Error generating total waste processing report:", e)
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
