from twilio.rest import Client
from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN

class TwilioClientSingleton:
    _client = None

    @classmethod
    def get_client(cls):
        # Lazy initialization
        if cls._client is None:
            print("Initializing Twilio Client...")
            cls._client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        return cls._client
