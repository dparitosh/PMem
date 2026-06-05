from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from agent.chat import generate_response #generate_response_with_cypher
from core.graph import graph
# from models.schema import ChatRequest, ChatResponse, ChatWithCypherResponse, ResetRequest
# from agent.memory import reset_memory
from models.schema import ChatRequest, ChatResponse, ResetRequest, TextSearchRequest, ChatWithCypherResponse

app = FastAPI()

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        result = generate_response(request.session_id, request.message)
        return ChatResponse(session_id=request.session_id, response=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @app.post("/reset")
# def reset(request: ResetRequest):
#     reset_memory(request.session_id)
#     return {"status": "ok"}

# @app.post("/chat-with-cypher", response_model=ChatWithCypherResponse)
# def chat_with_cypher(request: ChatRequest):
#     """Enhanced chat endpoint that returns both response and raw Cypher results"""
#     try:
#         result = generate_response_with_cypher(request.session_id, request.message)
#         return ChatWithCypherResponse(
#             session_id=result["session_id"],
#             response=result["response"],
#             raw_results=result["raw_results"]
#         )
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

@app.get("/graphvis")
def get_entire_graph():
    try:
        results = graph.query(
            """
        <GIVE YOUR QUERY HERE>"""
        )
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/graphfilter")
def filter_graph_nodes(request: TextSearchRequest):
    try:
        input_val = request.search.strip()

        query = """
        <GIVE YOUR QUERY HERE>"""

        results = graph.query(query, params={"input": input_val})
        return {"results": results}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graphtraverse/{node_id}")
def traverse_node(node_id: str = Path(..., description="Neo4j internal node ID")):
    try:
        query = """<GIVE YOUR QUERY HERE>
"""
        results = graph.query(query, params={"node_id": node_id})
        return {"results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
