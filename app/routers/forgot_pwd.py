from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx
from app.database import get_db
from app.config import BACKEND_URL

router = APIRouter()

class ForgotPasswordRequest(BaseModel):
    email: str

class OTPResponse(BaseModel):
    status: str
    message: str
    phone: str

@router.post("/forgot-pwd", response_model=OTPResponse)
async def forgot_password(request: ForgotPasswordRequest):

    # --- RAW SQL using psycopg2 ---
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT phone FROM bwg WHERE email = %s LIMIT 1",
                (request.email,)
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Email not found")

            phone_number = row[0]

    except Exception as db_error:
        raise HTTPException(status_code=500, detail=f"Database error: {db_error}")

    # --- CALL OTP SERVICE ---
    try:
        async with httpx.AsyncClient() as client:
            send_response = await client.post(
                f"{BACKEND_URL}/otp/send",
                json={"phone": phone_number}
            )

        if send_response.status_code == 200:
            return OTPResponse(
                status="success",
                message="OTP sent successfully",
                phone=phone_number
            )
        else:
            raise HTTPException(
                status_code=send_response.status_code,
                detail="Failed to send OTP"
            )

    except Exception as http_error:
        raise HTTPException(status_code=500, detail=f"OTP service error: {http_error}")
