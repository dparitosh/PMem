"""Conservative purge guard: registry consumers and retained usage provenance."""
import json
import os
import re


def require_unreferenced(artifact_id, artifact_store):
    if not isinstance(artifact_id,str) or not re.fullmatch(r'sha256:[0-9a-f]{64}',artifact_id):
        raise ValueError('Invalid artifact content address')
    if os.getenv('DEPO_DATABASE_URL') or os.getenv('DATABASE_URL'):
        from backend.mesh_store import PostgresRegistry
        # This operator-only check is bounded; it is never in the RDF hot path.
        path = '$.** ? (@ == ' + json.dumps(artifact_id) + ')'
        with PostgresRegistry('artifact_retention')._connect() as db, db.cursor() as cursor:
            cursor.execute("SELECT namespace FROM depo_registry WHERE namespace <> 'artifact_retention' AND value @? %s::jsonpath LIMIT 1", (path,))
            if cursor.fetchone():
                raise ValueError('Artifact is referenced by retained application records; preserve or archive its consumers before purge')
    directory = artifact_store._directory(artifact_id[7:])
    # Provenance may precede its owning registry commit or live only in retained
    # workflow files. Unknown/historical usages remain protected, not guessed idle.
    for usage_file in directory.glob('usage-*.json'):
        if usage_file.stat().st_size > 256*1024:
            raise ValueError('Artifact usage evidence requires review before purge')
        try:
            usage = json.loads(usage_file.read_text(encoding='utf-8'))
        except (ValueError,OSError) as exc:
            raise ValueError('Artifact usage evidence is unreadable; purge refused') from exc
        if usage.get('artifact_id') != artifact_id or usage.get('provenance'):
            raise ValueError('Artifact has retained usage provenance; review and archive those consumers before purge')
