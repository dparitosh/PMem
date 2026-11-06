"""Run the existing approved validation job; never auto-approve or publish."""
import argparse
import json
from pathlib import Path
import httpx
from dotenv import load_dotenv


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("instance", type=Path)
    options = parser.parse_args()
    load_dotenv(".env.local")
    from backend.ceim.plmxml_adapter import plmxml_to_ceim_batch
    from backend.artifact_store import ArtifactStore
    batch = plmxml_to_ceim_batch(options.instance.read_bytes())
    if batch["source_summary"]["unmapped_relationships"]:
        raise ValueError("Unmapped relationships block this acceptance execution")
    artifact = ArtifactStore().ingest(options.instance, kind="source-plmxml", media_type="application/xml")
    payload = {**batch, "representation": "normalized-ceim-v1", "ceim_version": "0.1.0",
               "artifact_ids": [artifact["artifact_id"]], "source_system": "Teamcenter",
               "ontology_id": "plmxml_12662e4cec26454b",
               "next_checkpoint": {"source_artifact_id": artifact["artifact_id"]}}
    with httpx.Client(timeout=180) as client:
        response = client.post("http://127.0.0.1:8019/api/v1/pipeline/jobs/definitions/teamcenter-plmxml-motor-ebom/1.0.0/run", json=payload)
        response.raise_for_status()
        result = response.json()
        print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
