"""Bounded Apache Spark transformations and telemetry for DEPO data jobs."""
from __future__ import annotations

import os
import json
import hashlib
import re
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.artifact_store import ArtifactStore


class SparkUnavailable(RuntimeError):
    """Raised when the optional Spark execution plane is intentionally unavailable."""


class SparkJobRunner:
    """Own one local Spark session and expose safe, UI-ready job telemetry.

    This service is a data-plane boundary.  It transforms bounded input batches
    and returns JSON; it never writes directly to Neo4j or bypasses CEIM's
    validation/publication APIs.
    """

    max_records = 50_000

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._spark: Any | None = None
        self._runs: deque[dict[str, Any]] = deque(maxlen=50)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _retain_json_artifact(
        value: Any,
        *,
        filename: str,
        kind: str,
        correlation_id: str,
    ) -> str:
        """Retain a bounded job partition as immutable, content-addressed JSON."""
        artifact = ArtifactStore().ingest_bytes(
            json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8"),
            filename=filename,
            kind=kind,
            media_type="application/json",
            provenance={"correlation_id": correlation_id, "producer": "data-pipeline-service"},
        )
        return str(artifact["artifact_id"])

    def _enabled(self) -> bool:
        return os.getenv("DEPO_SPARK_ENABLED", "false").strip().lower() == "true"

    def _neo4j_enabled(self) -> bool:
        return os.getenv("DEPO_SPARK_NEO4J_ENABLED", "false").strip().lower() == "true"

    @staticmethod
    def _spark_version(spark_home: Path) -> str:
        release = spark_home / "RELEASE"
        if not release.is_file():
            raise SparkUnavailable("Configured Spark runtime does not contain its RELEASE file")
        match = re.search(r"Spark\s+(\d+\.\d+\.\d+)", release.read_text(encoding="utf-8", errors="replace"))
        if not match:
            raise SparkUnavailable("Configured Spark runtime version could not be determined")
        return match.group(1)

    def _neo4j_connector_configuration(self, spark_home: Path) -> dict[str, str]:
        """Return the official connector configuration without exposing secrets."""
        package = os.getenv("DEPO_SPARK_NEO4J_PACKAGE", "").strip()
        uri = os.getenv("NEO4J_URI", "").strip()
        username = os.getenv("NEO4J_USER", "").strip()
        password = os.getenv("NEO4J_PASS", "").strip()
        database = os.getenv("NEO4J_DATABASE", "neo4j").strip()
        spark_version = self._spark_version(spark_home)
        if not spark_version.startswith(("4.0.", "4.1.")):
            raise SparkUnavailable(
                f"Neo4j Spark connector 6.x supports Spark 4.0–4.1; configured Spark {spark_version} is unsupported. "
                "Install a supported Spark runtime before enabling DEPO_SPARK_NEO4J_ENABLED."
            )
        if not package:
            raise SparkUnavailable("DEPO_SPARK_NEO4J_PACKAGE must name a Neo4j Spark connector compatible with the installed Spark runtime")
        if not uri or not username or not password:
            raise SparkUnavailable("NEO4J_URI, NEO4J_USER, and NEO4J_PASS are required when the Neo4j Spark connector is enabled")
        return {
            "spark.jars.packages": package,
            "neo4j.url": uri,
            "neo4j.authentication.basic.username": username,
            "neo4j.authentication.basic.password": password,
            "neo4j.database": database,
        }

    def _runtime_paths(self) -> tuple[Path, Path]:
        runtime_root = Path(__file__).resolve().parents[2] / "runtime"
        spark_home = Path(os.getenv("DEPO_SPARK_HOME") or runtime_root / "spark")
        java_home = Path(os.getenv("DEPO_JAVA_HOME") or runtime_root / "java")
        return spark_home, java_home

    def health(self) -> dict[str, Any]:
        spark_home, java_home = self._runtime_paths()
        runtime_present = (
            (java_home / "bin" / ("java.exe" if os.name == "nt" else "java")).is_file()
            and (spark_home / "python" / "lib" / "pyspark.zip").is_file()
            and bool(list((spark_home / "python" / "lib").glob("py4j-*-src.zip")))
        )
        status = "disabled" if not self._enabled() else (
            "unavailable" if not runtime_present else "initialized" if self._spark is not None else "configured"
        )
        return {
            "status": status,
            "runtime_files_present": runtime_present,
            "execution_verified": False,
            "execution_mode": "bounded_preview",
            "spark_enabled": self._enabled(),
            "spark_initialized": self._spark is not None,
            "spark_home_present": spark_home.is_dir(),
            "java_home_present": java_home.is_dir(),
            "neo4j_connector_enabled": self._neo4j_enabled(),
            "neo4j_connector_package_configured": bool(os.getenv("DEPO_SPARK_NEO4J_PACKAGE", "").strip()),
            "neo4j_connection_configured": bool(os.getenv("NEO4J_URI", "").strip() and os.getenv("NEO4J_USER", "").strip() and os.getenv("NEO4J_PASS", "").strip()),
            "runs_retained": len(self._runs),
        }

    def _spark_session(self) -> Any:
        if not self._enabled():
            raise SparkUnavailable("Spark data jobs are disabled; set DEPO_SPARK_ENABLED=true in the service environment")
        if self._spark is not None:
            return self._spark
        spark_home, java_home = self._runtime_paths()
        if not spark_home.is_dir() or not java_home.is_dir():
            raise SparkUnavailable("Configured Spark or Java runtime is unavailable")
        pyspark_zip = spark_home / "python" / "lib" / "pyspark.zip"
        py4j_archives = sorted((spark_home / "python" / "lib").glob("py4j-*-src.zip"))
        if not pyspark_zip.is_file() or not py4j_archives:
            raise SparkUnavailable("Configured Spark runtime does not contain PySpark libraries")
        os.environ.setdefault("SPARK_HOME", str(spark_home))
        os.environ.setdefault("JAVA_HOME", str(java_home))
        os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
        for archive in (str(pyspark_zip), str(py4j_archives[0])):
            if archive not in sys.path:
                sys.path.insert(0, archive)
        try:
            from pyspark.sql import SparkSession
        except ImportError as exc:
            raise SparkUnavailable("PySpark could not be loaded from the configured Spark runtime") from exc
        warehouse = os.getenv("DEPO_SPARK_OUTPUT_ROOT")
        if not warehouse or not Path(warehouse).is_absolute():
            raise SparkUnavailable("DEPO_SPARK_OUTPUT_ROOT must be an explicit absolute output path")
        builder = (
            SparkSession.builder.appName("depo-data-pipeline-service")
            .master(os.getenv("DEPO_SPARK_MASTER", "local[2]"))
            .config("spark.sql.warehouse.dir", warehouse)
            .config("spark.ui.enabled", "false")
        )
        if self._neo4j_enabled():
            for key, value in self._neo4j_connector_configuration(spark_home).items():
                builder = builder.config(key, value)
        self._spark = builder.getOrCreate()
        self._spark.sparkContext.setLogLevel(os.getenv("DEPO_SPARK_LOG_LEVEL", "WARN"))
        return self._spark

    @staticmethod
    def _validate_records(records: list[Any]) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        """Apply the synchronous input quality gate before allocating Spark work."""
        accepted: list[dict[str, str]] = []
        rejected: list[dict[str, Any]] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                rejected.append({"index": index, "rule": "record.object", "message": "Record must be an object"})
                continue
            standard = str(record.get("source_standard") or "").strip()
            concept = str(record.get("canonical_concept") or "").strip()
            status = str(record.get("validation_status") or "valid").strip().lower()
            if not standard or not concept:
                rejected.append({"index": index, "rule": "required.standard_or_concept", "message": "source_standard and canonical_concept are required"})
                continue
            if status not in {"valid", "warning", "invalid", "pending_review"}:
                rejected.append({"index": index, "rule": "validation_status.allowed", "message": "validation_status is not recognized"})
                continue
            if status == "invalid":
                rejected.append({"index": index, "rule": "validation_status.not_invalid", "message": "Records marked invalid cannot pass the quality gate"})
                continue
            accepted.append({"source_standard": standard, "canonical_concept": concept, "validation_status": status})
        return accepted, rejected

    def transform_quality_summary(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Run a quality-aware grouping transform and return ECharts-ready JSON.

        The endpoint accepts a constrained record shape so it is safe for an
        interactive client. Large source processing belongs to scheduled data
        jobs using the same transform contract.
        """
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("records must be a non-empty JSON array")
        if len(records) > self.max_records:
            raise ValueError(f"records exceeds the maximum of {self.max_records}")
        accepted, rejected = self._validate_records(records)
        if not accepted:
            raise ValueError("No records passed the input quality gate")

        started = time.perf_counter()
        job_id = str(uuid.uuid4())
        with self._lock:
            spark = self._spark_session()
            frame = spark.createDataFrame(accepted)
            rows = [row.asDict() for row in frame.groupBy("source_standard", "canonical_concept", "validation_status").count().orderBy("source_standard", "canonical_concept", "validation_status").collect()]
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        valid_count = sum(int(row["count"]) for row in rows if row["validation_status"] == "valid")
        quality = {
            "input_records": len(records),
            "accepted_records": len(accepted),
            "rejected_records": len(rejected),
            "valid_records": valid_count,
            "quality_gate": "passed" if not rejected and valid_count == len(accepted) else "failed" if rejected else "warning",
            "rejections": rejected[:100],
        }
        partition_artifacts = {
            "accepted": self._retain_json_artifact(
                accepted,
                filename=f"{job_id}-accepted.json",
                kind="accepted-quality-partition",
                correlation_id=correlation_id,
            ),
            "rejected": self._retain_json_artifact(
                rejected,
                filename=f"{job_id}-rejected.json",
                kind="rejected-quality-partition",
                correlation_id=correlation_id,
            ) if rejected else None,
        }
        result = {
            "job_id": job_id,
            "job_type": "interactive-quality-summary",
            "status": "completed",
            "correlation_id": correlation_id,
            "completed_at": self._now(),
            "duration_ms": duration_ms,
            "quality": quality,
            "partition_artifacts": partition_artifacts,
            "series": rows,
            "echarts": {
                "x_axis": [f"{row['source_standard']}:{row['canonical_concept']}" for row in rows],
                "series": [{"name": row["validation_status"], "value": row["count"], "source_standard": row["source_standard"], "canonical_concept": row["canonical_concept"]} for row in rows],
            },
        }
        self._runs.appendleft(result)
        return result

    def assess_data_quality(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Execute the reusable completeness, validity, uniqueness and provenance gate.

        Unlike the dashboard's interactive summary, this is a versioned data
        job.  It emits retained accepted/rejected partitions and a quality
        evidence report that upstream workflows can use as a blocking gate.
        It remains source/format-neutral: AP242, PLMXML, ReqIF, QIF and
        document-derived records use the same contract.
        """
        records = payload.get("records")
        if not isinstance(records, list) or not records:
            raise ValueError("records must be a non-empty JSON array")
        if len(records) > self.max_records:
            raise ValueError(f"records exceeds the maximum of {self.max_records}")

        enriched: list[dict[str, Any]] = []
        rejections: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                rejections.append({"index": index, "rule": "record.object", "dimension": "validity", "message": "Record must be an object"})
                continue
            source_id = str(record.get("source_id") or record.get("external_id") or "").strip()
            provenance = record.get("provenance")
            artifact_id = str(record.get("artifact_id") or (provenance or {}).get("artifact_id") or "").strip() if isinstance(provenance, dict) else str(record.get("artifact_id") or "").strip()
            if not source_id:
                rejections.append({"index": index, "rule": "identity.required", "dimension": "completeness", "message": "source_id or external_id is required"})
                continue
            if not artifact_id:
                rejections.append({"index": index, "rule": "provenance.artifact", "dimension": "provenance", "message": "artifact_id or provenance.artifact_id is required"})
                continue
            if source_id in seen_ids:
                rejections.append({"index": index, "rule": "identity.unique", "dimension": "uniqueness", "message": "source_id must be unique within a batch"})
                continue
            seen_ids.add(source_id)
            enriched.append({**record, "source_id": source_id, "artifact_id": artifact_id})

        accepted, validity_rejections = self._validate_records(enriched)
        rejections.extend([{**item, "dimension": "validity"} for item in validity_rejections])
        if not accepted:
            raise ValueError("No records passed the data quality contract")
        started = time.perf_counter()
        with self._lock:
            spark = self._spark_session()
            rows = [row.asDict() for row in spark.createDataFrame(accepted).groupBy("source_standard", "canonical_concept", "validation_status").count().orderBy("source_standard", "canonical_concept", "validation_status").collect()]
        job_id = str(uuid.uuid4())
        accepted_artifact = self._retain_json_artifact(accepted, filename=f"{job_id}-accepted-quality.json", kind="accepted-data-quality-partition", correlation_id=correlation_id)
        rejected_artifact = self._retain_json_artifact(rejections, filename=f"{job_id}-rejected-quality.json", kind="rejected-data-quality-partition", correlation_id=correlation_id) if rejections else None
        quality = {
            "quality_profile": "data-quality-core-v1",
            "input_records": len(records), "accepted_records": len(accepted), "rejected_records": len(rejections),
            "completeness": round((len(records) - len([item for item in rejections if item.get("dimension") == "completeness"])) / len(records), 4),
            "validity": round((len(records) - len([item for item in rejections if item.get("dimension") == "validity"])) / len(records), 4),
            "uniqueness": round((len(records) - len([item for item in rejections if item.get("dimension") == "uniqueness"])) / len(records), 4),
            "provenance": round((len(records) - len([item for item in rejections if item.get("dimension") == "provenance"])) / len(records), 4),
            "quality_gate": "passed" if not rejections else "warning",
            "rejections": rejections[:100],
        }
        result = {
            "job_id": job_id, "job_type": "data-quality-assessment", "status": "completed" if not rejections else "quality_warning",
            "correlation_id": correlation_id, "completed_at": self._now(), "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_contract": "data-quality-report-v1", "quality": quality, "series": rows,
            "partition_artifacts": {"accepted": accepted_artifact, "rejected": rejected_artifact},
            "publication": "not_attempted; quality assessment never publishes graph changes",
        }
        self._runs.appendleft(result)
        return result

    def build_schema_analytics_product(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Create a governed analytics-product draft from a retained schema.

        The input must already be a content-addressed schema artifact. The
        converter retains the XSD/EXPRESS source, Turtle serialization and
        analytics profile. Spark contributes the scalable aggregate view while
        publication remains an explicit Data Product API approval action.
        """
        artifact_id = str(payload.get("artifact_id") or "").strip()
        if not artifact_id:
            raise ValueError("artifact_id is required")
        metadata, source = ArtifactStore().resolve(artifact_id)
        filename = str(metadata.get("filename") or "schema.xsd")
        if metadata.get("kind") != "engineering-schema-source":
            raise ValueError("artifact_id must reference an engineering-schema-source artifact")
        if Path(filename).suffix.lower() not in {".xsd", ".exp", ".xmi"}:
            raise ValueError("schema analytics supports retained .xsd, .exp, or .xmi schema artifacts")
        content = source.read_bytes()
        from backend.ingestion_service.schema_conversion import converter
        converted = converter.convert(filename=filename, content=content)
        draft = dict(converted.get("data_product_draft") or {})
        if draft.get("contract") != "schema-analytics-data-product-v1":
            raise ValueError("Schema conversion did not return an analytics data-product draft")
        started = time.perf_counter()
        stats = dict(converted.get("statistics") or {})
        rows = [{"metric": str(key), "value": value if isinstance(value, (int, float, str, bool)) else json.dumps(value, sort_keys=True, default=str)} for key, value in stats.items()]
        if not rows:
            rows = [{"metric": "schema_artifacts", "value": len(draft.get("artifacts") or [])}]
        with self._lock:
            spark = self._spark_session()
            series = [row.asDict() for row in spark.createDataFrame(rows).orderBy("metric").collect()]
        result = {
            "job_id": str(uuid.uuid4()), "job_type": "schema-analytics-product", "status": "completed",
            "correlation_id": correlation_id, "completed_at": self._now(), "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "input_contract": "engineering-schema-artifact-v1", "output_contract": "schema-analytics-data-product-draft-v1",
            "source_artifact_id": artifact_id, "schema_format": converted.get("format"), "source_kind": converted.get("source_kind"),
            "counts": {"analytics_metrics": len(series), "retained_artifacts": len(draft.get("artifacts") or [])},
            "quality": {"quality_profile": "schema-analytics-v1", "schema_validation": converted.get("schema_validation"), "quality_status": draft.get("quality_status")},
            "data_product_draft": draft, "partition_artifacts": {"accepted": str((converted.get("artifacts") or {}).get("analytics_profile") or ""), "rejected": None},
            "series": series,
            "publication": "not_attempted; submit the returned data-product draft to the Data Product API after semantic-release and steward approval",
        }
        self._runs.appendleft(result)
        return result

    def normalize_ceim_batch(self, payload: dict[str, Any], *, correlation_id: str, validate: bool) -> dict[str, Any]:
        """Normalize a bounded source batch and optionally run CEIM SHACL.

        This is pre-publication work only.  It produces no graph mutation and
        therefore cannot bypass CEIM's separately approved publication route.
        """
        from backend.ceim.contract import contract

        standard = str(payload.get("standard") or "").strip().lower()
        entities = list(payload.get("entities") or [])
        relationships = list(payload.get("relationships") or [])
        if not standard:
            raise ValueError("standard is required")
        if not entities and not relationships:
            raise ValueError("entities or relationships are required")
        if len(entities) + len(relationships) > self.max_records:
            raise ValueError(f"batch exceeds the maximum of {self.max_records} records")
        started = time.perf_counter()
        representation = str(payload.get("representation") or "source-records-v1")
        if representation == "normalized-ceim-v1":
            if payload.get("ceim_version") != contract.version:
                raise ValueError("Normalized CEIM input version does not match the active CEIM contract")
            normalized_entities = [dict(record) for record in entities]
            normalized_relationships = [dict(record) for record in relationships]
            contract.validate_mapping_evidence(
                standard=standard, entities=normalized_entities, relationships=normalized_relationships,
            )
            # Validate the declared normalized shape before Spark receives it;
            # this rejects accidental or malicious pass-through records.
            contract.to_rdf(entities=normalized_entities, relationships=normalized_relationships)
        elif representation == "source-records-v1":
            normalized_entities = [contract.normalize_entity(standard=standard, record=dict(record)) for record in entities]
            normalized_relationships = [contract.normalize_relationship(standard=standard, record=dict(record)) for record in relationships]
        else:
            raise ValueError("representation must be source-records-v1 or normalized-ceim-v1")
        with self._lock:
            spark = self._spark_session()
            summary_rows = [row.asDict() for row in spark.createDataFrame(
                [{"ceim_type": item["ceim_type"]} for item in normalized_entities] or [{"ceim_type": "relationship-only"}]
            ).groupBy("ceim_type").count().orderBy("ceim_type").collect()]
        validation = contract.validate_projection(entities=normalized_entities, relationships=normalized_relationships) if validate else None
        normalized_batch = {
            "contract": "normalized-ceim-batch-v1",
            "representation": "normalized-ceim-v1",
            "standard": standard,
            "input_representation": representation,
            "ceim_version": contract.version,
            "mapping_digest": contract.mapping_pack(standard)["digest"],
            "mapping_pack": contract.mapping_pack(standard)["id"],
            "mapping_version": contract.mapping_pack(standard)["version"],
            "entities": normalized_entities,
            "relationships": normalized_relationships,
        }
        accepted_artifact_id = self._retain_json_artifact(
            normalized_batch,
            filename=f"{correlation_id}-normalized-ceim.json",
            kind="accepted-semantic-partition" if not validation or validation.get("conforms") else "rejected-semantic-partition",
            correlation_id=correlation_id,
        )
        result = {
            "job_id": str(uuid.uuid4()),
            "job_type": "validate-semantic-batch" if validate else "normalize-ceim",
            "status": "completed" if not validation or validation.get("conforms") else "validation_failed",
            "correlation_id": correlation_id,
            "completed_at": self._now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "standard": standard,
            "ceim_version": contract.version,
            "mapping": contract.mapping_pack(standard)["digest"],
            "counts": {"input_entities": len(entities), "input_relationships": len(relationships), "normalized_entities": len(normalized_entities), "normalized_relationships": len(normalized_relationships)},
            "series": summary_rows,
            "validation": validation,
            "partition_artifacts": {
                "accepted": accepted_artifact_id if not validation or validation.get("conforms") else None,
                "rejected": accepted_artifact_id if validation and not validation.get("conforms") else None,
            },
            "publication": "not_attempted; CEIM graph publication requires a separate approved request",
        }
        self._runs.appendleft(result)
        return result

    def validate_unstructured_evidence(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Validate retained document evidence before CEIM normalization.

        This job accepts only content-addressed source artifacts and preserves
        document chunks as evidence. It does not generate ontology assertions,
        embeddings, or graph writes; those require an approved mapping and the
        CEIM publication path.
        """
        documents = payload.get("documents")
        evidence_artifact_id = str(payload.get("evidence_artifact_id") or "")
        store = ArtifactStore()
        if evidence_artifact_id:
            metadata, content = store.resolve(evidence_artifact_id)
            if metadata.get("kind") != "unstructured-evidence-batch":
                raise ValueError("evidence_artifact_id must reference an unstructured evidence batch")
            try:
                envelope = json.loads(content.read_text(encoding="utf-8"))
                documents = envelope.get("documents")
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("evidence_artifact_id does not contain a valid evidence batch") from exc
        if not isinstance(documents, list) or not documents:
            raise ValueError("documents must be a non-empty unstructured evidence array")
        if len(documents) > self.max_records:
            raise ValueError(f"documents exceeds the maximum of {self.max_records}")
        accepted, rejected, rows = [], [], []
        for index, document in enumerate(documents):
            if not isinstance(document, dict):
                rejected.append({"index": index, "rule": "document.object", "message": "Document evidence must be an object"})
                continue
            artifact_id = str(document.get("artifact_id") or "")
            document_id = str(document.get("document_id") or "")
            chunks = document.get("chunks")
            if not artifact_id or not document_id or not isinstance(chunks, list) or not chunks:
                rejected.append({"index": index, "rule": "document.required_evidence", "message": "artifact_id, document_id and non-empty chunks are required"})
                continue
            try:
                metadata, _ = store.resolve(artifact_id)
            except ValueError as exc:
                rejected.append({"index": index, "rule": "artifact.content_addressed", "message": str(exc)})
                continue
            invalid_chunk = next((chunk for chunk in chunks if not isinstance(chunk, dict) or not str(chunk.get("chunk_id") or "").strip() or not str(chunk.get("content") or "").strip()), None)
            if invalid_chunk is not None:
                rejected.append({"index": index, "rule": "chunk.provenance", "message": "Every chunk must have chunk_id and content"})
                continue
            accepted.append(document)
            rows.append({"media_type": metadata.get("media_type", "application/octet-stream"), "chunk_count": len(chunks), "proposal_count": len((document.get("semantic_proposals") or {}).get("entities") or [])})
        if not accepted:
            raise ValueError("No documents passed unstructured evidence quality gates")
        started = time.perf_counter()
        with self._lock:
            spark = self._spark_session()
            series = [row.asDict() for row in spark.createDataFrame(rows).groupBy("media_type").sum("chunk_count", "proposal_count").orderBy("media_type").collect()]
        accepted_manifest = [
            {
                "artifact_id": item["artifact_id"],
                "document_id": item["document_id"],
                "chunk_ids": [chunk["chunk_id"] for chunk in item["chunks"]],
            }
            for item in accepted
        ]
        partition_artifacts = {
            "accepted": self._retain_json_artifact(
                accepted_manifest,
                filename=f"{correlation_id}-accepted-documents.json",
                kind="accepted-unstructured-evidence-partition",
                correlation_id=correlation_id,
            ),
            "rejected": self._retain_json_artifact(
                rejected,
                filename=f"{correlation_id}-rejected-documents.json",
                kind="rejected-unstructured-evidence-partition",
                correlation_id=correlation_id,
            ) if rejected else None,
        }
        result = {
            "job_id": str(uuid.uuid4()), "job_type": "validate-unstructured-evidence", "status": "completed" if not rejected else "quality_warning",
            "correlation_id": correlation_id, "completed_at": self._now(), "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_contract": "validated-unstructured-evidence-v1",
            "counts": {"input_documents": len(documents), "accepted_documents": len(accepted), "rejected_documents": len(rejected), "chunks": sum(len(item["chunks"]) for item in accepted)},
            "quality": {"quality_profile": "unstructured-evidence-v1", "rejections": rejected[:100], "publication": "not_attempted; CEIM mapping and approval are required"},
            "partition_artifacts": partition_artifacts,
            "series": series,
        }
        self._runs.appendleft(result)
        return result

    def enrich_document_evidence(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Build a bounded, evidence-first technical document graph proposal.

        The job deliberately performs deterministic structural enrichment only:
        it preserves supplied chunks, normalizes their text, records content
        digests and emits Document/DocumentChunk/HAS_CHUNK proposal records.
        OCR, model-based NER and embeddings remain separate, explicitly
        governed capabilities.  This job never maps, validates or publishes
        graph assertions, so it cannot bypass the CEIM publication boundary.
        """
        documents = payload.get("documents")
        evidence_artifact_id = str(payload.get("evidence_artifact_id") or "")
        store = ArtifactStore()
        if evidence_artifact_id:
            metadata, content = store.resolve(evidence_artifact_id)
            if metadata.get("kind") != "unstructured-evidence-batch":
                raise ValueError("evidence_artifact_id must reference an unstructured evidence batch")
            try:
                documents = json.loads(content.read_text(encoding="utf-8")).get("documents")
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError("evidence_artifact_id does not contain a valid evidence batch") from exc
        if not isinstance(documents, list) or not documents:
            raise ValueError("documents must be a non-empty unstructured evidence array")
        if len(documents) > self.max_records:
            raise ValueError(f"documents exceeds the maximum of {self.max_records}")

        accepted, rejected, rows = [], [], []
        for index, document in enumerate(documents):
            if not isinstance(document, dict):
                rejected.append({"index": index, "rule": "document.object", "message": "Document evidence must be an object"})
                continue
            artifact_id, document_id = str(document.get("artifact_id") or ""), str(document.get("document_id") or "")
            chunks = document.get("chunks")
            if not artifact_id or not document_id or not isinstance(chunks, list) or not chunks:
                rejected.append({"index": index, "rule": "document.required_evidence", "message": "artifact_id, document_id and non-empty chunks are required"})
                continue
            try:
                metadata, _ = store.resolve(artifact_id)
            except ValueError as exc:
                rejected.append({"index": index, "rule": "artifact.content_addressed", "message": str(exc)})
                continue
            proposed_chunks = []
            invalid = False
            for ordinal, chunk in enumerate(chunks):
                if not isinstance(chunk, dict) or not str(chunk.get("chunk_id") or "").strip():
                    invalid = True
                    break
                text = " ".join(str(chunk.get("content") or "").replace("\ufeff", "").split())
                if not text:
                    invalid = True
                    break
                proposed_chunks.append({
                    "id": f"document-chunk:{document_id}:{chunk['chunk_id']}",
                    "type": "DocumentChunk",
                    "document_id": document_id,
                    "chunk_id": str(chunk["chunk_id"]),
                    "ordinal": ordinal,
                    "content": text,
                    "content_digest": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "token_count_estimate": len(text.split()),
                    "provenance": {"artifact_id": artifact_id, "source_chunk_id": str(chunk["chunk_id"])},
                })
            if invalid:
                rejected.append({"index": index, "rule": "chunk.provenance", "message": "Every chunk must have chunk_id and non-empty content"})
                continue
            accepted.append({
                "id": f"document:{document_id}", "type": "Document", "document_id": document_id,
                "artifact_id": artifact_id, "media_type": metadata.get("media_type", "application/octet-stream"),
                "chunks": proposed_chunks,
            })
            rows.append({"media_type": metadata.get("media_type", "application/octet-stream"), "chunk_count": len(proposed_chunks), "token_count": sum(item["token_count_estimate"] for item in proposed_chunks)})
        if not accepted:
            raise ValueError("No documents passed document enrichment quality gates")

        started = time.perf_counter()
        with self._lock:
            spark = self._spark_session()
            series = [row.asDict() for row in spark.createDataFrame(rows).groupBy("media_type").sum("chunk_count", "token_count").orderBy("media_type").collect()]
        graph_nodes = []
        graph_edges = []
        for document in accepted:
            graph_nodes.append({key: value for key, value in document.items() if key != "chunks"})
            for chunk in document["chunks"]:
                graph_nodes.append(chunk)
                graph_edges.append({"type": "HAS_CHUNK", "source": document["id"], "target": chunk["id"], "provenance": chunk["provenance"]})
        proposal = {
            "contract": "document-graph-proposal-v1", "correlation_id": correlation_id,
            "documents": accepted, "nodes": graph_nodes, "relationships": graph_edges,
            "publication": "not_attempted; an approved CEIM mapping and canonical publication request are required",
        }
        partition_artifacts = {
            "accepted": self._retain_json_artifact(proposal, filename=f"{correlation_id}-document-graph-proposal.json", kind="document-graph-proposal", correlation_id=correlation_id),
            "rejected": self._retain_json_artifact(rejected, filename=f"{correlation_id}-rejected-document-enrichment.json", kind="rejected-document-enrichment-partition", correlation_id=correlation_id) if rejected else None,
        }
        result = {
            "job_id": str(uuid.uuid4()), "job_type": "enrich-document-evidence", "status": "completed" if not rejected else "quality_warning",
            "correlation_id": correlation_id, "completed_at": self._now(), "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_contract": "document-graph-proposal-v1",
            "counts": {"input_documents": len(documents), "accepted_documents": len(accepted), "rejected_documents": len(rejected), "chunks": sum(len(item["chunks"]) for item in accepted), "graph_nodes": len(graph_nodes), "graph_relationships": len(graph_edges)},
            "quality": {"quality_profile": "unstructured-evidence-v1", "rejections": rejected[:100], "enrichment": ["deterministic chunk normalization", "content digests", "artifact and chunk provenance"], "not_performed": ["OCR", "model-based NER", "embedding generation", "graph publication"]},
            "partition_artifacts": partition_artifacts, "series": series,
            "publication": proposal["publication"],
        }
        self._runs.appendleft(result)
        return result

    def normalize_unstructured_ceim(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Map an evidence-first document proposal through the CEIM contract.

        Unstructured content remains immutable source evidence.  This method
        publishes no graph mutation: it turns only the deterministic Document,
        DocumentChunk and HAS_CHUNK proposal shapes into an explicit, versioned
        CEIM batch and applies the same semantic validation used by structured
        engineering sources.
        """
        artifact_id = str(payload.get("proposal_artifact_id") or "")
        if not artifact_id:
            raise ValueError("proposal_artifact_id is required")
        metadata, path = ArtifactStore().resolve(artifact_id)
        if metadata.get("kind") != "document-graph-proposal":
            raise ValueError("proposal_artifact_id must reference a document graph proposal")
        try:
            proposal = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("proposal_artifact_id does not contain a valid document graph proposal") from exc
        if proposal.get("contract") != "document-graph-proposal-v1":
            raise ValueError("proposal artifact must use document-graph-proposal-v1")

        entities: list[dict[str, Any]] = []
        for node in proposal.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node_type = str(node.get("type") or "")
            node_id = str(node.get("id") or "")
            if node_type not in {"Document", "DocumentChunk"} or not node_id:
                continue
            attributes = {
                key: value for key, value in node.items()
                if key not in {"id", "type", "provenance", "chunks", "content"} and value not in (None, "")
            }
            # Raw chunk text remains in the retained source/proposal artifact;
            # the CEIM graph carries only a digest and evidence identity.
            if node_type == "DocumentChunk":
                attributes["content_digest"] = str(node.get("content_digest") or "")
            entities.append({"source_type": node_type, "source_id": node_id, "attributes": attributes})
        relationships = [
            {"source_type": "HAS_CHUNK", "source_id": edge["source"], "target_id": edge["target"]}
            for edge in proposal.get("relationships") or []
            if isinstance(edge, dict) and edge.get("type") == "HAS_CHUNK" and edge.get("source") and edge.get("target")
        ]
        if not entities:
            raise ValueError("Document graph proposal has no CEIM-mappable evidence nodes")

        result = self.normalize_ceim_batch(
            {
                "standard": "unstructured-evidence",
                "representation": "source-records-v1",
                "entities": entities,
                "relationships": relationships,
            },
            correlation_id=correlation_id,
            validate=True,
        )
        result["job_type"] = "normalize-unstructured-ceim"
        result["input_contract"] = "document-graph-proposal-v1"
        result["evidence_artifact_id"] = artifact_id
        result["publication"] = "not_attempted; CEIM graph publication requires a separate approved request"
        return result

    def rdf_quality_statistics(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Compute bounded distributed N-Triples statistics from an immutable RDF artifact.

        This is intentionally a read-only Spark job. It provides a compatible
        first step toward distributed RDF quality without importing a JVM
        semantic stack whose published Spark versions are incompatible with the
        configured Spark 4 runtime.
        """
        artifact_id = str(payload.get("artifact_id") or "")
        if not artifact_id:
            raise ValueError("artifact_id is required")
        metadata, artifact_path = ArtifactStore().resolve(artifact_id)
        filename = str(metadata.get("filename") or "").lower()
        if not filename.endswith((".nt", ".ntriples")):
            raise ValueError("rdf-quality-statistics currently accepts N-Triples (.nt) artifacts only")
        pattern = re.compile(r"^\s*(?:<[^>]+>|_:[A-Za-z][\w.-]*)\s+<([^>]+)>\s+(?:<[^>]+>|_:[A-Za-z][\w.-]*|\"(?:[^\"\\]|\\.)*\"(?:@[A-Za-z-]+|\^\^<[^>]+>)?)\s*\.\s*$")
        started = time.perf_counter()
        with self._lock:
            spark = self._spark_session()
            lines = spark.sparkContext.textFile(artifact_path.as_uri()).map(lambda line: line.strip()).filter(lambda line: bool(line) and not line.startswith("#"))
            total = lines.count()
            parsed = lines.map(lambda line: (bool(pattern.match(line)), pattern.match(line).group(1) if pattern.match(line) else ""))
            valid = parsed.filter(lambda row: row[0])
            valid_count = valid.count()
            predicate_counts = valid.map(lambda row: (row[1], 1)).reduceByKey(lambda left, right: left + right).takeOrdered(50, key=lambda row: (-row[1], row[0]))
        malformed = total - valid_count
        result = {
            "job_id": str(uuid.uuid4()), "job_type": "rdf-quality-statistics", "status": "completed" if malformed == 0 else "quality_warning",
            "correlation_id": correlation_id, "completed_at": self._now(), "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_contract": "rdf-quality-report-v1", "artifact_id": artifact_id,
            "counts": {"triples_examined": total, "valid_ntriples": valid_count, "malformed_lines": malformed, "distinct_predicates": len(predicate_counts)},
            "quality": {"syntax_conformance": "passed" if malformed == 0 else "warning", "scope": "N-Triples lexical integrity and predicate distribution", "publication": "not_attempted; statistics jobs are read-only"},
            "predicate_statistics": [{"predicate": predicate, "triple_count": count} for predicate, count in predicate_counts],
        }
        self._runs.appendleft(result)
        return result

    def rdf_deduplicate_serialize(self, payload: dict[str, Any], *, correlation_id: str) -> dict[str, Any]:
        """Create a deterministic N-Triples artifact through a bounded Spark job.

        Spark performs lexical validation and distributed deduplication. The
        driver collects at most ``max_records`` validated lines solely to
        create one content-addressed interchange artifact. Publication remains
        a separate governed operation through the canonical API.
        """
        artifact_id = str(payload.get("artifact_id") or "")
        if not artifact_id:
            raise ValueError("artifact_id is required")
        metadata, artifact_path = ArtifactStore().resolve(artifact_id)
        filename = str(metadata.get("filename") or "").lower()
        if not filename.endswith((".nt", ".ntriples")):
            raise ValueError("rdf-deduplicate-serialize accepts N-Triples (.nt) artifacts only")
        pattern = re.compile(r'^\s*(?:<[^>]+>|_:[A-Za-z][\w.-]*)\s+<[^>]+>\s+(?:<[^>]+>|_:[A-Za-z][\w.-]*|"(?:[^"\\]|\\.)*"(?:@[A-Za-z-]+|\^\^<[^>]+>)?)\s*\.\s*$')
        started = time.perf_counter()
        with self._lock:
            spark = self._spark_session()
            lines = spark.sparkContext.textFile(artifact_path.as_uri()).map(lambda line: line.strip()).filter(lambda line: bool(line) and not line.startswith("#"))
            total = lines.count()
            if total > self.max_records:
                raise ValueError(f"RDF artifact exceeds the bounded serialization limit of {self.max_records} triples")
            valid = lines.filter(lambda line: bool(pattern.match(line)))
            malformed_lines = lines.filter(lambda line: not pattern.match(line)).take(100)
            valid_count = valid.count()
            canonical_lines = valid.distinct().sortBy(lambda line: line).collect()
        canonical = (("\n".join(canonical_lines) + "\n") if canonical_lines else "").encode("utf-8")
        store = ArtifactStore()
        output = store.ingest_bytes(
            canonical,
            filename=f"{artifact_id.split(':', 1)[1]}-canonical.nt",
            kind="canonical-ntriples-partition",
            media_type="application/n-triples",
            provenance={"source_artifact_id": artifact_id, "correlation_id": correlation_id, "producer": "data-pipeline-service"},
        )
        rejected_id = self._retain_json_artifact(
            malformed_lines,
            filename=f"{artifact_id.split(':', 1)[1]}-rejected-lines.json",
            kind="rejected-rdf-partition",
            correlation_id=correlation_id,
        ) if malformed_lines else None
        duplicate_count = valid_count - len(canonical_lines)
        malformed_count = total - valid_count
        result = {
            "job_id": str(uuid.uuid4()), "job_type": "rdf-deduplicate-serialize",
            "status": "completed" if malformed_count == 0 else "quality_warning",
            "correlation_id": correlation_id, "completed_at": self._now(),
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
            "output_contract": "canonical-ntriples-v1", "source_artifact_id": artifact_id,
            "counts": {"triples_examined": total, "valid_ntriples": valid_count, "distinct_triples": len(canonical_lines), "duplicate_triples": duplicate_count, "malformed_lines": malformed_count},
            "quality": {"syntax_conformance": "passed" if malformed_count == 0 else "warning", "deterministic_order": True, "publication": "not_attempted; canonical publication approval is required"},
            "partition_artifacts": {"accepted": output["artifact_id"], "rejected": rejected_id},
        }
        self._runs.appendleft(result)
        return result

    def telemetry(self) -> dict[str, Any]:
        runs = list(self._runs)
        def metric(run: dict[str, Any], *names: str) -> int:
            values = {**(run.get("counts") or {}), **(run.get("quality") or {})}
            for name in names:
                if values.get(name) is not None:
                    return int(values[name])
            return 0
        return {
            "service": "data-pipeline",
            "execution_mode": "bounded_preview",
            "spark": self.health(),
            "totals": {
                "runs": len(runs),
                "records_processed": sum(metric(run, "input_records", "input_entities", "input_documents", "triples_examined") for run in runs),
                "records_accepted": sum(metric(run, "accepted_records", "normalized_entities", "accepted_documents", "valid_ntriples") for run in runs),
                "records_rejected": sum(metric(run, "rejected_records", "rejected_documents", "malformed_lines") for run in runs),
                "average_duration_ms": round(sum(float(run["duration_ms"]) for run in runs) / len(runs), 2) if runs else 0,
            },
            "recent_runs": runs,
        }

    def shutdown(self) -> None:
        """Release the local JVM when the API worker exits."""
        with self._lock:
            if self._spark is not None:
                self._spark.stop()
                self._spark = None


runner = SparkJobRunner()
