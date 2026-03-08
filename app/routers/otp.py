from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from twilio.base.exceptions import TwilioRestException
from app.services.twilio_client import TwilioClientSingleton
from app.config import TWILIO_VERIFY_SERVICE_SID

router = APIRouter()

# 🔐 Demo constants (Play Store)
DEMO_PHONE_RAW = "9999999999"
DEMO_PHONE_NORMALIZED = "+919999999999"
DEMO_OTP = "123456"


class PhoneNumber(BaseModel):
    phone: str


class VerifyOTP(BaseModel):
    phone: str
    code: str


def normalize_phone(phone: str) -> str:
    p = phone.replace(" ", "").replace("-", "")
    if not p.startswith("+"):
        p = "+91" + p.lstrip("0")
    return p


@router.post("/send")
def send_otp(data: PhoneNumber):
    phone = normalize_phone(data.phone)

    # ✅ DEMO OTP BYPASS
    if phone == DEMO_PHONE_NORMALIZED:
        return {
            "status": "pending",
            "message": "Demo OTP accepted",
            "is_demo": True
        }

    client = TwilioClientSingleton.get_client()

    try:
        verification = client.verify.v2.services(
            TWILIO_VERIFY_SERVICE_SID
        ).verifications.create(
            to=phone,
            channel="sms"
        )
        return {"status": verification.status}

    except TwilioRestException as e:
        raise HTTPException(status_code=400, detail=str(e.msg))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/verify")
def verify_otp(data: VerifyOTP):
    phone = normalize_phone(data.phone)

    # ✅ DEMO OTP BYPASS
    if phone == DEMO_PHONE_NORMALIZED:
        if data.code == DEMO_OTP:
            return {
                "status": "approved",
                "message": "Demo OTP verified",
                "is_demo": True
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid demo OTP")

    client = TwilioClientSingleton.get_client()

    try:
        result = client.verify.v2.services(
            TWILIO_VERIFY_SERVICE_SID
        ).verification_checks.create(
            to=phone,
            code=data.code
        )

        if result.status != "approved":
            raise HTTPException(status_code=400, detail="Invalid OTP")

        return {"status": result.status}

    except TwilioRestException as e:
        raise HTTPException(status_code=400, detail=str(e.msg))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
