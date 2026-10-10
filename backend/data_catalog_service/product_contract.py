"""Versioned product content is immutable; lifecycle is separate metadata."""

SERVER_FIELDS = {"product_id", "version", "updated_at"}
MUTABLE_FIELDS = {"lifecycle_state"}


def reject_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            name = str(key).lower().replace('-', '_')
            if name in {'headers', 'credentials', 'authorization', 'api_key', 'password', 'secret', 'token', 'ocp_apim_subscription_key'} or name.endswith(('_token', '_api_key', '_password', '_secret')):
                raise ValueError('Catalog metadata cannot contain credentials or arbitrary headers')
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


def public_record(record):
    # Allowlisted reader contract also protects legacy credential-bearing records.
    fields = {'product_id', 'version', 'updated_at', 'name', 'domain', 'owner', 'classification', 'steward',
              'lifecycle_state', 'sla', 'quality_status', 'sources', 'ontologies', 'semantic_releases',
              'manifest', 'product_kind', 'analytics_readiness', 'product_url', 'description'}
    def clean(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                try:
                    reject_secrets({key: None})
                except ValueError:
                    continue
                result[key] = clean(item)
            return result
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value
    return clean({key: value for key, value in record.items() if key in fields})


def validate_registration(payload: dict) -> None:
    reject_secrets(payload)
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
