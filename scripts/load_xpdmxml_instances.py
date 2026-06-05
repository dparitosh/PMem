"""
load_xpdmxml_instances.py
--------------------------
Loads XPDMXML instance files (Motor_BOP.xml, Motor_WorkPlan.xml) into Neo4j.

Each XPDMXML entity element (ManufacturingAssembly, ProvidedPart, WorkPlan,
HeaderOperation, LoadingOperation, GeneralOperation, GeneralSystem,
OperationInst, TransformationInst, SystemInst, SystemPortIN/OUT,
DataRequirementPortOUT, SystemImplementLink, EndToStartLink) becomes a node.

Relationships created:
  - OWNED_BY       : child.Owned  → parent entity
  - INSTANCES      : inst.Instancing → master entity
  - HAS_PORT       : port.Owned → parent entity  (alias for OWNED_BY)
  - PRECEDES       : EndToStartLink  FromInstanceRef → ToInstanceRef
  - IMPLEMENTS_OP  : SystemImplementLink OperationRef/PathItem → OperationInst
  - IMPLEMENTS_TRF : SystemImplementLink TransformationInstanceRef/PathItem → TransformationInst
  - INSTANCE_OF    : every instance node → OntologyClass node (if present in db)

Nodes get labels: <ElementType> + InstanceNode  (for shared index queries)

Usage:
  python load_xpdmxml_instances.py [--clean]

  --clean  : wipe all InstanceNode nodes from this dataset before loading
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# ── Neo4j ─────────────────────────────────────────────────────────────────────
from neo4j import GraphDatabase

NEO4J_URI  = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "tcs12345"
NEO4J_DB   = "spdm"

# ── Source files ───────────────────────────────────────────────────────────────
SOURCE_DIR = Path(r"C:\Users\895428\Depo\SPLM_Folder\Motor 2")
FILES = {
    "motor_bop":      SOURCE_DIR / "Motor_BOP.xml",
    "motor_workplan": SOURCE_DIR / "Motor_WorkPlan.xml",
}

DATASET_NAME = "3DEXPERIENCE"
ONTOLOGY_PREFIX = "ds3dx"  # used for INSTANCE_OF links

# ── Element types that become first-class nodes ────────────────────────────────
ENTITY_TYPES = {
    "ManufacturingAssembly",
    "ProvidedPart",
    "WorkPlan",
    "HeaderOperation",
    "LoadingOperation",
    "GeneralOperation",
    "GeneralSystem",
    "TransformationInst",
    "OperationInst",
    "SystemInst",
    "SystemPortIN",
    "SystemPortOUT",
    "DataRequirementPortOUT",
    "SystemImplementLink",
    "EndToStartLink",
}

# ── Properties we harvest from child text elements ─────────────────────────────
SCALAR_PROPS = {
    "ID", "Name", "Description", "RevisionName", "RevisionIndex",
    "RevisionFamily", "Maturity", "Lifecycle", "TimeCreated", "TimeModified",
    "Owner", "Organization", "Project", "SecurityLevel",
    "EstimatedTime", "ThroughputTime", "AnalysedTime", "CycleTime",
    "MeasuredTime", "TotalProductionTime", "EstimatedCost",
    "EstimatedCostCurrency", "EstimatedWeight",
    "ManufacturingAssemblyName", "ManufacturingAssemblyNumber",
    "OutSourced", "NeedDedicatedSystem", "IsSerialNumberRequired",
    "IsLotNumberRequired", "SpareManufacturedItem", "IsFlexiblePart",
    "ManufacturedItemClassification", "MaterialCategory",
    "DiscreteQuantity", "ChildOrder", "IsPredecessorOfOwned",
    "ReplaceStatus", "UseCase",
    "Delay", "DelayMode", "IsActive", "OptionalTimeConstraint",
    "ResourceConstraint", "MaterialNeed",
    "Overlap", "ImplementLinkUsage",
    "SequencingMode", "OperationMode", "DistributionRule",
    "UseGanttTimeSolver", "ManageVariant",
    "MeanTimeBetweenFailures", "MeanTimeToRepair",
    "Interruptible", "TrackTime", "TimeMode",
    "QueuingModeIN", "QueuingModeOUT", "QueuingPriority",
    "QualifiedForSourcing",
    "TargetReleaseDate", "EstimatedLeadTimeDescription",
    "ValueAddedRatioOnEstimatedTime", "Capacity",
}

# ─────────────────────────────────────────────────────────────────────────────
def _ns_strip(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_xpdmxml(path: Path, source_key: str):
    """
    Parse one XPDMXML file.
    Returns:
      nodes : list[dict]  — one dict per entity element
      edges : list[dict]  — one dict per relationship
    """
    tree = ET.parse(path)
    root = tree.getroot()
    ns_uri = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""

    def tag(el):
        return _ns_strip(el.tag)

    def child_text(el, name):
        c = el.find(f"{{{ns_uri}}}{name}" if ns_uri else name)
        if c is not None and c.text and c.text.strip():
            return c.text.strip()
        return None

    def child_path_items(el, name):
        """Return list of PathItem texts inside a named child element."""
        c = el.find(f"{{{ns_uri}}}{name}" if ns_uri else name)
        if c is None:
            return []
        return [
            pi.text.strip()
            for pi in c
            if _ns_strip(pi.tag) == "PathItem" and pi.text and pi.text.strip()
        ]

    # local xml-id → node uri  (built while iterating, used for edge wiring)
    ref_map: dict[str, str] = {}

    nodes = []
    deferred_edges = []  # list of callables(ref_map) → edge dict or None

    for struct in root:
        if tag(struct) == "InfoHeader":
            continue
        for el in struct:
            el_type = tag(el)
            if el_type not in ENTITY_TYPES:
                continue

            xml_id = el.get("id", "")
            xpdm_id = child_text(el, "ID") or xml_id
            name    = child_text(el, "Name") or xpdm_id

            # URI scoped to source file so IDs don't collide across files
            uri = f"xpdm:{source_key}:{xml_id}"

            ref_map[xml_id] = uri

            # Harvest scalar properties
            props: dict = {
                "uri":          uri,
                "name":         name,
                "xpdm_id":      xpdm_id,
                "xml_ref_id":   xml_id,
                "element_type": el_type,
                "source_file":  path.name,
                "source_key":   source_key,
                "dataset_name": DATASET_NAME,
                "prefix":       "ds3dx",
                "ontology_name": DATASET_NAME,
            }

            for prop_name in SCALAR_PROPS:
                v = child_text(el, prop_name)
                if v is not None:
                    props[prop_name.lower()] = v

            # UniqueID external
            uid_el = el.find(f"{{{ns_uri}}}UniqueID" if ns_uri else "UniqueID")
            if uid_el is not None:
                ext = uid_el.get("External") or uid_el.get("XID")
                if ext:
                    props["unique_id"] = ext

            nodes.append({"label": el_type, "props": props})

            # ── Deferred edge definitions ─────────────────────────────────
            owned = child_text(el, "Owned")
            if owned:
                _xml_id = xml_id
                _owned  = owned
                deferred_edges.append(("OWNED_BY", uri, lambda rm, o=_owned, sk=source_key: rm.get(f"{o}", rm.get(f"{o}"))))

            instancing = child_text(el, "Instancing")
            if instancing:
                _inst = instancing
                deferred_edges.append(("INSTANCES", uri, lambda rm, i=_inst, sk=source_key: rm.get(i)))

            # EndToStartLink: PRECEDES edge from→to
            if el_type == "EndToStartLink":
                from_items = child_path_items(el, "FromInstanceRef")
                to_items   = child_path_items(el, "ToInstanceRef")
                for fi in from_items:
                    for ti in to_items:
                        _fi, _ti, _sk = fi, ti, source_key
                        deferred_edges.append(("PRECEDES_RAW", _fi, _ti))

            # SystemImplementLink: IMPLEMENTS_OP + IMPLEMENTS_TRF
            if el_type == "SystemImplementLink":
                op_items  = child_path_items(el, "OperationRef")
                trf_items = child_path_items(el, "TransformationInstanceRef")
                for oi in op_items:
                    deferred_edges.append(("IMPL_OP", uri, oi))
                for ti in trf_items:
                    deferred_edges.append(("IMPL_TRF", uri, ti))

    # Resolve deferred edges into (rel_type, src_uri, tgt_uri)
    edges = []
    for item in deferred_edges:
        if item[0] == "PRECEDES_RAW":
            _, fi, ti = item
            src = ref_map.get(fi)
            tgt = ref_map.get(ti)
            if src and tgt:
                edges.append({"rel": "PRECEDES", "src": src, "tgt": tgt})
        elif item[0] in ("IMPL_OP", "IMPL_TRF"):
            rel, link_uri, xml_ref = item
            tgt = ref_map.get(xml_ref)
            if tgt:
                r = "IMPLEMENTS_OPERATION" if rel == "IMPL_OP" else "IMPLEMENTS_TRANSFORMATION"
                edges.append({"rel": r, "src": link_uri, "tgt": tgt})
        else:
            rel, src_uri, tgt_fn = item
            tgt_uri = tgt_fn(ref_map) if callable(tgt_fn) else tgt_fn
            if tgt_uri:
                edges.append({"rel": rel, "src": src_uri, "tgt": tgt_uri})

    return nodes, edges


# ─────────────────────────────────────────────────────────────────────────────
def ensure_indexes(session):
    session.run("""
        CREATE INDEX InstanceNode_uri IF NOT EXISTS
        FOR (n:InstanceNode) ON (n.uri)
    """)
    session.run("""
        CREATE INDEX InstanceNode_xpdm_id IF NOT EXISTS
        FOR (n:InstanceNode) ON (n.xpdm_id)
    """)


def flush_nodes(session, all_nodes: list[dict]):
    """Batch-upsert all nodes grouped by element_type label."""
    from collections import defaultdict
    by_label: dict[str, list] = defaultdict(list)
    for n in all_nodes:
        by_label[n["label"]].append(n["props"])

    for label, rows in by_label.items():
        # Safety: label must be alphanumeric
        if not label.replace("_", "").isalnum():
            print(f"  [SKIP] unsafe label: {label}")
            continue
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:{label}:InstanceNode {{uri: row.uri}})
                SET n += row
                """,
                rows=batch,
            )
        print(f"  [{label}] {len(rows)} nodes upserted")


