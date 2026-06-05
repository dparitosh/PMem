#!/usr/bin/env python
"""
Test chat agent stream to find exact failure point
"""

import sys
import os
import asyncio
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 70)
print("CHAT STREAM ASYNC TEST")
print("=" * 70)
print()

# Import everything needed
from backend.agent.chat import generate_response_stream
from langchain_core.messages import HumanMessage

async def test_stream():
    print("[TEST] Running generate_response_stream")
    print("-" * 70)
    
    try:
        session_id = "test-session-001"
        user_input = "What is Neo4j?"
        
        print(f"Session: {session_id}")
        print(f"Input: {user_input}")
        print()
        print("Stream output:")
        print("-" * 70)
        
        step = 0
        async for event in generate_response_stream(session_id, user_input):
            step += 1
            print(f"[Event {step}] {event[:100]}")
        
        print()
        print(f"✅ Stream completed with {step} events")
        
    except Exception as e:
        print(f"❌ Stream error: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        import traceback
        traceback.print_exc()

# Run the async test
asyncio.run(test_stream())

print()
print("=" * 70)
