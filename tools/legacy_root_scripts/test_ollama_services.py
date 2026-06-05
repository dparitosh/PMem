#!/usr/bin/env python
"""
Test script to verify Ollama API and Vector Search functionality
Tests:
1. Ollama API connectivity
2. Chat completion
3. Embeddings generation
4. Vector chain initialization
5. Cypher QA chain
6. Neo4j connectivity
"""

import sys
import os
import json
import requests
from typing import Dict, Any

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 70)
print("OLLAMA & VECTOR SEARCH SERVICES TEST")
print("=" * 70)
print()

# Test 1: Ollama API Connectivity
print("[TEST 1] Ollama API Connectivity")
print("-" * 70)

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
print(f"Testing Ollama at: {OLLAMA_BASE_URL}")

try:
    # Try to connect to Ollama
    response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
    if response.status_code == 200:
        models = response.json().get("models", [])
        print(f"✅ Ollama API is accessible")
        print(f"   Available models: {len(models)}")
        for model in models[:5]:  # Show first 5
            name = model.get("name", "unknown")
            size = model.get("size", 0) / (1024**3)  # Convert to GB
            print(f"   - {name} ({size:.1f}GB)")
        if len(models) > 5:
            print(f"   ... and {len(models) - 5} more")
    else:
        print(f"❌ Ollama API returned status {response.status_code}")
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to Ollama at {OLLAMA_BASE_URL}")
    print(f"   Make sure Ollama is running: ollama serve")
except Exception as e:
    print(f"❌ Error connecting to Ollama: {type(e).__name__}: {e}")

print()

# Test 2: Chat Completion
print("[TEST 2] Chat Completion (LLM Model)")
print("-" * 70)

LLM_MODEL = os.getenv("LLM_MODEL_NAME", "llama2:latest")
print(f"Testing chat with model: {LLM_MODEL}")

try:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/chat",
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": "What is 2+2? Answer in one word."}],
            "stream": False,
        },
        timeout=30,
    )
    if response.status_code == 200:
        result = response.json()
        answer = result.get("message", {}).get("content", "").strip()
        print(f"✅ Chat completion works")
        print(f"   Model: {LLM_MODEL}")
        print(f"   Response: {answer[:100]}")
    else:
        print(f"❌ Chat API returned status {response.status_code}")
        print(f"   Response: {response.text[:200]}")
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to Ollama for chat")
except requests.exceptions.Timeout:
    print(f"❌ Chat request timed out")
except Exception as e:
    print(f"❌ Chat error: {type(e).__name__}: {e}")

print()

# Test 3: Embeddings Generation
print("[TEST 3] Embeddings Generation")
print("-" * 70)

EMBED_MODEL = os.getenv("EMBED_MODEL_NAME", "nomic-embed-text:latest")
print(f"Testing embeddings with model: {EMBED_MODEL}")

try:
    response = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={
            "model": EMBED_MODEL,
            "prompt": "test embedding",
        },
        timeout=30,
    )
    if response.status_code == 200:
        result = response.json()
        embedding = result.get("embedding", [])
        print(f"✅ Embeddings generation works")
        print(f"   Model: {EMBED_MODEL}")
        print(f"   Embedding dimension: {len(embedding)}")
        print(f"   Sample values: {embedding[:3]}")
    else:
        print(f"❌ Embeddings API returned status {response.status_code}")
        print(f"   Response: {response.text[:200]}")
except requests.exceptions.ConnectionError:
    print(f"❌ Cannot connect to Ollama for embeddings")
except requests.exceptions.Timeout:
    print(f"❌ Embeddings request timed out")
except Exception as e:
    print(f"❌ Embeddings error: {type(e).__name__}: {e}")

print()

# Test 4: Backend LLM Module
print("[TEST 4] Backend LLM Module")
print("-" * 70)

try:
    from backend.core.llm import llm, embeddings, LLM_AVAILABLE, EMBEDDER_AVAILABLE
    
    print(f"✅ LLM module imported")
    print(f"   LLM Available: {LLM_AVAILABLE}")
    print(f"   Embedder Available: {EMBEDDER_AVAILABLE}")
    print(f"   LLM instance: {type(llm).__name__}")
    if embeddings:
        print(f"   Embeddings instance: {type(embeddings).__name__}")
    else:
        print(f"   Embeddings instance: None")
