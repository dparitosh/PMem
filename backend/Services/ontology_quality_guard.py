from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from rdflib import Graph, RDF, RDFS
from rdflib.namespace import OWL, XSD


@dataclass
class OntologyQualityReport:
    file: str
    triples: int
    class_property_punning: int
    object_property_xsd_like_range: int
    class_labels_leading_dot: int

    @property
    def issue_count(self) -> int:
        return (
            self.class_property_punning
            + self.object_property_xsd_like_range
            + self.class_labels_leading_dot
        )

    def to_dict(self) -> Dict[str, int | str]:
        return {
            "file": self.file,
            "triples": self.triples,
            "class_property_punning": self.class_property_punning,
            "object_property_xsd_like_range": self.object_property_xsd_like_range,
            "class_labels_leading_dot": self.class_labels_leading_dot,
            "issue_count": self.issue_count,
        }


def assess_ontology_quality(ontology_path: str) -> OntologyQualityReport:
    path = Path(ontology_path)
    if not path.exists():
        raise FileNotFoundError(f"Ontology file not found: {ontology_path}")

    g = Graph()
    formats = (
        ("turtle", "xml", "n3", "nt")
        if path.suffix.lower() in {".ttl", ".owl"}
        else ("xml", "turtle", "n3", "nt")
    )
    last_error: Exception | None = None
    for fmt in formats:
        try:
            g = Graph()
            g.parse(str(path), format=fmt)
            last_error = None
            break
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise ValueError(f"Ontology cannot be parsed as RDF: {path}: {last_error}") from last_error

    obj_props = set(g.subjects(RDF.type, OWL.ObjectProperty))
    data_props = set(g.subjects(RDF.type, OWL.DatatypeProperty))
    classes = set(g.subjects(RDF.type, OWL.Class))

    class_property_punning = sum(1 for p in (obj_props | data_props) if (p, RDF.type, OWL.Class) in g)

    object_property_xsd_like_range = 0
    for p in obj_props:
        for r in g.objects(p, RDFS.range):
            rs = str(r)
            if rs.startswith(str(XSD)) or "xsd_" in rs:
                object_property_xsd_like_range += 1

    class_labels_leading_dot = 0
    for c in classes:
        for label in g.objects(c, RDFS.label):
            if str(label).startswith("."):
                class_labels_leading_dot += 1

    return OntologyQualityReport(
        file=str(path),
        triples=len(g),
        class_property_punning=class_property_punning,
        object_property_xsd_like_range=object_property_xsd_like_range,
        class_labels_leading_dot=class_labels_leading_dot,
    )


def maybe_enforce_quality(ontology_path: str) -> None:
    """Apply optional quality checks to generated ontology artifacts.

    Env flags:
    - ONTO_QUALITY_CHECK=true|false (default: true)
    - ONTO_QUALITY_STRICT=true|false (default: false)
    - ONTO_QUALITY_REPORT=true|false (default: true)
    """
    import os

    do_check = os.getenv("ONTO_QUALITY_CHECK", "true").lower() in {"1", "true", "yes"}
    if not do_check:
        return

    report = assess_ontology_quality(ontology_path)

    do_report = os.getenv("ONTO_QUALITY_REPORT", "true").lower() in {"1", "true", "yes"}
    if do_report:
        report_path = Path(ontology_path).with_suffix(".quality.json")
        temp_path = report_path.with_name(f".{report_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(report.to_dict(), handle, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, report_path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    strict = os.getenv("ONTO_QUALITY_STRICT", "false").lower() in {"1", "true", "yes"}
    if strict and report.issue_count > 0:
        raise ValueError(
            "Ontology quality checks failed: "
            f"punning={report.class_property_punning}, "
            f"xsd_like_ranges={report.object_property_xsd_like_range}, "
            f"dot_labels={report.class_labels_leading_dot}"
        )
