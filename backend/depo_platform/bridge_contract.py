"""Shared deterministic identities for ingestion and Semantic Bridge publication."""
import hashlib
import json


class BridgeConflict(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()


def canonical_lookup(value):
    if isinstance(value,dict): return {key:canonical_lookup(item) for key,item in value.items()}
    if isinstance(value,(list,tuple,set)): return sorted((canonical_lookup(item) for item in value),key=digest)
    return value
