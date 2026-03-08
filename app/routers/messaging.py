# app/routers/messaging.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.twilio_client import TwilioClientSingleton
from app.config import TWILIO_VERIFY_SERVICE_SID, TWILIO_PHONE_NUMBER
import logging

router = APIRouter(tags=["Messaging"])

logger = logging.getLogger(__name__)


class SMSRequest(BaseModel):
    """Request model for sending SMS"""
    to_phone: str  # Recipient phone number
    message: str   # Message content
    message_type: Optional[str] = "general"  # Type of message (general, alert, notification, etc.)


class BulkSMSRequest(BaseModel):
    """Request model for sending bulk SMS"""
    phone_numbers: list[str]  # List of recipient phone numbers
    message: str              # Message content
    message_type: Optional[str] = "general"


class SMSResponse(BaseModel):
    """Response model for SMS sending"""
    success: bool
    message_sid: Optional[str] = None
    error: Optional[str] = None
    phone: str
    timestamp: str


@router.post("/send-sms", response_model=SMSResponse)
async def send_sms(request: SMSRequest):
    """
    Send a single SMS message via Twilio
    
    - **to_phone**: Recipient phone number (with or without country code)
    - **message**: SMS message content
    - **message_type**: Type of message (general, alert, notification, etc.)
    """
    try:
        logger.info(f"[SMS] Sending SMS to {request.to_phone}: {request.message}")
        
        # Get Twilio client
        client = TwilioClientSingleton.get_client()
        if not client:
            logger.error("[SMS] Could not initialize Twilio client")
            raise HTTPException(status_code=500, detail="Failed to initialize Twilio client")
        
        # Format phone number
        formatted_phone = request.to_phone.strip()
        if not formatted_phone.startswith("+"):
            formatted_phone = "+91" + formatted_phone  # India country code
        
        # Send SMS
        message = client.messages.create(
            body=request.message,
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )
        
        logger.info(f"[SMS] SUCCESS: Message sent to {formatted_phone}. SID: {message.sid}")
        
        from datetime import datetime
        return SMSResponse(
            success=True,
            message_sid=message.sid,
            phone=formatted_phone,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"[SMS] ERROR: Failed to send SMS: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to send SMS: {str(e)}")


@router.post("/send-bulk-sms")
async def send_bulk_sms(request: BulkSMSRequest):
    """
    Send SMS to multiple recipients
    
    - **phone_numbers**: List of recipient phone numbers
    - **message**: SMS message content
    - **message_type**: Type of message
    """
    try:
        logger.info(f"[SMS] Sending bulk SMS to {len(request.phone_numbers)} recipients")
        
        # Get Twilio client
        client = TwilioClientSingleton.get_client()
        if not client:
            logger.error("[SMS] Could not initialize Twilio client")
            raise HTTPException(status_code=500, detail="Failed to initialize Twilio client")
        
        results = {
            "total": len(request.phone_numbers),
            "sent": 0,
            "failed": 0,
            "messages": []
        }
        
        # Send SMS to each phone number
        for phone in request.phone_numbers:
            try:
                formatted_phone = phone.strip()
                if not formatted_phone.startswith("+"):
                    formatted_phone = "+91" + formatted_phone
                
                message = client.messages.create(
                    body=request.message,
                    from_=TWILIO_PHONE_NUMBER,
                    to=formatted_phone
                )
                
                results["sent"] += 1
                results["messages"].append({
                    "phone": formatted_phone,
                    "status": "sent",
                    "message_sid": message.sid
                })
                logger.info(f"[SMS] Sent to {formatted_phone}. SID: {message.sid}")
                
            except Exception as e:
                results["failed"] += 1
                results["messages"].append({
                    "phone": phone,
                    "status": "failed",
                    "error": str(e)
                })
                logger.error(f"[SMS] Failed to send to {phone}: {str(e)}")
        
        return results
        
    except Exception as e:
        logger.error(f"[SMS] ERROR in bulk send: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Bulk send failed: {str(e)}")


@router.post("/send-alert")
async def send_alert(request: SMSRequest):
    """
    Send an alert SMS with priority handling
    
    - **to_phone**: Recipient phone number
    - **message**: Alert message content
    """
    try:
        logger.info(f"[ALERT] Sending alert SMS to {request.to_phone}")
        
        client = TwilioClientSingleton.get_client()
        if not client:
            raise HTTPException(status_code=500, detail="Failed to initialize Twilio client")
        
        formatted_phone = request.to_phone.strip()
        if not formatted_phone.startswith("+"):
            formatted_phone = "+91" + formatted_phone
        
        # Add alert prefix to message
        alert_message = f"[ALERT] {request.message}"
        
        message = client.messages.create(
            body=alert_message,
            from_=TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )
        
        logger.info(f"[ALERT] Sent to {formatted_phone}. SID: {message.sid}")
        
        from datetime import datetime
        return SMSResponse(
            success=True,
            message_sid=message.sid,
            phone=formatted_phone,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"[ALERT] ERROR: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to send alert: {str(e)}")


@router.get("/sms-status/{message_sid}")
async def get_sms_status(message_sid: str):
    """
    Get the status of a sent SMS message
    
    - **message_sid**: Twilio message SID
    """
    try:
        logger.info(f"[SMS] Checking status for message: {message_sid}")
        
        client = TwilioClientSingleton.get_client()
        if not client:
            raise HTTPException(status_code=500, detail="Failed to initialize Twilio client")
        
        message = client.messages(message_sid).fetch()
        
        return {
            "message_sid": message.sid,
            "status": message.status,
            "to": message.to,
            "from": message.from_,
            "body": message.body,
            "date_sent": message.date_sent,
            "price": message.price,
            "error_code": message.error_code,
            "error_message": message.error_message
        }
        
    except Exception as e:
        logger.error(f"[SMS] ERROR checking status: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Failed to get message status: {str(e)}")


@router.get("/health")
async def health_check():
    """Check Twilio connectivity and health"""
    try:
        logger.info("[HEALTH] Checking Twilio client")
        
        client = TwilioClientSingleton.get_client()
        if not client:
            raise HTTPException(status_code=503, detail="Twilio client not initialized")
        
        # Try to fetch account info to verify connectivity
        account = client.api.accounts(client.account_sid).fetch()
        
        return {
            "status": "healthy",
            "twilio_account": client.account_sid,
            "twilio_phone": TWILIO_PHONE_NUMBER,
            "account_status": account.status,
            "friendly_name": account.friendly_name
        }
        
    except Exception as e:
        logger.error(f"[HEALTH] ERROR: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Twilio health check failed: {str(e)}")
