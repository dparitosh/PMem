from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, parse, request


class DepoApiError(RuntimeError):
    """Raised when the DEPO backend API cannot satisfy a request."""


@dataclass(slots=True)
class DepoBinaryResponse:
    filename: str
    media_type: str
    body: bytes
    download_url: str


class DepoApiClient:
    def __init__(self, base_url: str, timeout_seconds: float = 120.0, auth_token: str = "") -> None:
        self.base_url = str(base_url or "").rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.auth_token = str(auth_token or "").strip()
        if not self.base_url:
            raise DepoApiError("DEPO API base URL is required")

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/health")

    def list_registered_ontologies(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/v1/ontology/registered")

    def graph_search(self, search: str, ontology_prefix: str = "") -> dict[str, Any]:
        query = str(search or "").strip()
        if not query:
            raise DepoApiError("search is required")
        return self._request_json(
            "POST",
            "/graphfilter",
            data={"search": query, "ontology_prefix": str(ontology_prefix or "").strip()},
        )

    def graph_search_many(
        self,
        names: list[str] | None = None,
        search: str | list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        normalized_names = [str(name).strip() for name in (names or []) if str(name or "").strip()]
        if normalized_names:
            payload["names"] = normalized_names
        elif isinstance(search, list):
            normalized_search = [str(item).strip() for item in search if str(item or "").strip()]
            if normalized_search:
                payload["search"] = normalized_search
        else:
            query = str(search or "").strip()
            if query:
                payload["search"] = query

        if not payload:
            raise DepoApiError("search or names are required")
        return self._request_json("POST", "/graphfilter-multi", data=payload)

    def oslc_catalog(self) -> dict[str, Any]:
        return self._request_json("GET", "/oslc/catalog")

    def oslc_provider(self, provider_id: str = "depo") -> dict[str, Any]:
        normalized_provider_id = str(provider_id or "depo").strip() or "depo"
        return self._request_json("GET", f"/oslc/providers/{parse.quote(normalized_provider_id)}")

    def oslc_shapes(self, shape_id: str = "") -> dict[str, Any]:
        normalized_shape_id = str(shape_id or "").strip()
        if normalized_shape_id:
            return self._request_json("GET", f"/oslc/shapes/{parse.quote(normalized_shape_id)}")
        return self._request_json("GET", "/oslc/shapes")

    def oslc_query_resources(
        self,
        resource_type: str = "resources",
        query_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_type = str(resource_type or "resources").strip() or "resources"
        query = self._query_string(query_params or {})
        suffix = f"?{query}" if query else ""
        return self._request_json("GET", f"/oslc/query/{parse.quote(normalized_type)}{suffix}")

    def oslc_resource(self, element_id: str, include_links: bool = True) -> dict[str, Any]:
        normalized_element_id = str(element_id or "").strip()
        if not normalized_element_id:
            raise DepoApiError("element_id is required")
        query = parse.urlencode({"include_links": str(bool(include_links)).lower()})
        return self._request_json("GET", f"/oslc/resources/{parse.quote(normalized_element_id)}?{query}")

    def oslc_dictionary(
        self,
        prefix: str,
        instance_limit: int | None = None,
        relationship_limit: int | None = None,
        fallback_limit: int | None = None,
    ) -> dict[str, Any]:
        normalized_prefix = str(prefix or "").strip()
        if not normalized_prefix:
            raise DepoApiError("prefix is required")
        params = {
            key: value
            for key, value in {
                "instance_limit": instance_limit,
                "relationship_limit": relationship_limit,
                "fallback_limit": fallback_limit,
            }.items()
            if value is not None
        }
        query = self._query_string(params)
        suffix = f"?{query}" if query else ""
        return self._request_json("GET", f"/oslc/dictionaries/{parse.quote(normalized_prefix)}{suffix}")

    def oslc_taxonomies(self, ontology_id: str = "") -> dict[str, Any]:
        normalized_ontology_id = str(ontology_id or "").strip()
        if normalized_ontology_id:
            return self._request_json("GET", f"/oslc/taxonomies/{parse.quote(normalized_ontology_id)}")
        return self._request_json("GET", "/oslc/taxonomies")

    def oslc_trs(self, section: str = "descriptor", after: int | None = None, limit: int | None = None) -> dict[str, Any]:
        normalized_section = str(section or "descriptor").strip().lower()
        if normalized_section in {"descriptor", "trs"}:
            return self._request_json("GET", "/oslc/trs")
        if normalized_section == "base":
            query = self._query_string({"limit": limit} if limit is not None else {})
            suffix = f"?{query}" if query else ""
            return self._request_json("GET", f"/oslc/trs/base{suffix}")
        if normalized_section in {"changelog", "change_log"}:
            query = self._query_string({"after": after, "limit": limit})
            suffix = f"?{query}" if query else ""
            return self._request_json("GET", f"/oslc/trs/changelog{suffix}")
        raise DepoApiError("section must be descriptor, base, or changelog")

    def execute_workflow(self, workflow_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        workflow_name = str(workflow_id or "").strip()
        if not workflow_name:
            raise DepoApiError("workflow_id is required")
        return self._request_json(
            "POST",
            "/api/v1/workflows/execute",
            data={"workflow_id": workflow_name, "payload": payload or {}},
        )

    def merge_ontologies(self, from_ontology_id: str, to_ontology_id: str, dry_run: bool = False) -> dict[str, Any]:
        source_id = str(from_ontology_id or "").strip()
        target_id = str(to_ontology_id or "").strip()
        if not source_id or not target_id:
            raise DepoApiError("from_ontology_id and to_ontology_id are required")
        return self._request_json(
            "POST",
            "/api/v1/ontology/merge",
            data={
                "from_ontology_id": source_id,
                "to_ontology_id": target_id,
                "dry_run": bool(dry_run),
            },
        )

    def export_import_owl(self, task_id: str, export_format: str = "ttl") -> DepoBinaryResponse:
        normalized_task_id = str(task_id or "").strip()
        normalized_format = str(export_format or "ttl").strip().lower()
        if not normalized_task_id:
            raise DepoApiError("task_id is required")
        query = parse.urlencode({"format": normalized_format})
        path = f"/api/v1/import/owl/{parse.quote(normalized_task_id)}/export?{query}"
        return self._request_binary("GET", path)

    def download_import_owl_export(self, task_id: str, output_dir: str | Path, export_format: str = "ttl") -> dict[str, Any]:
        response = self.export_import_owl(task_id, export_format)
        destination_dir = Path(output_dir).resolve()
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / response.filename
        destination.write_bytes(response.body)
        return {
            "task_id": task_id,
            "format": export_format,
            "filename": response.filename,
            "media_type": response.media_type,
            "saved_to": str(destination),
            "download_url": response.download_url,
            "size_bytes": len(response.body),
        }

    def _request_json(self, method: str, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._request(method, path, data=data)
        try:
            return json.loads(response.decode("utf-8")) if response else {}
        except json.JSONDecodeError as exc:
            raise DepoApiError(f"Invalid JSON response from DEPO API for {path}: {exc}") from exc

    def _request_binary(self, method: str, path: str, data: dict[str, Any] | None = None) -> DepoBinaryResponse:
        response, headers, url = self._request(method, path, data=data, include_headers=True)
        disposition = headers.get("Content-Disposition", "")
        filename = self._extract_filename(disposition) or Path(parse.urlparse(url).path).name or "download.bin"
        media_type = headers.get_content_type() if hasattr(headers, "get_content_type") else headers.get("Content-Type", "application/octet-stream")
        return DepoBinaryResponse(filename=filename, media_type=media_type, body=response, download_url=url)

    def _request(
        self,
        method: str,
        path: str,
        data: dict[str, Any] | None = None,
        include_headers: bool = False,
    ) -> Any:
        url = self._build_url(path)
        payload = None
        headers = {"Accept": "application/json"}
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        req = request.Request(url=url, data=payload, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                body = resp.read()
                if include_headers:
                    return body, resp.headers, resp.geturl()
                return body
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise DepoApiError(f"DEPO API request failed: {exc.code} {exc.reason} for {url}. {details}") from exc
        except error.URLError as exc:
            raise DepoApiError(f"DEPO API unreachable at {url}: {exc.reason}") from exc

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    @staticmethod
    def _query_string(params: dict[str, Any]) -> str:
        cleaned = {key: value for key, value in params.items() if value is not None and str(value) != ""}
        return parse.urlencode(cleaned)

    @staticmethod
    def _extract_filename(content_disposition: str) -> str:
        for segment in str(content_disposition or "").split(";"):
            part = segment.strip()
            if part.lower().startswith("filename="):
                return part.split("=", 1)[1].strip().strip('"')
        return ""
