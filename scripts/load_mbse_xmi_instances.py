# load_mbse_xmi_instances.py
# ---------------------------
# Loads a MagicDraw/Cameo SysML XMI file as individual instance nodes into Neo4j,
# mapping each element to its corresponding SysML ontology class (INSTANCE_OF).
#
# Source: C:/Users/895428/Depo/SPLM_Folder/XMI/SugarPlantMBSE.xmi
# Target: Neo4j spdm database
"""

Node labels: <UmlType>  +  MbseNode   (shared index label)
  e.g. Class:MbseNode, Package:MbseNode, Association:MbseNode ...

Relationships created:
  OWNED_BY           - child element → parent element (containment)
  MEMBER_END         - Association → Property (association end)
  CLIENT             - Abstraction/Dependency → client element
  SUPPLIER           - Abstraction/Dependency → supplier element
  INCLUDES           - UseCase → included UseCase (uml:Include.addition)
  TYPED_BY           - Property/Port → type Class/Block
  INSTANCE_OF        - MbseNode → SysML OntologyClass node

SysML stereotype enrichment (applied as node properties):
  sysml:Block, sysml:Requirement, sysml:functionalRequirement,
  sysml:performanceRequirement, sysml:usabilityRequirement,
  sysml:businessRequirement, sysml:Refine, sysml:Trace, sysml:Allocate,
  sysml:BindingConnector, sysml:ConstraintBlock, sysml:Verify, ...

Usage:
  python load_mbse_xmi_instances.py [--clean]
"""

import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from neo4j import GraphDatabase

# ── Config ─────────────────────────────────────────────────────────────────────
NEO4J_URI  = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "tcs12345"
NEO4J_DB   = "spdm"

SOURCE_FILE  = Path(r"C:/Users/895428/Depo/SPLM_Folder/XMI/SugarPlantMBSE.xmi")
DATASET_NAME = "SYSML MBSE Ontology"
PREFIX       = "sysml"
SYSML_ONT_PREFIX = "sysml"

# ── Namespaces ─────────────────────────────────────────────────────────────────
NS_XMI   = "http://www.omg.org/spec/XMI/20131001"
NS_UML   = "http://www.omg.org/spec/UML/20131001"
NS_SYSML = "http://www.omg.org/spec/SysML/20181001/SysML"

def _xmi(name): return f"{{{NS_XMI}}}{name}"
def _uml(name): return f"{{{NS_UML}}}{name}"
def _sysml(name): return f"{{{NS_SYSML}}}{name}"

# ── UML types we care about ────────────────────────────────────────────────────
INTERESTING_TYPES = {
    "uml:Model", "uml:Package",
    "uml:Class", "uml:Actor", "uml:UseCase",
    "uml:Association", "uml:Property", "uml:Port",
    "uml:Connector", "uml:ConnectorEnd",
    "uml:Abstraction", "uml:Dependency",
    "uml:Include", "uml:Constraint", "uml:Comment",
    "uml:Diagram",
}

# UML type → short label safe for Neo4j
def uml_label(xmi_type: str) -> str:
    # "uml:Class" → "UmlClass", "uml:UseCase" → "UmlUseCase"
    local = xmi_type.split(":")[-1] if ":" in xmi_type else xmi_type
    return local  # Neo4j labels are case-sensitive; keep as-is

# ── SysML stereotype → SysML ontology class name mapping ──────────────────────
# Keys are the local name of the sysml: element; values are OntologyClass.name
SYSML_STEREOTYPE_TO_ONTO = {
    "Block":                    "Blocks",
    "ConstraintBlock":          "ConstraintBlocks",
    "Requirement":              "Requirements",
    "functionalRequirement":    "Requirements",
    "performanceRequirement":   "Requirements",
    "usabilityRequirement":     "Requirements",
    "businessRequirement":      "Requirements",
    "moe":                      "Requirements",
    "objectiveFunction":        "Requirements",
    "Refine":                   "ModelElements",
    "Trace":                    "Allocations",
    "Allocate":                 "Allocations",
    "Verify":                   "Allocations",
    "BindingConnector":         "ConstraintBlocks",
    "NestedConnectorEnd":       "ConstraintBlocks",
    "System":                   "Blocks",
    "External":                 "Blocks",
    "Subsystem":                "Blocks",
    "System_context":           "Blocks",
    "ElementGroup":             "ModelElements",
}

