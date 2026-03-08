"""
BWG Wise Payment API Router
Handles fetching BWGs, pickup points, pricing, and invoice generation for BWG payments.
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import List, Optional
from decimal import Decimal
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
import uuid
import jwt
from psycopg2.extras import RealDictCursor
from app.database import get_db
from app.config import JWT_SECRET

router = APIRouter()


# =========================
# AUTH
# =========================
def decode_admin_user(request: Request):
    """Decode and verify admin JWT token from header or cookie."""
    token = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    if not token:
        token = request.cookies.get("sessionToken-admin")

    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        decoded = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return decoded


def ensure_prices_table_exists(cur):
    """Create the bwg_pickup_prices table if it doesn't exist."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS bwg_pickup_prices (
            id SERIAL PRIMARY KEY,
            bwg_id VARCHAR(10) NOT NULL,
            pickup_point_id VARCHAR(20) NOT NULL,
            pickup_point_type VARCHAR(20) NOT NULL,
            price NUMERIC(10, 2) NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            UNIQUE (bwg_id, pickup_point_id)
        )
    """)


# =========================
# MODELS
# =========================
class BWGInfo(BaseModel):
    id: str
    organization: str
    address: Optional[str]
    phone: Optional[str]
    person: Optional[str]


class PickupPoint(BaseModel):
    id: str
    organization: str
    address: Optional[str]
    type: str  # 'main' or 'pickup'
    price: float = 0.0


class PickupPointsResponse(BaseModel):
    bwg: BWGInfo
    pickup_points: List[PickupPoint]
    total_amount: float


class SavePriceRequest(BaseModel):
    bwg_id: str
    pickup_point_id: str
    pickup_point_type: str
    wet_price_per_kg: float = 0.0
    dry_price_per_kg: float = 0.0
    wet_waste_kg: float = 0.0
    dry_waste_kg: float = 0.0
    price: float = 0.0


class SavePricesRequest(BaseModel):
    bwg_id: str
    prices: List[SavePriceRequest]


class GenerateBWGInvoiceRequest(BaseModel):
    bwg_id: str
    pickup_prices: List[SavePriceRequest]
    total_amount: float


# =========================
# GET ALL BWGs
# =========================
@router.get("/bwg-payment/bwgs")
async def get_all_bwgs(request: Request):
    """Fetch all approved BWGs for the BWG Wise Payment selection."""
    decode_admin_user(request)

    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute("""
                SELECT 
                    id, organization, address, phone, person
                FROM bwg 
                WHERE status = 'approved'
                ORDER BY organization
            """)
            rows = cur.fetchall()

        return {"bwgs": [dict(row) for row in rows]}

    except Exception as e:
        print(f"Error fetching BWGs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch BWGs")


# =========================
# GET PICKUP POINTS FOR BWG
# =========================
@router.get("/bwg-payment/{bwg_id}/pickup-points")
async def get_pickup_points(bwg_id: str, request: Request):
    """Fetch all pickup points (main + additional) for a specific BWG with their prices."""
    decode_admin_user(request)

    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # 1. Fetch main BWG address with waste kg and price per kg data
            cur.execute("""
                SELECT 
                    id, organization, address, location, phone, person,
                    COALESCE(wet_waste_kg, 0) as wet_waste_kg,
                    COALESCE(dry_waste_kg, 0) as dry_waste_kg,
                    COALESCE(wet_price_per_kg, 0) as wet_price_per_kg,
                    COALESCE(dry_price_per_kg, 0) as dry_price_per_kg
                FROM bwg 
                WHERE id = %s AND status = 'approved'
            """, (bwg_id,))
            bwg_row = cur.fetchone()

            if not bwg_row:
                raise HTTPException(status_code=404, detail="BWG not found")

            # 2. Fetch additional pickup addresses with waste kg and price per kg
            cur.execute("""
                SELECT 
                    id, organization_name as organization, address, location,
                    COALESCE(wet_waste_kg, 0) as wet_waste_kg,
                    COALESCE(dry_waste_kg, 0) as dry_waste_kg,
                    COALESCE(wet_price_per_kg, 0) as wet_price_per_kg,
                    COALESCE(dry_price_per_kg, 0) as dry_price_per_kg
                FROM pickup_address 
                WHERE id LIKE %s AND status = 'approved'
                ORDER BY created_at
            """, (f"{bwg_id}-P%",))
            pickup_rows = cur.fetchall()

            # 3. Ensure prices table exists
            ensure_prices_table_exists(cur)
            conn.commit()

        # Build pickup points list
        pickup_points = []

        # Helper to calculate price from price per kg
        def calc_price(wet_kg, dry_kg, wet_price, dry_price):
            return (float(wet_kg) * float(wet_price)) + (float(dry_kg) * float(dry_price))

        # Add main BWG address as first pickup point
        main_wet_kg = float(bwg_row['wet_waste_kg'] or 0)
        main_dry_kg = float(bwg_row['dry_waste_kg'] or 0)
        main_wet_price = float(bwg_row['wet_price_per_kg'] or 0)
        main_dry_price = float(bwg_row['dry_price_per_kg'] or 0)
        main_price = calc_price(main_wet_kg, main_dry_kg, main_wet_price, main_dry_price)
        
        pickup_points.append({
            "id": bwg_id,
            "organization": bwg_row['organization'],
            "address": bwg_row['address'],
            "location": bwg_row.get('location'),
            "type": "main",
            "wet_waste_kg": main_wet_kg,
            "dry_waste_kg": main_dry_kg,
            "wet_price_per_kg": main_wet_price,
            "dry_price_per_kg": main_dry_price,
            "price": main_price
        })

        # Add additional pickup addresses
        for row in pickup_rows:
            wet_kg = float(row['wet_waste_kg'] or 0)
            dry_kg = float(row['dry_waste_kg'] or 0)
            wet_price = float(row['wet_price_per_kg'] or 0)
            dry_price = float(row['dry_price_per_kg'] or 0)
            price = calc_price(wet_kg, dry_kg, wet_price, dry_price)
            
            pickup_points.append({
                "id": row['id'],
                "organization": row['organization'],
                "address": row['address'],
                "location": row.get('location'),
                "type": "pickup",
                "wet_waste_kg": wet_kg,
                "dry_waste_kg": dry_kg,
                "wet_price_per_kg": wet_price,
                "dry_price_per_kg": dry_price,
                "price": price
            })

        total_amount = sum(p['price'] for p in pickup_points)

        return {
            "bwg": dict(bwg_row),
            "pickup_points": pickup_points,
            "total_amount": total_amount
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching pickup points: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch pickup points")


# =========================
# SAVE PICKUP POINT PRICES
# =========================
@router.post("/bwg-payment/save-prices")
async def save_pickup_prices(body: SavePricesRequest, request: Request):
    """Save price per kg values to bwg or pickup_address tables."""
    decode_admin_user(request)

    try:
        with get_db() as conn:
            cur = conn.cursor()

            for price_item in body.prices:
                if price_item.pickup_point_type == 'main':
                    # Update bwg table
                    cur.execute("""
                        UPDATE bwg 
                        SET wet_price_per_kg = %s, dry_price_per_kg = %s,
                            wet_waste_kg = %s, dry_waste_kg = %s
                        WHERE id = %s
                    """, (
                        price_item.wet_price_per_kg,
                        price_item.dry_price_per_kg,
                        price_item.wet_waste_kg,
                        price_item.dry_waste_kg,
                        price_item.pickup_point_id
                    ))
                else:
                    # Update pickup_address table
                    cur.execute("""
                        UPDATE pickup_address 
                        SET wet_price_per_kg = %s, dry_price_per_kg = %s,
                            wet_waste_kg = %s, dry_waste_kg = %s
                        WHERE id = %s
                    """, (
                        price_item.wet_price_per_kg,
                        price_item.dry_price_per_kg,
                        price_item.wet_waste_kg,
                        price_item.dry_waste_kg,
                        price_item.pickup_point_id
                    ))

            conn.commit()

        return {"message": "Prices saved successfully"}

    except Exception as e:
        print(f"Error saving prices: {e}")
        raise HTTPException(status_code=500, detail="Failed to save prices")


# =========================
# GENERATE BWG PAYMENT INVOICE
# =========================
@router.post("/bwg-payment/generate-invoice")
async def generate_bwg_payment_invoice(body: GenerateBWGInvoiceRequest, request: Request):
    """Generate an invoice for BWG payment based on pickup point prices."""
    decode_admin_user(request)

    if body.total_amount <= 0:
        raise HTTPException(status_code=400, detail="Total amount must be greater than zero")

    IST = ZoneInfo("Asia/Kolkata")
    today = datetime.now(IST).date()

    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # 1. Check if BWG exists
            cur.execute("SELECT id, organization FROM bwg WHERE id = %s", (body.bwg_id,))
            bwg = cur.fetchone()
            if not bwg:
                raise HTTPException(status_code=404, detail="BWG not found")

            # 2. Get or create billing contract
            cur.execute("""
                SELECT contract_id, invoice_counter
                FROM billing_contracts
                WHERE bwg_id = %s
            """, (body.bwg_id,))
            contract = cur.fetchone()

            if not contract:
                # Create a new contract
                contract_id = str(uuid.uuid4())
                cur.execute("""
                    INSERT INTO billing_contracts 
                        (contract_id, bwg_id, default_amount, next_invoice_date, status, invoice_counter)
                    VALUES (%s, %s, %s, %s, 'ACTIVE', 1000)
                    RETURNING contract_id, invoice_counter
                """, (contract_id, body.bwg_id, body.total_amount, today + timedelta(days=30)))
                contract = cur.fetchone()

            contract_id = contract['contract_id']
            counter = contract['invoice_counter'] or 1000
            new_counter = counter + 1

            # 3. Create invoice
            invoice_id = str(uuid.uuid4())
            invoice_number = f"INV-{body.bwg_id}-{new_counter}"
            issue_date = today
            due_date = issue_date + timedelta(days=15)

            # Build description with pickup point breakdown
            description_lines = ["BWG Wise Payment Invoice:"]
            for price_item in body.pickup_prices:
                description_lines.append(f"  - {price_item.pickup_point_id}: ₹{price_item.price}")
            description_lines.append(f"Total: ₹{body.total_amount}")
            description = "\n".join(description_lines)

            cur.execute("""
                INSERT INTO invoices
                    (invoice_id, bwg_id, contract_id, invoice_number, description, amount_due, issue_date, due_date, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING invoice_id, invoice_number, amount_due
            """, (
                invoice_id, body.bwg_id, contract_id,
                invoice_number, description,
                body.total_amount, issue_date, due_date
            ))
            invoice = cur.fetchone()

            # 4. Update invoice counter
            cur.execute("""
                UPDATE billing_contracts
                SET invoice_counter = %s, updated_at = NOW()
                WHERE contract_id = %s
            """, (new_counter, contract_id))

            # 5. Save the prices to DB
            for price_item in body.pickup_prices:
                cur.execute("""
                    INSERT INTO bwg_pickup_prices 
                        (bwg_id, pickup_point_id, pickup_point_type, price, updated_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (bwg_id, pickup_point_id) 
                    DO UPDATE SET 
                        price = EXCLUDED.price,
                        updated_at = NOW()
                """, (
                    body.bwg_id,
                    price_item.pickup_point_id,
                    price_item.pickup_point_type,
                    price_item.price
                ))

            conn.commit()

        return {
            "message": f"Invoice {invoice_number} created successfully",
            "invoice_id": str(invoice['invoice_id']),
            "invoice_number": invoice['invoice_number'],
            "amount_due": float(invoice['amount_due'])
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error generating invoice: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate invoice")


# =========================
# GET INVOICES FOR A BWG
# =========================
@router.get("/bwg-payment/{bwg_id}/invoices")
async def get_bwg_invoices(bwg_id: str, request: Request, month: Optional[int] = None, year: Optional[int] = None):
    """Fetch all invoices for a specific BWG with optional month/year filtering."""
    decode_admin_user(request)

    try:
        with get_db() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Build query with optional month/year filter
            query = """
                SELECT 
                    invoice_id, invoice_number, amount_due, status, 
                    issue_date, due_date, created_at
                FROM invoices
                WHERE bwg_id = %s
            """
            params = [bwg_id]

            if year:
                query += " AND EXTRACT(YEAR FROM issue_date) = %s"
                params.append(year)
            
            if month:
                query += " AND EXTRACT(MONTH FROM issue_date) = %s"
                params.append(month)

            query += " ORDER BY issue_date DESC"

            cur.execute(query, tuple(params))
            invoices = cur.fetchall()

        return {
            "bwg_id": bwg_id,
            "invoices": [
                {
                    "invoice_id": str(inv['invoice_id']),
                    "invoice_number": inv['invoice_number'],
                    "amount_due": float(inv['amount_due']),
                    "status": inv['status'],
                    "issue_date": inv['issue_date'].isoformat() if inv['issue_date'] else None,
                    "due_date": inv['due_date'].isoformat() if inv['due_date'] else None
                }
                for inv in invoices
            ],
            "total_count": len(invoices)
        }

    except Exception as e:
        print(f"Error fetching invoices: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch invoices")

