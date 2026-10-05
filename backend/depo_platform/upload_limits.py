"""Shared bounded ontology upload configuration, without service initialization."""
import os


def ontology_upload_limit() -> int:
    try:
        value = int(os.getenv('ONTOLOGY_MAX_UPLOAD_BYTES', '26214400'))
    except ValueError:
        raise ValueError('ONTOLOGY_MAX_UPLOAD_BYTES must be a positive integer') from None
    if value <= 0:
        raise ValueError('ONTOLOGY_MAX_UPLOAD_BYTES must be a positive integer')
    return value

