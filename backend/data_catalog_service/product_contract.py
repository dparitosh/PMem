"""Versioned product content is immutable; lifecycle is separate metadata."""

SERVER_FIELDS = {"product_id", "version", "updated_at"}
MUTABLE_FIELDS = {"lifecycle_state"}


def validate_registration(payload: dict) -> None:
    for name in ("name", "domain", "owner", "classification", "steward"):
        if not isinstance(payload.get(name), str) or not payload[name].strip():
            raise ValueError(f"{name} must be a non-empty string")
    if payload.get("lifecycle_state") not in {"draft", "in_review", "approved", "published", "deprecated", "revoked"}:
        raise ValueError("Unsupported product lifecycle_state")
    if payload.get("lifecycle_state") in {"approved", "published"}:
        manifest = payload.get("manifest")
        if not isinstance(manifest, dict) or not manifest.get("artifacts"):
            raise ValueError("Approved/published products require an artifact manifest")
        if not isinstance(payload.get("semantic_releases"), list) or not payload["semantic_releases"]:
            raise ValueError("Approved/published products require semantic release references")


def validate_revision(existing: dict, proposed: dict) -> None:
    def content(record):
        return {k: v for k, v in record.items() if k not in SERVER_FIELDS | MUTABLE_FIELDS}

    if content(existing) != content(proposed):
        raise ValueError("Product version content is immutable; register a new version")
    if existing.get("lifecycle_state") == "revoked" and proposed.get("lifecycle_state") != "revoked":
        raise ValueError("A revoked product version cannot be reactivated")
