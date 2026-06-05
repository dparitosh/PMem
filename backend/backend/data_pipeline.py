import csv
import os
import re
from pathlib import Path
from neo4j import GraphDatabase
 
URI = "bolt://localhost:7687"   # change if needed
USER = "neo4j"
PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
CSV_FILE = "spinner_datatype.csv"      # path relative to where you run the script
 

def sanitize_label(name: str) -> str:
    if not name:
        return "Unnamed"
    # keep letters & digits as label with underscores for others
    label = re.sub(r"[^A-Za-z0-9]", "_", name).strip("_")
    return label or "Unnamed"

def build_attr_empty_map(row, fieldnames):
    """
    For each column starting with 'Attributes', take the *cell value* as a property name
    and set it to empty string "".
    Example:
      Attributes 1 = 'Color'  -> {'Color': ""}
      Attributes 2 = 'Mil Spec' -> {'Mil_Spec': ""}
    """
    attr_map = {}
    for col in fieldnames:
        if col and col.lower().startswith("attributes"):
            raw = (row.get(col) or "").strip()
            if not raw:
                continue
            # normalize property key (optional)
            key = re.sub(r"\s+", "_", raw)  # spaces -> underscore
            key = key.replace("`", "")      # remove backticks to be safe
            attr_map[key] = ""              # <-- empty string marker
    return attr_map

def main():
    csv_path = Path(CSV_FILE)
    driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

    with driver.session() as session, csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # Clean BOM and trim header names
        reader.fieldnames = [h.replace("\ufeff", "").strip() for h in (reader.fieldnames or [])]

        for row in reader:
            name = (row.get("Name") or "").strip()
            parent_type = (row.get("Parent Type") or "").strip()
            description = (row.get("Description") or "").strip()

            label = sanitize_label(name)
            attr_empty_map = build_attr_empty_map(row, reader.fieldnames)

            cypher = f"""
            MERGE (n:`{label}` {{name: $name}})
            SET n.parentType  = $parent_type,
                n.description = $description
            SET n += $attr_empty_map
            """
            session.run(
                cypher,
                name=name,
                parent_type=parent_type,
                description=description,
                attr_empty_map=attr_empty_map,
            )

    driver.close()

if __name__ == "__main__":
    main()
