from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List


@dataclass
class ArtifactSpec:
    path: str
    kind: str = "artifact"
    format: str = "bin"
    name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SourceSpec:
    id: str
    type: str
    name: str = ""
    source_uri: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DataProductSpec:
    product_id: str
    name: str
    version: str = "1.0.0"
    domain: str = "Engineering"
    description: str = ""
    owner: str = ""
    ontologies: List[Dict[str, Any]] = field(default_factory=list)
    sources: List[SourceSpec] = field(default_factory=list)
    artifacts: List[ArtifactSpec] = field(default_factory=list)
    catalog_path: str = ""

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "DataProductSpec":
        artifacts = [
            item if isinstance(item, ArtifactSpec) else ArtifactSpec(**item)
            for item in payload.get("artifacts", [])
        ]
        sources = [
            item if isinstance(item, SourceSpec) else SourceSpec(**item)
            for item in payload.get("sources", [])
        ]
        values = dict(payload)
        values["artifacts"] = artifacts
        values["sources"] = sources
        return cls(**values)

    def to_dict(self) -> Dict[str, Any]:
        values = asdict(self)
        values["sources"] = [source.to_dict() for source in self.sources]
        values["artifacts"] = [artifact.to_dict() for artifact in self.artifacts]
        return values
