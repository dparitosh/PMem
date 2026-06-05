# ========== Format Detection & Parsers ==========


# ========== Format Detection & Parsers ==========

# (Moved below FileType definition)

"""
Unified Data Import Service
Consolidates CSV, Excel, PLMXML, STEP, and XML imports with auto-detection,
validation, transformation, and Neo4j ingestion capabilities.
"""

import os
import json
import uuid
import logging
import csv
import io
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

from enum import Enum
from .data_import_service import DataImportService
from ..core.graph import graph

logger = logging.getLogger(__name__)

class FileType(Enum):
    CSV = 'csv'
    EXCEL = 'excel'
    PLMXML = 'plmxml'
    STEP = 'step'
    EXPRESS = 'express'
    XML = 'xml'
    XMI = 'xmi'


class ImportStatus(Enum):
    """Status of import task"""
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class ImportStage(Enum):
    """Stages of import pipeline"""
    UPLOAD = 'upload'
    DETECT = 'detect'
    PARSE = 'parse'
    VALIDATE = 'validate'
    TRANSFORM = 'transform'
    PREVIEW = 'preview'
    LOAD = 'load'
    INGEST = 'load'
    VERIFY = 'verify'


class FileFormatDetector:
    """Detects file format and provides format utilities"""
    
    # Mapping of file extensions to FileType
    _EXTENSION_MAP = {
        '.csv': FileType.CSV,
        '.xlsx': FileType.EXCEL,
        '.xls': FileType.EXCEL,
        '.plmxml': FileType.PLMXML,
        '.step': FileType.STEP,
        '.stp': FileType.STEP,
        '.stpx': FileType.STEP,
        '.exp': FileType.EXPRESS,
        '.xml': FileType.XML,
        '.xmi': FileType.XMI,
        '.mdxml': FileType.XMI,
    }
    
    @classmethod
    def detect(cls, filename: str) -> Optional[FileType]:
        """Detect file type from filename"""
        if not filename:
            return None
        
        # Get file extension
        _, ext = os.path.splitext(filename.lower())
        return cls._EXTENSION_MAP.get(ext)
    
    @classmethod
    def get_supported_formats(cls) -> list:
        """Get list of supported file formats"""
        return [f for f in cls._EXTENSION_MAP.keys() if f]


