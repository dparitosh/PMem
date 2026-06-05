#!/usr/bin/env python
"""
Find the correct LLM model name available on Azure Ollama
"""

import requests
import os
import time

print("=" * 70)
print("FINDING CORRECT LLM MODEL ON AZURE OLLAMA")
print("=" * 70)
print()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://azdtapimanager.azure-api.net/ollama/api/generate")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "56a2f436e96349f0982f4ee477fce451")

base_url = OLLAMA_BASE_URL.rsplit("/api/generate", 1)[0]

print(f"Testing: {base_url}")
print()

# List of models to try (in priority order)
models_to_try = [
    # Current configured
    ("3.1:8b", "Currently in .env"),
    
    # Common Ollama models
    ("llama2", "Llama 2 base"),
    ("llama2:latest", "Llama 2 latest"),
    ("mistral", "Mistral base"),
    ("phi", "Phi base"),
    ("phi-3", "Phi 3"),
    ("neural-chat", "Neural chat"),
    ("dolphin-mixtral", "Dolphin Mixtral"),
    ("openchat", "OpenChat"),
    ("solar", "Solar"),
    
    # Azure might have custom names
    ("gpt-3.1:8b", "GPT variant"),
    ("claude", "Claude-like"),
    
    # Vision models that can do text
    ("llava", "Llava"),
    ("bakllava", "Bakllava"),
    
    # Latest tags
    ("llama2:7b", "Llama 2 7B"),
    ("mistral:7b", "Mistral 7B"),
]

successful_models = []

print(f"Testing {len(models_to_try)} model names...")
print()

for model_name, description in models_to_try:
    print(f"Testing: {model_name:30} ({description})", end=" ... ")
    
    try:
        start = time.time()
        response = requests.post(
            f"{base_url}/api/chat",
            headers={"api-key": OLLAMA_API_KEY},
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": "test"}],
                "stream": False,
            },
            timeout=10,  # Short timeout to fail fast
        )
        elapsed = time.time() - start
        
        if response.status_code == 200:
            print(f"✅ SUCCESS ({elapsed:.2f}s)")
            successful_models.append(model_name)
        elif response.status_code == 404:
            error = response.json().get("error", "not found")
            if "not found" in error.lower():
                print(f"❌ Model not found")
            else:
                print(f"⚠️  404: {error[:50]}")
        else:
            print(f"⚠️  Status {response.status_code}")
            
    except requests.exceptions.Timeout:
        print(f"⏱️  Timeout (model might be loading)")
    except requests.exceptions.ConnectionError:
        print(f"❌ Connection error")
    except Exception as e:
        print(f"❌ {type(e).__name__}")

print()
print("=" * 70)
print("RESULTS")
print("=" * 70)

if successful_models:
    print(f"\n✅ FOUND {len(successful_models)} WORKING MODEL(S):\n")
    for model in successful_models:
        print(f"   - {model}")
    
    print(f"\n🔧 UPDATE .env with:")
    print(f"   LLM_MODEL_NAME={successful_models[0]}")
    
    print(f"\nThen restart backend:")
    print(f"   cd Depo_onto")
    print(f"   python main.py")
else:
    print("\n⚠️  NO MODELS FOUND")
    print("\nPossible reasons:")
    print("   1. Models need to be pulled on Azure endpoint")
    print("   2. Model names are different on this endpoint")
    print("   3. Need to contact Azure admin")
    
    print("\nNext steps:")
    print("   1. Ask Azure admin what models are available")
    print("   2. Check: curl -H 'api-key: ...' http://.../ollama/api/tags")
    print("   3. Or pull a model: ollama pull llama2:latest")

print()

# Also test embeddings to confirm endpoint is working
print("=" * 70)
print("VERIFY ENDPOINT IS WORKING (Testing Embeddings)")
print("=" * 70)
print()

try:
    response = requests.post(
        f"{base_url}/api/embeddings",
        headers={"api-key": OLLAMA_API_KEY},
        json={"model": "nomic-embed-text:latest", "prompt": "test"},
        timeout=10,
    )
    
    if response.status_code == 200:
        result = response.json()
        embedding = result.get("embedding", [])
        print(f"✅ Endpoint is working!")
        print(f"   Embeddings model: nomic-embed-text:latest")
        print(f"   Dimension: {len(embedding)}")
        print(f"   Status: READY FOR VECTOR SEARCH")
    else:
        print(f"❌ Embeddings endpoint error: {response.status_code}")
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"❌ Error: {type(e).__name__}: {e}")

print()
print("=" * 70)
