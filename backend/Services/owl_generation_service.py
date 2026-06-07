"""
OWL/Turtle Generation Service -- routes uploaded file bytes to the correct rdflib engine.

Supported formats and their engines:
  .exp / .express  -> express_parser.emit_owl_ttl          (pure Python, no rdflib)
  .stp / .step     -> owl_step_engine.convert_step_to_ttl  (rdflib)
  .xsd             -> owl_xsd_engine.convert_xsd_to_owl    (rdflib + SKOS/SHACL/OSLC)
  .xmi             -> owl_xmi_engine.convert_xmi_to_ttl    (rdflib)
  .csv             -> owl_csv_engine.convert_csv_to_ttl    (rdflib)
  .plmxml / .xml   -> owl_plmxml_engine.convert_plmxml_to_ttl (rdflib)

All methods accept raw bytes + original filename and return (ttl_str, metadata_dict).
Generated TTL is validated by OntologyValidator before being returned.

In-process cache: _owl_storage[task_id] = ttl_str  (single-worker safe).
"""

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# In-process TTL cache (safe only with --workers 1 / single uvicorn process)
_owl_storage: Dict[str, str] = {}

# Disk-backed TTL cache — survives process restarts (uvicorn --reload, crashes).
# Written alongside the in-memory cache so TTL is available after a hot reload.
_TTL_CACHE_DIR = Path(__file__).parent.parent / "ttl_cache"


def _ttl_path(task_id: str) -> Path:
    """Return the on-disk path for a cached TTL file."""
    return _TTL_CACHE_DIR / f"{task_id}.ttl"


