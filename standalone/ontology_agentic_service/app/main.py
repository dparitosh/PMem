import hmac

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from ontology_agentic.config import settings
from ontology_agentic.models import AgentRunRequest, Owlready2Request, WorkflowRunRequest
from ontology_agentic.runtime.engine import OntologyWorkflowEngine
from ontology_agentic.security import validate_input_path, validate_tool_inputs
from ontology_agentic.tool_catalog import describe_tools, validate_tool_catalog
from ontology_agentic.tools.owlready2_tools import owlready2_analyze


engine = OntologyWorkflowEngine()

app = FastAPI(
    title="Ontology Agentic Service",
    version="0.1.0",
    docs_url="/docs",
    openapi_url="/openapi.json",
    redoc_url=None,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )


@app.middleware("http")
async def optional_api_security(request: Request, call_next):
    """Require a bearer token for API routes only when security is enabled."""
    if settings.api_security_enabled and request.url.path.startswith("/api/"):
        if not settings.api_security_token:
            return JSONResponse(status_code=503, content={"detail": "API security is enabled but ONTOLOGY_API_TOKEN is empty"})
        authorization = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.api_security_token}"
        if not hmac.compare_digest(authorization, expected):
            return JSONResponse(status_code=401, content={"detail": "Missing or invalid bearer token"})
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": "ontology-agentic-service",
        "agents_loaded": engine.registry.names(),
        "data_dir": str(settings.data_dir),
    }


@app.get("/api/v1/agents")
def list_agents() -> dict:
    return {
        "agents": engine.registry.describe_all(),
    }


@app.get("/api/v1/tools")
def list_tools() -> dict:
    """Expose tool-node contracts for an external low-code orchestrator."""
    return {
        "tools": describe_tools(),
        "invalid_exports": validate_tool_catalog(),
    }


@app.post("/api/v1/agents/{agent_name}/run")
def run_agent(agent_name: str, body: AgentRunRequest) -> dict:
    try:
        validate_tool_inputs(body.inputs)
        return engine.run_agent(agent_name, body.inputs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ontology processing failed: {exc}") from exc


@app.post("/api/v1/workflows/run")
def run_workflow(body: WorkflowRunRequest) -> dict:
    try:
        validate_tool_inputs(body.inputs)
        return engine.run_workflow(body.workflow_id, body.inputs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ontology processing failed: {exc}") from exc


@app.post("/api/v1/ontology/owlready2")
def run_owlready2(body: Owlready2Request) -> dict:
    """Execute optional Owlready2 loading/reasoning behind the API boundary."""
    try:
        validate_input_path(body.path)
        return owlready2_analyze(
            path=body.path,
            run_reasoner=body.run_reasoner,
            reasoner=body.reasoner,
            infer_property_values=body.infer_property_values,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Owlready2 processing failed: {exc}") from exc


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
