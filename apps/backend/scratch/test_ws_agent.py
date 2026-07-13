import asyncio
import httpx
import websockets
import json
import sqlite3
import os
import sys

async def main():
    print("=== STARTING INTEGRATION TEST ===")
    
    # 1. Create a session mapping to 'coder'
    async with httpx.AsyncClient() as client:
        r = await client.post("http://127.0.0.1:8765/api/v1/sessions", json={
            "agent_id": "coder"
        })
        if r.status_code != 201:
            print(f"Failed to create session: {r.status_code} - {r.text}")
            sys.exit(1)
        
        session_data = r.json()
        session_id = session_data["session_id"]
        print(f"Created WindAgent session: {session_id}")

    # 2. Connect to the WebSocket endpoint to stream events
    uri = f"ws://127.0.0.1:8765/ws/{session_id}"
    print(f"Connecting to WebSocket: {uri}")
    
    async with websockets.connect(uri) as websocket:
        print("Connected to WebSocket successfully!")
        
        # 3. Post a message to start the agent execution
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"http://127.0.0.1:8765/api/v1/sessions/{session_id}/messages",
                json={"content": "hello, print 'Hello from integration test' to console using python or echo"}
            )
            if r.status_code != 202:
                print(f"Failed to send message: {r.status_code} - {r.text}")
                sys.exit(1)
            
            run_data = r.json()
            print(f"Sent message. Msg ID: {run_data['message_id']}. Hermes Run ID: {run_data['hermes_run_id']}")
        
        # 4. Read events from WebSocket
        print("Waiting for events from agent...")
        try:
            while True:
                # Bounded wait for messages
                message = await asyncio.wait_for(websocket.recv(), timeout=20.0)
                if message == "ping":
                    print("[WS Keepalive] ping")
                    continue
                
                event = json.loads(message)
                event_type = event.get("event")
                data = event.get("data", {})
                
                print(f"[WS Event] {event_type} - {list(data.keys())}")
                
                # Show content of text/markdown messages or tool outputs
                if event_type == "message":
                    print(f"  --> Agent Message: {data.get('content')}")
                elif event_type == "tool_call":
                    print(f"  --> Tool call: {data.get('name')} with args {data.get('arguments')}")
                elif event_type == "tool_output":
                    print(f"  --> Tool output status: {data.get('status')}")
                elif event_type == "run_completed":
                    print("Agent run completed successfully!")
                    break
        except asyncio.TimeoutError:
            print("No events received for 20 seconds. Stopping listener.")
        except Exception as e:
            print(f"Error reading WebSocket: {e}")

    # 5. Verify database records
    db_path = "windagent.db"
    if os.path.exists(db_path):
        print("\n=== VERIFYING DATABASE SCHEMAS & RECORDS ===")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Query session
        cursor.execute("SELECT id, status FROM chat_sessions WHERE id = ?", (session_id,))
        sess_record = cursor.fetchone()
        print(f"DB chat_sessions record for current run: {sess_record}")
        
        # Query messages
        cursor.execute("SELECT sender, content FROM messages WHERE session_id = ?", (session_id,))
        msg_records = cursor.fetchall()
        print("DB messages stored:")
        for idx, row in enumerate(msg_records, 1):
            print(f"  {idx}. {row[0].upper()}: {row[1][:100]}...")
            
        conn.close()
    else:
        print(f"Database file not found at {db_path}")

if __name__ == "__main__":
    asyncio.run(main())
