"""Lazy, allowlisted Semantica class loading; never instantiates a connector."""
from importlib import import_module

INGESTORS = ('File', 'Web', 'Parquet', 'XML', 'REST', 'PublicAPI', 'DB',
             'Databricks', 'Snowflake', 'Email', 'Feed', 'MCP', 'Ontology',
             'Repo', 'Stream', 'Arrow', 'CloudStorage')


def load_ingestor(name):
    if name not in INGESTORS:
        raise ValueError('Unknown reviewed Semantica ingestor')
    if name == 'Email':
        # Semantica 0.6.7 references email.message.Message in an annotation
        # without importing that stdlib submodule on a fresh interpreter.
        # Import its prerequisite without patching third-party package files.
        import_module('email.message')
    return getattr(import_module('semantica.ingest'), name + 'Ingestor')
