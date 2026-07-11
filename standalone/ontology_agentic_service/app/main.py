from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from ontology_agentic.config import settings
from ontology_agentic.models import AgentRunRequest, WorkflowRunRequest
from ontology_agentic.runtime.engine import OntologyWorkflowEngine


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


@app.post("/api/v1/agents/{agent_name}/run")
def run_agent(agent_name: str, body: AgentRunRequest) -> dict:
    try:
        return engine.run_agent(agent_name, body.inputs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/v1/workflows/run")
def run_workflow(body: WorkflowRunRequest) -> dict:
    try:
        return engine.run_workflow(body.workflow_id, body.inputs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )
