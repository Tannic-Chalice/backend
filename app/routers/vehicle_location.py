from fastapi import APIRouter, HTTPException
import requests
import os

router = APIRouter()

@router.get("/vehicle-location")
def get_vehicle_location():
    """
    Proxies vehicle location data from the external API to avoid CORS issues.
    """
    api_url = "https://api.wheelseye.com/currentLoc"
    access_token = os.getenv("VEHICLE_API_ACCESS_TOKEN", "3483a695-40e7-446c-83ad-f926b3d46168")
    try:
        resp = requests.get(f"{api_url}?accessToken={access_token}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch vehicle locations: {str(e)}")
