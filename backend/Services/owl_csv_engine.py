"""
Generic CSV -> OWL2/Turtle Converter
===================================
Converts a CSV file to a simple ontology representation where each row is an
individual and each column is modeled as a datatype property.
"""

from __future__ import annotations

import csv
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD


def _safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text.strip()) or "value"


def convert_csv_to_ttl(
    csv_path: str,
    output_path: str,
    base_uri: str = "",
    prefix: str = "",
    title: str = "",
    comment: str = "",
) -> str:
    """Convert a CSV file into an OWL/Turtle graph and write it to output_path."""
    src = Path(csv_path)
    if not src.exists():
        raise FileNotFoundError(f"CSV file not found: {src}")
    if src.suffix.lower() != ".csv":
        raise ValueError(f"Expected .csv input, got: {src.suffix}")

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    root_uri = (base_uri or "http://IAE-depo.com/csv-ontology#").strip()
    if not root_uri.endswith(("#", "/")):
        root_uri = root_uri + "#"

    ns_prefix = (prefix or "csv").strip() or "csv"
    onto_title = title or f"CSV Ontology: {src.stem}"
    onto_comment = comment or f"Ontology generated from CSV file {src.name}"

    ns = Namespace(root_uri)
    g = Graph()
    g.bind("", ns)
    g.bind(ns_prefix, ns)
    g.bind("owl", OWL)
    g.bind("rdf", RDF)
    g.bind("rdfs", RDFS)
    g.bind("xsd", XSD)

    ontology_node = URIRef(root_uri)
    row_class = ns["Row"]
    g.add((ontology_node, RDF.type, OWL.Ontology))
    g.add((ontology_node, RDFS.label, Literal(onto_title)))
    g.add((ontology_node, RDFS.comment, Literal(onto_comment)))
    g.add((row_class, RDF.type, OWL.Class))
    g.add((row_class, RDFS.label, Literal("Row")))

    with src.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []

        for field in fieldnames:
            prop = ns[f"has_{_safe_name(field)}"]
            g.add((prop, RDF.type, OWL.DatatypeProperty))
            g.add((prop, RDFS.domain, row_class))
            g.add((prop, RDFS.range, XSD.string))
            g.add((prop, RDFS.label, Literal(field)))

        for idx, row in enumerate(reader, start=1):
            row_uri = ns[f"row_{idx}"]
            g.add((row_uri, RDF.type, OWL.NamedIndividual))
            g.add((row_uri, RDF.type, row_class))
            g.add((row_uri, RDFS.label, Literal(f"Row {idx}")))

            for field in fieldnames:
                value = row.get(field)
                if value is None or value == "":
                    continue
                prop = ns[f"has_{_safe_name(field)}"]
                g.add((row_uri, prop, Literal(value)))

    g.serialize(destination=str(out), format="turtle")
    return str(out)
