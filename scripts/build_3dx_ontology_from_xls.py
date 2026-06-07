"""
Build 3DEXPERIENCE ontology in Neo4j from SPLM Schema XLS (TSV) files.

Source: C:\\Users\\895428\\Depo\\SPLM_Folder\\Schema - Shared
Output: Neo4j spdm database, prefix=ds3dx, ontology='3DEXPERIENCE'

Maps:
  SpinnerTypeData         -> OntologyClass nodes   (Business Object Types + parent hierarchy)
  SpinnerRelationshipData -> OntologyRelationship   (Relationship types linking BOTs)
  SpinnerAttributeData    -> OntologyProperty       (Attributes, scoped per type)
  SpinnerInterfaceData    -> OntologyInterface      (Interfaces with parent hierarchy)
  SpinnerPolicyData       -> OntologyPolicy         (Lifecycle policies)
  rel-b2b_*              -> CONNECTS edges          (from.type -> to.type via Rel Name)
"""

import os
import csv
import io
import sys
from pathlib import Path
from collections import defaultdict
from neo4j import GraphDatabase

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.core.db_config import get_config

# ── Config ───────────────────────────────────────────────────────────────────
_NEO4J_CONFIG = get_config()
SCHEMA_BASE   = os.getenv("SPLM_SCHEMA_BASE", r"C:\Users\895428\Depo\SPLM_Folder\Schema - Shared")
NEO4J_URI     = _NEO4J_CONFIG.uri
NEO4J_USER    = _NEO4J_CONFIG.username
NEO4J_PASS    = _NEO4J_CONFIG.password
NEO4J_DB      = _NEO4J_CONFIG.database
ONTOLOGY_NAME = "3DEXPERIENCE"
PREFIX        = "ds3dx"
NAMESPACE     = "http://3dexperience.dassault-systemes.com/ds3dx/"
BATCH         = 500

# ── TSV reader ────────────────────────────────────────────────────────────────
def read_tsv(path):
    """Read a TSV-formatted .xls file, return list of dicts."""
    rows = []
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                rows.append({k.strip(): (v.strip() if v else "") for k, v in row.items() if k})
    except Exception as e:
        print(f"  [WARN] Could not read {os.path.basename(path)}: {e}")
    return rows


def glob_tsv(subfolder, pattern="*.xls"):
    import glob
    return glob.glob(os.path.join(SCHEMA_BASE, subfolder, pattern))


# ── Neo4j helpers ─────────────────────────────────────────────────────────────
def base_props(name, reg_name="", description=""):
    return {
        "name":           name,
        "registry_name":  reg_name or name,
        "description":    description[:500] if description else "",
        "prefix":         PREFIX,
        "ontology_prefix": PREFIX,
        "ontology_name":  ONTOLOGY_NAME,
        "uri":            NAMESPACE + (reg_name or name).replace(" ", "_"),
    }


def flush_nodes(session, label, rows):
    """UNWIND batch MERGE by uri, set all props. Also adds OntologyNode label for index coverage."""
    if not rows:
        return
    session.run(
        f"UNWIND $rows AS row MERGE (n:{label}:OntologyNode {{uri: row.uri}}) SET n += row",
        rows=rows,
    )


def flush_rels(session, rows):
    """rows: [{src_uri, tgt_uri, rel_type, props}] — uses OntologyNode index for fast MATCH."""
    if not rows:
        return
    from collections import defaultdict
    by_type = defaultdict(list)
    for r in rows:
        rt = r["rel_type"].replace(" ", "_").replace("-", "_")
        by_type[rt].append({"src": r["src_uri"], "tgt": r["tgt_uri"], "props": r.get("props", {})})
    for rt, items in by_type.items():
        try:
            session.run(
                f"UNWIND $rows AS row "
                f"MATCH (a:OntologyNode {{uri: row.src}}), (b:OntologyNode {{uri: row.tgt}}) "
                f"MERGE (a)-[r:`{rt}`]->(b) SET r += row.props",
                rows=items,
            )
        except Exception as e:
            print(f"  [WARN] rel {rt}: {e}")


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_types(session):
    """SpinnerTypeData: Business Object Types → OntologyClass."""
    files = glob_tsv("Business", "SpinnerTypeData_ALL.xls")
    if not files:
        print("  [SKIP] SpinnerTypeData not found")
        return {}

    type_uri = {}  # name -> uri
    nodes = []
    rels  = []

    for path in files:
        for row in read_tsv(path):
            name    = row.get("Name", "").strip()
            reg     = row.get("Registry Name", "") or name
            parent  = row.get("Parent Type", "").strip()
            desc    = row.get("Description", "")
            abstract= row.get("Abstract", "").upper() == "TRUE"
            hidden  = row.get("Hidden", "").upper() == "TRUE"

            if not name:
                continue
            props = base_props(name, reg, desc)
            props["abstract"] = abstract
            props["hidden"]   = hidden
            props["node_type"] = "BusinessObjectType"
            type_uri[name] = props["uri"]
            nodes.append(props)

    if nodes:
        flush_nodes(session, "OntologyClass", nodes)
        print(f"  Types written: {len(nodes)}")

    # Parent hierarchy — second pass
    for path in files:
        for row in read_tsv(path):
            name   = row.get("Name", "").strip()
            parent = row.get("Parent Type", "").strip()
            if name and parent and name in type_uri and parent in type_uri:
                rels.append({"src_uri": type_uri[name], "tgt_uri": type_uri[parent],
                             "rel_type": "subClassOf", "props": {}})

    if rels:
        flush_rels(session, rels)
        print(f"  Type inheritance edges: {len(rels)}")

    return type_uri


