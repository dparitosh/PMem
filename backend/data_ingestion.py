from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import List
import pandas as pd
import io
import json
import re

try:
    from .core.graph import query_with_timeout
except ImportError:  # Support direct execution from the backend directory.
    from core.graph import query_with_timeout

router = APIRouter()

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_MAX_UPLOAD_BYTES = 25 * 1024 * 1024
_MAX_IMPORT_ROWS = 100_000


def _identifier(value: str, field_name: str) -> str:
    candidate = str(value or "").strip()
    if not _IDENTIFIER.fullmatch(candidate):
        raise ValueError(f"Invalid {field_name}: use letters, digits and underscores, starting with a letter or underscore")
    return candidate


def _property_list(values: List[str], field_name: str = "property") -> List[str]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"At least one {field_name} is required")
    return [_identifier(value, field_name) for value in values]

# Import functions from Neo4j_Import adapted for this app
def load_file_from_bytes(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Load file from bytes into DataFrame."""
    try:
        normalized_filename = str(filename or "").lower()
        if normalized_filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(file_bytes))
        elif normalized_filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            raise ValueError("Unsupported file type")
        df.columns = [str(c).strip() for c in df.columns]
        return df.replace(["", "NaN", "nan", "null", "NULL"], pd.NA).dropna(how='all')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

def create_node_import_query(label: str, properties: List[str], merge_keys: List[str]) -> str:
    """Generate Cypher query for node import."""
    label = _identifier(label, "node label")
    properties = _property_list(properties)
    merge_keys = [_identifier(key, "merge key") for key in (merge_keys or [])]
    if any(key not in properties for key in merge_keys):
        raise ValueError("Every merge key must also be included in properties")
    props_str = ", ".join([f"n.`{p}` = row.`{p}`" for p in properties])
    merge_str = ", ".join([f"`{k}`: row.`{k}`" for k in merge_keys])
    merge_clause = f"MERGE (n:`{label}` {{{merge_str}}})" if merge_keys else f"CREATE (n:`{label}`)"

    query = f"""
    UNWIND $rows AS row
    {merge_clause}
    SET {props_str}
    """
    return query

def create_relationship_import_query(rel_type: str, from_label: str, to_label: str,
                                   from_prop: str, to_prop: str) -> str:
    """Generate Cypher query for relationship import."""
    rel_type = _identifier(rel_type, "relationship type")
    from_label = _identifier(from_label, "source label")
    to_label = _identifier(to_label, "target label")
    from_prop = _identifier(from_prop, "source property")
    to_prop = _identifier(to_prop, "target property")
    query = f"""
    UNWIND $rows AS row
    MATCH (a:`{from_label}` {{{from_prop}: row.`{from_prop}`}})
    MATCH (b:`{to_label}` {{{to_prop}: row.`{to_prop}`}})
    MERGE (a)-[r:`{rel_type}`]->(b)
    """
    return query

def create_index_query(index_type: str, index_name: str, label: str, properties: List[str]) -> str:
    """Generate index creation query."""
    index_type = str(index_type or "").lower()
    index_name = _identifier(index_name, "index name")
    label = _identifier(label, "node label")
    properties = _property_list(properties)
    prop_list = ", ".join([f"n.`{p}`" for p in properties])
    if index_type == "range":
        return f"CREATE INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON ({prop_list})"
    elif index_type == "text":
        return f"CREATE TEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.`{properties[0]}`)"
    elif index_type == "fulltext":
        return f"CREATE FULLTEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON EACH [{prop_list}]"
    elif index_type == "vector":
        return f"CREATE VECTOR INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.`{properties[0]}`) OPTIONS {{indexConfig: {{`vector.dimensions`: 128, `vector.similarity_function`: 'cosine'}}}}"
    return ""

def create_constraint_query(constraint_type: str, constraint_name: str, label: str, properties: List[str]) -> str:
    """Generate constraint creation query."""
    constraint_type = str(constraint_type or "").lower()
    constraint_name = _identifier(constraint_name, "constraint name")
    label = _identifier(label, "node label")
    properties = _property_list(properties)
    prop_list = ", ".join([f"n.`{p}`" for p in properties])
    if constraint_type == "unique":
        return f"CREATE CONSTRAINT `{constraint_name}` IF NOT EXISTS FOR (n:`{label}`) REQUIRE ({prop_list}) IS UNIQUE"
    elif constraint_type == "exists":
        return f"CREATE CONSTRAINT `{constraint_name}` IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.`{properties[0]}` IS NOT NULL"
    elif constraint_type == "node_key":
        return f"CREATE CONSTRAINT `{constraint_name}` IF NOT EXISTS FOR (n:`{label}`) REQUIRE ({prop_list}) IS NODE KEY"
    return ""

@router.post("/ingest-data")
async def ingest_data(
    file: UploadFile = File(...),
    nodeDefinitions: str = Form(...),
    relationshipDefinitions: str = Form(...),
    indexes: str = Form(...),
    constraints: str = Form(...)
):
    """Import data from uploaded file into Neo4j."""
    try:
        # Parse configurations
        try:
            node_defs = json.loads(nodeDefinitions)
            rel_defs = json.loads(relationshipDefinitions)
            index_defs = json.loads(indexes)
            constraint_defs = json.loads(constraints)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON configuration: {exc.msg}") from exc
        if not all(isinstance(value, list) for value in (node_defs, rel_defs, index_defs, constraint_defs)):
            raise HTTPException(status_code=400, detail="All ingestion configuration fields must be JSON arrays")

        # Load file
        file_bytes = await file.read()
        if len(file_bytes) > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Upload exceeds the 25 MiB ingestion limit")
        df = load_file_from_bytes(file_bytes, file.filename)
        if len(df.index) > _MAX_IMPORT_ROWS:
            raise HTTPException(status_code=413, detail="Import exceeds the 100,000 row limit")

        # Convert to dict rows
        rows = df.where(pd.notnull(df), None).to_dict('records')

        queries = []

        # Create indexes and constraints first
        for idx_def in index_defs:
            query = create_index_query(
                idx_def['type'], idx_def['name'], idx_def['label'], idx_def['properties']
            )
            if query:
                queries.append(query)

        for const_def in constraint_defs:
            query = create_constraint_query(
                const_def['type'], const_def['name'], const_def['label'], const_def['properties']
            )
            if query:
                queries.append(query)

        # Create node import queries
        for node_def in node_defs:
            if node_def['label'] and node_def['properties']:
                query = create_node_import_query(
                    node_def['label'], node_def['properties'], node_def.get('mergeKeys', [])
                )
                queries.append(query)

        # Create relationship import queries
        for rel_def in rel_defs:
            if rel_def['type'] and rel_def['fromLabel'] and rel_def['toLabel']:
                query = create_relationship_import_query(
                    rel_def['type'], rel_def['fromLabel'], rel_def['toLabel'],
                    rel_def['fromProperty'], rel_def['toProperty']
                )
                queries.append(query)

        # Execute all queries
        results = []
        for query in queries:
            try:
                if "UNWIND" in query:
                    query_with_timeout(query, params={"rows": rows})
                else:
                    query_with_timeout(query)
                results.append({"status": "success"})
            except Exception as e:
                results.append({"status": "error", "error": str(e)})

        return {"message": "Data ingestion completed", "results": results}

    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
