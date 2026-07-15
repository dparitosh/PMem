"""Configuration for the minimal standalone ontology API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _csv(variable: str, defaults: list[str]) -> list[str]:
    configured = os.getenv(variable)
    return [value.strip() for value in configured.split(",") if value.strip()] if configured else defaults


def _path_roots(variable: str, defaults: list[Path]) -> list[Path]:
    configured = os.getenv(variable)
    values = configured.split(os.pathsep) if configured else [str(path) for path in defaults]
    return [Path(value.strip()).expanduser().resolve() for value in values if value.strip()]


@dataclass(slots=True)
class Settings:
    host: str
    port: int
    reload: bool
    data_dir: Path
    output_dir: Path
    agent_specs_dir: Path
    cors_origins: list[str]
    api_security_enabled: bool
    api_security_token: str
    allowed_input_roots: list[Path]
    allowed_output_roots: list[Path]


def load_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]
    _load_env_file(root / ".env")
    data_dir = Path(os.getenv("ONTOLOGY_AGENTIC_DATA_DIR", str(root / "data"))).resolve()
    output_dir = Path(os.getenv("ONTOLOGY_AGENTIC_OUTPUT_DIR", str(root / "output"))).resolve()
    result = Settings(
        host=os.getenv("ONTOLOGY_AGENTIC_HOST", "127.0.0.1"),
        port=int(os.getenv("ONTOLOGY_AGENTIC_PORT", "8012")),
        reload=_as_bool(os.getenv("ONTOLOGY_AGENTIC_RELOAD")),
        data_dir=data_dir,
        output_dir=output_dir,
        agent_specs_dir=Path(
            os.getenv(
                "ONTOLOGY_AGENTIC_AGENT_SPECS_DIR",
                str(root / "iif_bundle" / "AgentsRegistry" / "Agents"),
            )
        ).resolve(),
        cors_origins=_csv(
            "ONTOLOGY_AGENTIC_CORS_ORIGINS",
            ["http://localhost:3000", "http://127.0.0.1:3000"],
        ),
        api_security_enabled=_as_bool(os.getenv("ONTOLOGY_API_SECURITY_ENABLED")),
        api_security_token=os.getenv("ONTOLOGY_API_TOKEN", "").strip(),
        allowed_input_roots=_path_roots("ONTOLOGY_API_ALLOWED_INPUT_ROOTS", [data_dir]),
        allowed_output_roots=_path_roots("ONTOLOGY_API_ALLOWED_OUTPUT_ROOTS", [output_dir]),
    )
    result.data_dir.mkdir(parents=True, exist_ok=True)
    result.output_dir.mkdir(parents=True, exist_ok=True)
    return result


settings = load_settings()