def load_relationships(session, type_uri):
    """SpinnerRelationshipData + rel-b2b files → OntologyRelationship nodes + CONNECTS edges."""
    # 1. Relationship definitions → OntologyRelationship nodes
    rel_uri = {}
    nodes   = []
    files   = glob_tsv("Business", "SpinnerRelationshipData_ALL.xls")
    for path in files:
        for row in read_tsv(path):
            name = row.get("Name", "").strip()
            reg  = row.get("Registry Name", "") or name
            desc = row.get("Description", "")
            froms= row.get("From Types (use \"|\" delim)", "") or row.get("From Types", "")
            tos  = row.get("To Types (use \"|\" delim)", "") or row.get("To Types", "")
            if not name:
                continue
            props = base_props(name, reg, desc)
            props["from_types"] = froms
            props["to_types"]   = tos
            props["node_type"]  = "Relationship"
            rel_uri[name] = props["uri"]
            nodes.append(props)

    if nodes:
        flush_nodes(session, "OntologyRelationship", nodes)
        print(f"  Relationship defs written: {len(nodes)}")

    # 2. rel-b2b instance files → CONNECTS edges between OntologyClass nodes
    import glob
    b2b_files = glob.glob(os.path.join(SCHEMA_BASE, "Relationships", "*.xls"))
    rels = []
    for path in b2b_files:
        for row in read_tsv(path):
            rel_name   = row.get("Rel Name", "").strip()
            from_type  = row.get("from.type", "").strip()
            to_type    = row.get("to.type", "").strip()
            if not (rel_name and from_type and to_type):
                continue
            src = type_uri.get(from_type)
            tgt = type_uri.get(to_type)
            if src and tgt:
                rels.append({"src_uri": src, "tgt_uri": tgt,
                             "rel_type": rel_name,
                             "props": {"rel_name": rel_name}})

    if rels:
        flush_rels(session, rels)
        print(f"  Type-to-type connection edges: {len(rels)}")

    return rel_uri


def load_attributes(session, type_uri):
    """SpinnerAttributeData: Attributes → OntologyProperty, linked to their types."""
    files = glob_tsv("Business", "SpinnerAttributeData_ALL.xls")
    nodes = []
    rels  = []
    attr_uri = {}

    for path in files:
        for row in read_tsv(path):
            name  = row.get("Attribute Name", "").strip()
            reg   = row.get("Registry Name", "") or name
            scope = row.get("Scope", "")      # pipe-delimited type names
            dtype = row.get("Type", "string")
            desc  = row.get("Description", "")
            if not name:
                continue
            props = base_props(name, reg, desc)
            props["data_type"]  = dtype
            props["scope"]      = scope
            props["node_type"]  = "Attribute"
            attr_uri[name] = props["uri"]
            nodes.append(props)

            # DOMAIN edges: each scope type → this attribute
            for t in scope.split("|"):
                t = t.strip()
                if t and t in type_uri:
                    rels.append({"src_uri": type_uri[t], "tgt_uri": props["uri"],
                                 "rel_type": "hasAttribute", "props": {}})

    batch_size = BATCH
    for i in range(0, len(nodes), batch_size):
        flush_nodes(session, "OntologyProperty", nodes[i:i+batch_size])
    print(f"  Attributes written: {len(nodes)}")

    if rels:
        for i in range(0, len(rels), batch_size):
            flush_rels(session, rels[i:i+batch_size])
        print(f"  Attribute domain edges: {len(rels)}")

    return attr_uri


