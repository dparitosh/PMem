"""Completeness gate shared by queued and synchronous architecture publication."""
def require_complete_archimate(task):
    stats = task.get('stats') or {}
    if str(stats.get('source_format') or stats.get('file_format') or task.get('file_type') or '').lower() == 'archimate' and int(stats.get('unresolved_relationship_count') or 0) > 0:
        raise ValueError('ArchiMate has unresolved references. Correct the model and re-import before graph publication.')
