from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict


class CameoConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['draft'] = 'draft'
    native_operations_enabled: Literal[False] = False
    cameo_home: str = ''
    mdk_descriptor: str = ''
    cameo_version: str = ''
    mdk_version: str = ''
    mms_version: str = ''
    mms_url: str = ''
    credential_reference: str = ''
    export_profile: Literal['sysml-v1'] = 'sysml-v1'


def inspect_local(config: CameoConfig):
    """Local CLI only: existence is evidence, not proof of compatibility."""
    home = Path(config.cameo_home) if config.cameo_home else None
    descriptor = Path(config.mdk_descriptor) if config.mdk_descriptor else None
    return {'status': 'unverified', 'native_operations_enabled': False,
        'checks': {'cameo_directory_exists': bool(home and home.is_dir()),
                   'mdk_descriptor_exists': bool(descriptor and descriptor.is_file()),
                   'versions_declared': bool(config.cameo_version and config.mdk_version),
                   'mms_configured': bool(config.mms_url)},
        'pending': ['Verify version compatibility with the MDK compatibility matrix',
                    'Confirm MDK loaded in Cameo Plugin Manager',
                    'Validate model export and MMS authentication in the customer environment']}
