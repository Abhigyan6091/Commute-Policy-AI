from pathlib import Path
from typing import Literal
from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    environment: Literal['development', 'production', 'test'] = 'production'
    data_dir: Path = Field(default=Path('data/runtime'), validation_alias=AliasChoices('DATA_DIR', 'DATABASE_PATH'))
    jwt_secret: SecretStr = Field(validation_alias=AliasChoices('JWT_SECRET', 'JWT_SECRET_KEY'))
    jwt_algorithm: Literal['HS256'] = 'HS256'
    jwt_issuer: str = 'commutepolicy'
    jwt_audience: str = 'commutepolicy-api'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    embedding_device: str = 'cpu'
    llm_provider: Literal['openai_compatible', 'mock'] = 'openai_compatible'
    llm_api_key: SecretStr = SecretStr('')
    llm_model: str = ''
    llm_base_url: str = ''
    llm_timeout: float = Field(2.2, gt=0, le=30)
    llm_max_tokens: int = Field(700, ge=100, le=2000)
    request_deadline: float = Field(2.9, gt=0, le=30)
    retrieval_mode: Literal['dense', 'hybrid'] = 'hybrid'
    relevance_threshold: float = Field(0.24, ge=-1, le=1)
    chunk_tokens: int = Field(600, ge=100, le=1000)
    chunk_overlap: int = Field(80, ge=0)
    max_upload_bytes: int = Field(10_000_000, ge=1024)
    max_text_chars: int = Field(500_000, ge=1024)
    max_pages: int = Field(150, ge=1)
    requests_per_minute: int = Field(60, ge=1)
    cache_ttl: float = Field(0, ge=0, le=300)
    cache_entries: int = Field(256, ge=1)
    @model_validator(mode='after')
    def check(self):
        if len(self.jwt_secret.get_secret_value().encode()) < 32:
            raise ValueError('JWT_SECRET must contain at least 32 bytes')
        if self.chunk_overlap >= self.chunk_tokens:
            raise ValueError('Overlap must be smaller than chunk size')
        if self.environment == 'production':
            if not self.llm_model or not self.llm_api_key.get_secret_value():
                raise ValueError('Configure LLM_MODEL and LLM_API_KEY for production')
            if not self.llm_base_url.startswith('https://'):
                raise ValueError('LLM_BASE_URL must use HTTPS in production')
        elif self.environment == 'development':
            if self.llm_provider == 'openai_compatible' and self.llm_api_key.get_secret_value():
                if not self.llm_model:
                    raise ValueError('Configure LLM_MODEL when LLM_API_KEY is provided')
                if not (self.llm_base_url.startswith('https://') or self.llm_base_url.startswith('http://localhost') or self.llm_base_url.startswith('http://127.0.0.1')):
                    raise ValueError('LLM_BASE_URL must use HTTPS or localhost')
        return self
