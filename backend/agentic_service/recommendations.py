"""Immutable review recommendations stored through the PostgreSQL data layer."""
import copy
from datetime import datetime, timezone
from uuid import uuid4
from backend.mesh_store import PostgresRegistry


class RecommendationStore:
    def __init__(self, store=None):
        self.store = store or PostgresRegistry('agentic_recommendations_v1')

    def create(self, recommendation, owner):
        def check(value):
            if isinstance(value, dict):
                if any(str(key).lower().replace('-', '_') in {'approval_token', 'authorization', 'api_key', 'admin_api_key', 'ollama_api_key', 'password', 'access_token'}
                       or str(key).upper().endswith('_TOKEN') for key in value):
                    raise ValueError('Recommendations must not include credentials')
                for item in value.values():
                    check(item)
            elif isinstance(value, list):
                for item in value:
                    check(item)
        check(recommendation.get('command', {}).get('inputs', {}))
        from .prompt_security import protect
        recommendation = protect(recommendation)
        identifier = 'recommendation-' + uuid4().hex
        record = {**copy.deepcopy(recommendation), 'recommendation_id': identifier,
                  'created_at': datetime.now(timezone.utc).isoformat(), 'owner': owner}
        self.store.create(identifier, record)
        return copy.deepcopy({key: value for key, value in record.items() if key != 'owner'})

    def get(self, identifier, owner):
        record = self.store.get(identifier)
        if record is None:
            raise KeyError(identifier)
        if record.get('owner') != owner:
            raise PermissionError('Recommendation belongs to another identity')
        from .prompt_security import protect
        return protect(copy.deepcopy({key: value for key, value in record.items() if key != 'owner'}))


recommendations = RecommendationStore()
