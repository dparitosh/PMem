from fastapi import APIRouter
from .config import CameoConfig

router = APIRouter(prefix='/cameo-mdk', tags=['Cameo MDK preparation'])


@router.get('/template')
def template():
    return CameoConfig().model_dump()


@router.post('/validate')
def validate(config: CameoConfig):
    # Do not probe client-supplied filesystem paths or URLs through HTTP.
    return {'status': 'draft', 'native_operations_enabled': False,
            'export_profile': config.export_profile,
            'missing': [key for key in ('cameo_home', 'mdk_descriptor', 'cameo_version', 'mdk_version') if not getattr(config, key).strip()],
            'compatibility': 'unverified', 'connection_tested': False}