# Fallback: xmi:type → SysML ontology class name
XMITYPE_TO_ONTO = {
    "uml:Package":      "ModelElements",
    "uml:Model":        "ModelElements",
    "uml:Class":        "ModelElements",      # overridden by stereotype
    "uml:UseCase":      "ModelElements",
    "uml:Actor":        "ModelElements",
    "uml:Association":  "ModelElements",
    "uml:Abstraction":  "ModelElements",
    "uml:Dependency":   "ModelElements",
    "uml:Port":         "Ports&amp;Flows",    # match encoded name in ontology
    "uml:Connector":    "ConstraintBlocks",
    "uml:Property":     "ModelElements",
    "uml:Constraint":   "ModelElements",
}


# ─────────────────────────────────────────────────────────────────────────────
def parse_xmi(path: Path):
    """
    Walk the XMI tree collecting:
      - nodes  : {xmi_id → {props dict, label, sysml_stereotype}}
      - edges  : list of {rel, src_id, tgt_id}
      - parent : {xmi_id → parent_xmi_id}
    """
    tree = ET.parse(path)
    root = tree.getroot()

    id_attr   = _xmi("id")
    type_attr = _xmi("type")
    idref_attr = _xmi("idref")

    nodes: dict[str, dict] = {}   # xmi_id → node dict
    edges: list[dict] = []
    parent_map: dict[str, str] = {}   # child_id → parent_id

    # ── Pass 1: collect sysml stereotype annotations ───────────────────────
    # key: xmi_id of the base element → list of stereotype names + extra props
    stereotype_map: dict[str, list[dict]] = defaultdict(list)

    for el in root.iter():
        ns = el.tag.split("}")[0].lstrip("{") if "}" in el.tag else ""
        if "SysML" not in ns:
            continue
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        st_id = el.get(id_attr, "")
        # Find which base element this stereotype applies to
        for k, v in el.attrib.items():
            kl = k.split("}")[-1] if "}" in k else k
            if kl.startswith("base_") and v:
                stereotype_map[v].append({
                    "stereotype":      local,
                    "stereotype_id":   st_id,
                    "base_attr":       kl,
                    "Text":            el.get("Text"),
                    "req_id":          el.get("Id"),
                })

    # ── Pass 2: walk the tree recursively, collecting nodes ────────────────
    def walk(el, parent_xmi_id=None):
        xmi_id   = el.get(id_attr)
        xmi_type = el.get(type_attr)

        if xmi_id and xmi_type in INTERESTING_TYPES:
            label = uml_label(xmi_type)
            name  = el.get("name", "")

            props = {
                "uri":          f"mbse:{xmi_id}",
                "xmi_id":       xmi_id,
                "xmi_type":     xmi_type,
                "name":         name or xmi_id,
                "label_hint":   label,
                "dataset_name": DATASET_NAME,
                "prefix":       PREFIX,
                "ontology_name": DATASET_NAME,
                "source_file":  path.name,
                "visibility":   el.get("visibility", ""),
            }

            # Merge stereotype data
            stereotypes_applied = []
            for st in stereotype_map.get(xmi_id, []):
                stereotypes_applied.append(st["stereotype"])
                if st.get("Text"):
                    props["requirement_text"] = st["Text"]
                if st.get("req_id"):
                    props["requirement_id"] = st["req_id"]
            if stereotypes_applied:
                props["sysml_stereotype"] = "|".join(stereotypes_applied)
                props["primary_stereotype"] = stereotypes_applied[0]

            # Determine SysML ontology class
            onto_class = None
            for st in stereotypes_applied:
                onto_class = SYSML_STEREOTYPE_TO_ONTO.get(st)
                if onto_class:
                    break
            if not onto_class:
                onto_class = XMITYPE_TO_ONTO.get(xmi_type, "ModelElements")
            props["onto_class_name"] = onto_class

            nodes[xmi_id] = {"label": label, "props": props}

            if parent_xmi_id:
                parent_map[xmi_id] = parent_xmi_id

            # Child element edges
            for child in el:
                child_id   = child.get(id_attr)
                child_type = child.get(type_attr)
                child_tag  = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                child_idref = child.get(idref_attr)

                # Inline typed children
                if child_id and child_type in INTERESTING_TYPES:
                    walk(child, xmi_id)

                # Association member ends (idref)
                if child_tag in ("memberEnd", "navigableOwnedEnd") and child_idref:
                    edges.append({"rel": "MEMBER_END", "src": xmi_id, "tgt": child_idref})

                # Abstraction client / supplier
                if child_tag == "client" and child_idref:
                    edges.append({"rel": "CLIENT", "src": xmi_id, "tgt": child_idref})
                if child_tag == "supplier" and child_idref:
                    edges.append({"rel": "SUPPLIER", "src": xmi_id, "tgt": child_idref})

                # UseCase include → addition
                if child_tag == "include" and child_type == "uml:Include":
                    addition = child.get("addition")
                    if addition:
                        edges.append({"rel": "INCLUDES", "src": xmi_id, "tgt": addition})

                # Property typed by a class
                if child_tag in ("ownedAttribute", "ownedEnd") and child_type == "uml:Property":
                    prop_id = child.get(id_attr)
                    if prop_id:
                        walk(child, xmi_id)
                        prop_type = child.get("type")
                        if prop_type:
                            edges.append({"rel": "TYPED_BY", "src": prop_id, "tgt": prop_type})
                        assoc = child.get("association")
                        if assoc:
                            edges.append({"rel": "PART_OF_ASSOCIATION", "src": prop_id, "tgt": assoc})

                # Port
                if child_tag == "ownedPort" and child_type == "uml:Port":
                    walk(child, xmi_id)
                    port_id = child.get(id_attr)
                    port_type = child.get("type")
                    if port_id and port_type:
                        edges.append({"rel": "TYPED_BY", "src": port_id, "tgt": port_type})

                # Connector ends
                if child_tag == "end" and child_type == "uml:ConnectorEnd":
                    role = child.get("role")
                    if role:
                        edges.append({"rel": "CONNECTS_TO", "src": xmi_id, "tgt": role})

        else:
            # Still walk children even if this el itself is not captured
            for child in el:
                walk(child, parent_xmi_id)

    walk(root)

    # OWNED_BY edges from parent_map
    for child_id, parent_id in parent_map.items():
        edges.append({"rel": "OWNED_BY", "src": f"mbse:{child_id}", "tgt": f"mbse:{parent_id}"})

    # Convert src/tgt xmi_ids to URIs where target is a known node
    resolved_edges = []
    for e in edges:
        src = e["src"]
        tgt = e["tgt"]
        # src may already be a uri (OWNED_BY) or raw xmi_id
        src_uri = src if src.startswith("mbse:") else f"mbse:{src}"
        tgt_uri = tgt if tgt.startswith("mbse:") else f"mbse:{tgt}"
        # Only include if both endpoints are in nodes
        src_id = src_uri.replace("mbse:", "")
        tgt_id = tgt_uri.replace("mbse:", "")
        if src_id in nodes and tgt_id in nodes:
            resolved_edges.append({
                "rel": e["rel"],
                "src": src_uri,
                "tgt": tgt_uri,
            })

    # Finalize node URIs
    final_nodes = []
    for xmi_id, n in nodes.items():
        n["props"]["uri"] = f"mbse:{xmi_id}"
        final_nodes.append(n)

    return final_nodes, resolved_edges


