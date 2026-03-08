# app/routers/addpickup.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Optional, List
import boto3
import time
import json
import os
from app.database import get_db
from psycopg2.extras import RealDictCursor
from datetime import datetime

router = APIRouter(prefix="/addpickup", tags=["Add Pickup"])

# 1. Load Configuration from Env Variables
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# 2. Initialize S3 Client with Credentials
s3 = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name=AWS_REGION,
)


def sanitize_folder(name: str) -> str:
    return (
        name.lower()
        .replace(" ", "-")
        .replace("/", "-")
        .replace("\\", "-")
        + "-" + str(int(time.time()))
    )


async def upload_to_s3(file: UploadFile, folder: str):
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket configuration missing")

    filename = f"{int(time.time())}-{file.filename.replace(' ', '_')}"
    key = f"pickup_address/{folder}/{filename}"

    # Use the configured bucket name
    s3.upload_fileobj(
        file.file, 
        S3_BUCKET_NAME, 
        key, 
        ExtraArgs={"ContentType": file.content_type}
    )
    
    # Construct URL dynamically based on Region and Bucket
    return f"https://{S3_BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"


# -------------------------------------------------------------------
# GET → fetch all pickup_address records
# -------------------------------------------------------------------
@router.get("")
def get_pickups():
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
              p.*, 
              z.name AS zone_name,
              CONCAT(w.ward_name,' (', w.ward_number,')') AS ward_display
            FROM pickup_address p
            LEFT JOIN zones z ON z.id::text = p.zone
            LEFT JOIN wards w ON w.id::text = p.ward
            ORDER BY p.created_at DESC
        """)
        rows = cur.fetchall()
        return list(rows)


# -------------------------------------------------------------------
# POST → Add new pickup request + upload photos
# -------------------------------------------------------------------
@router.post("")
async def add_pickup(
    bwg_id: str = Form(...),
    organization_name: str = Form(...),
    generator_type: str = Form(...),
    contact_person: str = Form(...),
    contact_number: str = Form(...),
    address: str = Form(...),
    waste_types: str = Form("[]"),
    email: Optional[str] = Form(None),
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
    id_proof_url: Optional[UploadFile] = File(None),
    org_photo_url: Optional[UploadFile] = File(None)
):
    folder = sanitize_folder(organization_name)

    id_proof_uploaded = None
    org_photo_uploaded = None

    if id_proof_url:
        id_proof_uploaded = await upload_to_s3(id_proof_url, folder)

    if org_photo_url:
        org_photo_uploaded = await upload_to_s3(org_photo_url, folder)

    waste_types_json = json.loads(waste_types)

    with get_db() as conn:
        cur = conn.cursor()

        zone_id = None
        if ward:
            cur.execute("SELECT zone_id FROM wards WHERE id = %s", (ward,))
            result = cur.fetchone()
            if result:
                zone_id = result[0]

        cur.execute(
            "SELECT COUNT(*) FROM pickup_address WHERE id LIKE %s",
            (f"{bwg_id}-P%",),
        )
        count = int(cur.fetchone()[0]) + 1
        pickup_id = f"{bwg_id}-P{count}"

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
            [
                pickup_id,
                organization_name,
                generator_type,
                contact_person,
                contact_number,
                email,
                address,
                json.dumps(waste_types_json),
                id_proof_uploaded,
                org_photo_uploaded,
                location,
                inspection_date,
                avg_daily_qty,
                existing_vendor,
                remarks,
                declaration in ["1", "true", "True"],
                preferred_collection_time,
                pincode,
                ward,
                zone,
                zone_id, wet_waste_kg, dry_waste_kg
            ],
        )

        row = cur.fetchone()
        
        # --- CRITICAL FIX: Commit the transaction ---
        conn.commit() 
        # --------------------------------------------

        cols = [c[0] for c in cur.description]
        return {"message": "Pickup address added successfully", "pickup": dict(zip(cols, row))}


# -------------------------------------------------------------------
# PATCH → update status
# -------------------------------------------------------------------
@router.patch("")
async def update_pickup(request: Request):
    body = await request.json()
    pickup_id = body.get("id")
    status = body.get("status")

    if not pickup_id or not status:
        raise HTTPException(400, "ID and status required")

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE pickup_address SET status=%s WHERE id=%s RETURNING *",
            (status, pickup_id),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(404, "Pickup not found")
            
        # --- CRITICAL FIX: Commit the transaction ---
        conn.commit() 
        # --------------------------------------------

        cols = [c[0] for c in cur.description]
        return dict(zip(cols, row))


# -------------------------------------------------------------------
# DELETE → remove pickup + delete S3 images
# -------------------------------------------------------------------
@router.delete("/{id}")
async def delete_pickup(id: str):
    if not S3_BUCKET_NAME:
        raise HTTPException(status_code=500, detail="S3 bucket configuration missing")

    with get_db() as conn:
        cur = conn.cursor()

        cur.execute(
            "SELECT id_proof_url, org_photo_url FROM pickup_address WHERE id=%s",
            (id,),
        )
        row = cur.fetchone()

        if not row:
            raise HTTPException(404, "Record not found")

        urls = [u for u in row if u]

        for url in urls:
            # Safely extract key based on the URL structure we created
            key = url.split(".com/")[-1]
            try:
                s3.delete_object(Bucket=S3_BUCKET_NAME, Key=key)
            except:
                pass

        cur.execute("DELETE FROM pickup_address WHERE id=%s", (id,))
        
        # --- CRITICAL FIX: Commit the transaction ---
        conn.commit()
        # --------------------------------------------

        return {"message": "Pickup address deleted"}