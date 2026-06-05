#!/usr/bin/env python
"""
Test exact endpoint structure from .env
"""

import requests
import os
import json

print("=" * 70)
print("TESTING EXACT ENDPOINT: /ollama/api/generate")
print("=" * 70)
print()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://azdtapimanager.azure-api.net/ollama/api/generate")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "56a2f436e96349f0982f4ee477fce451")
LLM_MODEL = os.getenv("LLM_MODEL_NAME", "3.1:8b")

print(f"Exact URL from .env: {OLLAMA_BASE_URL}")
print(f"API Key: {OLLAMA_API_KEY[:20]}...")
print(f"Model: {LLM_MODEL}")
print()

# Test 1: POST to /api/generate (Ollama generate endpoint)
print("[TEST 1] POST to /api/generate")
print("-" * 70)

try:
    response = requests.post(
        OLLAMA_BASE_URL,
        headers={"api-key": OLLAMA_API_KEY},
        json={
            "model": LLM_MODEL,
            "prompt": "What is 2+2?",
            "stream": False,
        },
        timeout=30,
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        print("✅ /api/generate works!")
    
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print()

# Test 2: Try base URL without /api/generate to get models
print("[TEST 2] GET base URL /ollama")
print("-" * 70)

base_url = "http://azdtapimanager.azure-api.net/ollama"
try:
    response = requests.get(
        base_url,
        headers={"api-key": OLLAMA_API_KEY},
        timeout=10,
    )
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print()

# Test 3: Try direct endpoints
print("[TEST 3] Trying /ollama/api/generate directly (like ollama does)")
print("-" * 70)

endpoints_to_try = [
    ("generate", {"model": LLM_MODEL, "prompt": "test", "stream": False}),
    ("chat", {"model": LLM_MODEL, "messages": [{"role": "user", "content": "test"}], "stream": False}),
    ("embeddings", {"model": "nomic-embed-text:latest", "prompt": "test"}),
    ("tags", None),  # GET request
]

for endpoint_name, payload in endpoints_to_try:
    url = f"{base_url}/api/{endpoint_name}"
    print(f"\n{endpoint_name}: {url}")
    
    try:
        if payload is None:
            response = requests.get(
                url,
                headers={"api-key": OLLAMA_API_KEY},
                timeout=10,
            )
        else:
            response = requests.post(
                url,
                headers={"api-key": OLLAMA_API_KEY},
                json=payload,
                timeout=30,
            )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            print(f"✅ SUCCESS")
            if "embeddings" in endpoint_name:
                try:
                    data = response.json()
                    embedding = data.get("embedding", [])
                    print(f"   Embedding dimension: {len(embedding)}")
                except:
                    pass
        else:
            print(f"Response: {response.text[:200]}")
            
    except Exception as e:
        print(f"Error: {type(e).__name__}: {str(e)[:100]}")

print()
print("=" * 70)
