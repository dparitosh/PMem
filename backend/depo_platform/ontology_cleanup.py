"""Independent cleanup and read-back verification of both ontology registries."""
import logging

logger = logging.getLogger(__name__)


def clear_ontology_registrations(upload_manager=None, catalog=None):
    cleared, failed, verification = 0, [], {}
    # Resolve and process each source independently: one failure must not skip
    # cleanup of the other store after an explicitly requested full reset.
    for source in ('ingestion', 'catalog'):
        try:
            if source == 'ingestion':
                if upload_manager is None:
                    from backend.Services.ontology_upload_manager import OntologyUploadManager
                    upload_manager = OntologyUploadManager
                outcome = upload_manager.clear_all_metadata()
            else:
                if catalog is None:
                    from backend.ontology_service.catalog import catalog as native_catalog
                    catalog = native_catalog
                outcome = catalog.clear_registration_metadata()
            cleared += outcome.get('cleared', 0)
            if outcome.get('status') != 'success':
                failed.append(source)
        except Exception:
            logger.exception('Ontology cleanup failed for %s', source)
            failed.append(source)
        try:
            if source == 'ingestion':
                upload_manager._invalidate_list_cache()
                remaining = upload_manager.list_all_ontologies()
                if remaining.get('status') != 'success':
                    raise RuntimeError('Ingestion registry verification failed')
                rows = remaining['ontologies']
            else:
                rows = catalog.list(include_superseded=True)
            verification[source] = {'status': 'empty' if not rows else 'remaining', 'remaining': len(rows)}
            if rows and source not in failed:
                failed.append(source)
        except Exception:
            logger.exception('Ontology cleanup verification failed for %s', source)
            verification[source] = {'status': 'unverified', 'remaining': None}
            if source not in failed:
                failed.append(source)
    return {'status': 'partial' if failed else 'success', 'cleared': cleared,
            'failed': failed, 'verification': verification}