def load_interfaces(session):
    """SpinnerInterfaceData: Interfaces → OntologyInterface with parent links."""
    files = glob_tsv("Business", "SpinnerInterfaceData_ALL.xls")
    iface_uri = {}
    nodes = []
    rels  = []

    for path in files:
        for row in read_tsv(path):
            name    = row.get("Name", "").strip()
            reg     = row.get("Registry Name", "") or name
            parents = row.get("Parents (use \"|\" delim)", "") or row.get("Parents", "")
            desc    = row.get("Description", "")
            if not name:
                continue
            props = base_props(name, reg, desc)
            props["node_type"] = "Interface"
            iface_uri[name]    = props["uri"]
            nodes.append(props)

    if nodes:
        flush_nodes(session, "OntologyInterface", nodes)
        print(f"  Interfaces written: {len(nodes)}")

    # Parent hierarchy
    for path in files:
        for row in read_tsv(path):
            name    = row.get("Name", "").strip()
            parents = row.get("Parents (use \"|\" delim)", "") or row.get("Parents", "")
            if name in iface_uri:
                for p in parents.split("|"):
                    p = p.strip()
                    if p and p in iface_uri:
                        rels.append({"src_uri": iface_uri[name], "tgt_uri": iface_uri[p],
                                     "rel_type": "subClassOf", "props": {}})

    if rels:
        flush_rels(session, rels)
        print(f"  Interface inheritance edges: {len(rels)}")

    return iface_uri


def load_policies(session, type_uri):
    """SpinnerPolicyData: Policies → OntologyPolicy nodes + GOVERNED_BY edges."""
    files = glob_tsv("Business", "SpinnerPolicyData_ALL.xls")
    pol_uri = {}
    nodes   = []
    rels    = []

    for path in files:
        for row in read_tsv(path):
            name  = row.get("Name", "").strip()
            reg   = row.get("Registry Name", "") or name
            desc  = row.get("Description", "")
            types = row.get("Types (use \"|\" delim)", "") or row.get("Types", "")
            if not name:
                continue
            props = base_props(name, reg, desc)
            props["governed_types"] = types
            props["node_type"]      = "Policy"
            pol_uri[name]  = props["uri"]
            nodes.append(props)

            for t in types.split("|"):
                t = t.strip()
                if t and t in type_uri:
                    rels.append({"src_uri": type_uri[t], "tgt_uri": props["uri"],
                                 "rel_type": "GOVERNED_BY", "props": {}})

    if nodes:
        flush_nodes(session, "OntologyPolicy", nodes)
        print(f"  Policies written: {len(nodes)}")
    if rels:
        flush_rels(session, rels)
        print(f"  Policy governance edges: {len(rels)}")

    return pol_uri


# ── Main ──────────────────────────────────────────────────────────────────────
def ensure_indexes(session):
    """Create uri indexes on all ontology labels for fast MATCH lookups."""
    labels = ["OntologyClass", "OntologyRelationship", "OntologyProperty",
              "OntologyInterface", "OntologyPolicy"]
    for lbl in labels:
        try:
            session.run(f"CREATE INDEX {lbl}_uri IF NOT EXISTS FOR (n:{lbl}) ON (n.uri)")
        except Exception:
            pass  # older Neo4j without IF NOT EXISTS
    # Generic index covering all nodes via a shared label
    try:
        session.run("CREATE INDEX OntologyNode_uri IF NOT EXISTS FOR (n:OntologyNode) ON (n.uri)")
    except Exception:
        pass
    print("  Indexes ensured.")


def main():
    print(f"Connecting to Neo4j ({NEO4J_URI}, db={NEO4J_DB})...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    print(f"\nBuilding '{ONTOLOGY_NAME}' ontology (prefix={PREFIX}) from:\n  {SCHEMA_BASE}\n")

    with driver.session(database=NEO4J_DB) as session:
        print("── Creating indexes ───────────────────────────────────────────")
        ensure_indexes(session)

        print("── Types (OntologyClass) ──────────────────────────────────────")
        type_uri = load_types(session)

        print("\n── Relationships (OntologyRelationship) ──────────────────────")
        rel_uri = load_relationships(session, type_uri)

        print("\n── Attributes (OntologyProperty) ─────────────────────────────")
        load_attributes(session, type_uri)

        print("\n── Interfaces (OntologyInterface) ────────────────────────────")
        load_interfaces(session)

        print("\n── Policies (OntologyPolicy) ─────────────────────────────────")
        load_policies(session, type_uri)

        # Summary
        print("\n══ Neo4j spdm — Final Summary ════════════════════════════════")
        for label in ["OntologyClass", "OntologyRelationship", "OntologyProperty",
                      "OntologyInterface", "OntologyPolicy"]:
            c = session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]
            print(f"  {label:25} : {c}")
        total = session.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edges = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        print(f"  {'TOTAL nodes':25} : {total}")
        print(f"  {'TOTAL edges':25} : {edges}")

    driver.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
