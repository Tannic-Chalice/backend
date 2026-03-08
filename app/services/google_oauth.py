# app/services/google_oauth.py
from google.oauth2 import id_token
from google.auth.transport import requests
from app.config import GOOGLE_CLIENT_ID

def verify_google_token(token: str):
    """Returns payload dict or raises."""
    return id_token.verify_oauth2_token(
        token,
        requests.Request(),
        GOOGLE_CLIENT_ID,
    )
