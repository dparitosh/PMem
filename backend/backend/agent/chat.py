import os
import json
import logging
from typing import TypedDict, Annotated, Sequence, AsyncGenerator
from typing_extensions import Literal
from ..chains.vector import get_node_info, get_data_info
from ..chains.cypher import cypher_qa
from .memory import get_memory

from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from ..core.llm import llm, LLM_AVAILABLE

logger = logging.getLogger(__name__)

# Define the graph state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    session_id: str

# Define tools using the @tool decorator
@tool
def general_chat(query: str) -> str:
    """For general questions not covered by other tools"""
    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a PLM & Graph DataBase expert providing general information related to PLM & Graph Database"),
        ("human", "{input}")
    ])
    chain = chat_prompt | llm
    result = chain.invoke({"input": query})
    return result.content

from pydantic import BaseModel, Field
 
# Define strict input schemas
class ProjectProductInfoInput(BaseModel):
    """Input schema for project_product_info tool"""
    query: str = Field(description="The query about project/product information")
 
class VectorSearchInput(BaseModel):
    """Input schema for vector_search tool"""
    query: str = Field(description="The search query for datasheet facts, definitions & explanations")
 
# Make tools strict by adding args_schema
@tool#(args_schema=ProjectProductInfoInput, return_direct=True)
def project_product_info(query: str) -> str:
    """Answer graph and nodes questions using Cypher"""
    if cypher_qa is None:
        return "Cypher QA chain is not available (LLM not configured or unreachable)."
    return cypher_qa(query)

@tool #(args_schema=VectorSearchInput)
def vector_search(query: str) -> str:
    """Overall vector search for datasheet facts, definitions & explanations"""
    return get_data_info(query)

# ──── Recommendation engine tools ────────────────────────────────────────
from ..core.graph import graph as _rec_graph
from ..services.change_impact_recommender import ChangeImpactRecommender
from ..services.similar_parts_recommender import SimilarPartsRecommender
from ..services.manufacturing_process_recommender import ManufacturingProcessRecommender

_ci = ChangeImpactRecommender(_rec_graph)
_sp = SimilarPartsRecommender(_rec_graph)
_mp = ManufacturingProcessRecommender(_rec_graph)

@tool
def change_impact_analysis(query: str) -> str:
    """Analyse the ripple effects of a change request or part across assemblies, requirements, and processes. Use when user asks about change impact, affected parts, or ripple effects."""
    result = _ci.analyse(change_name=query, part_name=query)
    ce = result.get("change_entity") or {}
    parts = result.get("impacted_parts", [])
    asm = result.get("assembly_impact", [])
    reqs = result.get("impacted_requirements", [])
    procs = result.get("process_impacts", [])
    chain = result.get("realization_chain", [])
    score = result.get("impact_score", 0)
    if not ce:
        return f"No change entity found for '{query}'. Please verify the name exists in the graph."

    # Score label
    if score <= 40:
        score_label = "Low"
    elif score <= 70:
        score_label = "Medium"
    else:
        score_label = "High"

    lines = [
        f"## Change Impact Analysis — {ce.get('name')}",
        f"**Entity type:** {ce.get('source_tag', 'Unknown')}  |  "
        f"**Impact score:** {score}/100 ({score_label})",
        "",
    ]

    # Impacted parts
    lines.append(f"### Directly Impacted Parts ({len(parts)})")  
    if parts:
        for p in parts:
            rel = f" via {p['relation_type']}" if p.get('relation_type') and p['relation_type'] != 'self' else ""
            lines.append(f"- **{p['name']}** ({p.get('source_tag', '—')}){rel}")
    else:
        lines.append("- None identified via GeneralRelation")

    # Assembly impact
    lines.append(f"\n### Assembly Impact ({len(asm)} assemblies)")
    if asm:
        shown = asm[:10]
        for a in shown:
            lines.append(f"- {a['assembly_name']} (depth {a.get('depth', '?')})")
        if len(asm) > 10:
            lines.append(f"- … and {len(asm) - 10} more")
    else:
        lines.append("- No assembly impact found")

    # Requirements
    lines.append(f"\n### Impacted Requirements ({len(reqs)})")
    if reqs:
        for r in reqs[:8]:
            lines.append(f"- **{r['name']}**" + (f" (linked to {r['linked_part']})" if r.get('linked_part') else ""))
        if len(reqs) > 8:
            lines.append(f"- … and {len(reqs) - 8} more")
    else:
        lines.append("- No requirements impacted")

    # Processes
    lines.append(f"\n### Process Impact ({len(procs)} processes)")
    if procs:
        for p in procs[:8]:
            lines.append(f"- {p['name']} ({p.get('source_tag', '—')})")
        if len(procs) > 8:
            lines.append(f"- … and {len(procs) - 8} more")
    else:
        lines.append("- No processes impacted")

    # Realization chain
    lines.append(f"\n### Realization Chain ({len(chain)} entities)")
    if chain:
        for c in chain[:8]:
            link = f" [{c.get('link_type', '?')}]" if c.get('link_type') else ""
            lines.append(f"- **{c['name']}** ({c.get('source_tag', '—')}){link}")
        if len(chain) > 8:
            lines.append(f"- … and {len(chain) - 8} more")
    else:
        lines.append("- No realization chain found")

    return "\n".join(lines)

