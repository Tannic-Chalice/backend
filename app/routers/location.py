from fastapi import APIRouter

router = APIRouter()

@router.get("/test")
def location_test():
    return {"message": "Location router working"}
