"""Stable, content-bound identities for stateless comparison exports."""
import hashlib
import json

def report_digest(report):
    payload=json.dumps(report,sort_keys=True,separators=(',', ':'),ensure_ascii=True,allow_nan=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
