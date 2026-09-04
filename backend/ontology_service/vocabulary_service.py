"""Versioned, steward-governed SKOS vocabulary curation."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from rdflib import Graph, Literal, RDF, URIRef
from rdflib.namespace import DCTERMS, SKOS

from backend.Services.semantic_taxonomy_service import SemanticTaxonomyService, normalize_skos_payload
from backend.artifact_store import ArtifactStore
from backend.mesh_store import PostgresRegistry


_ID = re.compile(r"[a-z][a-z0-9-]{2,62}$")
_SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_TRANSITIONS = {"draft": {"in_review"}, "in_review": {"draft", "approved"}, "approved": set(), "published": set()}


class VocabularyService:
    def __init__(self) -> None:
        self.store = PostgresRegistry("skos_vocabulary_releases")
        self.artifacts = ArtifactStore()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def key(scheme_id: str, version: str) -> str:
        return f"{scheme_id}:{version}"

    def create(self, payload: dict[str, Any], actor: str) -> dict[str, Any]:
        scheme, concepts = normalize_skos_payload(payload)
        if not _ID.fullmatch(scheme.scheme_id):
            raise ValueError("scheme_id must be lowercase kebab-case and 3–63 characters")
        if not _SEMVER.fullmatch(scheme.version):
            raise ValueError("vocabulary version must use semantic version major.minor.patch")
        base_uri = str(payload.get("base_uri") or "").strip()
        steward = str(payload.get("steward") or "").strip()
        provenance = dict(payload.get("provenance") or {})
        if not base_uri.startswith(("https://", "urn:")):
            raise ValueError("base_uri must be an HTTPS or URN namespace")
        if not steward or not provenance.get("source") or not provenance.get("rationale"):
            raise ValueError("steward and provenance source/rationale are required")
        validation = SemanticTaxonomyService.validate(concepts)
        if not validation["valid"]:
            raise ValueError("SKOS validation failed: " + ", ".join(sorted({item["code"] for item in validation["issues"]})))
        key = self.key(scheme.scheme_id, scheme.version)
        if self.store.get(key):
            raise FileExistsError("Vocabulary scheme version already exists and is immutable")
        normalized_concepts = [SemanticTaxonomyService.to_dict(concept) for concept in concepts]
        record = {
            "scheme": {"scheme_id": scheme.scheme_id, "pref_label": scheme.pref_label, "definition": scheme.definition, "version": scheme.version},
            "base_uri": base_uri.rstrip("/#") + "/", "concepts": normalized_concepts,
            "steward": steward, "provenance": {**provenance, "created_by": actor},
            "lifecycle_status": "draft", "publication_status": "not_published",
            "validation": validation, "created_at": self._now(), "updated_at": self._now(),
            "history": [{"from": None, "to": "draft", "actor": actor, "at": self._now(), "reason": provenance["rationale"]}],
        }
        return self.store.put(key, record)

    def list(self) -> list[dict[str, Any]]:
        return sorted(self.store.all().values(), key=lambda item: item.get("updated_at", ""), reverse=True)

    def get(self, scheme_id: str, version: str) -> dict[str, Any] | None:
        return self.store.get(self.key(scheme_id, version))

    def transition(self, scheme_id: str, version: str, target: str, actor: str, reason: str) -> dict[str, Any]:
        record = self.get(scheme_id, version)
        if not record:
            raise LookupError("Vocabulary release was not found")
        current = str(record.get("lifecycle_status"))
        if target not in _TRANSITIONS.get(current, set()):
            raise ValueError(f"Vocabulary cannot transition from {current} to {target}")
        if not reason.strip():
            raise ValueError("reason is required for lifecycle evidence")
        now = self._now()
        updated = {
            **record, "lifecycle_status": target, "updated_at": now,
            "history": [*record.get("history", []), {"from": current, "to": target, "actor": actor, "at": now, "reason": reason}],
        }
        return self.store.put(self.key(scheme_id, version), updated)

    @staticmethod
    def _iri(base_uri: str, value: str) -> URIRef:
        return URIRef(value) if value.startswith(("http://", "https://", "urn:")) else URIRef(base_uri + quote(value, safe="-._~"))

    def turtle(self, record: dict[str, Any]) -> bytes:
        graph, base_uri = Graph(), str(record["base_uri"])
        scheme_data = record["scheme"]
        scheme_iri = self._iri(base_uri, scheme_data["scheme_id"])
        graph.add((scheme_iri, RDF.type, SKOS.ConceptScheme))
        graph.add((scheme_iri, SKOS.prefLabel, Literal(scheme_data["pref_label"])))
        if scheme_data.get("definition"):
            graph.add((scheme_iri, SKOS.definition, Literal(scheme_data["definition"])))
        graph.add((scheme_iri, DCTERMS.hasVersion, Literal(scheme_data["version"])))
        by_id = {concept["concept_id"]: self._iri(base_uri, concept["concept_id"]) for concept in record["concepts"]}
        mapping_predicates = {name: URIRef(str(SKOS) + name) for name in ("exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch")}
        for concept in record["concepts"]:
            iri = by_id[concept["concept_id"]]
            graph.add((iri, RDF.type, SKOS.Concept)); graph.add((iri, SKOS.inScheme, scheme_iri))
            graph.add((iri, SKOS.prefLabel, Literal(concept["pref_label"])))
            for label in concept.get("alt_labels", []): graph.add((iri, SKOS.altLabel, Literal(label)))
            if concept.get("definition"): graph.add((iri, SKOS.definition, Literal(concept["definition"])))
            for target in concept.get("broader", []): graph.add((iri, SKOS.broader, by_id[target]))
            for target in concept.get("narrower", []): graph.add((iri, SKOS.narrower, by_id[target]))
            for target in concept.get("related", []): graph.add((iri, SKOS.related, by_id[target]))
            for mapping_type, targets in concept.get("mappings", {}).items():
                for target in targets: graph.add((iri, mapping_predicates[mapping_type], URIRef(target)))
        return graph.serialize(format="turtle", encoding="utf-8")

    def publication_artifact(self, record: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        content = self.turtle(record)
        scheme = record["scheme"]
        artifact = self.artifacts.ingest_bytes(
            content, filename=f"{scheme['scheme_id']}-{scheme['version']}.ttl", kind="skos-vocabulary",
            media_type="text/turtle", provenance={"scheme_id": scheme["scheme_id"], "version": scheme["version"], "steward": record["steward"]},
        )
        return artifact, content

    def mark_published(self, record: dict[str, Any], actor: str, artifact: dict[str, Any], publication: dict[str, Any]) -> dict[str, Any]:
        if record.get("publication_status") == "published":
            return record
        now = self._now(); scheme = record["scheme"]
        updated = {
            **record, "lifecycle_status": "published", "publication_status": "published", "updated_at": now,
            "artifact_id": artifact["artifact_id"], "publication": publication,
            "publication_digest": "sha256:" + hashlib.sha256(
                json.dumps(publication, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest(),
            "history": [*record.get("history", []), {"from": "approved", "to": "published", "actor": actor, "at": now, "reason": "Approved SKOS publication"}],
        }
        return self.store.put(self.key(scheme["scheme_id"], scheme["version"]), updated)


vocabularies = VocabularyService()
