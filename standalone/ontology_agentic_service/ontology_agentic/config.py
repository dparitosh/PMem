from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    reload: bool
    data_dir: Path
    output_dir: Path
    agent_specs_dir: Path
    depo_api_base_url: str
    depo_api_timeout_seconds: float
    depo_api_token: str


def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parents[1]
    _load_env_file(base_dir / ".env")
    data_dir = Path(os.getenv("ONTOLOGY_AGENTIC_DATA_DIR", str(base_dir / "data"))).resolve()
    output_dir = Path(os.getenv("ONTOLOGY_AGENTIC_OUTPUT_DIR", str(base_dir / "output"))).resolve()
    agent_specs_dir = Path(os.getenv("ONTOLOGY_AGENTIC_AGENT_SPECS_DIR", str(base_dir / "ontology_agentic" / "agents" / "specs"))).resolve()

    settings = Settings(
        host=os.getenv("ONTOLOGY_AGENTIC_HOST", "0.0.0.0"),
        port=int(os.getenv("ONTOLOGY_AGENTIC_PORT", "8012")),
        reload=_as_bool(os.getenv("ONTOLOGY_AGENTIC_RELOAD"), default=False),
        data_dir=data_dir,
        output_dir=output_dir,
        agent_specs_dir=agent_specs_dir,
        depo_api_base_url=os.getenv("ONTOLOGY_AGENTIC_DEPO_API_BASE_URL", "http://localhost:8000").rstrip("/"),
        depo_api_timeout_seconds=float(os.getenv("ONTOLOGY_AGENTIC_DEPO_API_TIMEOUT_SECONDS", "120")),
        depo_api_token=os.getenv("ONTOLOGY_AGENTIC_DEPO_API_TOKEN", "").strip(),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    return settings


settings = load_settings()
