#!/usr/bin/env python
"""
Test UI Chat functionality with corrected Ollama configuration
"""

import requests
import json
import time
import sys

print("=" * 70)
print("TESTING UI CHAT FUNCTIONALITY")
print("=" * 70)
print()

BACKEND_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{BACKEND_URL}/chat-stream"
HEALTH_ENDPOINT = f"{BACKEND_URL}/health"

# Test 1: Check backend is running
print("[TEST 1] Backend Health Check")
print("-" * 70)

try:
    response = requests.get(HEALTH_ENDPOINT, timeout=5)
    if response.status_code == 200:
        health = response.json()
        print(f"✅ Backend is running")
        print(f"   Status: {health.get('status', 'unknown')}")
        print(f"   Neo4j: {health.get('neo4j', 'unknown')}")
        print(f"   LLM: {health.get('llm', 'unknown')}")
    else:
        print(f"⚠️  Backend responded but status is {response.status_code}")
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to backend at {BACKEND_URL}")
    print(f"   Make sure backend is running: python main.py")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")
    sys.exit(1)

print()

# Test 2: Test chat-stream endpoint
print("[TEST 2] Chat-Stream Endpoint")
print("-" * 70)

chat_payload = {
    "session_id": "test-session-001",
    "message": "What is Neo4j?"
}

print(f"Sending chat request: {json.dumps(chat_payload)}")
print()

try:
    response = requests.post(
        CHAT_ENDPOINT,
        json=chat_payload,
        timeout=30,
        stream=True,  # For streaming response
    )
    
    if response.status_code == 200:
        print(f"✅ Chat endpoint responding (200 OK)")
        print(f"   Content-Type: {response.headers.get('content-type')}")
        
        # Try to read streaming response
        print("\n   Streaming response:")
        print("-" * 70)
        
        full_response = ""
        token_count = 0
        error_occurred = False
        
        for line in response.iter_lines():
            if line:
                line_str = line.decode('utf-8') if isinstance(line, bytes) else line
                
                if line_str.startswith('data: '):
                    try:
                        data = json.loads(line_str[6:])
                        
                        if 'token' in data:
                            print(data['token'], end='', flush=True)
                            full_response += data['token']
                            token_count += 1
                        
                        elif 'status' in data:
                            print(f"\n   [Status] {data['status']}")
                        
                        elif 'error' in data:
                            print(f"\n   ❌ [Error] {data['error']}")
                            error_occurred = True
                        
                        elif 'done' in data and data['done']:
                            print("\n\n   ✅ Chat stream completed")
                            
                    except json.JSONDecodeError:
                        pass
        
        if not error_occurred and token_count > 0:
            print(f"\n✅ Chat stream successful")
            print(f"   Tokens received: {token_count}")
            print(f"   Response length: {len(full_response)} characters")
            print(f"   First 200 chars: {full_response[:200]}...")
        elif error_occurred:
            print(f"\n❌ Chat encountered an error")
        else:
            print(f"\n⚠️  No tokens received (might indicate no chat service)")
            
    elif response.status_code == 404:
        print(f"❌ Chat endpoint not found (404)")
        print(f"   Make sure backend is at {BACKEND_URL}")
    else:
        print(f"❌ Chat endpoint returned status {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except requests.exceptions.Timeout:
    print(f"❌ Chat request timed out after 30 seconds")
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to {CHAT_ENDPOINT}")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print()

print("""
To manually test the chat UI:

1. Start the backend:
   cd Depo_onto
   python main.py

2. In another terminal, start the frontend:
   cd Depo_onto/frontend
   npm start

3. Open browser: http://localhost:3000

4. Navigate to the Chat section and try:
   - Sample query: "What is Neo4j?"
   - Check the response streaming
   - Verify no errors appear

Expected behavior:
✅ Chat messages appear in real-time
✅ Response uses Mistral model
✅ Markdown formatting works
✅ Error messages display properly if issues occur
""")

print()
