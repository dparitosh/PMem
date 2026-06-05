#!/usr/bin/env python
"""
Check what models are actually available on Azure Ollama endpoint
"""

import requests
import os
import json

print("=" * 70)
print("CHECKING AVAILABLE MODELS ON AZURE OLLAMA")
print("=" * 70)
print()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://azdtapimanager.azure-api.net/ollama/api/generate")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "56a2f436e96349f0982f4ee477fce451")

base_url = OLLAMA_BASE_URL.rsplit("/api/generate", 1)[0]

print(f"Endpoint base: {base_url}")
print()

# Get list of available models
print("[TEST] List Available Models")
print("-" * 70)

try:
    response = requests.get(
        f"{base_url}/api/tags",
        headers={"api-key": OLLAMA_API_KEY},
        timeout=10,
    )
    
    print(f"Status: {response.status_code}")
    print()
    
    if response.status_code == 200:
        data = response.json()
        models = data.get("models", [])
        
        print(f"✅ Available models: {len(models)}")
        print()
        
        for i, model in enumerate(models, 1):
            name = model.get("name", "unknown")
            size = model.get("size", 0)
            size_gb = size / (1024**3)
            details = model.get("details", {})
            
            print(f"{i}. {name}")
            print(f"   Size: {size_gb:.2f} GB")
            print(f"   Details: {details}")
            print()
            
        # Check specifically for the models in .env
        print("-" * 70)
        print("[CHECKING SPECIFIC MODELS]")
        print()
        
        available_names = [m.get("name") for m in models]
        
        # Check LLM model
        llm_model = os.getenv("LLM_MODEL_NAME", "3.1:8b")
        if llm_model in available_names:
            print(f"✅ LLM model '{llm_model}' is available")
        else:
            print(f"❌ LLM model '{llm_model}' is NOT available")
            print(f"   Possible alternatives:")
            for name in available_names:
                if "3.1" in name.lower() or "llm" in name.lower():
                    print(f"      - {name}")
        
        print()
        
        # Check embeddings model
        embed_model = os.getenv("EMBED_MODEL_NAME", "nomic-embed-text:latest")
        if embed_model in available_names:
            print(f"✅ Embeddings model '{embed_model}' is available")
        else:
            print(f"❌ Embeddings model '{embed_model}' is NOT available")
            print(f"   Possible alternatives:")
            for name in available_names:
                if "embed" in name.lower() or "nomic" in name.lower():
                    print(f"      - {name}")
        
    else:
        print(f"Error: {response.text}")
        
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

print()

# Try with different model names
print("-" * 70)
print("[TRYING DIFFERENT MODEL NAMES]")
print()

test_models = [
    "3.1:8b",
    "3.1:latest",
    "3.1",
    "neural-chat:latest",
    "mistral:latest",
    "llama2:latest",
]

for model in test_models:
    try:
        response = requests.post(
            f"{base_url}/api/chat",
            headers={"api-key": OLLAMA_API_KEY},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "test"}],
                "stream": False,
            },
            timeout=5,
        )
        
        if response.status_code == 200:
            print(f"✅ {model}: WORKS")
        elif response.status_code == 404:
            error = response.json().get("error", "not found")
            if "not found" in error.lower():
                print(f"❌ {model}: Model not found")
            else:
                print(f"❌ {model}: {error}")
        else:
            print(f"⚠️  {model}: Status {response.status_code}")
    except requests.exceptions.Timeout:
        print(f"⏱️  {model}: Request timeout")
    except Exception as e:
        print(f"❌ {model}: {type(e).__name__}")

print()
print("=" * 70)