# ─────────────────────────────────────────────────────────────────────────────
def ensure_indexes(session):
    session.run("CREATE INDEX MbseNode_uri IF NOT EXISTS FOR (n:MbseNode) ON (n.uri)")
    session.run("CREATE INDEX MbseNode_xmi_id IF NOT EXISTS FOR (n:MbseNode) ON (n.xmi_id)")
    session.run("CREATE INDEX MbseNode_prefix IF NOT EXISTS FOR (n:MbseNode) ON (n.prefix)")


def flush_nodes(session, nodes: list[dict]):
    by_label = defaultdict(list)
    for n in nodes:
        by_label[n["label"]].append(n["props"])

    for label, rows in by_label.items():
        if not label.replace("_", "").isalnum():
            print(f"  [SKIP] unsafe label: {label}")
            continue
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i+BATCH]
            session.run(
                f"""
                UNWIND $rows AS row
                MERGE (n:{label}:MbseNode {{uri: row.uri}})
                SET n += row
                """,
                rows=batch,
            )
        print(f"  [{label}] {len(rows)} nodes")


def flush_edges(session, edges: list[dict]):
    by_rel = defaultdict(list)
    for e in edges:
        by_rel[e["rel"]].append({"src": e["src"], "tgt": e["tgt"]})

    for rel, rows in by_rel.items():
        if not rel.replace("_", "").isalnum():
            continue
        BATCH = 500
        for i in range(0, len(rows), BATCH):
            batch = rows[i:i+BATCH]
            session.run(
                f"""
                UNWIND $rows AS row
                MATCH (a:MbseNode {{uri: row.src}})
                MATCH (b:MbseNode {{uri: row.tgt}})
                MERGE (a)-[:{rel}]->(b)
                """,
                rows=batch,
            )
        print(f"  [{rel}] {len(rows)} edges")


