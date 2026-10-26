"""Gateway-only settings; AOI account credentials never enter PMem requests."""
from dataclasses import dataclass, field
import os
from pathlib import Path


def number(name, default, maximum):
    try:
        value = int(os.getenv(name, str(default)))
        if not 1 <= value <= maximum:
            raise ValueError()
        return value
    except ValueError:
        raise ValueError('Invalid ' + name) from None


@dataclass(frozen=True)
class Settings:
    token: str = field(repr=False)
    vendor_dir: Path
    username: str = field(default='', repr=False)
    password: str = field(default='', repr=False)
    model: str = 'aoi-chat'
    embedding_model: str = 'aoi-embedding'
    upstream_model: str = 'gpt-4o'
    deployment: str = ''
    upstream_embedding_model: str = 'text-embedding-ada-002'
    embedding_deployment: str = ''
    embedding_dimensions: int = 1536
    timeout: int = 45
    startup_timeout: int = 45

    @classmethod
    def from_env(cls):
        token = os.getenv('AOI_GATEWAY_TOKEN', '').strip()
        if len(token) < 32 or '<' in token or any(c.isspace() for c in token):
            raise ValueError('Set AOI_GATEWAY_TOKEN to a private random token of at least 32 characters')
        directory = os.getenv('AOI_WRAPPER_DIR', '')
        if not directory or not Path(directory).is_absolute():
            raise ValueError('AOI_WRAPPER_DIR must be an absolute private wrapper-copy directory')
        return cls(token=token, vendor_dir=Path(directory).resolve(),
                   username=os.getenv('AOI_USERNAME', ''), password=os.getenv('AOI_PASSWORD', ''),
                   model=os.getenv('AOI_MODEL', 'aoi-chat').strip(),
                   embedding_model=os.getenv('AOI_EMBED_MODEL', 'aoi-embedding').strip(),
                   upstream_model=os.getenv('AOI_LLM_MODEL_NAME', 'gpt-4o').strip(),
                   deployment=os.getenv('AOI_LLM_DEPLOYMENT', '').strip(),
                   upstream_embedding_model=os.getenv('AOI_EMBED_MODEL_NAME', 'text-embedding-ada-002').strip(),
                   embedding_deployment=os.getenv('AOI_EMBED_DEPLOYMENT', '').strip(),
                   embedding_dimensions=number('AOI_EMBEDDING_DIMENSIONS', 1536, 8192),
                   timeout=number('AOI_REQUEST_TIMEOUT_SECONDS', 45, 120),
                   startup_timeout=number('AOI_STARTUP_TIMEOUT_SECONDS', 45, 120))

    def missing(self):
        values = {'AOI_USERNAME': self.username, 'AOI_PASSWORD': self.password,
                  'AOI_MODEL': self.model, 'AOI_EMBED_MODEL': self.embedding_model,
                  'AOI_LLM_MODEL_NAME': self.upstream_model,
                  'AOI_EMBED_MODEL_NAME': self.upstream_embedding_model,
                  'AOI_LLM_DEPLOYMENT': self.deployment,
                  'AOI_EMBED_DEPLOYMENT': self.embedding_deployment}
        return sorted(key for key, value in values.items() if not value or '<' in value)
