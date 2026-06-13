import asyncio
import websockets
import pytest


@pytest.mark.anyio
async def test_ws_no_token():
    uri = "ws://127.0.0.1:8000/ws/incidents"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected without token")
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                print(f"Received message: {message}")
            except asyncio.TimeoutError:
                print("No message received within timeout")
    except Exception as e:
        print(f"Connection failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_ws_no_token())
