"""
Ontology Creation Pipeline Step
Extracts ontology schema (classes, properties) from PLMXML and creates OntologyClass/OntologyProperty nodes in Neo4j.
"""

from pathlib import Path
from neo4j import GraphDatabase
try:
    from backend.core.db_config import Neo4jConnection
except Exception:
    # fallback for direct script execution
    from core.db_config import Neo4jConnection

try:
    from backend.Services.plmxml_parser import parse_plmxml_file
except ModuleNotFoundError:
    # Fallback for direct script execution
    import sys
    from pathlib import Path as _Path
    sys.path.append(str(_Path(__file__).parent))
    from plmxml_parser import parse_plmxml_file

# Adjust these as needed
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "tcs12345"
NEO4J_DATABASE = "ontology"


def extract_classes_and_properties(plmxml_doc):
    """
    Returns a set of (class_name, set(properties)) from all parts, requirements, etc.
    """
    class_props = {}
    # Helper to add properties for a class
    def add_props(class_name, props):
        if not class_name:
            return
        class_props.setdefault(class_name, set()).update(props)

    # Parts
    for part in plmxml_doc.parts.values():
        add_props(part.part_type or "Part", part.properties.keys())
    # Product Views
    for pv in plmxml_doc.product_views.values():
        add_props("ProductView", pv.properties.keys())
    # Product Instances
    for pi in plmxml_doc.product_instances:
        add_props("ProductInstance", pi.properties.keys())
    # Processes
    for proc in plmxml_doc.processes.values():
        add_props(proc.process_type or "Process", proc.properties.keys())
    # Process Views
    for pv in plmxml_doc.process_views.values():
        add_props("ProcessView", pv.properties.keys())
    # Process Instances
    for pi in plmxml_doc.process_instances:
        add_props("ProcessInstance", pi.properties.keys())
    # Change Notices
    for cn in plmxml_doc.change_notices.values():
        add_props("ChangeNotice", cn.properties.keys())
    # Revisions
    for rev in plmxml_doc.revisions.values():
        add_props("Revision", rev.properties.keys())
    # Transforms
    for tf in plmxml_doc.transforms.values():
        add_props("Transform", ["matrix"])
    # User Data
    for ud in plmxml_doc.user_data.values():
        add_props("UserData", list(ud.values.keys()))
    # Documents
    for doc in plmxml_doc.documents.values():
        add_props("DocumentItem", doc.properties.keys())
    # External Files
    for ef in plmxml_doc.external_files.values():
        add_props("ExternalFile", ef.properties.keys())
    # Requirements
    for req in plmxml_doc.requirements.values():
        add_props("Requirement", req.properties.keys())
    # General Relations
    for rel in plmxml_doc.general_relations:
        add_props("GeneralRelation", rel.properties.keys())
    # Forms
    for form in plmxml_doc.forms.values():
        add_props("Form", list(form.attributes.keys()) + list(form.properties.keys()))
    # Relationships
    for rel in plmxml_doc.relationships:
        add_props("Relationship", rel.properties.keys())
    return class_props


def create_ontology_in_neo4j(class_props):
    # Use centralized connection manager to ensure sessions/drivers are handled
    with Neo4jConnection(database=NEO4J_DATABASE) as session:
        for class_name, props in class_props.items():
            session.run("MERGE (c:OntologyClass {name: $name})", {"name": class_name})
            for prop in props:
                session.run(
                    "MERGE (p:OntologyProperty {name: $prop})-[:PROPERTY_OF]->(c)",
                    {"prop": prop, "name": class_name},
                )


def step_0_generate_ontology(plmxml_path):
    doc = parse_plmxml_file(Path(plmxml_path))
    class_props = extract_classes_and_properties(doc)
    create_ontology_in_neo4j(class_props)
    print(f"Ontology created for {len(class_props)} classes.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python step_0_generate_ontology.py <plmxml_file>")
        exit(1)
    step_0_generate_ontology(sys.argv[1])
