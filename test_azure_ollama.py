#!/usr/bin/env python
"""
Test Azure API Manager Ollama endpoint
"""

import requests
import os
from urllib.parse import urljoin

print("=" * 70)
print("TESTING AZURE API MANAGER OLLAMA ENDPOINT")
print("=" * 70)
print()

AZURE_ENDPOINT = "https://azdtapimanager.azure-api.net/ollama"
AZURE_API_KEY = os.getenv("OLLAMA_API_KEY", "56a2f436e96349f0982f4ee477fce451")

print(f"Endpoint: {AZURE_ENDPOINT}")
print(f"API Key: {AZURE_API_KEY[:20]}...")
print()

# Test 1: Check if endpoint is accessible
print("[TEST 1] Azure Endpoint Accessibility")
print("-" * 70)

try:
    response = requests.get(
        f"{AZURE_ENDPOINT}/api/tags",
        headers={"api-key": AZURE_API_KEY},
        timeout=10,
        verify=True
    )
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        models = response.json().get("models", [])
        print(f"✅ Azure Ollama endpoint is accessible")
        print(f"   Available models: {len(models)}")
        for model in models[:5]:
            name = model.get("name", "unknown")
            print(f"   - {name}")
        if len(models) > 5:
            print(f"   ... and {len(models) - 5} more")
    elif response.status_code == 401:
        print(f"❌ Unauthorized (401) - API key may be invalid")
        print(f"   Response: {response.text[:200]}")
    elif response.status_code == 403:
        print(f"❌ Forbidden (403) - Check API key and permissions")
        print(f"   Response: {response.text[:200]}")
    elif response.status_code == 404:
        print(f"❌ Not Found (404) - Endpoint may not exist")
        print(f"   Response: {response.text[:200]}")
    else:
        print(f"❌ Unexpected status: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except requests.exceptions.ConnectionError as e:
    print(f"❌ Connection error - endpoint not reachable")
    print(f"   Details: {str(e)[:200]}")
except requests.exceptions.Timeout:
    print(f"❌ Request timeout - endpoint not responding")
except requests.exceptions.SSLError as e:
    print(f"❌ SSL/TLS error - certificate issue")
    print(f"   Details: {str(e)[:200]}")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {str(e)[:200]}")

print()

# Test 2: Try chat endpoint
print("[TEST 2] Azure Chat Endpoint")
print("-" * 70)

try:
    response = requests.post(
        f"{AZURE_ENDPOINT}/api/chat",
        headers={"api-key": AZURE_API_KEY},
        json={
            "model": "3.1:8b",
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        },
        timeout=30,
        verify=True
    )
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        print(f"✅ Chat endpoint works")
        print(f"   Response: {str(result)[:200]}")
    else:
        print(f"❌ Chat endpoint returned {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ Chat error: {type(e).__name__}: {str(e)[:200]}")

print()

# Test 3: Try embeddings endpoint
print("[TEST 3] Azure Embeddings Endpoint")
print("-" * 70)

try:
    response = requests.post(
        f"{AZURE_ENDPOINT}/api/embeddings",
        headers={"api-key": AZURE_API_KEY},
        json={
            "model": "nomic-embed-text",
            "prompt": "test",
        },
        timeout=30,
        verify=True
    )
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        result = response.json()
        embedding = result.get("embedding", [])
        print(f"✅ Embeddings endpoint works")
        print(f"   Embedding dimension: {len(embedding)}")
        print(f"   Sample: {embedding[:3]}")
    else:
        print(f"❌ Embeddings endpoint returned {response.status_code}")
        print(f"   Response: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ Embeddings error: {type(e).__name__}: {str(e)[:200]}")

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
If Azure endpoint tests pass:
- Ollama services are available via Azure API Manager
- Vector search and Cypher QA chain can be enabled
- No local installation needed

If Azure endpoint tests fail:
- Either API key is invalid
- Or endpoint URL is wrong
- Or no network access to Azure

Contact your Azure API Manager administrator for:
- Correct endpoint URL
- Valid API key
- Network access verification
""")
