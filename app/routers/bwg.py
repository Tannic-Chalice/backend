from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Query,
    Form,
    UploadFile,
    File,
)
from typing import Optional
import os
import jwt
import json
from datetime import datetime
from urllib.parse import urlparse

import boto3

from app.database import get_db
from app.config import JWT_SECRET

router = APIRouter(tags=["BWG"])

AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)


# -------------------------------------------------
# Common helper – decode BWG id from Header OR Cookie
# -------------------------------------------------
def decode_bwg_id(request: Request) -> str:
    token = None
    
    # 1. Check Authorization Header (Priority for Capacitor/Mobile)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    # 2. Fallback to Cookie (For Web)
    if not token:
        token = request.cookies.get("sessionToken-bwg")

    # 3. Validation
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized - No valid token found")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid or expired token")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token")

    if not isinstance(decoded, dict) or "id" not in decoded:
        raise HTTPException(status_code=401, detail="Unauthorized - Invalid token payload")

    return str(decoded["id"])


# -------------------------------------------------
# 1) GET /bwg/main-address-details?bwgId=...
# -------------------------------------------------
@router.get("/main-address-details")
def main_address_details(request: Request, bwgId: str = Query(...)):
    current_bwg_id = decode_bwg_id(request)

    if bwgId != current_bwg_id:
        raise HTTPException(status_code=403, detail="Forbidden - Access to this ID is denied")

    query = """
      SELECT 
        b.id, b.username, b.organization, b.phone, b.person, b.location, b.address, 
        b.generator_type, b.email, b.waste_types, b.created_at, b.inspection_date, 
        b.ward_id, b.collection_time, b.segregation_methods, b.daily_waste_kg, 
        b.vendor, b.remarks, b.consent, b.status,
        w.ward_number, w.ward_name, 
        z.name AS zone_name,
        z.id AS zone_id
      FROM public.bwg b
      LEFT JOIN public.wards w ON b.ward_id = w.id 
      LEFT JOIN public.zones z ON w.zone_id = z.id
      WHERE b.id = %s
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (bwgId,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Main address not found")

    (
        _id,
        username,
        organization,
        phone,
        person,
        location,
        address,
        generator_type,
        email,
        waste_types,
        created_at,
        inspection_date,
        ward_id,
        collection_time,
        segregation_methods,
        daily_waste_kg,
        vendor,
        remarks,
        consent,
        status,
        ward_number,
        ward_name,
        zone_name,
        zone_id,
    ) = row

    response_data = {
        "type": "main",
        "id": _id,
        "username": username,
        "organization": organization,
        "phone": phone,
        "person": person,
        "location": location,
        "address": address,
        "generator_type": generator_type,
        "email": email,
        "waste_types": waste_types,
        "created_at": created_at.isoformat() if created_at else None,
        "inspection_date": inspection_date.isoformat() if inspection_date else None,
        "ward_number": ward_number,
        "ward_name": ward_name,
        "zone_id": zone_id,
        "zone_name": zone_name,
        "collection_time": collection_time,
        "segregation_methods": segregation_methods,
        "daily_waste_kg": daily_waste_kg,
        "vendor": vendor,
        "remarks": remarks,
        "status": status,
    }

    return response_data


# -------------------------------------------------
# 2) GET /bwg/pickup-address-details?pickupId=...
# -------------------------------------------------
@router.get("/pickup-address-details")
def pickup_address_details(request: Request, pickupId: str = Query(...)):
    current_bwg_id = decode_bwg_id(request)

    if not pickupId.startswith(current_bwg_id):
        raise HTTPException(
            status_code=403,
            detail="Forbidden - Access to this pickup address is denied",
        )

    query = """
      SELECT 
        p.id, p.organization_name, p.generator_type, p.contact_person, p.contact_number, 
        p.email, p.address, p.waste_types, p.id_proof_url, p.org_photo_url, p.status, 
        p.created_at, p.location, p.inspection_date, p.avg_daily_qty, p.existing_vendor, 
        p.remarks, p.declaration, p.preferred_collection_time, p.pincode, p.zone,
        p.ward, p.zone_id, 
        w.ward_number as ward_number_fk, 
        w.ward_name as ward_name_fk,
        z.name AS zone_name,
        z.id AS zone_id_fk
      FROM public.pickup_address p
      LEFT JOIN public.wards w ON p.ward::integer = w.ward_number 
      LEFT JOIN public.zones z ON w.zone_id = z.id
      WHERE p.id = %s
      LIMIT 1
    """

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query, (pickupId,))
        row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Pickup address not found")

    (
        _id,
        organization_name,
        generator_type,
        contact_person,
        contact_number,
        email,
        address,
        waste_types,
        id_proof_url,
        org_photo_url,
        status,
        created_at,
        location,
        inspection_date,
        avg_daily_qty,
        existing_vendor,
        remarks,
        declaration,
        preferred_collection_time,
        pincode,
        zone,
        ward,
        zone_id,
        ward_number_fk,
        ward_name_fk,
        zone_name,
        zone_id_fk,
    ) = row

    response_data = {
        "type": "pickup",
        "id": _id,
        "organization": organization_name,
        "address": address,
        "contact_person": contact_person,
        "contact_number": contact_number,
        "email": email,
        "generator_type": generator_type,
        "waste_types": waste_types,
        "id_proof_url": id_proof_url,
        "org_photo_url": org_photo_url,
        "status": status,
        "created_at": created_at.isoformat() if created_at else None,
        "location": location,
        "inspection_date": inspection_date.isoformat() if inspection_date else None,
        "avg_daily_qty": avg_daily_qty,
        "existing_vendor": existing_vendor,
        "remarks": remarks,
        "preferred_collection_time": preferred_collection_time,
        "pincode": pincode,
        "ward_number": ward_number_fk,
        "ward_name": ward_name_fk,
        "zone_name": zone_name,
        "zone_id": zone_id_fk,
        "ward": ward,
        "zone": zone,
    }

    return response_data


# -------------------------------------------------
# 3) GET /bwg/pickup-addresses
# -------------------------------------------------
@router.get("/pickup-addresses")
def pickup_addresses(request: Request):
    # This now uses the updated Header logic
    bwg_id = decode_bwg_id(request)

    bwg_query = """
      SELECT 
        id,
        organization as organization, 
        address as address, 
        status as status
      FROM bwg 
      WHERE id = %s
    """

    pickup_query = """
      SELECT 
        id,
        organization_name as organization, 
        address, 
        status
      FROM pickup_address 
      WHERE id LIKE %s
      ORDER BY created_at DESC
    """

    with get_db() as conn:
        cur = conn.cursor()
        
        # Fetch from bwg table (which now has synced registration data when approved)
        cur.execute(bwg_query, (bwg_id,))
        bwg_rows = cur.fetchall()
        main_addresses = [
            {
                "id": r[0],
                "organization": r[1],
                "address": r[2],
                "status": r[3],
                "isMain": True,
            }
            for r in bwg_rows
        ]

        # Always fetch pickup addresses from pickup_address table
        cur.execute(pickup_query, (f"{bwg_id}-P%",))
        pickup_rows = cur.fetchall()

        pickup_addresses = [
            {
                "id": r[0],
                "organization": r[1],
                "address": r[2],
                "status": r[3],
                "isMain": False,
            }
            for r in pickup_rows
        ]

    all_addresses = main_addresses + pickup_addresses
    return all_addresses


# -------------------------------------------------
# 4) S3 helpers for pickup-registration
# -------------------------------------------------
async def upload_to_s3(file: UploadFile, folder_name: str) -> str:
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket missing")

    contents = await file.read()
    safe_orig = (file.filename or "upload").replace(" ", "_")
    file_name = f"{int(datetime.utcnow().timestamp())}-{safe_orig}"
    s3_key = f"pickup_address/{folder_name}/{file_name}"

    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=s3_key,
        Body=contents,
        ContentType=file.content_type or "application/octet-stream",
    )

    return f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{s3_key}"


def sanitize_for_folder_name(name: str) -> str:
    sanitized = (
        name.lower()
        .replace(" ", "-")
        .encode("ascii", errors="ignore")
        .decode("ascii")
    )
    sanitized = "".join(ch for ch in sanitized if ch.isalnum() or ch == "-")
    return f"{sanitized}-{str(int(datetime.utcnow().timestamp()))[-6:]}"


def extract_key_from_url(url: str) -> Optional[str]:
    try:
        parsed = urlparse(url)
        return parsed.path.lstrip("/")
    except Exception:
        return None


# -------------------------------------------------
# 5) GET /bwg/pickup-registration  (list all)
# -------------------------------------------------
@router.get("/pickup-registration")
def list_pickup_registration():
    query = "SELECT * FROM pickup_address ORDER BY created_at DESC"
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]

    return [dict(zip(cols, r)) for r in rows]


# -------------------------------------------------
# 6) POST /bwg/pickup-registration  (create)
# -------------------------------------------------
@router.post("/pickup-registration")
async def create_pickup_registration(
    request: Request,
    organization_name: str = Form(...),
    generator_type: str = Form(...),
    contact_person: str = Form(...),
    contact_number: str = Form(...),
    email: Optional[str] = Form(None),
    address: str = Form(...),
    waste_types: Optional[str] = Form("[]"),
    location: Optional[str] = Form(None),
    inspection_date: Optional[str] = Form(None),
    avg_daily_qty: Optional[str] = Form(None),
    wet_waste_kg: Optional[int] = Form(None),
    dry_waste_kg: Optional[int] = Form(None),
    existing_vendor: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    declaration: Optional[str] = Form(None),
    preferred_collection_time: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    ward: Optional[str] = Form(None),
    zone: Optional[str] = Form(None),
    id_proof: Optional[UploadFile] = File(None),
    org_photo: Optional[UploadFile] = File(None),
):
    # Uses header auth logic now
    bwg_id = decode_bwg_id(request)

    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket missing")

    folder_name = sanitize_for_folder_name(organization_name)

    id_proof_url = None
    org_photo_url = None

    if id_proof is not None:
        id_proof_url = await upload_to_s3(id_proof, folder_name)
    if org_photo is not None:
        org_photo_url = await upload_to_s3(org_photo, folder_name)

    try:
        wt_list = json.loads(waste_types or "[]")
    except json.JSONDecodeError:
        wt_list = []

    inspection_dt = None
    if inspection_date:
        try:
            inspection_dt = datetime.fromisoformat(inspection_date)
        except ValueError:
            inspection_dt = None

    declaration_bool = declaration in ("1", "true", "True", "TRUE")

    with get_db() as conn:
        cur = conn.cursor()

        zone_id = None
        if ward:
            cur.execute("SELECT zone_id FROM wards WHERE id = %s", (ward,))
            z_row = cur.fetchone()
            zone_id = z_row[0] if z_row else None

        cur.execute(
            "SELECT COUNT(*) FROM pickup_address WHERE id LIKE %s",
            (f"{bwg_id}-P%",),
        )
        count = int(cur.fetchone()[0])
        pickup_count = count + 1
        pickup_id = f"{bwg_id}-P{pickup_count}"

        cur.execute(
            """
            INSERT INTO pickup_address (
              id, organization_name, generator_type, contact_person, contact_number,
              email, address, waste_types, id_proof_url, org_photo_url, status,
              location, inspection_date, avg_daily_qty, existing_vendor, remarks,
              declaration, preferred_collection_time, pincode, ward, zone, zone_id, wet_waste_kg, dry_waste_kg
            )
            VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
              'pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, %s, %s
            )
            RETURNING *
            """,
            (
                pickup_id,
                organization_name,
                generator_type,
                contact_person,
                contact_number,
                email,
                address,
                json.dumps(wt_list),
                id_proof_url,
                org_photo_url,
                location,
                inspection_dt,
                avg_daily_qty,
                existing_vendor,
                remarks,
                declaration_bool,
                preferred_collection_time,
                pincode,
                ward,
                zone,
                zone_id, wet_waste_kg, dry_waste_kg
            ),
        )
        row = cur.fetchone()
        
        # --- CRITICAL FIX: Commit the transaction ---
        conn.commit()
        # --------------------------------------------
        
        cols = [d[0] for d in cur.description]

    return {
        "message": "Pickup address added successfully",
        "pickup": dict(zip(cols, row)),
    }


# -------------------------------------------------
# 7) PATCH /bwg/pickup-registration  (update status)
# -------------------------------------------------
@router.patch("/pickup-registration")
async def update_pickup_registration_status(request: Request):
    body = await request.json()
    pickup_id = body.get("id")
    status = body.get("status")

    if not pickup_id or not status:
        raise HTTPException(status_code=400, detail="ID and status required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pickup_address SET status = %s WHERE id = %s RETURNING *",
            (status, pickup_id),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Pickup not found")
            
        # --- CRITICAL FIX: Commit the transaction ---
        conn.commit()
        # --------------------------------------------
        
        cols = [d[0] for d in cur.description]

    return dict(zip(cols, row))


# -------------------------------------------------
# 8) DELETE /bwg/pickup-registration?id=...
# -------------------------------------------------
@router.delete("/pickup-registration")
def delete_pickup_registration(id: str = Query(...)):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id_proof_url, org_photo_url FROM pickup_address WHERE id = %s",
            (id,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Record not found")

        id_proof_url, org_photo_url = row
        urls = [u for u in [id_proof_url, org_photo_url] if u]

        for url in urls:
            key = extract_key_from_url(url)
            if key and S3_BUCKET_NAME:
                try:
                    s3_client.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
                except Exception:
                    pass

        cur.execute("DELETE FROM pickup_address WHERE id = %s", (id,))
        conn.commit()

    return {"message": "Pickup address deleted"}


# -------------------------------------------------
# 9) GET /bwg/map-data - Fetch BWG data joined with wards and trips
# -------------------------------------------------
@router.get("/map-data")
def get_map_data(
    ward_id: Optional[int] = Query(None),
    zone_id: Optional[int] = Query(None),
):
    """
    Fetch BWG data joined with wards and trips for map display.
    Optionally filter by ward_id or zone_id.
    """
    query = """
        SELECT 
            b.id,
            b.username,
            b.organization,
            b.phone,
            b.person,
            b.address,
            b.location,
            b.status,
            b.daily_waste_kg,
            b.collection_time,
            b.created_at,
            w.id as ward_id,
            w.ward_number,
            w.ward_name,
            z.id as zone_id,
            z.name as zone_name,
            COUNT(DISTINCT t.trip_id) as total_trips,
            MAX(t.trip_date) as last_trip_date,
            MAX(t.status) as last_trip_status
        FROM 
            public.bwg b
        LEFT JOIN 
            public.wards w ON b.ward_id = w.id
        LEFT JOIN 
            public.zones z ON w.zone_id = z.id
        LEFT JOIN 
            public.pickups p ON b.id = p.bwg_id
        LEFT JOIN 
            public.trips t ON p.trip_id = t.trip_id
        WHERE 1=1
    """
    
    params = []
    
    if ward_id:
        query += " AND w.id = %s"
        params.append(ward_id)
    
    if zone_id:
        query += " AND z.id = %s"
        params.append(zone_id)
    
    query += """
        GROUP BY 
            b.id, b.username, b.organization, b.phone, b.person, 
            b.address, b.location, b.status, b.daily_waste_kg, 
            b.collection_time, b.created_at, w.id, w.ward_number, 
            w.ward_name, z.id, z.name
        ORDER BY 
            b.created_at DESC
    """
    
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        
        result = [dict(zip(cols, row)) for row in rows]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


# -------------------------------------------------
# 10) GET /bwg/ward-details - Fetch BWG details with driver, vehicle, supervisor for a ward
# -------------------------------------------------
@router.get("/ward-details")
def get_ward_details(ward_id: int = Query(..., description="Ward ID is required")):
    """
    Fetch approved BWG data for a specific ward with driver, vehicle, and supervisor details
    from the most recent trip/pickup
    """
    query = """
        SELECT DISTINCT ON (b.id)
            b.id,
            b.organization,
            b.generator_type,
            b.address,
            b.status,
            b.collection_time,
            w.ward_number,
            w.ward_name,
            d.name as driver_name,
            d.id as driver_id,
            v.registration_number as vehicle_registration,
            v.vehicle_id,
            s.name as supervisor_name,
            s.id as supervisor_id,
            t.trip_id,
            t.trip_date,
            t.status as trip_status
        FROM 
            public.bwg b
        LEFT JOIN 
            public.wards w ON b.ward_id = w.id
        LEFT JOIN 
            public.pickups p ON b.id = p.bwg_id
        LEFT JOIN 
            public.trips t ON p.trip_id = t.trip_id
        LEFT JOIN 
            public.driver d ON t.driver_id = d.id
        LEFT JOIN 
            public.vehicles v ON t.vehicle_id = v.vehicle_id
        LEFT JOIN 
            public.supervisors s ON t.supervisor_id = s.id
        WHERE 
            b.ward_id = %s
            AND b.status = 'approved'
        ORDER BY 
            b.id, t.trip_date DESC NULLS LAST
    """
    
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(query, (ward_id,))
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description]
        
        result = [dict(zip(cols, row)) for row in rows]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")