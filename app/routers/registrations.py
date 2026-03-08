# app/routers/registrations.py
import os
import uuid
import json
import boto3
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from app.database import get_db
from botocore.exceptions import ClientError
from psycopg2.extras import RealDictCursor
from app.services.twilio_client import TwilioClientSingleton

router = APIRouter(prefix="/registrations", tags=["Registrations"])

AWS_REGION = os.getenv("AWS_REGION")
BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

s3 = boto3.client(
    "s3",
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
)


# --------------------
# SMS sending helper
# --------------------
def send_registration_sms(phone: str, contact_person: str, is_approved: bool = False):
    """Send registration confirmation SMS via Twilio"""
    try:
        print(f"[SMS] Attempting to send SMS to {phone} for {contact_person}")
        
        client = TwilioClientSingleton.get_client()
        if not client:
            print("[SMS] ERROR: Could not get Twilio client")
            return False
        
        # Get the first available phone number from the account (like OTP does with Verify Service)
        phone_numbers = client.incoming_phone_numbers.stream(limit=1)
        twilio_phone = None
        for pn in phone_numbers:
            twilio_phone = pn.phone_number
            break
        
        if not twilio_phone:
            print("[SMS] ERROR: No Twilio phone number found in account")
            return False
        
        print(f"[SMS] Using Twilio phone: {twilio_phone}")
        
        if is_approved:
            message_text = f"Hi {contact_person}, Your BWG registration has been approved! Your account is ready to use. Please log in to the portal."
        else:
            message_text = f"Hi {contact_person}, Thank you for registering as a BWG. Your registration has been submitted for review. You'll be notified once approved."
        
        # Format phone number for Twilio (ensure it starts with +)
        formatted_phone = phone
        if not formatted_phone.startswith("+"):
            formatted_phone = "+91" + formatted_phone  # India country code
        
        print(f"[SMS] Formatted phone: {formatted_phone}")
        print(f"[SMS] Message: {message_text}")
        
        message = client.messages.create(
            body=message_text,
            from_=twilio_phone,
            to=formatted_phone
        )
        
        print(f"[SMS] SUCCESS: SMS sent to {formatted_phone}. SID: {message.sid}")
        return True
        
    except Exception as e:
        print(f"[SMS] ERROR: Failed to send SMS: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


# --------------------
# Upload helper
# --------------------
def upload_to_s3(folder: str, file: UploadFile) -> str:
    filename = f"{uuid.uuid4()}-{file.filename.replace(' ', '_')}"
    key = f"registrations/{folder}/{filename}"

    try:
        s3.upload_fileobj(
            file.file,
            BUCKET_NAME,
            key,
            ExtraArgs={"ContentType": file.content_type or "application/octet-stream"}
        )
        return f"https://{BUCKET_NAME}.s3.{AWS_REGION}.amazonaws.com/{key}"
    except ClientError as e:
        raise HTTPException(500, f"S3 Upload Failed: {str(e)}")


# --------------------
# GET registrations
# --------------------
@router.get("")
def get_registrations():
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("""
            SELECT 
                r.*, 
                w.ward_name, 
                w.ward_number, 
                w.zone_name, -- Pulled directly from wards table
                CONCAT(w.ward_name, ' (', w.ward_number, ')') AS ward_display
            FROM registrations r
            LEFT JOIN wards w ON r.ward_id = w.id
            ORDER BY r.created_at DESC
        """)
        return cur.fetchall()

# --------------------
# GET current user's registration or signup status
# --------------------
@router.get("/me")
def get_my_registration(request: Request):
    """Get the registration for the currently logged-in BWG user
    Logic:
    1. Check if registration exists in registrations table
    2. If registration exists:
       - If status != 'approved' → return registration data
       - If status == 'approved' → return bwg data (which should have synced details)
    3. If no registration → return bwg data with signup status
    """
    try:
        from app.routers.auth import decode_bwg_from_cookie
        
        bwg_id = decode_bwg_from_cookie(request)
        
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # Get the BWG's details
            cur.execute("""
                SELECT id, organization, person, phone, email, status, location, address,
                       generator_type, waste_types, id_proof_url, org_photo_url, 
                       inspection_date, collection_time, daily_waste_kg, vendor, remarks, consent, wet_waste_kg, dry_waste_kg
                FROM bwg WHERE id=%s
            """, (bwg_id,))
            bwg_row = cur.fetchone()
            
            if not bwg_row:
                raise HTTPException(status_code=404, detail="User not found")
            
            print(f"=== /registrations/me DEBUG ===")
            print(f"BWG ID: {bwg_id}")
            print(f"BWG email: {bwg_row['email']}")
            print(f"BWG phone: {bwg_row['phone']}")
            
            # ALWAYS search for registration by email if available
            registration = None
            
            if bwg_row['email']:
                cur.execute("""
    SELECT 
        r.*, 
        w.ward_name, 
        w.ward_number, 
        w.zone_name,
        CONCAT(w.ward_name, ' (', w.ward_number, ')') AS ward_display
    FROM registrations r
    LEFT JOIN wards w ON r.ward_id = w.id
    WHERE r.email = %s
    ORDER BY r.created_at DESC
    LIMIT 1
""", (bwg_row['email'],))
                registration = cur.fetchone()
                print(f"Registration found: {registration['id'] if registration else 'NONE'}")
                print(f"Registration status: {registration['status'] if registration else 'N/A'}")
            else:
                print("BWG email is NULL - cannot search for registration")
            
            print(f"==============================")
            
            # Decision logic
            if registration:
                if registration['status'] == 'approved':
                    # Status is approved → return bwg data (which should have synced details)
                    return {
                        "source": "bwg",
                        "data": dict(bwg_row),
                        "status": "approved"
                    }
                else:
                    # Status is not approved → return registration data
                    return {
                        "source": "registration",
                        "data": dict(registration),
                        "status": registration['status']
                    }
            else:
                # No registration found → return bwg data with signup status
                return {
                    "source": "bwg",
                    "data": dict(bwg_row),
                    "status": "signup"
                }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------
# POST registration (multipart form)
# --------------------
@router.post("")
async def create_registration(
    request: Request,
    organization_name: Optional[str] = Form(None),
    generator_type: Optional[str] = Form(None),
    contact_person: Optional[str] = Form(None),
    contact_number: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    waste_types: str = Form("[]"),
    location: Optional[str] = Form(None),
    inspection_date: Optional[str] = Form(None),
    avg_daily_qty: Optional[str] = Form(None),
    wet_waste_kg: Optional[str] = Form(None),
    dry_waste_kg: Optional[str] = Form(None),
    existing_vendor: Optional[str] = Form(None),
    remarks: Optional[str] = Form(None),
    declaration: str = Form("false"),
    preferred_collection_time: Optional[str] = Form(None),
    pincode: Optional[str] = Form(None),
    ward: Optional[str] = Form(None),
    zone: Optional[str] = Form(None),
    created_by_admin: Optional[str] = Form(None),
    id_proof: Optional[UploadFile] = File(None),
    org_photo: Optional[UploadFile] = File(None)
):
    # Try to get authenticated BWG user id (optional - might not be logged in yet)
    bwg_id = None
    try:
        from app.routers.auth import decode_bwg_from_cookie
        bwg_id = decode_bwg_from_cookie(request)
    except:
        pass  # No auth is fine - user might be registering for first time
    
    # Validation
    errors = {}
    
    if not organization_name or len(organization_name.strip()) < 3:
        errors["organizationName"] = "Organization name must be at least 3 characters"
    if not generator_type:
        errors["generatorType"] = "Generator type is required"
    if not contact_person or len(contact_person.strip()) < 2:
        errors["contactPerson"] = "Contact person is required"
    if not contact_number or not contact_number.isdigit() or len(contact_number) != 10:
        errors["contactNumber"] = "Valid 10-digit phone number required"
    if not email or "@" not in email:
        errors["email"] = "Valid email is required"
    if not address or len(address.strip()) < 10:
        errors["address"] = "Address must be at least 10 characters"
    if not location:
        errors["mapLocation"] = "Map location is required"
    if not zone:
        errors["zone"] = "Zone is required"
    if not ward:
        errors["ward"] = "Ward is required"
    if not inspection_date:
        errors["inspectionDate"] = "Inspection date is required"
    if not id_proof:
        errors["idProof"] = "ID Proof is mandatory"
    
    # Check waste types
    try:
        wt = json.loads(waste_types)
        if not wt or len(wt) == 0:
            errors["wasteTypes"] = "Select at least one waste type"
    except:
        errors["wasteTypes"] = "Invalid waste types format"
    
    # Check declaration
    if declaration.lower() not in ("1", "true", "yes"):
        errors["declaration"] = "You must accept the declaration"
    
    if errors:
        return JSONResponse(
            status_code=422,
            content={"message": "Validation failed", "errors": errors}
        )
    
    folder = organization_name.lower().replace(" ", "-")

    id_proof_url = upload_to_s3(folder, id_proof) if id_proof else None
    org_photo_url = upload_to_s3(folder, org_photo) if org_photo else None

    with get_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Resolve zone / ward IDs
        ward_id = int(ward) if ward and ward.isdigit() else None
        zone_id = None

        if ward_id:
            cur.execute("SELECT zone_id FROM wards WHERE id=%s", (ward_id,))
            w_res = cur.fetchone()
            zone_id = w_res["zone_id"] if w_res else None
        else:
            zone_id = int(zone) if zone and zone.isdigit() else None
        # if ward_result:
        #     ward_id = ward_result["id"]
        #     zone_id = ward_result["zone_id"]

        # Always set status to pending - admins cannot auto-approve
        status = "pending"

        cur.execute(
            """
            INSERT INTO registrations (
                organization_name, generator_type, contact_person, contact_number, email,
                address, waste_types, id_proof_url, org_photo_url, location,
                inspection_date, status, avg_daily_qty, existing_vendor, remarks,
                declaration, preferred_collection_time, pincode, ward_id, zone_id, wet_waste_kg, dry_waste_kg
            )
            VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s, %s, %s
            )
            RETURNING *
            """,
            [
                organization_name,
                generator_type,
                contact_person,
                contact_number,
                email,
                address,
                waste_types,
                id_proof_url,
                org_photo_url,
                location,
                inspection_date,
                status,
                avg_daily_qty,
                existing_vendor,
                remarks,
                declaration.lower() in ("1", "true", "yes"),
                preferred_collection_time,
                pincode,
                ward_id,
                zone_id, wet_waste_kg, dry_waste_kg
            ]
        )

        registration = cur.fetchone()
        
        # Sync email, phone, and contact person to the user's BWG record IF they're logged in
        # This ensures the registration lookup works by matching email/phone
        if bwg_id:
            cur.execute(
                """
                UPDATE bwg SET 
                    email=%s,
                    phone=%s,
                    person=%s
                WHERE id=%s
                """,
                (email, contact_number, contact_person, bwg_id)
            )
        
        conn.commit()

        # Send confirmation SMS
        if contact_number:
            send_registration_sms(contact_number, contact_person, is_approved=False)

        return {"message": "Registration created successfully", "registration": registration}



# --------------------
# PATCH update registration
# --------------------
@router.patch("")
async def update_registration(request: Request):
    data = await request.json()
    reg_id = data.get("id")
    status = data.get("status")

    if not reg_id or not status:
        raise HTTPException(400, "ID and status required")

    with get_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cur.execute("BEGIN")

            cur.execute("SELECT * FROM registrations WHERE id=%s FOR UPDATE", (reg_id,))
            reg = cur.fetchone()
            if not reg:
                raise HTTPException(404, "Registration not found")

            # ↪ If approved → sync registration data to BWG table
            if status == "approved" and reg["status"] != "approved":
                print(f"Approving registration {reg_id}, syncing data to BWG table")
                
                # Find the BWG record by email
                cur.execute("SELECT id FROM bwg WHERE email=%s", (reg["email"],))
                bwg_row = cur.fetchone()
                
                if bwg_row:
                    bwg_id = bwg_row["id"]
                    # Sync all registration data to BWG table
                    # waste_types needs to be cast to jsonb
                    cur.execute(
                        """
                        UPDATE bwg SET
                            organization=%s,
                            phone=%s,
                            person=%s,
                            address=%s,
                            waste_types=%s::jsonb,
                            generator_type=%s,
                            id_proof_url=%s,
                            org_photo_url=%s,
                            location=%s,
                            inspection_date=%s,
                            collection_time=%s,
                            daily_waste_kg=%s,
                            vendor=%s,
                            remarks=%s,
                            consent=%s,
                            zone_id=%s,
                            ward_id=%s,
                            status=%s, wet_waste_kg=%s, dry_waste_kg=%s
                        WHERE id=%s
                        """,
                        (
                            reg["organization_name"],
                            reg["contact_number"],
                            reg["contact_person"],
                            reg["address"],
                            json.dumps(reg["waste_types"]) if isinstance(reg["waste_types"], list) else reg["waste_types"],
                            reg["generator_type"],
                            reg["id_proof_url"],
                            reg["org_photo_url"],
                            reg["location"],
                            reg["inspection_date"],
                            reg["preferred_collection_time"],
                            reg["avg_daily_qty"],
                            reg["existing_vendor"],
                            reg["remarks"],
                            reg["declaration"],
                            reg["zone_id"],
                            reg["ward_id"],
                            "approved", reg["wet_waste_kg"], reg["dry_waste_kg"],
                            bwg_id
                        )
                    )
                    print(f"Successfully synced registration {reg_id} to BWG {bwg_id}")

            # After syncing registration data to BWG
            cur.execute(
                """
                UPDATE bwg b
                SET
                    ward_number = w.ward_number,
                    ward_name   = w.ward_name,
                    zone        = w.zone_name
                FROM wards w
                WHERE b.ward_id = w.id
                AND b.id = %s
                """,
                (bwg_id,)
            )
            print(f"Ward details synced for BWG {bwg_id}")

            # update registration status - this is the main operation
            cur.execute(
                "UPDATE registrations SET status=%s WHERE id=%s RETURNING *",
                (status, reg_id)
            )
            
            updated_reg = cur.fetchone()
            conn.commit()
            print(f"Successfully updated registration {reg_id} to status {status}")
            return updated_reg

        except Exception as e:
            conn.rollback()
            print(f"DEBUG: Error updating registration {reg_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(500, f"Error updating: {str(e)}")


# --------------------
# DELETE registration
# --------------------
@router.delete("/{reg_id}")
def delete_registration(reg_id: str):
    with get_db() as conn:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # cur.execute(
        #     "SELECT id_proof_url, org_photo_url FROM registrations WHERE id=%s",
        #     (reg_id,)
        # )
        # row = cur.fetchone()
        # if not row:
        #     raise HTTPException(404, "Not found")

        # urls = [row["id_proof_url"], row["org_photo_url"]]
        # for url in urls:
        #     if not url:
        #         continue
        #     key = url.split(".amazonaws.com/")[1]
        #     try:
        #         s3.delete_object(Bucket=BUCKET_NAME, Key=key)
        #     except:
        #         pass

        cur.execute("DELETE FROM registrations WHERE id=%s", (reg_id,))
        conn.commit()

        return {"message": f"Registration {reg_id} deleted"}