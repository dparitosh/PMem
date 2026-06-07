#!/usr/bin/env python
"""
Diagnose DNS/network issue with Azure endpoint
"""

import requests
import os
import socket

print("=" * 70)
print("DIAGNOSING AZURE OLLAMA CONNECTIVITY")
print("=" * 70)
print()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/generate")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
base_url = OLLAMA_BASE_URL.rsplit("/api/generate", 1)[0]

print(f"Azure Endpoint: {base_url}")
print(f"API Key: {OLLAMA_API_KEY[:20]}...")
print()

# Test 1: DNS resolution
print("[TEST 1] DNS Resolution")
print("-" * 70)

try:
    hostname = "localhost"
    ip = socket.gethostbyname(hostname)
    print(f"✅ DNS resolved: {hostname} → {ip}")
except socket.gaierror as e:
    print(f"❌ DNS resolution failed: {e}")
    print(f"   This might be a network connectivity issue")

print()

# Test 2: HTTP GET (embeddings - known to work)
print("[TEST 2] HTTP GET - Embeddings Endpoint")
print("-" * 70)

try:
    response = requests.post(
        f"{base_url}/api/embeddings",
        headers={"api-key": OLLAMA_API_KEY},
        json={"model": "nomic-embed-text:latest", "prompt": "test"},
        timeout=10,
    )
    
    if response.status_code == 200:
        print(f"✅ POST /api/embeddings works (status 200)")
    else:
        print(f"⚠️  Status {response.status_code}")
        
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")

print()

# Test 3: HTTP POST to chat (mistral - failing)
print("[TEST 3] HTTP POST - Chat Endpoint (mistral)")
print("-" * 70)

try:
    print(f"Sending chat request to: {base_url}/api/chat")
    response = requests.post(
        f"{base_url}/api/chat",
        headers={"api-key": OLLAMA_API_KEY},
        json={
            "model": "mistral",
            "messages": [{"role": "user", "content": "test"}],
            "stream": False,
        },
        timeout=15,
    )
    
    print(f"✅ Status: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"   Response: {str(result)[:150]}")
    else:
        print(f"   Response: {response.text[:200]}")
        
except requests.exceptions.ConnectError as e:
    print(f"❌ Connection Error: {e}")
except requests.exceptions.Timeout:
    print(f"⏱️  Request timeout")
except Exception as e:
    print(f"❌ {type(e).__name__}: {e}")

print()

# Test 4: Try with shorter timeout
print("[TEST 4] Simple HEAD Request (checking endpoint responsiveness)")
print("-" * 70)

try:
    response = requests.head(
        base_url,
        headers={"api-key": OLLAMA_API_KEY},
        timeout=5,
    )
    print(f"Status: {response.status_code}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print()

# Test 5: Check via requests library
print("[TEST 5] Direct Requests Library Test")
print("-" * 70)

try:
    # Create session
    s = requests.Session()
    s.headers.update({"api-key": OLLAMA_API_KEY})
    
    # Try GET first
    print("GET request to /api/chat...")
    r = s.get(f"{base_url}/api/chat", timeout=5)
    print(f"GET Status: {r.status_code}")
    
    # Try POST with simple data
    print("POST request with mistral model...")
    r = s.post(
        f"{base_url}/api/chat",
        json={"model": "mistral", "messages": [{"role": "user", "content": "hi"}], "stream": False},
        timeout=20,
    )
    print(f"POST Status: {r.status_code}")
    if r.status_code == 200:
        print(f"✅ SUCCESS: {r.text[:100]}")
    else:
        print(f"Response: {r.text[:200]}")
        
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)[:200]}")

print()
print("=" * 70)
print("ANALYSIS")
print("=" * 70)
print()

print("""
Possible causes of connection issue:

1. Network/Proxy Issue
   - Azure endpoint might not be accessible from current network
   - Check firewall rules
   - Try from different network

2. DNS Issue
   - Hostname not resolving
   - Use IP instead: dig localhost

3. Azure Endpoint Issue
   - Service might be down
   - Check Azure Portal

4. Model Loading Issue
   - Mistral might be slow to load (first request takes time)
   - Embeddings is smaller/faster to load

Next steps:
1. Check if embeddings still work (it did earlier)
2. Check Azure service status
3. Try from different network
4. Check Azure logs/diagnostics
""")
