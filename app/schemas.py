from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Principal(StrictModel):
    user_id: str = Field(min_length=1, max_length=100)
    employee_id: str = Field(min_length=1, max_length=100)
    company_id: str = Field(pattern=r'^COMPANY_[A-Z0-9_]{1,40}$')
    role: Literal['employee', 'policy_admin']

class Question(StrictModel):
    question: str = Field(min_length=1, max_length=2000)
    @field_validator('question')
    @classmethod
    def normalize(cls, value):
        value = ' '.join(value.split())
        if not value:
            raise ValueError('Question is empty')
        return value

class Chunk(StrictModel):
    chunk_id: str
    company_id: str
    policy_id: str
    policy_version: str
    document_name: str
    section_number: str
    section_title: str
    page_number: int | None = None
    text: str
    content_hash: str

class Support(StrictModel):
    chunk_id: str
    quote: str = Field(min_length=1, max_length=1800)

class Draft(StrictModel):
    status: Literal['answered', 'not_covered', 'needs_clarification']
    answer: str = Field(default='', max_length=6000)
    citation_chunk_ids: list[str] = Field(default_factory=list, max_length=3)
    support: list[Support] = Field(default_factory=list, max_length=3)
    clarifying_question: str | None = Field(default=None, max_length=300)
    @model_validator(mode='after')
    def consistency(self):
        if self.status == 'answered':
            ids = [s.chunk_id for s in self.support] if self.support else self.citation_chunk_ids
            if not ids or len(set(ids)) != len(ids):
                raise ValueError('Citations must be non-empty and unique')
            if self.clarifying_question is not None:
                raise ValueError('Answered response cannot request clarification')
        else:
            if self.citation_chunk_ids or self.support:
                raise ValueError('Non-answer must not assert evidence')
        return self

class Citation(StrictModel):
    chunk_id: str
    document: str = ''
    document_name: str | None = None
    section: str = ''
    section_number: str | None = None
    section_title: str = ''
    page: int | None = None
    page_number: int | None = None
    quote: str = ''

    @model_validator(mode='before')
    @classmethod
    def normalize_fields(cls, data):
        if isinstance(data, dict):
            if not data.get('document') and data.get('document_name'):
                data['document'] = data['document_name']
            if not data.get('section') and data.get('section_number'):
                data['section'] = data['section_number']
            if data.get('page') is None and data.get('page_number') is not None:
                data['page'] = data['page_number']
        return data

class ChatResponse(StrictModel):
    request_id: str
    status: Literal['answered', 'not_covered', 'needs_clarification', 'temporary_error']
    answer: str
    citations: list[Citation] = Field(default_factory=list, max_length=3)
    policy_version: str | None = None
    clarifying_question: str | None = None
    fallback: str = 'Please contact your company transport desk for assistance.'
    llm_calls: int = Field(0, ge=0, le=2)
    timings_ms: dict[str, float] = Field(default_factory=dict)
    cached: bool = False

class Feedback(StrictModel):
    request_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    helpful: bool
    reason: str = Field('', max_length=500)

class Version(StrictModel):
    id: str
    company_id: str
    number: int
    document: str
    status: Literal['STAGING', 'ACTIVE', 'SUPERSEDED', 'FAILED']
    created: str
    error: str | None

class AuditEvent(StrictModel):
    id: int
    company_id: str
    actor: str
    event: str
    request_id: str
    detail: str
    created: str