def link_to_sysml_ontology(session):
    """
    For each MbseNode, match its onto_class_name to a SysML OntologyClass.name
    and create an INSTANCE_OF relationship.
    """
    # Get all onto_class_names present
    result = session.run(
        "MATCH (n:MbseNode) WHERE n.onto_class_name IS NOT NULL "
        "RETURN n.onto_class_name AS cn, count(*) AS cnt"
    )
    onto_names = {row["cn"]: row["cnt"] for row in result}
    print(f"\n  Onto class names requested: {list(onto_names.keys())}")

    linked_total = 0
    for onto_name, cnt in onto_names.items():
        # Match by exact name or decoded name (handle &amp;)
        decoded = onto_name.replace("&amp;", "&")
        result2 = session.run(
            """
            MATCH (oc) WHERE oc.prefix = $prefix
              AND (oc.name = $name OR oc.name = $decoded)
            RETURN oc.uri AS uri, oc.name AS name, id(oc) AS nid
            LIMIT 1
            """,
            prefix=SYSML_ONT_PREFIX,
            name=onto_name,
            decoded=decoded,
        )
        row = result2.single()
        if row:
            onto_node_id = row["nid"]
            r = session.run(
                """
                MATCH (n:MbseNode {onto_class_name: $cn})
                MATCH (oc) WHERE id(oc) = $nid
                MERGE (n)-[:INSTANCE_OF]->(oc)
                RETURN count(*) AS linked
                """,
                cn=onto_name,
                nid=onto_node_id,
            )
            linked = r.single()["linked"]
            print(f"  INSTANCE_OF → '{row['name']}' : {linked} nodes linked")
            linked_total += linked
        else:
            print(f"  [NO MATCH] onto_class_name='{onto_name}' not found in SysML ontology")

    print(f"\n  Total INSTANCE_OF links: {linked_total}")


def clean_dataset(session):
    r = session.run(
        "MATCH (n:MbseNode {dataset_name: $ds}) DETACH DELETE n RETURN count(*) AS d",
        ds=DATASET_NAME,
    )
    print(f"  Deleted {r.single()['d']} existing MbseNode nodes")


# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    print(f"Parsing {SOURCE_FILE.name} ...")
    nodes, edges = parse_xmi(SOURCE_FILE)
    print(f"  → {len(nodes)} elements, {len(edges)} relationships")

    # Summary
    from collections import Counter
    type_counts = Counter(n["label"] for n in nodes)
    for t, c in type_counts.most_common():
        print(f"    {c:4d}  {t}")
    rel_counts = Counter(e["rel"] for e in edges)
    print("  Relationships:")
    for r, c in rel_counts.most_common():
        print(f"    {c:4d}  {r}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    with driver.session(database=NEO4J_DB) as session:
        print("\nEnsuring indexes ...")
        ensure_indexes(session)

        if args.clean:
            print("Cleaning existing dataset ...")
            clean_dataset(session)

        print("\nUploading nodes ...")
        flush_nodes(session, nodes)

        print("\nUploading edges ...")
        flush_edges(session, edges)

        print("\nLinking to SysML ontology ...")
        link_to_sysml_ontology(session)

    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
