"""
Semantic workflow execution service.

These workflows are intentionally artifact-first: each run writes reviewable
outputs to WorkflowArtifactService before any destructive or graph-mutating
operation is introduced.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ontology_upload_manager import OntologyUploadManager
from .workflow_artifact_service import WorkflowArtifactService


def _tokenize(value: str) -> List[str]:
    return [t for t in re.split(r"[^a-zA-Z0-9]+", value.lower()) if len(t) > 1]


def _jaccard(left: List[str], right: List[str]) -> float:
    lset, rset = set(left), set(right)
    if not lset or not rset:
        return 0.0
    return len(lset & rset) / len(lset | rset)


class SemanticWorkflowService:
    @staticmethod
    def _new_task(workflow_id: str, source_filename: str = "") -> str:
        task_id = f"{workflow_id.replace('.', '-')}-{uuid.uuid4()}"
        WorkflowArtifactService.ensure_task(task_id, workflow_id=workflow_id, filename=source_filename)
        return task_id

    @staticmethod
    def _ontology_metadata(ontology_id: str) -> Dict[str, Any]:
        result = OntologyUploadManager.get_ontology(ontology_id)
        if result.get("status") != "success":
            raise ValueError(result.get("error") or f"Ontology not found: {ontology_id}")
        return result["metadata"]

    @staticmethod
    def _read_ontology_file(meta: Dict[str, Any]) -> str:
        path = Path(meta.get("file_path", ""))
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8-sig", errors="replace")
        except Exception:
            return path.read_bytes().decode("utf-8", errors="replace")

    @staticmethod
    def _extract_terms(text: str) -> List[Dict[str, Any]]:
        candidates = re.findall(r"\b[A-Z][A-Za-z0-9_]{2,}\b|\b[a-z][a-z0-9_]{3,}\b", text or "")
        seen = {}
        for term in candidates:
            key = term.lower()
            if key in seen:
                seen[key]["frequency"] += 1
            else:
                seen[key] = {
                    "term": term,
                    "normalized": key,
                    "frequency": 1,
                    "tokens": _tokenize(term),
                }
        terms = sorted(seen.values(), key=lambda x: (-x["frequency"], x["normalized"]))
        return terms[:500]

    @classmethod
    def execute(cls, workflow_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        handlers = {
            "instance.link": cls.link_instances,
            "ontology.merge": cls.merge_ontologies,
            "ontology.validate": cls.validate_ontology,
            "dictionary.generate": cls.generate_dictionary,
            "taxonomy.generate": cls.generate_taxonomy,
            "graph.chunk": cls.chunk_graph,
        }
        handler = handlers.get(workflow_id)
        if not handler:
            raise ValueError(f"Unsupported workflow: {workflow_id}")
        return handler(payload)

    @classmethod
    def validate_ontology(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = payload.get("ontology_id")
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        text = cls._read_ontology_file(meta)
        task_id = cls._new_task("ontology.validate", meta.get("original_filename", ""))

        findings = []
        if not meta.get("prefix"):
            findings.append({"severity": "error", "message": "Ontology prefix is missing"})
        if not meta.get("ontology_name"):
            findings.append({"severity": "warning", "message": "Ontology name is missing"})
        if not Path(meta.get("file_path", "")).exists():
            findings.append({"severity": "error", "message": "Source ontology file is missing"})
        if text and len(text.strip()) < 20:
            findings.append({"severity": "warning", "message": "Ontology file content is very small"})
        if text and "http://" not in text and "https://" not in text and "xmlns" not in text:
            findings.append({"severity": "info", "message": "No namespace URI detected in source text"})

        report = {
            "workflow_id": "ontology.validate",
            "ontology_id": ontology_id,
            "ontology_name": meta.get("ontology_name"),
            "prefix": meta.get("prefix"),
            "file_type": meta.get("file_type"),
            "checked_at": datetime.now().isoformat(),
            "findings": findings,
            "summary": {
                "errors": sum(1 for f in findings if f["severity"] == "error"),
                "warnings": sum(1 for f in findings if f["severity"] == "warning"),
                "infos": sum(1 for f in findings if f["severity"] == "info"),
            },
        }
        WorkflowArtifactService.write_json(task_id, "validation", "ontology_validation_report.json", report, "validation_report")
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def generate_dictionary(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = payload.get("ontology_id")
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        text = cls._read_ontology_file(meta)
        task_id = cls._new_task("dictionary.generate", meta.get("original_filename", ""))
        terms = cls._extract_terms(text)
        dictionary = {
            "workflow_id": "dictionary.generate",
            "ontology_id": ontology_id,
            "prefix": meta.get("prefix"),
            "generated_at": datetime.now().isoformat(),
            "terms": [
                {
                    "term": t["term"],
                    "definition": "",
                    "frequency": t["frequency"],
                    "source": meta.get("original_filename"),
                    "status": "needs_review",
                }
                for t in terms
            ],
        }
        WorkflowArtifactService.write_json(task_id, "reports", "data_dictionary.json", dictionary, "data_dictionary")
        csv_lines = ["term,frequency,status,source"] + [
            f"{json.dumps(t['term'])},{t['frequency']},needs_review,{json.dumps(meta.get('original_filename', ''))}"
            for t in terms
        ]
        WorkflowArtifactService.write_text(task_id, "reports", "data_dictionary.csv", "\n".join(csv_lines), "data_dictionary_csv")
        return {"task_id": task_id, "status": "completed", "result": dictionary, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def generate_taxonomy(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = payload.get("ontology_id")
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        text = cls._read_ontology_file(meta)
        task_id = cls._new_task("taxonomy.generate", meta.get("original_filename", ""))
        terms = cls._extract_terms(text)
        groups: Dict[str, List[str]] = {}
        for item in terms:
            key = item["normalized"][0].upper()
            groups.setdefault(key, []).append(item["term"])
        taxonomy = {
            "workflow_id": "taxonomy.generate",
            "ontology_id": ontology_id,
            "root": meta.get("ontology_name") or meta.get("prefix") or ontology_id,
            "generated_at": datetime.now().isoformat(),
            "children": [
                {"label": letter, "children": [{"label": term} for term in sorted(set(values))[:50]]}
                for letter, values in sorted(groups.items())
            ],
        }
        WorkflowArtifactService.write_json(task_id, "reports", "taxonomy.json", taxonomy, "taxonomy")
        return {"task_id": task_id, "status": "completed", "result": taxonomy, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def merge_ontologies(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        source_id = payload.get("source_ontology_id") or payload.get("from_ontology_id")
        target_id = payload.get("target_ontology_id") or payload.get("to_ontology_id")
        if not source_id or not target_id:
            raise ValueError("source_ontology_id and target_ontology_id are required")
        source = cls._ontology_metadata(source_id)
        target = cls._ontology_metadata(target_id)
        source_terms = cls._extract_terms(cls._read_ontology_file(source))
        target_terms = cls._extract_terms(cls._read_ontology_file(target))
        task_id = cls._new_task("ontology.merge", f"{source_id}__{target_id}")

        target_by_norm = {t["normalized"]: t for t in target_terms}
        overlaps = []
        additions = []
        for term in source_terms:
            if term["normalized"] in target_by_norm:
                overlaps.append({"term": term["term"], "target_term": target_by_norm[term["normalized"]]["term"], "confidence": 1.0})
            else:
                additions.append({"term": term["term"], "action": "add_candidate"})
        report = {
            "workflow_id": "ontology.merge",
            "source_ontology_id": source_id,
            "target_ontology_id": target_id,
            "generated_at": datetime.now().isoformat(),
            "overlaps": overlaps[:200],
            "additions": additions[:300],
            "summary": {"overlap_count": len(overlaps), "addition_count": len(additions)},
        }
        WorkflowArtifactService.write_json(task_id, "reports", "merge_plan.json", report, "merge_plan")
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def link_instances(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = payload.get("ontology_id")
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        import_manifest = payload.get("import_artifact_manifest") or {}
        task_id = cls._new_task("instance.link", meta.get("original_filename", ""))
        ontology_terms = cls._extract_terms(cls._read_ontology_file(meta))
        source_terms = cls._extract_terms(json.dumps(import_manifest)) if import_manifest else []
        candidates = []
        for src in source_terms[:100]:
            scored = [
                {"ontology_term": onto["term"], "confidence": round(_jaccard(src["tokens"], onto["tokens"]), 3)}
                for onto in ontology_terms[:200]
            ]
            best = max(scored, key=lambda x: x["confidence"], default=None)
            if best and best["confidence"] > 0:
                candidates.append({"source_term": src["term"], **best})
        report = {
            "workflow_id": "instance.link",
            "ontology_id": ontology_id,
            "generated_at": datetime.now().isoformat(),
            "candidates": sorted(candidates, key=lambda x: -x["confidence"])[:200],
            "summary": {"candidate_count": len(candidates), "committed": False},
        }
        WorkflowArtifactService.write_json(task_id, "reports", "link_candidates.json", report, "link_candidates")
        return {"task_id": task_id, "status": "completed", "result": report, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}

    @classmethod
    def chunk_graph(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        ontology_id = payload.get("ontology_id")
        chunk_size = int(payload.get("chunk_size") or 80)
        if not ontology_id:
            raise ValueError("ontology_id is required")
        meta = cls._ontology_metadata(ontology_id)
        terms = cls._extract_terms(cls._read_ontology_file(meta))
        task_id = cls._new_task("graph.chunk", meta.get("original_filename", ""))
        chunks = []
        for idx in range(0, len(terms), chunk_size):
            subset = terms[idx:idx + chunk_size]
            chunks.append({
                "chunk_id": f"chunk_{idx // chunk_size + 1:04d}",
                "term_count": len(subset),
                "terms": [t["term"] for t in subset],
            })
        manifest = {
            "workflow_id": "graph.chunk",
            "ontology_id": ontology_id,
            "chunk_size": chunk_size,
            "generated_at": datetime.now().isoformat(),
            "chunks": chunks,
            "summary": {"chunk_count": len(chunks), "term_count": len(terms)},
        }
        WorkflowArtifactService.write_json(task_id, "reports", "chunk_manifest.json", manifest, "chunk_manifest")
        for chunk in chunks:
            WorkflowArtifactService.write_json(task_id, "reports", f"{chunk['chunk_id']}.json", chunk, "graph_chunk")
        return {"task_id": task_id, "status": "completed", "result": manifest, "artifact_manifest": WorkflowArtifactService.get_manifest(task_id)}
