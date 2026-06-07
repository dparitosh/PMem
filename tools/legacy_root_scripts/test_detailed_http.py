#!/usr/bin/env python
"""
Direct HTTP test with full debugging
"""

import requests
import json
import time
import sys

print("=" * 70)
print("DETAILED HTTP STREAMING TEST")
print("=" * 70)
print()

BACKEND_URL = "http://localhost:8000"
CHAT_ENDPOINT = f"{BACKEND_URL}/chat-stream"

# First, verify backend is up
print("[0] Health Check")
print("-" * 70)

try:
    response = requests.get(f"{BACKEND_URL}/health", timeout=5)
    print(f"[OK] Backend health: {response.status_code}")
except Exception as e:
    print(f"[ERROR] Backend not responding: {e}")
    sys.exit(1)

print()

# Now test streaming with detailed error capture
print("[1] Streaming Request Test")
print("-" * 70)

chat_payload = {
    "session_id": "test-001",
    "message": "Hello"
}

print(f"Endpoint: {CHAT_ENDPOINT}")
print(f"Payload: {json.dumps(chat_payload)}")
print()

try:
    # Make the request
    response = requests.post(
        CHAT_ENDPOINT,
        json=chat_payload,
        timeout=60,
        stream=True,
    )
    
    print(f"Status Code: {response.status_code}")
    print(f"Headers:")
    for key, value in response.headers.items():
        if key.lower() not in ['content-length', 'date', 'server', 'set-cookie']:
            print(f"  {key}: {value}")
    print()
    
    if response.status_code != 200:
        print(f"[ERROR] Got status {response.status_code}")
        print(f"Response body: {response.text[:500]}")
        sys.exit(1)
    
    # Read the full response
    print("Full Response Stream:")
    print("-" * 70)
    
    full_text = ""
    full_json = ""
    
    for line in response.iter_lines(decode_unicode=True):
        if line:
            full_text += line + "\n"
            
            if line.startswith('data: '):
                json_str = line[6:]
                try:
                    data = json.loads(json_str)
                    print(f"{json_str}")
                except json.JSONDecodeError as je:
                    print(f"[Invalid JSON] {json_str[:100]}")
    
    print()
    print(f"Total bytes received: {len(full_text)}")
    print()
    
    # Parse all the data
    print("Parsed Events:")
    print("-" * 70)
    
    events = []
    for line in full_text.split('\n'):
        if line.startswith('data: '):
            try:
                event = json.loads(line[6:])
                events.append(event)
                
                if 'token' in event:
                    print(f"[TOKEN] {event['token']}")
                elif 'status' in event:
                    print(f"[STATUS] {event['status']}")
                elif 'error' in event:
                    print(f"[ERROR] {event['error']}")
                elif 'done' in event:
                    print(f"[DONE] {event['done']}")
                    
            except Exception as e:
                print(f"[PARSE ERROR] {e}")
    
    print()
    print(f"Total events: {len(events)}")
    
    # Check for errors
    has_error = any('error' in e for e in events)
    if has_error:
        errors = [e for e in events if 'error' in e]
        print(f"\n[ERROR] Errors found:")
        for err in errors:
            print(f"   {err['error']}")
    else:
        tokens = [e.get('token', '') for e in events if 'token' in e]
        response_text = ''.join(tokens)
        print(f"\n[OK] Response received: {response_text[:100]}...")
        
except requests.exceptions.ConnectionError as e:
    print(f"[ERROR] Connection error: {e}")
except requests.exceptions.Timeout as e:
    print(f"[ERROR] Request timeout: {e}")
except Exception as e:
    print(f"[ERROR] Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)
