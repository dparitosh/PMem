#!/usr/bin/env python
"""
Test chat with detailed error logging
"""

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

print("=" * 70)
print("DETAILED CHAT TEST")
print("=" * 70)
print()

# Test 1: Check imports
print("[TEST 1] Import Backend Modules")
print("-" * 70)

try:
    from backend.core.llm import llm, LLM_AVAILABLE
    print(f"✅ LLM imported")
    print(f"   Type: {type(llm).__name__}")
    print(f"   Available: {LLM_AVAILABLE}")
except Exception as e:
    print(f"❌ Failed to import LLM: {e}")
    sys.exit(1)

print()

# Test 2: Check agent imports
print("[TEST 2] Import Chat Agent")
print("-" * 70)

try:
    from backend.agent.chat import generate_response_stream, chat_agent
    print(f"✅ Chat agent imported")
    print(f"   Agent type: {type(chat_agent).__name__}")
except Exception as e:
    print(f"❌ Failed to import chat agent: {e}")
    sys.exit(1)

print()

# Test 3: Try to use LLM directly
print("[TEST 3] Direct LLM Test")
print("-" * 70)

if LLM_AVAILABLE:
    try:
        print("Invoking LLM directly with message...")
        response = llm.invoke("Hello")
        print(f"✅ LLM direct invocation works")
        print(f"   Response: {str(response)[:100]}")
    except Exception as e:
        print(f"❌ LLM invocation failed: {type(e).__name__}")
        print(f"   Error: {str(e)[:200]}")
else:
    print("⚠️  LLM not available")

print()

# Test 4: Try to bind tools
print("[TEST 4] LLM Bind Tools Test")
print("-" * 70)

try:
    from langchain_core.tools import tool
    from langchain_core.messages import SystemMessage, HumanMessage
    
    # Create a simple test tool
    @tool
    def test_tool(query: str) -> str:
        """A test tool"""
        return f"Test result for: {query}"
    
    tools = [test_tool]
    
    print("Binding tools to LLM...")
    llm_with_tools = llm.bind_tools(tools)
    print(f"✅ Tools bound successfully")
    print(f"   LLM with tools type: {type(llm_with_tools).__name__}")
    
    # Try to invoke with tools
    print("\nInvoking LLM with bound tools...")
    messages = [
        SystemMessage(content="You are a helpful assistant"),
        HumanMessage(content="Hello")
    ]
    response = llm_with_tools.invoke(messages)
    print(f"✅ LLM with tools invocation works")
    print(f"   Response type: {type(response).__name__}")
    print(f"   Tool calls: {getattr(response, 'tool_calls', 'none')}")
    
except Exception as e:
    print(f"❌ Tool binding/invocation failed: {type(e).__name__}")
    print(f"   Error: {str(e)}")
    import traceback
    traceback.print_exc()

print()

# Test 5: Try to run chat agent
print("[TEST 5] Chat Agent Execution")
print("-" * 70)

try:
    from langchain_core.messages import HumanMessage
    
    print("Creating initial state...")
    initial_state = {
        "messages": [HumanMessage(content="What is Neo4j?")],
        "session_id": "test-session",
    }
    
    config = {"configurable": {"thread_id": "test-session"}}
    
    print("Running chat agent...")
    print("(This might take a moment...)")
    print()
    
    step_count = 0
    for state_update in chat_agent.stream(initial_state, config):
        step_count += 1
        print(f"   Step {step_count}: {list(state_update.keys())}")
        if "agent" in state_update:
            msg = state_update["agent"]["messages"][-1]
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                print(f"      Tool calls: {[tc.get('name', 'unknown') if isinstance(tc, dict) else getattr(tc, 'name', 'unknown') for tc in tool_calls]}")
            else:
                content = getattr(msg, "content", str(msg))
                if isinstance(content, str) and content:
                    print(f"      Response: {content[:100]}")
    
    print()
    print(f"✅ Chat agent executed ({step_count} steps)")
    
except Exception as e:
    print(f"❌ Chat agent execution failed: {type(e).__name__}")
    print(f"   Error: {str(e)}")
    import traceback
    traceback.print_exc()

print()
print("=" * 70)
