"""Strict, versioned CEIM v0.1 normalization contract.

This module deliberately maps only declared source types.  It does not infer a
canonical type from a filename or a free-text label, keeping standards mapping
reviewable and suitable for batch/Spark processing.
"""
from __future__ import annotations

import json
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, RDF, URIRef

from backend.Services.shacl_service import ShaclValidationService
from backend.ceim.normalization import normalize_record
from backend.ceim.resolution import analyze_entities


class CEIMContract:
    version = "0.1.0"
    namespace = "https://depo.example.org/ceim/0.1/"
    entity_types = frozenset({"Product", "ProductRevision", "Part", "Assembly", "Requirement", "QualityMeasurement", "Document", "Change", "Configuration", "Test", "Process", "Resource", "Feature", "Characteristic", "Datum", "DatumReferenceFrame", "PMIAnnotation", "GeometryBody"})
    relationship_types = frozenset({"HAS_PART", "HAS_GEOMETRY", "HAS_FEATURE", "HAS_CHARACTERISTIC", "USES_DATUM", "USES_REFERENCE_FRAME", "REALIZES", "SATISFIES", "TRACE_TO", "DERIVED_FROM", "VERIFIED_BY", "VALIDATED_BY", "IMPACTS", "PRODUCES", "CONSUMES"})

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "data" / "ceim"
        self.mapping_root = self.root / "mapping-packs"

    @lru_cache(maxsize=32)
    def mapping_pack(self, standard: str) -> dict[str, Any]:
        identifier = str(standard or "").strip().lower()
        path = self.mapping_root / f"{identifier}.json"
        if not path.is_file():
            raise ValueError(f"No CEIM mapping pack is registered for: {standard}")
        raw = path.read_bytes()
        pack = json.loads(raw.decode("utf-8"))
        if pack.get("ceim_version") != self.version:
            raise ValueError(f"CEIM mapping pack {identifier} is incompatible with CEIM {self.version}")
        self._validate_pack(pack, identifier)
        return {**pack, "digest": f"sha256:{hashlib.sha256(raw).hexdigest()}"}

    def _validate_pack(self, pack: dict[str, Any], identifier: str) -> None:
        if not str(pack.get("id") or "").strip() or not str(pack.get("version") or "").strip():
            raise ValueError(f"CEIM mapping pack {identifier} requires id and version")
        entities, relationships = pack.get("entities"), pack.get("relationships")
        if not isinstance(entities, dict) or not isinstance(relationships, dict):
            raise ValueError(f"CEIM mapping pack {identifier} requires entities and relationships objects")
        for source_type, mapping in entities.items():
            if not str(source_type).strip() or not isinstance(mapping, dict) or mapping.get("ceim_type") not in self.entity_types or not isinstance(mapping.get("properties", {}), dict):
                raise ValueError(f"CEIM mapping pack {identifier} has invalid entity mapping: {source_type}")
        for source_type, mapping in relationships.items():
            if not str(source_type).strip() or not isinstance(mapping, dict) or mapping.get("relationship") not in self.relationship_types:
                raise ValueError(f"CEIM mapping pack {identifier} has invalid relationship mapping: {source_type}")
        for rule in pack.get("reference_rules", []):
            if not isinstance(rule, dict) or not all(str(rule.get(key) or "").strip() for key in ("source_type", "attribute", "relationship_source_type")):
                raise ValueError(f"CEIM mapping pack {identifier} has an invalid structural reference rule")
            if rule["source_type"] not in entities or rule["relationship_source_type"] not in relationships:
                raise ValueError(f"CEIM mapping pack {identifier} references an undeclared entity or relationship mapping")

    def normalize_entity(self, *, standard: str, record: dict[str, Any]) -> dict[str, Any]:
        record, normalization = normalize_record(record)
        pack = self.mapping_pack(standard)
        source_type = str(record.get("source_type") or "").strip()
        source_id = str(record.get("source_id") or record.get("id") or "").strip()
        if not source_type or not source_id:
            raise ValueError("CEIM normalization requires source_type and source_id")
        mapping = dict(pack.get("entities") or {}).get(source_type)
        if not mapping:
            raise ValueError(f"No CEIM entity mapping for {standard}:{source_type}")
        attributes = dict(record.get("attributes") or {})
        properties: dict[str, Any] = {}
        for source, target in dict(mapping.get("properties") or {}).items():
            value = source_id if source == "$source_id" else attributes.get(source)
            if value not in (None, ""):
                properties[target] = value
        return {
            "id": f"{standard.lower()}:{source_id}",
            "ceim_type": mapping["ceim_type"],
            "properties": properties,
            "provenance": {
                "ceim_version": self.version,
                "mapping_pack": pack["id"],
                "mapping_version": pack["version"],
                "mapping_digest": pack["digest"],
                "source_standard": standard,
                "source_type": source_type,
                "source_id": source_id,
                "normalization": normalization,
            },
        }

    def normalize_relationship(self, *, standard: str, record: dict[str, Any]) -> dict[str, Any]:
        record, normalization = normalize_record(record)
        pack = self.mapping_pack(standard)
        source_type = str(record.get("source_type") or "").strip()
        source_id, target_id = str(record.get("source_id") or "").strip(), str(record.get("target_id") or "").strip()
        if not source_type or not source_id or not target_id:
            raise ValueError("CEIM relationship normalization requires source_type, source_id, and target_id")
        mapping = dict(pack.get("relationships") or {}).get(source_type)
        if not mapping:
            raise ValueError(f"No CEIM relationship mapping for {standard}:{source_type}")
        return {
            "source_id": f"{standard.lower()}:{source_id}",
            "relationship": mapping["relationship"],
            "target_id": f"{standard.lower()}:{target_id}",
            "provenance": {
                "ceim_version": self.version, "mapping_pack": pack["id"],
                "mapping_version": pack["version"], "mapping_digest": pack["digest"],
                "source_standard": standard, "source_type": source_type,
                # Structural adapters declare the exact source field (for
                # example parentRef or rootRefs) that asserted this edge.
                "source_key": str(record.get("source_key") or f"mapping:{source_type}"),
                "normalization": normalization,
            },
        }

    def validate_mapping_evidence(
        self, *, standard: str, entities: list[dict[str, Any]], relationships: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Reject normalized records produced by a different mapping release.

        A retained batch is reproducible only when its mapping evidence still
        matches the governed pack selected for the run.  This deliberately
        prevents a replay from silently publishing assertions produced by an
        obsolete or mixed mapping pack.
        """
        pack = self.mapping_pack(standard)
        expected = {"mapping_pack": str(pack["id"]), "mapping_version": str(pack["version"]), "mapping_digest": str(pack["digest"])}
        for record in [*entities, *relationships]:
            provenance = record.get("provenance") if isinstance(record, dict) else None
            if not isinstance(provenance, dict):
                raise ValueError("Normalized CEIM input requires mapping provenance for every record")
            for key, value in expected.items():
                if str(provenance.get(key) or "") != value:
                    raise ValueError(f"Normalized CEIM input {key} does not match the active governed mapping pack")
        return expected

    @staticmethod
    def _predicate_name(value: str) -> str:
        parts = [part for part in str(value).split("_") if part]
        return parts[0] + "".join(part.capitalize() for part in parts[1:]) if parts else "value"

    def to_rdf(self, *, entities: list[dict[str, Any]], relationships: list[dict[str, Any]], decision: dict[str, Any] | None = None) -> Graph:
        """Create a deterministic RDF projection suitable for SHACL and graph publication."""
        graph = Graph()
        ceim, prov = Namespace(self.namespace), Namespace("http://www.w3.org/ns/prov#")
        boc = Namespace("https://depo.example.org/ontology/bill-of-characteristics/1.0/")
        normalized_entities = []
        for entity in entities:
            normalized, changes = normalize_record(entity)
            provenance = dict(normalized.get("provenance") or {})
            provenance["normalization"] = [*list(provenance.get("normalization") or []), *changes]
            normalized["provenance"] = provenance; normalized_entities.append(normalized)
        resolution = analyze_entities(normalized_entities)
        if resolution["blocking"]:
            raise ValueError("Entity-resolution conflicts require a steward decision before RDF construction")
        entities = resolution["entities"]
        entity_uris: dict[str, URIRef] = {}
        for entity in entities:
            entity_id = str(entity.get("id") or "").strip()
            entity_type = str(entity.get("ceim_type") or "").strip()
            if not entity_id or entity_type not in self.entity_types:
                raise ValueError("CEIM RDF projection requires a valid normalized entity id and ceim_type")
            uri = URIRef(f"{self.namespace}entity/{quote(entity_id, safe='')}")
            entity_uris[entity_id] = uri
            graph.add((uri, RDF.type, ceim[entity_type]))
            source_standard = str(provenance.get("source_standard") or "").lower()
            source_type = str(provenance.get("source_type") or "")
            boc_type = {
                ("qif", "CharacteristicDefinition"): boc.Characteristic,
                ("qif", "CharacteristicNominal"): boc.NominalCharacteristic,
                ("ap242", "dimension"): boc.DimensionalCharacteristic,
                ("ap242", "geometric_tolerance"): boc.TolerancedCharacteristic,
            }.get((source_standard, source_type))
            if boc_type is not None:
                graph.add((uri, RDF.type, boc_type))
            for key, value in dict(entity.get("properties") or {}).items():
                if value not in (None, ""):
                    graph.add((uri, ceim[self._predicate_name(str(key))], Literal(value)))
            provenance = dict(entity.get("provenance") or {})
            source = URIRef(f"urn:depo:source:{quote(str(provenance.get('source_standard') or 'unknown'), safe='')}:{quote(str(provenance.get('source_id') or entity_id), safe='')}")
            activity_digest = hashlib.sha256(json.dumps(provenance, sort_keys=True, default=str).encode()).hexdigest()
            activity = URIRef(f"urn:depo:activity:mapping:{activity_digest}")
            graph.add((uri, prov.wasDerivedFrom, source)); graph.add((uri, prov.wasGeneratedBy, activity))
            graph.add((activity, prov.used, source)); graph.add((activity, prov.wasAssociatedWith, URIRef(f"urn:depo:mapping:{quote(str(provenance.get('mapping_pack') or 'unknown'), safe='')}")))
            graph.add((activity, ceim.mappingDigest, Literal(str(provenance.get("mapping_digest") or ""))))
        for relationship in relationships:
            relationship, relationship_changes = normalize_record(relationship)
            source_id = str(relationship.get("source_id") or "").strip()
            target_id = str(relationship.get("target_id") or "").strip()
            relation = str(relationship.get("relationship") or "").strip()
            if relation not in self.relationship_types or source_id not in entity_uris or target_id not in entity_uris:
                raise ValueError("CEIM RDF projection relationship must reference normalized entities in the same batch")
            predicate = ceim[self._predicate_name(relation.lower())]
            graph.add((entity_uris[source_id], predicate, entity_uris[target_id]))
            provenance = dict(relationship.get("provenance") or {})
            provenance["normalization"] = [*list(provenance.get("normalization") or []), *relationship_changes]
            assertion = URIRef(f"urn:depo:assertion:{hashlib.sha256(f'{source_id}|{relation}|{target_id}|{json.dumps(provenance, sort_keys=True, default=str)}'.encode()).hexdigest()}")
            source = URIRef(f"urn:depo:source:{quote(str(provenance.get('source_standard') or 'unknown'), safe='')}:{quote(str(provenance.get('source_type') or relation), safe='')}")
            graph.add((assertion, RDF.type, RDF.Statement))
            graph.add((assertion, RDF.subject, entity_uris[source_id])); graph.add((assertion, RDF.predicate, predicate)); graph.add((assertion, RDF.object, entity_uris[target_id])); graph.add((assertion, prov.wasDerivedFrom, source))
            graph.add((assertion, ceim.sourceStandard, Literal(str(provenance.get("source_standard") or "unknown"))))
            graph.add((assertion, ceim.sourceType, Literal(str(provenance.get("source_type") or relation))))
            graph.add((assertion, ceim.sourceKey, Literal(str(provenance.get("source_key") or f"mapping:{provenance.get('source_type') or relation}"))))
        if decision:
            decision_id = hashlib.sha256(json.dumps(decision, sort_keys=True, default=str).encode()).hexdigest()
            activity = URIRef(f"urn:depo:activity:publication:{decision_id}")
            graph.add((activity, RDF.type, prov.Activity)); graph.add((activity, prov.wasAssociatedWith, URIRef(f"urn:depo:actor:{quote(str(decision.get('approved_by') or 'unknown'), safe='')}")))
            graph.add((activity, ceim.semanticRelease, Literal(json.dumps(decision.get("semantic_release") or {}, sort_keys=True))))
        validation_digest = hashlib.sha256("|".join(sorted(str(entity.get("id") or "") for entity in entities)).encode()).hexdigest()
        validation = URIRef(f"urn:depo:activity:shacl:{validation_digest}")
        graph.add((validation, RDF.type, prov.Activity)); graph.add((validation, prov.used, URIRef("urn:depo:shacl:ceim-v0.1")))
        for uri in entity_uris.values(): graph.add((uri, prov.wasGeneratedBy, validation))
        return graph

    def validate_projection(self, *, entities: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> dict[str, Any]:
        graph = self.to_rdf(entities=entities, relationships=relationships)
        shapes = (self.root / "ceim-v0.1-shapes.ttl").read_text(encoding="utf-8")
        report = ShaclValidationService().validate_graph(graph, shacl_graph_str=shapes)
        return {**report, "ceim_version": self.version, "triple_count": len(graph)}

    def turtle_projection(self, *, entities: list[dict[str, Any]], relationships: list[dict[str, Any]], decision: dict[str, Any] | None = None) -> str:
        return self.to_rdf(entities=entities, relationships=relationships, decision=decision).serialize(format="turtle")


contract = CEIMContract()
