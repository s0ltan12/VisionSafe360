import asyncio
import websockets
import json
import requests
import time
import sys

async def main():
    token = sys.argv[1]
    uri = "ws://127.0.0.1:8000/ws/incidents"
    incident_id = f"TEST-INC-{int(time.time())}"
    
    async with websockets.connect(uri) as websocket:
        print("WS connected")
        # Ensure we skip the connection message
        await websocket.recv()
        
        # Post incident
        payload = {
            "id": incident_id,
            "zone": "Zone A",
            "classification": "Safety Violation",
            "severity": "High",
            "root_cause": "Test Cause",
            "corrective_action": "Test Action",
            "created_at": "2024-10-25"
        }
        
        resp = requests.post(
            "http://127.0.0.1:8000/api/incidents",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        print(f"POST status: {resp.status_code}")
        
        # Wait for WS message
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
            data = json.loads(message)
            print(f"WS received type: {data['type']}")
            if data['data']['id'] == incident_id:
                print("SUCCESS: ID matched")
            else:
                print(f"FAILURE: Expected {incident_id}, got {data['data']['id']}")
        except Exception as e:
            print(f"Error or timeout: {e}")

if __name__ == "__main__":
    asyncio.run(main())