except ImportError as e:
    print(f"❌ Cannot import LLM module: {e}")
except Exception as e:
    print(f"❌ Error loading LLM module: {type(e).__name__}: {e}")

print()

# Test 5: Neo4j Connectivity
print("[TEST 5] Neo4j Database Connectivity")
print("-" * 70)

try:
    from backend.core.db_config import get_driver
    
    driver = get_driver()
    # Test connection
    with driver.session() as session:
        result = session.run("RETURN 1 as test")
        record = result.single()
        if record:
            print(f"✅ Neo4j connection successful")
            print(f"   Driver: {type(driver).__name__}")
            
            # Get database info
            result = session.run("MATCH (n) RETURN count(n) as count")
            count = result.single()["count"]
            print(f"   Total nodes in database: {count}")
        else:
            print(f"❌ Neo4j query returned no results")
except Exception as e:
    print(f"❌ Neo4j connection failed: {type(e).__name__}: {e}")

print()

# Test 6: Vector Chain Initialization
print("[TEST 6] Vector Chain Initialization")
print("-" * 70)

try:
    from backend.chains.vector import (
        general_vector,
        datasheet_vector,
        general_retriever,
        datasheet_retriever,
        general_qa_chain,
        data_qa_chain,
    )
    
    if general_vector and datasheet_vector:
        print(f"✅ Vector chains initialized successfully")
        print(f"   General vector: {type(general_vector).__name__}")
        print(f"   Datasheet vector: {type(datasheet_vector).__name__}")
    else:
        print(f"⚠️  Vector chains not initialized (expected if Ollama unavailable)")
        print(f"   General vector: {general_vector}")
        print(f"   Datasheet vector: {datasheet_vector}")
except ImportError as e:
    print(f"⚠️  Cannot import vector chains: {e}")
except Exception as e:
    print(f"⚠️  Vector chain error: {type(e).__name__}: {e}")

print()

# Test 7: Cypher QA Chain
print("[TEST 7] Cypher QA Chain Initialization")
print("-" * 70)

try:
    from backend.chains.cypher import (
        cypher_qa,
        cypher_qa_available,
        query_cypher,
    )
    
    if cypher_qa_available():
        print(f"✅ Cypher QA chain is available")
        print(f"   Type: {type(cypher_qa).__name__}")
    else:
        print(f"⚠️  Cypher QA chain not available (expected - type validation issue)")
        print(f"   But fallback works - testing direct queries...")
        
        try:
            # Test fallback
            result = query_cypher("MATCH (n) RETURN count(n) as count LIMIT 1")
            print(f"✅ Direct Cypher queries work (fallback)")
            print(f"   Sample query result: {result}")
        except Exception as e:
            print(f"❌ Direct Cypher query failed: {e}")
            
except ImportError as e:
    print(f"❌ Cannot import Cypher chains: {e}")
except Exception as e:
    print(f"❌ Cypher chain error: {type(e).__name__}: {e}")

print()

# Test 8: Vector Search Test (if available)
print("[TEST 8] Vector Search Test")
print("-" * 70)

try:
    from backend.chains.vector import general_retriever
    
    if general_retriever:
        print(f"Testing vector search with query: 'motor specifications'")
        try:
            results = general_retriever.invoke({"input": "motor specifications"})
            if results and results.get("context"):
                docs = results.get("context", [])
                print(f"✅ Vector search works")
                print(f"   Results found: {len(docs)}")
                if docs:
                    print(f"   First result: {docs[0].page_content[:100]}...")
            else:
                print(f"⚠️  Vector search returned no results")
        except Exception as e:
            print(f"❌ Vector search failed: {type(e).__name__}: {e}")
    else:
        print(f"⚠️  Vector retriever not available (Ollama needed)")
except ImportError:
    print(f"⚠️  Cannot test vector search - module import failed")
except Exception as e:
    print(f"⚠️  Vector search test error: {type(e).__name__}: {e}")

print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)

print("""
✅ = Service working
⚠️  = Service unavailable (may be expected)
❌ = Service error

Next steps:
1. If Ollama services show ❌:
   - Install Ollama: https://ollama.com/download
   - Run: ollama serve
   - Pull models: ollama pull llama2:latest
   - Pull embeddings: ollama pull nomic-embed-text:latest

2. For production, use Azure OpenAI or Azure API Manager

3. Vector search and Cypher QA are optional - system works without them
""")
