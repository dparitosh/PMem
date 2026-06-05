import asyncio
import os
import sys
import json
import logging
from typing import TypedDict, Annotated, Sequence, AsyncGenerator
from typing_extensions import Literal
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from chains.vector import get_data_info, deep_vector_search
from chains.cypher import cypher_qa
from agent.memory import get_memory

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver
from core.llm import llm, LLM_AVAILABLE

logger = logging.getLogger(__name__)


def _normalize_graph_response(result) -> str:
    if result is None:
        return "No graph answer was returned."
    if isinstance(result, dict):
        for key in ("result", "answer", "output", "response"):
            if key in result and result[key] is not None:
                value = result[key]
                if isinstance(value, (dict, list)):
                    return json.dumps(value, indent=2, default=str)
                return str(value)
        return json.dumps(result, indent=2, default=str)
    return str(result)


def _normalize_retrieval_response(result, title: str) -> str:
    if not isinstance(result, dict):
        return str(result)

    answer = result.get("answer") or result.get("result") or "No contextual answer found."
    context = result.get("context") or []
    lines = [f"## {title}", "", str(answer)]

    sources = []
    for doc in context[:5]:
        metadata = getattr(doc, "metadata", {}) or {}
        source_name = (
            metadata.get("filename")
            or metadata.get("node_id")
            or metadata.get("chunkID")
            or metadata.get("source")
        )
        if source_name:
            sources.append(f"- {source_name}")

    if sources:
        lines.extend(["", "### Sources", *sources])

    return "\n".join(lines)

# Define the graph state
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    session_id: str

# Define tools using the @tool decorator
@tool
async def general_chat(query: str) -> str:
    """For general questions not covered by other tools"""
    chat_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a PLM & Graph DataBase expert providing general information related to PLM & Graph Database"),
        ("human", "{input}")
    ])
    chain = chat_prompt | llm
    result = await chain.ainvoke({"input": query})
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
    return _normalize_graph_response(cypher_qa(query))

@tool #(args_schema=VectorSearchInput)
def vector_search(query: str) -> str:
    """Search supporting datasheets and document chunks for factual context and explanations."""
    return _normalize_retrieval_response(get_data_info(query), "Document Context Insights")


@tool
def graph_context_search(query: str) -> str:
    """Use Neo4j GraphRAG context to answer graph-first questions about connected entities, traceability, and engineering context."""
    return _normalize_retrieval_response(deep_vector_search(query), "Graph Context Insights")


@tool
def digital_thread_traceability(query: str) -> str:
    """Trace end-to-end digital thread links across requirements, parts, CAD, process, realization, and change relationships."""
    if cypher_qa is None:
        return "Digital thread traceability is unavailable because the Cypher QA chain is not ready."
    guided_query = (
        f"{query}\n"
        "Focus on digital thread traceability across requirements, functions, logical elements, physical parts, CAD, processes, and change relationships."
    )
    return _normalize_graph_response(cypher_qa(guided_query))


@tool
def cad_structure_analysis(query: str) -> str:
    """Answer CAD-centric questions about assemblies, part structure, where-used, component hierarchy, and CAD relationships."""
    if cypher_qa is None:
        return "CAD structure analysis is unavailable because the Cypher QA chain is not ready."
    try:
        guided_query = (
            f"{query}\n"
            "Focus on CAD assemblies, component hierarchy, part structure, where-used relationships, and associated product structure context."
        )
        result = cypher_qa(guided_query)
        normalized = _normalize_graph_response(result)
        
        # Provide fallback guidance if result is empty
        if not normalized or normalized.strip() == "":
            return f"No CAD structure data found for '{query}'. Try searching for 'Motor Cover Machined' or 'Rotor Shaft' to see available parts."
        return normalized
    except Exception as e:
        logger.error(f"CAD structure analysis failed: {e}", exc_info=True)
        return f"Unable to analyze CAD structure for '{query}'. This could mean the component hasn't been imported yet or the name doesn't match. Try one of the sample queries or verify the exact component name."


@tool
def part_contextual_insights(query: str) -> str:
    """Provide graph-first part insights including connected assemblies, traceability context, associated processes, and related engineering entities."""
    if cypher_qa is None:
        return "Part contextual insights are unavailable because the Cypher QA chain is not ready."
    guided_query = (
        f"{query}\n"
        "Focus on part intelligence: connected assemblies, traceability, associated processes, related requirements, and lifecycle context."
    )
    return _normalize_graph_response(cypher_qa(guided_query))