@tool
def find_similar_parts(query: str) -> str:
    """Find parts similar to a given part using structural and semantic scoring. Use when user asks 'what is similar to X', 'parts like X', or 'find similar parts'."""
    result = _sp.recommend(query, top_n=10)
    sp = result.get("source_part")
    if not sp:
        return f"Part '{query}' not found in the graph."
    parts = result.get("similar_parts", [])
    lines = [
        f"## Similar Parts — {sp.get('name')}",
        f"**Type:** {sp.get('source_tag', '—')}  |  **RFLP layer:** {sp.get('rflp_layer') or '—'}  |  **{len(parts)} results found**",
        "",
    ]
    if not parts:
        lines.append("No similar parts found based on current scoring criteria.")
        return "\n".join(lines)
    lines.append("| # | Part Name | Score | Type Match | RFLP Match | Assembly | Traceability |")
    lines.append("|---|-----------|-------|------------|------------|----------|-------------|")
    for i, p in enumerate(parts, 1):
        type_m  = "✅" if p.get('source_tag_match') else "—"
        rflp_m  = "✅" if p.get('rflp_layer_match') else "—"
        asm_m   = "✅" if p.get('shared_assembly') else "—"
        trace   = p.get('traceability_link') or "—"
        lines.append(f"| {i} | **{p['name']}** | {p['similarity_score']}/100 | {type_m} | {rflp_m} | {asm_m} | {trace} |")
    return "\n".join(lines)

