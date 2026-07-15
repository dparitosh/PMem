"""Optional API authentication and filesystem-boundary enforcement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ontology_agentic.config import settings


def _contained(path_value: str | Path, roots: list[Path]) -> bool:
    candidate = Path(path_value).expanduser().resolve()
    return any(candidate == root or candidate.is_relative_to(root) for root in roots)


def validate_input_path(path_value: str | Path) -> None:
    if settings.api_security_enabled and not _contained(path_value, settings.allowed_input_roots):
        raise ValueError("Input path is outside ONTOLOGY_API_ALLOWED_INPUT_ROOTS")


def validate_output_path(path_value: str | Path, *, directory: bool = False) -> None:
    if not settings.api_security_enabled:
        return
    candidate = Path(path_value).expanduser().resolve()
    target = candidate if directory else candidate.parent
    if not _contained(target, settings.allowed_output_roots):
        raise ValueError("Output path is outside ONTOLOGY_API_ALLOWED_OUTPUT_ROOTS")


def validate_tool_inputs(inputs: dict[str, Any]) -> None:
    """Validate known filesystem fields while leaving non-file inputs unchanged."""
    if not settings.api_security_enabled:
        return
    for key in ("ontology_path", "file_path"):
        value = inputs.get(key)
        if value:
            validate_input_path(value)
    if inputs.get("output_dir"):
        validate_output_path(inputs["output_dir"], directory=True)
    if inputs.get("output_path"):
        validate_output_path(inputs["output_path"])


__all__ = ["validate_input_path", "validate_output_path", "validate_tool_inputs"]
