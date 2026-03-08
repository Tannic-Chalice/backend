from app.main import app
from fastapi.testclient import TestClient
import json

client = TestClient(app)

# Test all lookup endpoints
endpoints = [
    '/admin/supervisors',
    '/admin/drivers', 
    '/admin/vehicles',
    '/admin/wards',
    '/admin/weigh-bridges'
]

for endpoint in endpoints:
    print(f'\nTesting {endpoint}')
    try:
        resp = client.get(endpoint)
        print(f'Status: {resp.status_code}')
        if resp.status_code == 200:
            data = resp.json()
            print(f'Count: {len(data)}')
            if len(data) > 0:
                print(f'Sample: {data[0]}')
        else:
            print(f'Error: {resp.text[:100]}')
    except Exception as e:
        print(f'Exception: {e}')