def _write_tmp(content: bytes, suffix: str) -> Path:
    """Write bytes to a temp file and return its Path. Caller must unlink."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


def _read_and_validate(ttl_path: Path) -> Tuple[str, Dict[str, Any]]:
    """Read generated TTL from disk, run OntologyValidator, return (ttl_str, report_dict)."""
    ttl_str = ttl_path.read_text(encoding="utf-8")
    report: Dict[str, Any] = {}
    try:
        from .ontology_validator import OntologyValidator
        validator = OntologyValidator()
        result = validator.validate_file(str(ttl_path))
        report = result.to_dict() if hasattr(result, "to_dict") else {}
    except Exception as val_err:
        logger.debug(f"Ontology validation skipped: {val_err}")
    return ttl_str, report


class OWLGenerationService:
    """Dispatch uploaded file bytes to the right rdflib OWL generation engine."""

    @staticmethod
    def generate_owl(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """Route to the format-specific engine based on filename extension."""
        ext = Path(filename).suffix.lower().lstrip(".")
        dispatch = {
            "exp":     OWLGenerationService.generate_owl_from_express,
            "express": OWLGenerationService.generate_owl_from_express,
            "stp":     OWLGenerationService.generate_owl_from_step,
            "step":    OWLGenerationService.generate_owl_from_step,
            "stpx":    OWLGenerationService.generate_owl_from_step,
            "xsd":     OWLGenerationService.generate_owl_from_xsd,
            "xmi":     OWLGenerationService.generate_owl_from_xmi,
            "csv":     OWLGenerationService.generate_owl_from_csv,
            "plmxml":  OWLGenerationService.generate_owl_from_plmxml,
            "xml":     OWLGenerationService.generate_owl_from_plmxml,
        }
        handler = dispatch.get(ext)
        if handler is None:
            raise ValueError(f"No OWL engine for file extension '.{ext}' (filename: {filename})")
        return handler(file_content, filename)

    @staticmethod
    def generate_owl_from_express(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """EXPRESS schema -> OWL2/Turtle via express_parser.emit_owl_ttl."""
        tmp_path: Optional[Path] = None
        try:
            tmp_path = _write_tmp(file_content, ".exp")
            from .express_parser import parse_express, emit_owl_ttl
            schema = parse_express(tmp_path)
            base_uri = f"http://depo-onto.local/exp#{schema.name}/"
            owl_ttl = emit_owl_ttl(schema, base_uri=base_uri, prefix="exp", source_path=tmp_path)
            derives = sum(len(e.derived_attributes) for e in schema.entities.values())
            inverses = sum(len(e.inverse_attributes) for e in schema.entities.values())
            metadata = {
                "format": "EXPRESS",
                "schema_name": schema.name,
                "entity_count": len(schema.entities),
                "enumeration_count": len(schema.enumerations),
                "select_type_count": len(schema.select_types),
                "derived_attributes": derives,
                "inverse_attributes": inverses,
                "reference_count": len(schema.references),
                "ttl_lines": owl_ttl.count("\n"),
                "validation": {},
            }
            return owl_ttl, metadata
        except Exception as e:
            logger.error(f"EXPRESS OWL generation failed: {e}")
            raise ValueError(f"EXPRESS -> OWL failed: {e}") from e
        finally:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

    @staticmethod
    def generate_owl_from_step(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """STEP (.stp/.step/.stpx) -> OWL2/Turtle via owl_step_engine."""
        ext = Path(filename).suffix or ".stp"
        tmp_in: Optional[Path] = None
        tmp_out: Optional[Path] = None
        try:
            tmp_in = _write_tmp(file_content, ext)
            tmp_out = tmp_in.with_suffix(".ttl")
            from .owl_step_engine import convert_step_to_ttl
            stats = convert_step_to_ttl(
                file_path=tmp_in,
                output_path=tmp_out,
                base_uri=f"http://depo-onto.local/step#{Path(filename).stem}/",
                namespace_prefix="step",
                include_pmi=True,
                validate_against_domain=False,
                copy_reference_ontology=False,
            )
            ttl_str, report = _read_and_validate(tmp_out)
            # convert_step_to_ttl may return either a flat stats dict or a wrapper
            # like {"success": True, "stats": {...}}. Normalize to a flat dict.
            if isinstance(stats, dict) and 'stats' in stats and isinstance(stats['stats'], dict):
                flat_stats = stats['stats']
            else:
                flat_stats = stats if isinstance(stats, dict) else {}
            metadata = {**flat_stats, "format": "STEP", "validation": report}
            return ttl_str, metadata
        except Exception as e:
            logger.error(f"STEP OWL generation failed: {e}")
            raise ValueError(f"STEP -> OWL failed: {e}") from e
        finally:
            for p in (tmp_in, tmp_out):
                if p and p.exists():
                    p.unlink(missing_ok=True)

    @staticmethod
    def generate_owl_from_xsd(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """XSD schema -> OWL2/Turtle with full SKOS/SHACL/OSLC via owl_xsd_engine."""
        tmp_dir: Optional[Path] = None
        try:
            tmp_dir = Path(tempfile.mkdtemp())
            xsd_path = tmp_dir / filename
            xsd_path.write_bytes(file_content)
            tmp_out = tmp_dir / (Path(filename).stem + ".ttl")
            from .owl_xsd_engine import convert_xsd_to_owl, minimal_config
            stem = Path(filename).stem
            cfg = minimal_config(
                base_uri=f"http://depo-onto.local/xsd#{stem}/",
                prefix=(stem[:16] or "xsd"),
                title=f"{stem} Ontology",
                schema_dir=str(tmp_dir),
                output_ttl=str(tmp_out),
            )
            result_path = convert_xsd_to_owl(cfg)
            ttl_str, report = _read_and_validate(result_path)
            metadata = {
                "format": "XSD",
                "schema_name": stem,
                "ttl_lines": ttl_str.count("\n"),
                "validation": report,
            }
            return ttl_str, metadata
        except Exception as e:
            logger.error(f"XSD OWL generation failed: {e}")
            raise ValueError(f"XSD -> OWL failed: {e}") from e
        finally:
            if tmp_dir and tmp_dir.exists():
                import shutil as _sh
                _sh.rmtree(tmp_dir, ignore_errors=True)

    @staticmethod
    def generate_owl_from_xmi(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """XMI model -> OWL2/Turtle via owl_xmi_engine."""
        tmp_in: Optional[Path] = None
        tmp_out: Optional[Path] = None
        try:
            tmp_in = _write_tmp(file_content, ".xmi")
            tmp_out = tmp_in.with_suffix(".ttl")
            from .owl_xmi_engine import convert_xmi_to_ttl
            convert_xmi_to_ttl(
                xmi_path=str(tmp_in),
                output_path=str(tmp_out),
                base_uri=f"http://depo-onto.local/xmi#{Path(filename).stem}/",
            )
            ttl_str, report = _read_and_validate(tmp_out)
            metadata = {
                "format": "XMI",
                "schema_name": Path(filename).stem,
                "ttl_lines": ttl_str.count("\n"),
                "validation": report,
            }
            return ttl_str, metadata
        except Exception as e:
            logger.error(f"XMI OWL generation failed: {e}")
            raise ValueError(f"XMI -> OWL failed: {e}") from e
        finally:
            for p in (tmp_in, tmp_out):
                if p and p.exists():
                    p.unlink(missing_ok=True)

    @staticmethod
    def generate_owl_from_csv(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """CSV -> OWL2/Turtle (each row = NamedIndividual) via owl_csv_engine."""
        tmp_in: Optional[Path] = None
        tmp_out: Optional[Path] = None
        try:
            tmp_in = _write_tmp(file_content, ".csv")
            tmp_out = tmp_in.with_suffix(".ttl")
            from .owl_csv_engine import convert_csv_to_ttl
            stem = Path(filename).stem
            convert_csv_to_ttl(
                csv_path=str(tmp_in),
                output_path=str(tmp_out),
                base_uri=f"http://depo-onto.local/csv#{stem}/",
                prefix=(stem[:12] or "csv"),
                title=f"{stem} Ontology",
            )
            ttl_str, report = _read_and_validate(tmp_out)
            metadata = {
                "format": "CSV",
                "schema_name": stem,
                "ttl_lines": ttl_str.count("\n"),
                "validation": report,
            }
            return ttl_str, metadata
        except Exception as e:
            logger.error(f"CSV OWL generation failed: {e}")
            raise ValueError(f"CSV -> OWL failed: {e}") from e
        finally:
            for p in (tmp_in, tmp_out):
                if p and p.exists():
                    p.unlink(missing_ok=True)

    @staticmethod
    def generate_owl_from_plmxml(file_content: bytes, filename: str) -> Tuple[str, Dict[str, Any]]:
        """PLMXML / generic XML -> OWL2/Turtle via owl_plmxml_engine."""
        ext = Path(filename).suffix or ".plmxml"
        tmp_in: Optional[Path] = None
        tmp_out: Optional[Path] = None
        try:
            tmp_in = _write_tmp(file_content, ext)
            tmp_out = tmp_in.with_suffix(".ttl")
            from .owl_plmxml_engine import convert_plmxml_to_ttl
            convert_plmxml_to_ttl(
                plmxml_source=str(tmp_in),
                output_path=str(tmp_out),
            )
            ttl_str, report = _read_and_validate(tmp_out)
            metadata = {
                "format": "PLMXML",
                "schema_name": Path(filename).stem,
                "ttl_lines": ttl_str.count("\n"),
                "validation": report,
            }
            return ttl_str, metadata
        except Exception as e:
            logger.error(f"PLMXML OWL generation failed: {e}")
            raise ValueError(f"PLMXML -> OWL failed: {e}") from e
        finally:
            for p in (tmp_in, tmp_out):
                if p and p.exists():
                    p.unlink(missing_ok=True)

    @staticmethod
    def validate_with_shacl(ttl_content: str, shacl_shapes: Optional[str] = None) -> Dict[str, Any]:
        """Validate a Turtle graph against SHACL shapes via shacl_service."""
        try:
            from .shacl_service import ShaclValidationService
            import rdflib
            data_graph = rdflib.Graph()
            data_graph.parse(data=ttl_content, format="turtle")
            svc = ShaclValidationService()
            if shacl_shapes:
                shacl_graph = rdflib.Graph()
                shacl_graph.parse(data=shacl_shapes, format="turtle")
            else:
                default_shapes_ttl = svc.create_default_shapes()
                shacl_graph = rdflib.Graph()
                shacl_graph.parse(data=default_shapes_ttl, format="turtle")
            return svc.validate_graph(data_graph, shacl_graph)
        except Exception as e:
            logger.warning(f"SHACL validation failed: {e}")
            return {"is_valid": True, "error_count": 0, "warning_count": 0, "error": str(e)}

    @staticmethod
    def store_owl(task_id: str, ttl: str) -> None:
        """Store generated TTL in memory cache and persist to disk."""
        _owl_storage[task_id] = ttl
        try:
            _TTL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _ttl_path(task_id).write_text(ttl, encoding="utf-8")
        except Exception as e:
            logger.warning(f"TTL disk write failed for {task_id}: {e}")

    @staticmethod
    def store(task_id: str, ttl: str) -> None:
        """Alias for store_owl."""
        OWLGenerationService.store_owl(task_id, ttl)

    @staticmethod
    def retrieve_owl(task_id: str) -> Optional[str]:
        """Retrieve cached TTL from memory, falling back to disk if not found."""
        if task_id in _owl_storage:
            return _owl_storage[task_id]
        # Disk fallback — survives process restart / hot reload
        disk = _ttl_path(task_id)
        if disk.exists():
            try:
                ttl = disk.read_text(encoding="utf-8")
                _owl_storage[task_id] = ttl  # repopulate in-memory cache
                return ttl
            except Exception as e:
                logger.warning(f"TTL disk read failed for {task_id}: {e}")
        return None

    @staticmethod
    def retrieve(task_id: str) -> Optional[str]:
        """Alias for retrieve_owl."""
        return OWLGenerationService.retrieve_owl(task_id)
