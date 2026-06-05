#!/usr/bin/env python
"""
Test ACTUAL Azure Ollama endpoint from .env configuration
"""

import requests
import os
import sys

print("=" * 70)
print("TESTING AZURE OLLAMA - USING EXACT .ENV CONFIGURATION")
print("=" * 70)
print()

# Read actual configuration from environment (as backend would)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api/generate")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL_NAME", "3.1:8b")
EMBED_MODEL = os.getenv("EMBED_MODEL_NAME", "nomic-embed-text:latest")

print(f"Configuration from .env:")
print(f"  OLLAMA_BASE_URL: {OLLAMA_BASE_URL}")
print(f"  OLLAMA_API_KEY: {OLLAMA_API_KEY[:20]}...")
print(f"  LLM_MODEL_NAME: {LLM_MODEL}")
print(f"  EMBED_MODEL_NAME: {EMBED_MODEL}")
print()

# Test 1: Check endpoint accessibility
print("[TEST 1] Azure Endpoint Accessibility")
print("-" * 70)

# Note: The URL in .env has /api/generate at the end
# Need to test if this is the base URL or needs modification

print(f"Testing: {OLLAMA_BASE_URL}")
print()

# Try as-is
print("1a) Testing base URL as-is (from .env):")
try:
    response = requests.get(
        OLLAMA_BASE_URL,
        headers={"api-key": OLLAMA_API_KEY},
        timeout=10,
    )
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {type(e).__name__}: {str(e)[:100]}")

print()

# Try without /api/generate (in case it's just /ollama)
base_without_api = OLLAMA_BASE_URL.rsplit("/api/generate", 1)[0]
print(f"1b) Testing without /api/generate: {base_without_api}")
try:
    response = requests.get(
        f"{base_without_api}/api/tags",
        headers={"api-key": OLLAMA_API_KEY},
        timeout=10,
    )
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print(f"   ✅ SUCCESS - Models available:")
        models = response.json().get("models", [])
        for model in models[:3]:
            print(f"      - {model.get('name')}")
    else:
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"   Error: {type(e).__name__}: {str(e)[:100]}")

print()

# Test 2: Try chat endpoint (as langchain ChatOllama would)
print("[TEST 2] Chat Endpoint")
print("-" * 70)

# According to Ollama API, chat would be POST /api/chat or similar
chat_url = base_without_api + "/api/chat"
print(f"Testing: {chat_url}")
print()

try:
    response = requests.post(
        chat_url,
        headers={"api-key": OLLAMA_API_KEY},
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": "Hello"}],
            "stream": False,
        },
        timeout=30,
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Chat works!")
        result = response.json()
        print(f"Response: {str(result)[:200]}")
    else:
        print(f"Response: {response.text[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)[:100]}")

print()

# Test 3: Try embeddings endpoint
print("[TEST 3] Embeddings Endpoint")
print("-" * 70)

embeddings_url = base_without_api + "/api/embeddings"
print(f"Testing: {embeddings_url}")
print()

try:
    response = requests.post(
        embeddings_url,
        headers={"api-key": OLLAMA_API_KEY},
        json={
            "model": EMBED_MODEL,
            "prompt": "test embedding",
        },
        timeout=30,
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        print(f"✅ Embeddings work!")
        result = response.json()
        embedding = result.get("embedding", [])
        print(f"Embedding dimension: {len(embedding)}")
        print(f"Sample: {embedding[:3]}")
    else:
        print(f"Response: {response.text[:300]}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)[:100]}")

print()

# Test 4: Check how langchain ChatOllama would call it
print("[TEST 4] LangChain Integration Test")
print("-" * 70)

print(f"Testing if backend modules can connect with configured URL:")
print()

try:
    from backend.core.llm import llm, embeddings, LLM_AVAILABLE, EMBEDDER_AVAILABLE
    
    print(f"✅ LLM module imported")
    print(f"   LLM type: {type(llm).__name__}")
    print(f"   LLM Available: {LLM_AVAILABLE}")
    print(f"   Embeddings type: {type(embeddings).__name__}")
    print(f"   Embedder Available: {EMBEDDER_AVAILABLE}")
    print()
    
    # Try to use LLM
    if LLM_AVAILABLE:
        print("Attempting to use LLM for simple query...")
        try:
            response = llm.invoke("What is 2+2?")
            print(f"✅ LLM invocation successful!")
            print(f"Response: {str(response)[:100]}")
        except Exception as e:
            print(f"❌ LLM invocation failed: {type(e).__name__}")
            print(f"   Error: {str(e)[:200]}")
    
    print()
    
    # Try to use embeddings
    if EMBEDDER_AVAILABLE:
        print("Attempting to use embeddings for test text...")
        try:
            embedding = embeddings.embed_query("test")
            print(f"✅ Embeddings invocation successful!")
            print(f"Embedding dimension: {len(embedding)}")
        except Exception as e:
            print(f"❌ Embeddings invocation failed: {type(e).__name__}")
            print(f"   Error: {str(e)[:200]}")
            
except ImportError as e:
    print(f"❌ Cannot import LLM module: {e}")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print("""
Results show whether Azure Ollama endpoint is accessible with:
  - Correct protocol (http://)
  - Correct URL structure
  - Correct API key
  - Correct endpoint paths

If all tests pass, the backend should be able to:
  - Initialize ChatOllama LLM
  - Initialize OllamaEmbeddings
  - Enable vector search
  - Enable Cypher QA chain (if GraphStore issue resolved)

If tests fail, check:
  - Is the Azure endpoint URL correct?
  - Is the API key valid?
  - Does the endpoint support /api/tags, /api/chat, /api/embeddings?
  - Network connectivity to Azure API Manager
""")
