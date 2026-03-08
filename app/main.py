# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.routers import (
    bswl, driver_user, zones, wards,
    otp, addpickup, get_file_url,
    location, registrations, admin_profile,
    payments, vehicles,
    forgot_pwd, registrations,
    driver,
    bwg,
    supervisor,
    admin,
    bwg,
    grievances,
    pickups,
    auth,
    driver_task,
    admin_metrics,
    collection_data,
    reports, vehicle_location, weight_bridge,
    messaging)
from app.routers.admin import billing
from app.routers.admin import bwg_payment
from app.scheduler import init_scheduler, shutdown_scheduler


# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("uvicorn")

app = FastAPI()

WEB_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://localhost:3000",
    "https://127.0.0.1:3000",
    "http://localhost",
    "capacitor://localhost",
    "https://localhost",
    "https://www.oribymsgp.com",
    "https://www.oribymsgp.com/",
    "http://192.168.1.42:3000",
]

# Allow any LAN host on port 3000 (mobile testing)
LAN_ORIGIN_REGEX = r"http://(192\\.168|10\\.\d{1,3}|172\\.(1[6-9]|2[0-9]|3[0-1]))\\.\d{1,3}:3000"

app.add_middleware(
    CORSMiddleware,
    allow_origins=WEB_ORIGINS, 
    # "*" is required for Capacitor (native app has no Origin header)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_origin_regex=LAN_ORIGIN_REGEX,
)


@app.get("/")
def root():
    return {"message": "FastAPI backend running!"}

app.include_router(otp.router, prefix="/otp", tags=["OTP"])
app.include_router(registrations.router, prefix="/registrations", tags=["Registrations"])
app.include_router(location.router, prefix="/location", tags=["Location"])
app.include_router(payments.router, prefix="/payments", tags=["Payments"])
app.include_router(forgot_pwd.router, prefix="/forgot_pwd", tags=["Forgot Password"])
app.include_router(auth.router, prefix="/auth")
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(billing.router, prefix="/api/admin", tags=["Admin Billing"])
app.include_router(bwg_payment.router, prefix="/api/admin", tags=["BWG Payment"])
app.include_router(admin_metrics.router, prefix="/admin", tags=["Admin Metrics"])
app.include_router(bwg.router, prefix="/bwg", tags=["BWG"])
app.include_router(bswl.router, prefix="/bswl", tags=["BSWML"])
app.include_router(driver.router, prefix="/drivers", tags=["Driver"])
app.include_router(grievances.router, prefix="/grievances", tags=["Grievances"])
app.include_router(pickups.router, prefix="/pickups", tags=["Pickups"])
app.include_router(zones.router, prefix="/zones", tags=["Zones"])
# app.include_router(meta.router, prefix="/meta", tags=["Meta"])
app.include_router(wards.router)
app.include_router(addpickup.router)
app.include_router(get_file_url.router)
app.include_router(registrations.router)
app.include_router(admin_profile.router)
app.include_router(driver_user.router)
app.include_router(vehicles.router)
app.include_router(driver_task.router, prefix="/driver_task", tags=["Driver Task"])
app.include_router(vehicle_location.router, prefix="/backend-api", tags=["Vehicle Locations"])
app.include_router(collection_data.router, prefix="/admin", tags=["Collection Data"])
app.include_router(reports.router, prefix="/admin", tags=["Reports"])
app.include_router(weight_bridge.router)
app.include_router(supervisor.router)
app.include_router(messaging.router, prefix="/messaging", tags=["Messaging"])


# Startup and shutdown events for scheduler
@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on application startup."""
    try:
        init_scheduler()
        logger.info("Application startup complete - scheduler initialized")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler on startup: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Shutdown scheduler on application shutdown."""
    try:
        shutdown_scheduler()
        logger.info("Application shutdown complete - scheduler stopped")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