@tool
def recommend_manufacturing_processes(query: str) -> str:
    """Recommend manufacturing processes for a given part. Use when user asks about processes, manufacturing steps, or how a part is made. Pass the part name EXACTLY as stated by the user — do NOT remove words, abbreviate, or modify the name in any way."""
    result = _mp.recommend(query)
    pt = result.get("part")
    if not pt:
        return f"Part '{query}' not found in the graph."
    direct   = result.get("direct_processes", [])
    instances = result.get("process_instances", [])
    related  = result.get("related_part_processes", [])
    summary  = result.get("process_summary") or {}

    lines = [
        f"## Manufacturing Processes — {pt.get('name')}",
        f"**Type:** {pt.get('source_tag', '—')}  |  "
        f"**Direct:** {summary.get('total_direct', len(direct))}  |  "
        f"**Instances:** {summary.get('total_instances', len(instances))}  |  "
        f"**Related:** {summary.get('total_related', len(related))}",
        "",
    ]

    # Direct processes
    lines.append(f"### Direct Processes ({len(direct)})")
    if direct:
        for p in direct[:10]:
            ptype = f" [{p.get('process_type')}]" if p.get('process_type') else ""
            lines.append(f"- **{p['process_name']}**{ptype}")
        if len(direct) > 10:
            lines.append(f"- … and {len(direct) - 10} more")
    else:
        lines.append("- No direct processes found")

    # Process instances
    lines.append(f"\n### Process Instances ({len(instances)})")
    if instances:
        for p in instances[:10]:
            lines.append(f"- **{p['name']}** ({p.get('source_tag', '—')})")
        if len(instances) > 10:
            lines.append(f"- … and {len(instances) - 10} more")
    else:
        lines.append("- No process instances found")

    # Related part processes
    lines.append(f"\n### Related Part Processes ({len(related)})")
    if related:
        # Group by process name for clarity
        seen_r = set()
        shown = 0
        for p in related:
            pname = p.get('process_name') or p.get('name', '—')
            if pname not in seen_r:
                seen_r.add(pname)
                part_ref = f" (via {p['part_name']})" if p.get('part_name') else ""
                lines.append(f"- {pname}{part_ref}")
                shown += 1
            if shown >= 12:
                remaining = len(related) - shown
                if remaining > 0:
                    lines.append(f"- … and {remaining} more")
                break
    else:
        lines.append("- No related-part processes found")

    return "\n".join(lines)
# ──────────────────────────────────────────────────────────────────────────

# @tool
# def project_product_info(query: str) -> str:
#     """Answer structured graph questions using Cypher"""
#     return cypher_qa(query)

# # Uncomment if needed
# @tool
# def vector_search(query: str) -> str:
#     """Overall vector search for datasheet facts, definitions & explanations"""
#     return get_data_info(query)

# Recommendation tools whose output should be returned verbatim — no LLM reformatting
_DIRECT_RESULT_TOOLS = {"change_impact_analysis", "find_similar_parts", "recommend_manufacturing_processes"}

tools = [general_chat, project_product_info, vector_search,
         change_impact_analysis, find_similar_parts, recommend_manufacturing_processes]

# Define the assistant node
def call_model(state: AgentState):
    messages = list(state["messages"])

    # ── Short-circuit: if the last message is a ToolMessage from one of our
    # recommendation tools, return its content directly as the final answer
    # without feeding it back through the LLM (which tends to add meta-commentary).
    from langchain_core.messages import ToolMessage
    if messages and isinstance(messages[-1], ToolMessage):
        tool_msg = messages[-1]
        # Find the AIMessage that triggered this tool call
        for m in reversed(messages[:-1]):
            if hasattr(m, "tool_calls") and m.tool_calls:
                for tc in m.tool_calls:
                    tc_name = tc.get("name", "") if isinstance(tc, dict) else getattr(tc, "name", "")
                    tc_id   = tc.get("id", "")   if isinstance(tc, dict) else getattr(tc, "id", "")
                    if tc_id == tool_msg.tool_call_id and tc_name in _DIRECT_RESULT_TOOLS:
                        return {"messages": [AIMessage(content=tool_msg.content)]}
                break  # only check the most recent AIMessage with tool_calls

    system_prompt = """You are a PLM knowledge graph assistant. Call the right tool and present its output directly.

CRITICAL — Part/Entity name rule:
Pass the part or entity name EXACTLY as the user typed it. Do NOT shorten, correct, or rephrase names.
Example: "Motor Cover Machined" must be passed as "Motor Cover Machined", never as "Motor Cover".

Tool selection rules:
- "find_similar_parts": Similar parts, alternatives, comparable components.
- "change_impact_analysis": Change impact, affected parts, ripple effects.
- "recommend_manufacturing_processes": Manufacturing processes, how a part is made.
- "project_product_info": Graph queries about nodes/relationships/product structure.
- "vector_search": Datasheet facts, definitions, explanations.
- "general_chat": ONLY for greetings or questions that match none of the above.

Never answer a tool-eligible question without calling the tool first.
"""

    # Prepend system message only if not already present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages

    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(tools)
    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}

