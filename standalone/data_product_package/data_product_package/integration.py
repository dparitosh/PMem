"""Small adapter for packaging outputs produced by the main application.

This module accepts already-exported files and metadata. It deliberately does
not import FastAPI, Neo4j, or the ontology-agentic package.
"""

from __future__ import annotations

from typing import Any, Iterable

from .builder import DataProductBuilder
from .models import ArtifactSpec, DataProductSpec, SourceSpec


def build_from_app_outputs(
    *,
    output_dir: str,
    product: dict[str, Any],
    artifacts: Iterable[dict[str, Any]],
    ontologies: Iterable[dict[str, Any]] = (),
    sources: Iterable[dict[str, Any]] = (),
    catalog_path: str = "",
) -> dict[str, Any]:
    """Build a package from explicit app exports and lineage metadata.

    The caller can obtain ``artifacts`` from ontology export, graph JSON-LD,
    report, or import-artifact APIs. No database access is performed here.
    """
    spec = DataProductSpec(
        product_id=str(product.get("product_id") or "").strip(),
        name=str(product.get("name") or "").strip(),
        version=str(product.get("version") or "1.0.0").strip(),
        domain=str(product.get("domain") or "Engineering"),
        description=str(product.get("description") or ""),
        owner=str(product.get("owner") or ""),
        ontologies=[dict(item) for item in ontologies],
        sources=[item if isinstance(item, SourceSpec) else SourceSpec(**dict(item)) for item in sources],
        artifacts=[item if isinstance(item, ArtifactSpec) else ArtifactSpec(**dict(item)) for item in artifacts],
        catalog_path=catalog_path,
    )
    return DataProductBuilder(output_dir).build(spec, catalog_path=catalog_path)