# ──── Recommendation engine tools ────────────────────────────────────────
from core.graph import graph as _rec_graph
from Services.change_impact_recommender import ChangeImpactRecommender
from Services.similar_parts_recommender import SimilarPartsRecommender
from Services.manufacturing_process_recommender import ManufacturingProcessRecommender

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
        type_m  = "[Y]" if p.get('source_tag_match') else "—"
        rflp_m  = "[Y]" if p.get('rflp_layer_match') else "—"
        asm_m   = "[Y]" if p.get('shared_assembly') else "—"
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
_DIRECT_RESULT_TOOLS: set = set()  # All tools pass through LLM for domain-language reformatting

tools = [
    digital_thread_traceability,
    cad_structure_analysis,
    part_contextual_insights,
    graph_context_search,
    vector_search,
    project_product_info,
    change_impact_analysis,
    find_similar_parts,
    recommend_manufacturing_processes,
    general_chat,
]

# Define the assistant node
async def call_model(state: AgentState):
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

    system_prompt = """You are a senior Digital Engineering expert with deep expertise in Manufacturing Engineering, Systems Engineering (MBSE/SysML), and 3DEXPERIENCE PLM platform. You help Manufacturing Engineers, Operations Managers, and Systems Engineers understand their product and process data.

== KNOWLEDGE GRAPH CONTEXT ==
The graph (Neo4j, database: spdm) contains two domains:

1. Motor Assembly — 3DEXPERIENCE (ds3dx):
   - 5 HP MOTOR ASSEMBLY with 15 parts: ROTOR SHAFT, LAMINATED ROTOR CORE, THREE PHASE WINDINGS, LAMINATED STATOR CORE, SKF_6205-2Z, SKF_6306-2Z, END BELL, MOTOR COVER, FAN, FAN COVER, BEARING_HOLDER, CIRCLIP_1, FLANGE, ROTOR SHAFT KEY, TERMINAL BOX
   - Assembly sequence: #10 (ROTOR SHAFT) → #20 (LAMINATED ROTOR CORE) → ... → #180 (Current Sensor)
   - WorkPlan: SugarPlant assembly Process | HeaderOps: 5 HP Motor Assembly Process A, FDA Unit Process
   - Cross-domain: Requirements (REQ-001 to REQ-008), Design Decisions (DD-001 to DD-004), Change Requests (CR-2024-001 to CR-2024-004)

2. Sugar Plant MBSE — SysML 2018 (sysml):
   - Use Cases: Variable Speed Drive, Energy efficiency for juice purification, Deliver RPM & Power, Maintain Temperature, Monitor Motor Parameters, Start/Stop Motor, etc.
   - Blocks: Variable Speed Drive, Bearing System, Cooling System, Motor Specifications, etc.
   - Packages: Problem Domain, Functional Analysis, Logical Architecture, Bearing Subsystem, etc.
   - Actor: Service Engineer

== RESPONSE STYLE — CRITICAL ==
You are talking to: Manufacturing Engineers, Operations Managers, Systems Engineers, and PLM Analysts.

ALWAYS:
- Answer in plain engineering domain language. Speak like a senior engineer explaining to a colleague.
- Present findings as actionable insights: what it means for the design, process, or decision.
- Use manufacturing terms: assembly sequence, bill of process, loading operation, work plan, header operation, part traceability, change impact, design rationale, requirement allocation.
- Structure answers with short headers, bullet points, and a brief summary conclusion.
- When listing operations, present them as a numbered sequence (Step 1, Step 2...) not raw database names.
- When discussing change requests, frame them as engineering actions with severity and risk context.
- When discussing requirements, explain what they mean in physical/functional terms.

NEVER:
- Show tool names, function calls, or code snippets (e.g. NEVER show `digital_thread_traceability(...)` or `project_product_info(...)`).
- Show raw Cypher queries or graph database syntax to the user.
- Say "I will use the X tool" or "calling the Y function".
- Show JSON, dictionary output, or raw data structures.
- Explain HOW you retrieved the data — only present WHAT the data means.

== PART/ENTITY NAME RULE ==
Pass part names EXACTLY as typed by the user. Do NOT shorten or rephrase.
"ROTOR SHAFT" stays "ROTOR SHAFT". Never "Rotor" or "shaft".

== TOOL SELECTION ==
- digital_thread_traceability → traceability, digital thread, requirements to shop floor
- cad_structure_analysis → assembly structure, BOM, component hierarchy, where-used
- part_contextual_insights → part lifecycle, linked assemblies, process steps
- graph_context_search → contextual engineering insights, connected graph context
- find_similar_parts → alternative parts, comparable components
- change_impact_analysis → change impact, ripple effects, affected parts/requirements
- recommend_manufacturing_processes → manufacturing processes, assembly steps, how a part is made
- project_product_info → graph facts, MBSE elements, ontology lookups, node/relationship queries
- vector_search → datasheet content, document evidence, definitions
- general_chat → greetings ONLY

Graph-first rule: Always call the appropriate tool before answering. Never fabricate graph data.
"""

    # Prepend system message only if not already present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=system_prompt)] + messages

    # Bind tools to the LLM and invoke with retry for transient network failures
    llm_with_tools = llm.bind_tools(tools)
    last_exc = None
    for attempt in range(3):
        try:
            response = await llm_with_tools.ainvoke(messages)
            return {"messages": [response]}
        except Exception as exc:
            exc_str = str(exc)
            if "getaddrinfo" in exc_str or "ConnectError" in exc_str or "Connect" in type(exc).__name__:
                last_exc = exc
                logger.warning(f"LLM connect error (attempt {attempt + 1}/3): {exc}")
                if attempt < 2:
                    await asyncio.sleep(1.5 * (attempt + 1))
            else:
                raise
    raise last_exc

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

