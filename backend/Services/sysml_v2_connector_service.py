"""
Optional SysML v2 API connector readiness service.

This module does not import a generated SysML v2 client. It provides a small,
release-safe boundary for configuration, readiness, and future connector work.
Actual repository synchronization should only be enabled after a customer SysML
v2 API server, authentication model, and OpenAPI compatibility are confirmed.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from typing import Any, Dict, Optional
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_TRUE_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SysMLV2ConnectorConfig:
    enabled: bool
    base_url: str
    token: str
    project_id: str
    branch_id: str
    commit_id: str
    page_size: int
    request_timeout_seconds: int

    @classmethod
    def from_env(cls) -> "SysMLV2ConnectorConfig":
        return cls(
            enabled=str(os.getenv("SYSML_V2_API_ENABLED", "false")).strip().lower() in _TRUE_VALUES,
            base_url=str(os.getenv("SYSML_V2_API_BASE_URL", "")).strip().rstrip("/"),
            token=str(os.getenv("SYSML_V2_API_TOKEN", "")).strip(),
            project_id=str(os.getenv("SYSML_V2_PROJECT_ID", "")).strip(),
            branch_id=str(os.getenv("SYSML_V2_BRANCH_ID", "")).strip(),
            commit_id=str(os.getenv("SYSML_V2_COMMIT_ID", "")).strip(),
            page_size=_safe_int(os.getenv("SYSML_V2_PAGE_SIZE"), 500),
            request_timeout_seconds=_safe_int(os.getenv("SYSML_V2_REQUEST_TIMEOUT_SECONDS"), 120),
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url)

    @property
    def masked_base_url(self) -> str:
        if not self.base_url:
            return ""
        parsed = urlparse(self.base_url)
        if not parsed.scheme or not parsed.netloc:
            return self.base_url
        return f"{parsed.scheme}://{parsed.netloc}"


def _safe_int(value: Optional[str], default: int) -> int:
    try:
        return int(str(value).strip()) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


class SysMLV2ConnectorService:
    """Readiness boundary for a future SysML v2 API repository connector."""

    def __init__(self, config: Optional[SysMLV2ConnectorConfig] = None):
        self.config = config or SysMLV2ConnectorConfig.from_env()

    def status(self) -> Dict[str, Any]:
        cfg = self.config
        return {
            "status": "disabled" if not cfg.enabled else ("configured" if cfg.configured else "not_configured"),
            "enabled": cfg.enabled,
            "configured": cfg.configured,
            "base_url": cfg.masked_base_url,
            "project_configured": bool(cfg.project_id),
            "branch_configured": bool(cfg.branch_id),
            "commit_configured": bool(cfg.commit_id),
            "page_size": cfg.page_size,
            "request_timeout_seconds": cfg.request_timeout_seconds,
            "current_capability": "readiness_only",
            "release_position": "planned_optional_connector",
            "message": (
                "SysML v2 API sync is disabled. Current supported SysML-style ingestion remains file/XMI based."
                if not cfg.enabled
                else "SysML v2 API connector is configured for readiness checks only; repository sync is not implemented yet."
            ),
        }

    def integration_plan(self) -> Dict[str, Any]:
        return {
            "connector": "SysMLV2ConnectorService",
            "supported_when": [
                "Customer provides a live SysML v2 API server",
                "Authentication and OpenAPI compatibility are verified",
                "License posture for any generated client is approved",
            ],
            "not_a_replacement_for": ["XMI parser", "MDXML parser", "Owlready2", "RDFLib", "SHACL", "Neo4j"],
            "recommended_flow": [
                "projects / branches / commits",
                "roots / elements / relationships / query-results",
                "normalized DEPO import model",
                "Semantic Bridge mapping",
                "Neo4j instance graph",
                "OSLC / GraphRAG / visualization / reports",
            ],
            "kerml_position": {
                "status": "planned_not_implemented",
                "role": "KerML is the semantic kernel foundation for SysML v2; current DEPO runtime does not parse .kerml files yet.",
                "release_guidance": "Use XMI/MDXML for current MBSE file import. Use SysML v2 endpoints for readiness only until a real API server or KerML parser is validated.",
            },
            "normalization_contract": {
                "source_format": "sysmlv2",
                "source_system": "sysml-v2-api",
                "external_id": "element id from repository",
                "name": "human-readable element name",
                "element_type": "Requirement | PartDefinition | ActionUsage | ...",
                "owner_id": "owning element id when present",
                "documentation": "description/documentation when present",
                "properties": "raw and normalized element properties",
                "relationships": "semantic relationships to other model elements",
            },
        }

    def probe_projects(self) -> Dict[str, Any]:
        """Best-effort GET /projects probe for a configured SysML v2 API server."""
        cfg = self.config
        if not cfg.enabled:
            return {**self.status(), "probe_status": "skipped", "probe_message": "Connector is disabled."}
        if not cfg.configured:
            return {**self.status(), "probe_status": "skipped", "probe_message": "SYSML_V2_API_BASE_URL is not configured."}

        url = f"{cfg.base_url}/projects"
        headers = {"Accept": "application/json"}
        if cfg.token:
            headers["Authorization"] = f"Bearer {cfg.token}"

        req = urllib_request.Request(url, headers=headers, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=cfg.request_timeout_seconds) as resp:
                body = resp.read(1024 * 1024).decode("utf-8", errors="replace")
                try:
                    payload: Any = json.loads(body) if body else None
                except json.JSONDecodeError:
                    payload = {"raw_preview": body[:1000]}
                count = len(payload) if isinstance(payload, list) else None
                return {
                    **self.status(),
                    "probe_status": "ok",
                    "http_status": getattr(resp, "status", 200),
                    "projects_count": count,
                    "payload_preview": payload if count is not None and count <= 5 else None,
                }
        except HTTPError as exc:
            logger.warning("SysML v2 /projects probe failed with HTTP %s", exc.code)
            return {**self.status(), "probe_status": "failed", "http_status": exc.code, "probe_message": str(exc)}
        except (URLError, TimeoutError, OSError) as exc:
            logger.warning("SysML v2 /projects probe failed: %s", exc)
            return {**self.status(), "probe_status": "failed", "probe_message": str(exc)}


def get_sysml_v2_connector_service() -> SysMLV2ConnectorService:
    return SysMLV2ConnectorService()
