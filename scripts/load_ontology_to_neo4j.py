"""
Direct Neo4j loader for TTL ontology files.
Combines 3dx_ontology.ttl + 13052026_from_xpdm.ttl into a single
'3DEXPERIENCE' ontology (prefix: ds3dx) in the spdm database.
Bypasses the import pipeline to avoid embedding/LLM stalls.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import rdflib
from rdflib import RDF, RDFS, OWL, URIRef, Literal, BNode
from neo4j import GraphDatabase

NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "tcs12345"
NEO4J_DB   = "spdm"

# Both TTL files → single 3DEXPERIENCE ontology
TTL_FILES = [
    "outputs/3dx_ontology.ttl",
    "outputs/13052026_from_xpdm.ttl",
]
ONTOLOGY_PREFIX = "ds3dx"
ONTOLOGY_NAME   = "3DEXPERIENCE"

BATCH_SIZE = 500


def local_name(uri):
    s = str(uri)
    for sep in ("#", "/", ":"):
        idx = s.rfind(sep)
        if 0 <= idx < len(s) - 1:
            return s[idx + 1:]
    return s


def safe_str(val, maxlen=500):
    s = str(val)
    return s[:maxlen]


def write_nodes(session, rows):
    """Write a batch of node dicts to Neo4j using UNWIND (fast)."""
    # Group by label combination for efficient UNWIND
    from collections import defaultdict
    by_labels = defaultdict(list)
    for row in rows:
        key = ":".join(row["labels"])
        by_labels[key].append({"uri": row["uri"], "props": row["props"]})

    for labels_str, items in by_labels.items():
        cypher = (
            f"UNWIND $rows AS row "
            f"MERGE (n:{labels_str} {{uri: row.uri}}) "
            f"SET n += row.props"
        )
        session.run(cypher, rows=items)


def write_relationships(session, rows):
    """Write a batch of relationship dicts to Neo4j using UNWIND per rel type."""
    from collections import defaultdict
    by_type = defaultdict(list)
    for row in rows:
        rel_type = row["rel"].replace("`", "").replace(" ", "_")
        by_type[rel_type].append({"src": row["src"], "tgt": row["tgt"]})

    for rel_type, items in by_type.items():
        cypher = (
            f"UNWIND $rows AS row "
            f"MATCH (a {{uri: row.src}}), (b {{uri: row.tgt}}) "
            f"MERGE (a)-[:`{rel_type}`]->(b)"
        )
        try:
            session.run(cypher, rows=items)
        except Exception:
            pass


def load_ttl_files(driver, paths, prefix, ontology_name):
    # Merge all TTL files into one rdflib graph
    g = rdflib.ConjunctiveGraph()
    for path in paths:
        print(f"  Parsing {path}...")
        g.parse(path, format="turtle")
    print(f"  Total triples: {len(g)}")

    # Classify subjects
    OWL_CLASS_TYPES = {OWL.Class, RDFS.Class}
    SKIP_TYPES = {
        OWL.Class, RDFS.Class, OWL.ObjectProperty, OWL.DatatypeProperty,
        OWL.AnnotationProperty, OWL.NamedIndividual, OWL.Ontology, RDF.Property,
    }

    classes      = set()
    obj_props    = set()
    data_props   = set()
    annotations  = set()
    individuals  = set()

    for s, p, o in g.triples((None, RDF.type, None)):
        if isinstance(s, BNode) or not isinstance(s, URIRef):
            continue
        if o == OWL.Class or o == RDFS.Class:
            classes.add(s)
        elif o == OWL.ObjectProperty:
            obj_props.add(s)
        elif o == OWL.DatatypeProperty:
            data_props.add(s)
        elif o == OWL.AnnotationProperty:
            annotations.add(s)
        elif o == OWL.NamedIndividual:
            individuals.add(s)
        elif isinstance(o, URIRef) and o not in SKIP_TYPES:
            individuals.add(s)

    print(f"  Classes: {len(classes)}, ObjProps: {len(obj_props)}, "
          f"DataProps: {len(data_props)}, Annotations: {len(annotations)}, "
          f"Individuals: {len(individuals)}")

    node_map = []  # (uri_node, [labels])
    for c in classes:
        node_map.append((c, ["OntologyClass"]))
    for p in obj_props:
        node_map.append((p, ["OntologyProperty", "ObjectProperty"]))
    for p in data_props:
        node_map.append((p, ["OntologyProperty", "DatatypeProperty"]))
    for p in annotations:
        node_map.append((p, ["OntologyProperty", "AnnotationProperty"]))
    for ind in individuals:
        node_map.append((ind, ["OntologyIndividual"]))

    total_nodes = 0
    batch = []

    with driver.session(database=NEO4J_DB) as session:
        for uri_node, labels in node_map:
            uri = str(uri_node)
            name = local_name(uri_node)
            props = {
                "name": name,
                "uri": uri,
                "prefix": prefix,
                "ontology_prefix": prefix,
                "ontology_name": ontology_name,
            }
            for lbl in g.objects(uri_node, RDFS.label):
                props["label"] = safe_str(lbl)
                break
            for cmt in g.objects(uri_node, RDFS.comment):
                props["description"] = safe_str(cmt)
                break

            batch.append({"uri": uri, "labels": labels, "props": props})
            total_nodes += 1

            if len(batch) >= BATCH_SIZE:
                write_nodes(session, batch)
                batch.clear()
                print(f"    ...{total_nodes} nodes written")

        if batch:
            write_nodes(session, batch)
            batch.clear()

        print(f"  Nodes written: {total_nodes}")

        # Relationships
        REL_PREDICATES = {
            "subClassOf", "subPropertyOf", "domain", "range",
            "equivalentClass", "inverseOf", "onProperty", "type",
        }
        rel_batch = []
        total_rels = 0

        for s, p, o in g:
            if isinstance(s, BNode) or isinstance(o, BNode):
                continue
            if not isinstance(o, URIRef):
                continue
            pname = local_name(p)
            if pname in REL_PREDICATES:
                rel_batch.append({"src": str(s), "tgt": str(o), "rel": pname})
                total_rels += 1
                if len(rel_batch) >= BATCH_SIZE:
                    write_relationships(session, rel_batch)
                    rel_batch.clear()

        if rel_batch:
            write_relationships(session, rel_batch)

        print(f"  Relationships written: {total_rels}")


def main():
    # Script lives in Depo_onto/scripts/, TTL files are in Depo_onto/outputs/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    paths = [os.path.join(base_dir, p) for p in TTL_FILES]

    print(f"Connecting to Neo4j at {NEO4J_URI} (db={NEO4J_DB})...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    print(f"Loading {len(paths)} TTL files as ontology '{ONTOLOGY_NAME}' (prefix={ONTOLOGY_PREFIX})...")
    load_ttl_files(driver, paths, ONTOLOGY_PREFIX, ONTOLOGY_NAME)

    with driver.session(database=NEO4J_DB) as session:
        total = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        classes = session.run(
            "MATCH (n:OntologyClass) RETURN count(n) AS c"
        ).single()["c"]
        props = session.run(
            "MATCH (n:OntologyProperty) RETURN count(n) AS c"
        ).single()["c"]
        inds = session.run(
            "MATCH (n:OntologyIndividual) RETURN count(n) AS c"
        ).single()["c"]

    print(f"\n=== Neo4j spdm database summary ===")
    print(f"  Total nodes      : {total}")
    print(f"  OntologyClass    : {classes}")
    print(f"  OntologyProperty : {props}")
    print(f"  OntologyIndividual: {inds}")

    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