class FileParser:
    """Parse uploaded files into preview rows plus format metadata."""

    @staticmethod
    def parse(file_content: bytes, file_type: FileType) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if file_type == FileType.CSV:
            return FileParser.parse_csv(file_content)
        if file_type == FileType.EXCEL:
            return FileParser.parse_excel(file_content)
        if file_type == FileType.EXPRESS:
            return DataTransformer.parse_express(file_content)
        if file_type == FileType.XMI:
            return DataTransformer.parse_xmi(file_content)
        if file_type in {FileType.XML, FileType.PLMXML}:
            return FileParser.parse_xml(file_content, file_type.value)
        if file_type == FileType.STEP:
            return FileParser.parse_step(file_content)
        raise ValueError(f"Unsupported file type: {file_type.value}")

    @staticmethod
    def parse_csv(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        text = file_content.decode("utf-8-sig", errors="replace")
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows = [FileParser._clean_row(row) for row in reader if any((v or "").strip() for v in row.values())]
        return rows, {
            "row_count": len(rows),
            "column_count": len(reader.fieldnames or []),
            "columns": reader.fieldnames or [],
            "format": "csv",
        }

    @staticmethod
    def parse_excel(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        try:
            import openpyxl
        except ImportError as exc:
            raise ValueError("Excel import requires openpyxl to be installed") from exc

        wb = openpyxl.load_workbook(io.BytesIO(file_content), read_only=True, data_only=True)
        ws = wb.active
        rows_iter = ws.iter_rows(values_only=True)
        headers = next(rows_iter, None)
        if not headers:
            return [], {"row_count": 0, "columns": [], "format": "excel", "sheet": ws.title}

        columns = [str(h).strip() if h is not None else f"column_{idx + 1}" for idx, h in enumerate(headers)]
        rows = []
        for values in rows_iter:
            row = {columns[idx]: FileParser._normalize_cell(value) for idx, value in enumerate(values or []) if idx < len(columns)}
            if any(value not in (None, "") for value in row.values()):
                rows.append(row)

        return rows, {
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": columns,
            "format": "excel",
            "sheet": ws.title,
        }

    @staticmethod
    def parse_xml(file_content: bytes, format_name: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        root = ET.fromstring(file_content)
        rows = []
        for idx, elem in enumerate(root.iter()):
            tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
            row = {
                "id": elem.attrib.get("id") or elem.attrib.get("ID") or f"{tag}_{idx}",
                "label": tag,
                "text": (elem.text or "").strip(),
                **{k: v for k, v in elem.attrib.items()},
            }
            rows.append(row)

        columns = sorted({key for row in rows for key in row.keys()})
        return rows, {
            "row_count": len(rows),
            "column_count": len(columns),
            "columns": columns,
            "format": format_name,
            "root": root.tag,
        }

    @staticmethod
    def parse_step(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        text = file_content.decode("utf-8", errors="replace")
        entity_pattern = re.compile(r"^\s*#(\d+)\s*=\s*([A-Z0-9_]+)\s*\((.*)", re.IGNORECASE)
        rows = []
        for line in text.splitlines():
            match = entity_pattern.match(line)
            if not match:
                continue
            step_id, entity_type, raw_args = match.groups()
            rows.append({
                "id": f"STEP_{step_id}",
                "step_id": int(step_id),
                "label": entity_type.upper(),
                "entity_type": entity_type.upper(),
                "raw": raw_args.rstrip(";"),
            })
        return rows, {
            "row_count": len(rows),
            "column_count": 5,
            "columns": ["id", "step_id", "label", "entity_type", "raw"],
            "format": "step",
        }

    @staticmethod
    def _clean_row(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            str(k).strip() if k is not None else "column": FileParser._normalize_cell(v)
            for k, v in row.items()
        }

    @staticmethod
    def _normalize_cell(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return value
        return str(value)


class DataTransformer:
    """Build a simple, safe Neo4j schema and Cypher for parsed rows."""

    _IDENTIFIER_RE = re.compile(r"[^A-Za-z0-9_]")

    @classmethod
    def auto_detect_schema(cls, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not rows:
            return {"nodes": [], "relationships": [], "indexes": [], "constraints": []}
        columns = list(rows[0].keys())
        merge_key = cls._choose_merge_key(columns)
        return {
            "nodes": [{
                "label": "ImportedRecord",
                "properties": columns,
                "mergeKeys": [merge_key],
            }],
            "relationships": [],
            "indexes": [{
                "type": "range",
                "name": "idx_imported_record_merge_key",
                "label": "ImportedRecord",
                "properties": [merge_key],
            }],
            "constraints": [],
        }

    @classmethod
    def transform_to_nodes(
        cls,
        rows: List[Dict[str, Any]],
        node_label: str,
        merge_keys: Optional[List[str]] = None,
    ) -> Tuple[List[str], Dict[str, int]]:
        if not rows:
            return [], {"created": 0}

        label = cls._safe_identifier(node_label or "ImportedRecord")
        all_keys = [key for key in rows[0].keys() if key]
        merge_keys = [key for key in (merge_keys or []) if key in all_keys] or [cls._choose_merge_key(all_keys)]
        merge_map = ", ".join(f"{cls._quote_identifier(key)}: row.{cls._quote_identifier(key)}" for key in merge_keys)
        set_props = ", ".join(f"n.{cls._quote_identifier(key)} = row.{cls._quote_identifier(key)}" for key in all_keys)

        query = f"""
        UNWIND $rows AS row
        MERGE (n:`{label}` {{{merge_map}}})
        SET {set_props}
        """
        return [query], {"created": len(rows)}

    @classmethod
    def create_indexes(cls, index_defs: List[Dict[str, Any]]) -> List[str]:
        queries = []
        for idx in index_defs or []:
            index_type = idx.get("type", "range")
            index_name = cls._safe_identifier(idx.get("name") or f"idx_{uuid.uuid4().hex[:8]}")
            label = cls._safe_identifier(idx.get("label") or "")
            properties = [p for p in idx.get("properties", []) if p]
            if not label or not properties:
                continue
            prop_list = ", ".join(f"n.{cls._quote_identifier(p)}" for p in properties)
            if index_type == "range":
                queries.append(f"CREATE INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON ({prop_list})")
            elif index_type == "text":
                queries.append(f"CREATE TEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.{cls._quote_identifier(properties[0])})")
            elif index_type == "fulltext":
                queries.append(f"CREATE FULLTEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON EACH [{prop_list}]")
        return queries

    @classmethod
    def _choose_merge_key(cls, columns: List[str]) -> str:
        for candidate in ("id", "ID", "name", "Name"):
            if candidate in columns:
                return candidate
        return columns[0]

    @classmethod
    def _safe_identifier(cls, value: str) -> str:
        cleaned = cls._IDENTIFIER_RE.sub("_", str(value or "").strip())
        cleaned = cleaned.strip("_")
        if not cleaned:
            return "ImportedRecord"
        if cleaned[0].isdigit():
            cleaned = f"_{cleaned}"
        return cleaned

    @staticmethod
    def _quote_identifier(value: str) -> str:
        return f"`{str(value).replace('`', '``')}`"



    @staticmethod
    def parse_xmi(file_content: bytes) -> tuple[list[dict], dict]:
        """Parse XMI/MDXML file using independent XMIParser."""
        from pathlib import Path
        # Import from local services module
        from .xmi_parser import XMIParser

        # Write content to a temp file for parser compatibility
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix='.xmi') as tmp:
            tmp.write(file_content)
            tmp_path = Path(tmp.name)

        try:
            parser = XMIParser()
            parsed = parser.parse(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)



        nodes = parsed.get("nodes", [])
        relationships = parsed.get("relationships", [])
        provenance = parsed.get("provenance", {})

        # For preview: flatten nodes to rows, extract common columns
        preview_rows = []
        columns = set()
        for node in nodes:
            row = {"label": node.get("label", "Element")}
            props = node.get("properties", {})
            row.update(props)
            preview_rows.append(row)
            columns.update(row.keys())

        # For relationships, optionally add a relationships preview (not as rows, but as stats)
        rel_stats = {
            "relationship_count": len(relationships),
            "relationship_types": list({r.get("type") for r in relationships}),
        }

        stats = {
            "row_count": len(preview_rows),
            "column_count": len(columns),
            "columns": list(columns),
            "relationships": rel_stats,
            "provenance": provenance,
        }
        return preview_rows, stats

    @staticmethod
    def parse_express(file_content: bytes) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Parse EXPRESS schema file and generate OWL"""
        try:
            from .owl_generation_service import OWLGenerationService
            
            # Generate both schema metadata AND OWL/Turtle
            owl_ttl, schema_metadata = OWLGenerationService.generate_owl_from_express(
                file_content, 
                "schema.exp"
            )
            
            # Add OWL data to metadata for storage
            schema_metadata['owl_ttl'] = owl_ttl
            
            # Convert to rows for preview
            rows = [
                {'type': 'Schema', 'name': schema_metadata.get('schema_name', 'Unknown'), 'entities': schema_metadata.get('entity_count', 0)},
                {'type': 'DERIVE', 'count': schema_metadata.get('derived_attributes', 0)},
                {'type': 'INVERSE', 'count': schema_metadata.get('inverse_attributes', 0)},
                {'type': 'UNIQUE', 'count': schema_metadata.get('unique_constraints', 0)},
                {'type': 'OWL Generated', 'triples': schema_metadata.get('owl_triple_count', 0)},
            ]
            
            for entity_name in schema_metadata.get('entities', [])[:10]:  # Preview first 10
                rows.append({
                    'label': 'DataNode',
                    'entity': entity_name,
                })
            
            return rows, schema_metadata
        except Exception as e:
            logging.error(f"EXPRESS parser error: {e}")
            return [], {'error': str(e)}

    @staticmethod
    def transform_to_nodes(rows: List[Dict[str, Any]], node_label: str, 
                          merge_keys: Optional[List[str]] = None) -> Tuple[List[str], Dict[str, int]]:
        """Generate Cypher queries for node creation"""
        if not rows:
            return [], {'created': 0}
        
        label = DataTransformer._safe_identifier(node_label or "ImportedRecord")
        all_keys = [key for key in rows[0].keys() if key]
        merge_keys = [key for key in (merge_keys or []) if key in all_keys] or [DataTransformer._choose_merge_key(all_keys)]
        
        # Build MERGE clause
        merge_props = ", ".join([f"{DataTransformer._quote_identifier(key)}: row.{DataTransformer._quote_identifier(key)}" for key in merge_keys])
        merge_clause = f"MERGE (n:`{label}` {{{merge_props}}})"
        
        # Build SET clause for all properties
        set_props = ", ".join([f"n.{DataTransformer._quote_identifier(key)} = row.{DataTransformer._quote_identifier(key)}" for key in all_keys])
        
        query = f"""
        UNWIND $rows AS row
        {merge_clause}
        SET {set_props}
        """
        
        stats = {'created': len(rows)}
        return [query], stats

    @staticmethod
    def create_indexes(index_defs: List[Dict[str, Any]]) -> List[str]:
        """Generate index creation queries"""
        queries = []
        
        for idx in index_defs or []:
            index_type = idx.get('type', 'range')
            index_name = DataTransformer._safe_identifier(idx.get('name') or f"idx_{uuid.uuid4().hex[:8]}")
            label = DataTransformer._safe_identifier(idx.get('label') or '')
            properties = [p for p in idx.get('properties', []) if p]
            
            if not label or not properties:
                continue
            
            prop_list = ", ".join([f"n.{DataTransformer._quote_identifier(p)}" for p in properties])
            
            if index_type == "range":
                query = f"CREATE INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON ({prop_list})"
            elif index_type == "text":
                query = f"CREATE TEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON (n.{DataTransformer._quote_identifier(properties[0])})"
            elif index_type == "fulltext":
                query = f"CREATE FULLTEXT INDEX `{index_name}` IF NOT EXISTS FOR (n:`{label}`) ON EACH [{prop_list}]"
            else:
                continue
            
            queries.append(query)
        
        return queries


# ========== Neo4j Integration ==========

class Neo4jImporter:
    """Handles Neo4j ingestion"""

    @staticmethod
    def validate_before_ingest(rows: List[Dict[str, Any]], schema: Dict[str, Any]) -> Tuple[bool, str]:
        """
        🔒 DATA LOSS PREVENTION: Validate data before Neo4j ingestion
        
        Checks:
        - Data not empty
        - Required fields present
        - No malformed entries
        - No duplicate keys in merge strategy
        
        Returns: (is_valid, error_message)
        """
        if not rows:
            return False, "No data rows to ingest"
        
        if not schema or not schema.get('nodes'):
            return False, "No schema defined for ingestion"
        
        # Validate each row has required keys
        for node_def in schema.get('nodes', []):
            merge_keys = node_def.get('mergeKeys', [])
            
            for row_idx, row in enumerate(rows):
                if not row:
                    return False, f"Row {row_idx} is empty"
                
                for key in merge_keys:
                    if key not in row or row[key] is None:
                        return False, f"Row {row_idx} missing required merge key '{key}'"
        
        return True, ""

    @staticmethod
    def check_duplicate_entries(rows: List[Dict[str, Any]], schema: Dict[str, Any]) -> Tuple[int, List[str]]:
        """
        🔒 DATA LOSS PREVENTION: Detect duplicate entries
        
        Returns: (duplicate_count, duplicate_ids)
        """
        duplicates = []
        seen_keys = {}
        
        for node_def in schema.get('nodes', []):
            merge_keys = node_def.get('mergeKeys', [])
            
            for row in rows:
                if not merge_keys:
                    continue
                
                # Create composite key from merge keys
                key_values = tuple(row.get(k) for k in merge_keys)
                key_str = '|'.join(str(v) for v in key_values)
                
                if key_str in seen_keys:
                    duplicates.append(key_str)
                else:
                    seen_keys[key_str] = True
        
        return len(duplicates), duplicates

    @staticmethod
    def execute_cypher(queries: List[str], rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Execute Cypher queries with error tracking"""
        stats = {
            'queries_executed': 0,
            'nodes_created': 0,
            'relationships_created': 0,
            'errors': []
        }
        
        try:
            for query in queries:
                if not query or not query.strip():
                    continue
                
                try:
                    if rows and 'UNWIND $rows' in query:
                        graph.query(query, {'rows': rows})
                        if 'MERGE (n:' in query or 'CREATE (n:' in query:
                            stats['nodes_created'] += len(rows)
                    else:
                        graph.query(query)
                    stats['queries_executed'] += 1
                except Exception as e:
                    logger.error(f"Query execution error: {str(e)}", exc_info=True)
                    stats['errors'].append(str(e))
            
            return stats
        except Exception as e:
            stats['errors'].append(f"Ingestion failed: {str(e)}")
            raise


# ========== Main Service ==========

# Global task tracking
import_tasks: Dict[str, Dict[str, Any]] = {}


class UnifiedDataImportService:
    """Main service for unified data import"""

    UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
    import_tasks = import_tasks

    @classmethod
    def initialize(cls):
        """Initialize upload directory"""
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    async def start_import(cls, file_content: bytes, filename: str) -> str:
        """
        Start an import task
        Returns task_id
        """
        # Validate file type
        file_type = FileFormatDetector.detect(filename)
        if not file_type:
            raise ValueError(f"Unsupported file type. Supported: {', '.join(FileFormatDetector.get_supported_formats())}")

        # Create task
        task_id = str(uuid.uuid4())
        task_info = {
            'task_id': task_id,
            'filename': filename,
            'file_type': file_type.value,
            'current_stage': ImportStage.UPLOAD.value,
            'progress': 10,
            'message': 'File uploaded, starting processing...',
            'status': ImportStatus.PROCESSING.value,
            'error': None,
            'preview_data': None,
            'stats': None,
            'started_at': datetime.now().isoformat(),
            'completed_at': None,
            'result': None,
            'file_content': file_content,
        }
        import_tasks[task_id] = task_info

        # Parse file
        try:
            task_info['current_stage'] = ImportStage.PARSE.value
            task_info['progress'] = 25
            task_info['message'] = f'Parsing {file_type.value.upper()} file...'
            
            rows, stats = FileParser.parse(file_content, file_type)
            task_info['parsed_rows'] = rows
            task_info['stats'] = stats
            
            # For EXPRESS files, stats contains schema_metadata with OWL
            if file_type == FileType.EXPRESS:
                task_info['schema_metadata'] = stats
                # Store OWL separately if present
                if 'owl_ttl' in stats:
                    task_info['owl_ttl'] = stats.pop('owl_ttl')
            
            # Validate
            task_info['current_stage'] = ImportStage.VALIDATE.value
            task_info['progress'] = 40
            task_info['message'] = f'Validating data ({len(rows)} records)...'
            
            if not rows:
                raise ValueError("File is empty or contains no valid data")
            
            # Transform
            task_info['current_stage'] = ImportStage.TRANSFORM.value
            task_info['progress'] = 60
            task_info['message'] = 'Preparing data structure...'
            
            schema = DataTransformer.auto_detect_schema(rows)
            task_info['auto_schema'] = schema
            
            # Generate preview
            task_info['current_stage'] = ImportStage.PREVIEW.value
            task_info['progress'] = 75
            task_info['message'] = 'Ready for review'
            
            preview = {
                'row_count': len(rows),
                'columns': list(rows[0].keys()) if rows else [],
                'sample_rows': rows[:5],
                'auto_schema': schema,
            }
            task_info['preview_data'] = preview
            
            logger.info(f"Task {task_id} ready for preview: {len(rows)} rows")
            
        except Exception as e:
            task_info['status'] = ImportStatus.FAILED.value
            task_info['error'] = str(e)
            task_info['completed_at'] = datetime.now().isoformat()
            logger.error(f"Task {task_id} failed during parsing: {str(e)}")
            raise

        return task_id

    @classmethod
    def get_status(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status"""
        if task_id not in import_tasks:
            return None
        
        task = import_tasks[task_id]
        return {
            'task_id': task['task_id'],
            'filename': task['filename'],
            'file_type': task['file_type'],
            'current_stage': task['current_stage'],
            'progress': task['progress'],
            'message': task['message'],
            'status': task['status'],
            'error': task.get('error'),
            'stats': task.get('stats'),
            'schema_metadata': task.get('schema_metadata'),
            'owl_ttl': task.get('owl_ttl'),  # Include OWL if available
            'started_at': task['started_at'],
            'completed_at': task.get('completed_at'),
        }

    @classmethod
    def get_preview(cls, task_id: str) -> Optional[Dict[str, Any]]:
        """Get preview data"""
        if task_id not in import_tasks:
            return None
        
        task = import_tasks[task_id]
        return task.get('preview_data')

    @classmethod
    async def commit_import(cls, task_id: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Commit import to Neo4j
        Uses auto-detected schema if config not provided
        """
        if task_id not in import_tasks:
            raise ValueError(f"Task not found: {task_id}")
        
        task = import_tasks[task_id]
        
        if task['status'] != ImportStatus.PROCESSING.value:
            raise ValueError(f"Task not in processing state: {task['status']}")
        
        try:
            task['current_stage'] = ImportStage.INGEST.value
            task['progress'] = 80
            task['message'] = 'Validating data before Neo4j commit...'
            
            rows = task.get('parsed_rows', [])
            schema = config or task.get('auto_schema', {})
            
            # 🔒 DATA LOSS PREVENTION: Validate data integrity before commit
            is_valid, error_msg = Neo4jImporter.validate_before_ingest(rows, schema)
            if not is_valid:
                raise ValueError(f"Data validation failed: {error_msg}")
            
            # 🔒 DATA LOSS PREVENTION: Check for duplicates
            dup_count, dup_ids = Neo4jImporter.check_duplicate_entries(rows, schema)
            if dup_count > 0:
                logger.warning(f"Found {dup_count} duplicate entries. These will be merged by merge keys. IDs: {dup_ids[:5]}...")
            
            task['message'] = 'Writing to Neo4j...'
            task['progress'] = 85
            
            # Generate and execute queries
            all_queries = []
            
            # Node queries
            for node_def in schema.get('nodes', []):
                label = node_def.get('label', 'DataNode')
                merge_keys = node_def.get('mergeKeys', [])
                queries, _ = DataTransformer.transform_to_nodes(rows, label, merge_keys)
                all_queries.extend(queries)
            
            # Index queries
            index_queries = DataTransformer.create_indexes(schema.get('indexes', []))
            all_queries.extend(index_queries)
            
            # Execute
            result = Neo4jImporter.execute_cypher(all_queries, rows)
            
            task['current_stage'] = ImportStage.INGEST.value
            task['progress'] = 100
            task['message'] = 'Import completed successfully'
            task['status'] = ImportStatus.COMPLETED.value
            task['result'] = result
            task['completed_at'] = datetime.now().isoformat()
            
            logger.info(f"Task {task_id} completed: {result}")
            return result
            
        except Exception as e:
            task['status'] = ImportStatus.FAILED.value
            task['error'] = str(e)
            task['completed_at'] = datetime.now().isoformat()
            logger.error(f"Task {task_id} commit failed: {str(e)}")
            raise

    @classmethod
    def cancel_import(cls, task_id: str) -> None:
        """Cancel import task"""
        if task_id in import_tasks:
            task = import_tasks[task_id]
            if task['status'] == ImportStatus.PROCESSING.value:
                task['status'] = ImportStatus.CANCELLED.value
                task['completed_at'] = datetime.now().isoformat()
                logger.info(f"Task {task_id} cancelled")