def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """Determine whether to continue or end the conversation"""
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the LLM makes a tool call, then we route to the "tools" node
    if last_message.tool_calls:
        return "tools"
    # Otherwise, we stop (reply to the user)
    return "end"

# Create the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("agent", call_model)
workflow.add_node("tools", ToolNode(tools))

# Set the entrypoint
workflow.set_entry_point("agent")

# Add conditional edges
workflow.add_conditional_edges(
    "agent",
    should_continue,
    {"tools": "tools", "end": END}
)

# Add edge from tools back to agent
workflow.add_edge("tools", "agent")

# Initialize memory
memory = MemorySaver()

# Compile the graph
chat_agent = workflow.compile(checkpointer=memory)

def generate_response(session_id: str, user_input: str) -> str:
    """Generate response using LangGraph agent"""
    if not LLM_AVAILABLE:
        return "LLM is not available. Please check your LLM configuration and ensure the service is running."
    try:
        # Create the thread configuration
        config = {"configurable": {"thread_id": session_id}}
        
        # Create initial state with user message
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id
        }
        
        # Run the graph
        result = chat_agent.invoke(initial_state, config)
        
        # Get the last AI message
        last_message = result["messages"][-1]
        
        # Store in memory (if using custom memory system)
        try:
            memory = get_memory(session_id)
            memory.add_user_message(user_input)
            memory.add_ai_message(last_message.content)
        except:
            pass  # Memory handling is optional with LangGraph's built-in memory
        
        logger.info(f"Agent response: {last_message.content}")
        return last_message.content
        
    except Exception as e:
        return f"Sorry, I couldn't process your request: {str(e)}"


# ──── Streaming response ─────────────────────────────────────────────────────
_TOOL_LABELS = {
    "recommend_manufacturing_processes": "🏭 Looking up manufacturing processes…",
    "change_impact_analysis": "⚡ Analysing change impact…",
    "find_similar_parts": "🔍 Finding similar parts…",
    "project_product_info": "🔗 Querying the knowledge graph…",
    "vector_search": "📖 Searching datasheets…",
    "general_chat": "💬 Thinking…",
}

async def generate_response_stream(session_id: str, user_input: str) -> AsyncGenerator[str, None]:
    """Yield Server-Sent Events (SSE).

    Uses chat_agent.astream() (same execution path as generate_response/invoke)
    so the final answer is IDENTICAL to the /chat endpoint.
    Tool-call status labels are extracted from AIMessage.tool_calls — no raw
    LLM text is captured during tool-selection steps.
    The final answer is then streamed in small character chunks.
    """
    if not LLM_AVAILABLE:
        yield f"data: {json.dumps({'token': 'LLM is not available. Please check your configuration.'})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
        return

    try:
        config = {"configurable": {"thread_id": session_id}}
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id,
        }

        final_answer = None

        async for state_update in chat_agent.astream(initial_state, config):
            # Each update is {"agent": {...}} or {"tools": {...}}
            if "agent" in state_update:
                msg = state_update["agent"]["messages"][-1]
                tool_calls = getattr(msg, "tool_calls", None)
                if tool_calls:
                    # Intermediate step — LLM is calling a tool
                    tool_name = tool_calls[0].get("name", "") if isinstance(tool_calls[0], dict) else getattr(tool_calls[0], "name", "")
                    label = _TOOL_LABELS.get(tool_name, f"⚙️ Running {tool_name}…")
                    yield f"data: {json.dumps({'status': label})}\n\n"
                else:
                    # Final response — no tool calls remaining
                    final_answer = msg.content if hasattr(msg, "content") else str(msg)

        if final_answer:
            # Stream in 6-character chunks so the browser renders progressively
            chunk_size = 6
            for i in range(0, len(final_answer), chunk_size):
                yield f"data: {json.dumps({'token': final_answer[i:i + chunk_size]})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"