def flush_edges(session, edges: list[dict]):
    """Batch-upsert edges grouped by rel type."""
    from collections import defaultdict
    by_rel: dict[str, list] = defaultdict(list)
    for e in edges:
        by_rel[e["rel"]].append({"src": e["src"], "tgt": e["tgt"]})

    for rel, rows in by_rel.items():
        if not rel.replace("_", "").isalnum():
            continue
        batch_size = 500
        for i in range(0, len(rows), batch_size):
            batch = rows[i:i + batch_size]
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (a:InstanceNode {{uri: row.src}})
                MATCH (b:InstanceNode {{uri: row.tgt}})
                MERGE (a)-[:{rel}]->(b)
                """,
                rows=batch,
            )
        print(f"  [{rel}] {len(rows)} edges upserted")


def link_to_ontology(session):
    """
    For each InstanceNode, try to find a matching OntologyClass or OntologyRelationship
    in the ds3dx ontology by matching element_type to ontology name, then create
    INSTANCE_OF relationship.
    """
    result = session.run("""
        MATCH (i:InstanceNode)
        WITH i.element_type AS et, collect(i) AS nodes
        OPTIONAL MATCH (oc:OntologyNode {prefix: $prefix})
          WHERE toLower(oc.name) = toLower(et)
             OR toLower(oc.local_name) = toLower(et)
        RETURN et, oc.uri AS oc_uri, size(nodes) AS cnt
    """, prefix=ONTOLOGY_PREFIX)
    linked = 0
    for row in result:
        et   = row["et"]
        oc_uri = row["oc_uri"]
        cnt  = row["cnt"]
        if oc_uri:
            session.run("""
                MATCH (i:InstanceNode {element_type: $et})
                MATCH (oc:OntologyNode {uri: $oc_uri})
                MERGE (i)-[:INSTANCE_OF]->(oc)
            """, et=et, oc_uri=oc_uri)
            print(f"  INSTANCE_OF  {et} ({cnt} nodes) → {oc_uri}")
            linked += cnt
    print(f"  Total INSTANCE_OF links created: {linked}")


def clean_dataset(session):
    result = session.run("""
        MATCH (n:InstanceNode {dataset_name: $ds})
        DETACH DELETE n
        RETURN count(*) AS deleted
    """, ds=DATASET_NAME)
    rec = result.single()
    deleted = rec["deleted"] if rec else 0
    print(f"  Deleted {deleted} existing InstanceNode nodes for dataset '{DATASET_NAME}'")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true", help="Delete existing dataset nodes before loading")
    args = parser.parse_args()

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    all_nodes: list[dict] = []
    all_edges: list[dict] = []

    print("Parsing XPDMXML files ...")
    for source_key, path in FILES.items():
        print(f"  {path.name}")
        nodes, edges = parse_xpdmxml(path, source_key)
        print(f"    → {len(nodes)} entities, {len(edges)} relationships")
        all_nodes.extend(nodes)
        all_edges.extend(edges)

    print(f"\nTotal: {len(all_nodes)} nodes, {len(all_edges)} edges")

    with driver.session(database=NEO4J_DB) as session:
        print("\nEnsuring indexes ...")
        ensure_indexes(session)

        if args.clean:
            print("Cleaning existing dataset ...")
            clean_dataset(session)

        print("\nUploading nodes ...")
        flush_nodes(session, all_nodes)

        print("\nUploading edges ...")
        flush_edges(session, all_edges)

        print("\nLinking to 3DEXPERIENCE ontology ...")
        link_to_ontology(session)

    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
