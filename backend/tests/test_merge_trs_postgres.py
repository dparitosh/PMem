"""Deletion notifications and retry against an isolated acceptance schema only."""
from backend.tests.test_reporting_trs_postgres import reporting_db
from backend.oslc_service import notifications
from backend.Services.oslc_trs_service import OSLCTRSService


def test_real_postgres_merge_absence_emits_one_deletion_and_reset_requires_rebase(reporting_db,monkeypatch):
    Registry=type(reporting_db)
    with reporting_db._connect() as db:
        db.execute("CREATE TABLE depo_registry(namespace text NOT NULL,key text NOT NULL,value jsonb NOT NULL,updated_at timestamptz NOT NULL DEFAULT now(),PRIMARY KEY(namespace,key))")
    native=Registry('ontology_merge_previews')
    monkeypatch.setattr(notifications,'PostgresRegistry',Registry)
    monkeypatch.setattr(OSLCTRSService,'_store',Registry('oslc_trs'))
    monkeypatch.setattr(OSLCTRSService,'_storage_backend',classmethod(lambda cls:'postgres'))
    monkeypatch.setattr(OSLCTRSService,'is_enabled',classmethod(lambda cls:True))
    record={'preview_id':'retained','change_request':{'revision':1,'plan_digest':'a'*64,'state':'submitted'}}
    notifications.retain_merge_change(native,'retained',record)
    assert native.get('retained')==record
    notifications.reconcile()
    first=OSLCTRSService.change_log(after=0)
    assert [event['event_type'] for event in first['events']]==['Modification']
    # Only this UUID-named test schema's native row is removed.
    with native._connect() as db:
        db.execute('DELETE FROM depo_registry WHERE namespace=%s AND key=%s',('ontology_merge_previews','retained'))
    notifications.reconcile();notifications.reconcile()
    events=OSLCTRSService.change_log(after=0)
    assert [event['event_type'] for event in events['events']]==['Modification','Deletion']
    assert events['head_order']==2
    assert Registry(notifications.NAMESPACE).page(field='status',value='pending')[0]==0
    OSLCTRSService._store.put('change_log',{'counter':0,'events':[]})
    assert OSLCTRSService.change_log(after=2)['rebase_required'] is True
