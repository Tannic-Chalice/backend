from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)
try:
    response = client.get("/admin/vehicle-logs")
    print(f"Status: {response.status_code}")
    print(f"Content: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
