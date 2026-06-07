"""Quick endpoint health check — run with the venv python."""
import requests, json, time

base = "http://localhost:8000"

def call_test(label, method, url, timeout=10, **kwargs):
    t0 = time.time()
    try:
        r = method(url, timeout=timeout, **kwargs)
        ms = int((time.time() - t0) * 1000)
        body = r.text[:120].replace("\n", " ")
        print(f"  [{ms:>5}ms] {label}: HTTP {r.status_code}  {body}")
        return r
    except requests.exceptions.Timeout:
        ms = int((time.time() - t0) * 1000)
        print(f"  [{ms:>5}ms] {label}: TIMEOUT after {ms}ms")
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        print(f"  [{ms:>5}ms] {label}: ERROR {e}")


def _main():
    print("=== Graph visualization endpoints ===")
    for t in ["ap239", "plmxml", "step", "xmi", "mbse_instances", "mbse"]:
        call_test(f"/ontology/{t}", requests.get, f"{base}/ontology/{t}")

    print()
    print("=== Data dictionary endpoints ===")
    for p in ["ap239", "plmxml", "xmi", "mbse"]:
        r = call_test(f"/api/v1/ontology/{p}/data-dictionary", requests.get, f"{base}/api/v1/ontology/{p}/data-dictionary")
        if r and r.status_code == 200:
            d = r.json()
            print(f"       -> entities={d.get('entity_count',0)}  props={d.get('property_count',0)}  rels={d.get('relationship_count',0)}  source={d.get('source','?')}")

    print()
    print("=== Mappings endpoints ===")
    for p in ["ap239", "plmxml", "xmi"]:
        call_test(f"/api/v1/ontology/{p}/mappings/xmi", requests.get, f"{base}/api/v1/ontology/{p}/mappings/xmi")

    print()
    print("=== Pre-commit health check ===")
    call_test("/api/v1/import/pre-commit/fake-task-id", requests.get, f"{base}/api/v1/import/pre-commit/fake-task-id")

    print()
    print("=== Registered ontologies ===")
    r = call_test("/api/v1/import/registered", requests.get, f"{base}/api/v1/import/registered")
    if r and r.status_code == 200:
        d = r.json()
        onts = d.get("ontologies", [])
        print(f"     Found {len(onts)} registered ontologies:")
        for o in onts:
            print(f"       prefix={o.get('prefix')}  name={o.get('ontology_name')}  id={o.get('ontology_id')}")

    print()
    print("=== Neo4j node count (sanity check) ===")
    r = call_test("/api/v1/import/pre-commit/fake-task-id", requests.get, f"{base}/api/v1/import/pre-commit/fake-task-id")
    if r:
        try:
            d = r.json()
            checks = d.get("checks", {})
            neo4j = checks.get("neo4j", {})
            print(f"     Neo4j: {neo4j}")
        except Exception:
            pass

    print()
    print("Done.")


if __name__ == '__main__':
    _main()