async def generate_response(session_id: str, user_input: str) -> str:
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
        
        # Run the graph asynchronously (required when call_model is async)
        result = await chat_agent.ainvoke(initial_state, config)
        
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
        logger.error(f"Chat agent error for session {session_id}: {e}", exc_info=True)
        return "Sorry, I couldn't process your request. Please try again."


# ──── Streaming response ─────────────────────────────────────────────────────
_TOOL_LABELS = {
    "digital_thread_traceability": "[TRACE] Tracing the digital thread…",
    "cad_structure_analysis": "[CAD] Exploring CAD structure…",
    "part_contextual_insights": "[PART] Building part insights…",
    "graph_context_search": "[GRAPH] Gathering graph context…",
    "recommend_manufacturing_processes": "[MFG] Looking up manufacturing processes…",
    "change_impact_analysis": "[IMPACT] Analysing change impact…",
    "find_similar_parts": "[SIMILAR] Finding similar parts…",
    "project_product_info": "[QUERY] Querying the knowledge graph…",
    "vector_search": "[DOC] Searching supporting documents…",
    "general_chat": "[CHAT] Thinking…",
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
        logger.info(f"Starting chat stream for session {session_id}")
        config = {"configurable": {"thread_id": session_id}}
        initial_state = {
            "messages": [HumanMessage(content=user_input)],
            "session_id": session_id,
        }

        logger.info(f"Initial state prepared, about to call chat_agent.astream()")
        final_answer = None

        try:
            stream = chat_agent.astream(initial_state, config)
            logger.info("chat_agent.astream() returned successfully")
        except Exception as stream_init_error:
            logger.error(f"Error initializing astream: {type(stream_init_error).__name__}: {stream_init_error}", exc_info=True)
            raise

        async for state_update in stream:
            # Each update is {"agent": {...}} or {"tools": {...}}
            try:
                if "agent" in state_update:
                    msg = state_update["agent"]["messages"][-1]
                    tool_calls = getattr(msg, "tool_calls", None)
                    if tool_calls:
                        # Intermediate step — LLM is calling a tool
                        tool_name = tool_calls[0].get("name", "") if isinstance(tool_calls[0], dict) else getattr(tool_calls[0], "name", "")
                        label = _TOOL_LABELS.get(tool_name, f"[RUN] Running {tool_name}…")
                        logger.info(f"Yielding status label for tool: {tool_name}")
                        yield f"data: {json.dumps({'status': label})}\n\n"
                    else:
                        # Final response — no tool calls remaining
                        final_answer = msg.content if hasattr(msg, "content") else str(msg)
                        logger.info(f"Got final answer: {final_answer[:100] if final_answer else 'None'}")
            except Exception as loop_error:
                logger.error(f"Error in astream loop iteration: {type(loop_error).__name__}: {loop_error}", exc_info=True)
                raise

        if final_answer:
            # Stream in 6-character chunks so the browser renders progressively
            chunk_size = 6
            for i in range(0, len(final_answer), chunk_size):
                yield f"data: {json.dumps({'token': final_answer[i:i + chunk_size]})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(f"Stream error for session {session_id} ({error_type}): {error_msg}", exc_info=True)
        yield f"data: {json.dumps({'error': f'Unable to process your request ({error_type}). Please try again.'})}\n\n"
        yield f"data: {json.dumps({'done': True})}\n\n"
