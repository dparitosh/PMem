"""Small shared lifecycle vocabulary; owning services retain all write authority."""
from datetime import datetime,timezone

REVIEW_ACTIONS={'accept':{'submitted'},'reject':{'submitted','accepted'},
    'authorize':{'accepted'},'cancel':{'submitted','accepted','authorized'},
    'reconcile':{'executing','needs_recovery'}}


def event(change,action,actor,reason=''):
    from .approval_matrix import snapshot, decide
    if action in {'rebase','rebase_tracking'} and change.get('approval_matrix'):
        from copy import deepcopy
        change.setdefault('prior_approval_matrices',[]).append(deepcopy(change['approval_matrix']))
    if action in {'submit','rebase','rebase_tracking'}:snapshot(change)
    complete=decide(change,action,actor) if action in {'accept','authorize'} else None
    change['revision']+=1
    change['history'].append({'revision':change['revision'],'action':action,'actor':actor,
        'reason':reason,'at':datetime.now(timezone.utc).isoformat(),
        **({'stage_complete':complete} if complete is not None else {})})
