# app/services/jwt_utils.py
import jwt
from datetime import datetime, timedelta
from app.config import JWT_SECRET

ALGORITHM = "HS256"

def create_token(payload: dict, hours: int = 24) -> str:
    to_encode = payload.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(hours=hours)
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
