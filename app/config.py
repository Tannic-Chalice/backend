from dotenv import load_dotenv
import os

load_dotenv()

# --- Core Credentials ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_VERIFY_SERVICE_SID = os.getenv("TWILIO_VERIFY_SERVICE_SID")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
BACKEND_URL = os.getenv("BACKEND_URL")
JWT_SECRET = os.getenv("JWT_SECRET", "")
GOOGLE_CLIENT_ID = os.getenv("NEXT_PUBLIC_GOOGLE_CLIENT_ID") 
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = "ap-south-1"  # change if needed
AWS_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")

# --- Razorpay Credentials ---
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET") 

# --- Environment & Cookie Logic ---

# Default to "development" if not set.
# IMPORTANT: In GCP (Cloud Run/App Engine), add an environment variable: ENVIRONMENT=production
ENV = os.getenv("ENVIRONMENT", "development")

def _get_cookie_settings():
    """
    Returns the correct cookie configuration based on the environment.
    - Production (GCP+Vercel): Requires Secure=True and SameSite=None for cross-origin.
    - Development (Localhost): Requires Secure=False and SameSite=Lax (since no HTTPS).
    """
    if ENV == "production":
        return {
            "secure": True,        # Must be True for SameSite=None
            "samesite": "none",    # Allow cookie to cross from Vercel -> GCP
            "httponly": True,      # Prevent JS access (security best practice)
        }
    else:
        return {
            "secure": True,       # Localhost is HTTP, so Secure must be False
            "samesite": "lax",     # 'Lax' works reliably on localhost
            "httponly": True,
        }

# Export this dict to be used in your router
COOKIE_SETTINGS = _get_cookie_settings()