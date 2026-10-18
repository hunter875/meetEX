from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from zoneinfo import ZoneInfo

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')

class ProjectCreate(Strict):
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default='', max_length=3000)
    glossary: dict[str, str] = Field(default_factory=dict)
    @field_validator('glossary')
    @classmethod
    def glossary_budget(cls,value):
        import json
        if len(json.dumps(value,ensure_ascii=False))>5000:raise ValueError('Glossary is limited to 5000 characters')
        return value

class ProjectPatch(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=3000)
    glossary: dict[str, str] | None = None
    @field_validator('glossary')
    @classmethod
    def glossary_budget(cls,value):
        return ProjectCreate.glossary_budget(value) if value is not None else value

class SourceInput(Strict):
    kind: Literal['repo', 'text', 'schema', 'tickets_csv', 'tickets_json', 'data_csv']
    title: str = Field(min_length=1, max_length=200)
    local_path: str | None = Field(default=None, max_length=4096)
    pasted_text: str | None = Field(default=None, max_length=10*1024*1024)
    mapping: dict[str, str] = Field(default_factory=lambda:dict(id='id',title='title',description='description',status='status',updated_at='updated_at',url='url'))
    @field_validator('pasted_text')
    @classmethod
    def safe_text(cls,value):
        if value is not None and ('\0' in value or 'PRIVATE KEY-----' in value):raise ValueError('Binary text or private key content is excluded')
        return value

class SearchInput(Strict):
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)

class MeetingCreate(Strict):
    project_id: str
    title: str = Field(min_length=1, max_length=200)
    timezone: str = 'America/Los_Angeles'
    persistence_mode: Literal['local', 'memory'] = 'local'
    demo: bool = False
    meeting_key: str | None = None
    @field_validator('timezone')
    @classmethod
    def timezone_known(cls, value):
        try: ZoneInfo(value)
        except Exception: raise ValueError('Unknown IANA timezone')
        return value

class Control(Strict):
    action: Literal['pause', 'resume', 'end', 'interrupt']
    idempotency_key: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=150)

class MeetingPrefs(Strict):
    self_speaker: str | None = None
    auto_mode: bool | None = None
    confirmed_segment_ids: list[str] | None = Field(default=None,max_length=50)

class Caption(Strict):
    type: Literal['caption.upsert'] = 'caption.upsert'
    protocol_version: Literal[1] = 1
    event_id: str = Field(min_length=1, max_length=100)
    capture_epoch: str = Field(min_length=1, max_length=100)
    segment_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=1)
    seq: int = Field(ge=1)
    speaker_label: str | None = Field(default=None, max_length=200)
    text: str = Field(min_length=1, max_length=10000)
    observed_at: str
    stable: bool
    adapter_version: str = Field(max_length=100)
    @field_validator('observed_at')
    @classmethod
    def utc_timestamp(cls, value):
        from datetime import datetime
        if datetime.fromisoformat(value.replace('Z','+00:00')).tzinfo is None:
            raise ValueError('observed_at requires timezone')
        return value

class SuggestInput(Strict):
    action: Literal['auto', 'suggest', 'shorter', 'explain', 'clarify', 'ask'] = 'suggest'
    base_suggestion_id: str | None = None
    selected_segment_ids: list[str] = Field(default_factory=list, max_length=50)
    question: str = Field(default='', max_length=2000)
    response_mode: Literal['auto', 'fast', 'explain', 'deep', 'clarify'] = 'auto'

class RoutingDecision(Strict):
    version: str = 'rules-v1'
    route: Literal['fast', 'explain', 'deep', 'clarify', 'listen']
    automatic_route: Literal['fast', 'explain', 'deep', 'clarify', 'listen']
    source: Literal['automatic', 'manual'] = 'automatic'
    reasons: list[str]
    risks: list[str]
    evidence_state: Literal['missing', 'available', 'stale', 'conflicting']
    requires_verification: bool
    trigger_segment_ids: list[str]
    target_min_s: float
    target_max_s: float
    classifier_ms: float

class Finding(Strict):
    text_vi: str = Field(max_length=1200)
    source_ids: list[str]

class SuggestionPayload(Strict):
    input_revision: int
    intent: Literal['question', 'request', 'decision', 'update', 'other']
    meaning_vi: str = Field(max_length=3000)
    findings: list[Finding] = Field(max_length=12)
    reply_en: str = Field(min_length=1, max_length=1400)
    reply_vi: str = Field(max_length=2000)
    clarification_en: str = Field(max_length=600)
    evidence_status: Literal['supported', 'partial', 'missing', 'conflicting']
    uncertainties: list[str] = Field(max_length=12)
    supporting_segment_ids: list[str]

class ReportItem(Strict):
    id: str
    text: str = Field(max_length=4000)
    text_en: str = Field(default='', max_length=4000)
    evidence_segment_ids: list[str]
    origin: Literal['transcript', 'user_edit', 'ai_proposal']
    confirmation: Literal['confirmed', 'unconfirmed', 'proposed'] = 'unconfirmed'
    owner: str | None = None
    raw_due_text: str | None = None
    normalized_due: str | None = None
    status: str = 'open'

class ReportPayload(Strict):
    summary_vi: str = Field(default='', max_length=15000)
    summary_en: str = Field(default='', max_length=15000)
    summary_segment_ids: list[str] = Field(default_factory=list)
    requirements: list[ReportItem] = Field(default_factory=list)
    decisions: list[ReportItem] = Field(default_factory=list)
    action_items: list[ReportItem] = Field(default_factory=list)
    open_questions: list[ReportItem] = Field(default_factory=list)
    ai_proposals: list[ReportItem] = Field(default_factory=list)
    capture_warnings: list[str] = Field(default_factory=list)

class ReportGenerate(Strict):
    transcript_revision: int

class ReportEdit(Strict):
    expected_version: int
    payload: ReportPayload
    reviewed: bool = False

class Credential(Strict):
    api_key: SecretStr

class SettingsPatch(Strict):
    provider_url: str | None = None
    model: str | None = Field(default=None,min_length=1,max_length=200)
    auto_mode: bool | None = None
    retention_days: int | None = Field(default=None,ge=1,le=3650)
    persistence_mode: Literal['local','memory'] | None = None
    semantic_enabled: bool | None = None
    auto_per_minute: int | None = Field(default=None,ge=1,le=60)
    sentence_limit: int | None = Field(default=None,ge=1,le=3)
    price_input: float | None = Field(default=None,ge=0)
    price_output: float | None = Field(default=None,ge=0)
    price_date: str | None = None
    @field_validator('provider_url')
    @classmethod
    def https_only(cls,value):
        from urllib.parse import urlparse
        if value is not None and (urlparse(value).scheme != 'https' or not urlparse(value).hostname or urlparse(value).username or urlparse(value).query or urlparse(value).fragment):
            raise ValueError('Provider requires HTTPS URL without credentials/query/fragment')
        return value.rstrip('/') if value else value

# Response models drive generated TypeScript contracts. Additional server metadata is preserved.
class DTO(BaseModel):
    model_config=ConfigDict(extra='allow')

class ProjectDTO(ProjectCreate):
    id:str
    created_at:str

class SegmentDTO(DTO):
    id:str
    capture_epoch:str
    revision:int
    speaker:str|None
    text:str
    stable:bool
    observed_from:str
    observed_to:str

class CitationDTO(DTO):
    id:str
    source_id:str
    project_id:str
    generation:int
    content:str
    title:str
    kind:str
    path:str
    line_start:int
    line_end:int
    indexed_at:str
    content_hash:str
    stale:bool=False
    source_changed:bool=False
    source_deleted:bool=False

class AISnapshot(DTO):
    meeting_id:str
    project_id:str
    transcript_revision:int
    index_generation:dict[str,int]
    segments:list[SegmentDTO]
    memory:list[SegmentDTO]=Field(default_factory=list)
    sources:list[CitationDTO]
    action:str
    question:str
    input_hash:str
    routing:RoutingDecision|None=None

class SuggestionDTO(DTO):
    id:str
    request_id:str
    created_at:str
    mode:str
    payload:SuggestionPayload
    snapshot:AISnapshot
    stale:bool
    automatic:bool
    duration_ms:float

class ReportDTO(DTO):
    id:str
    meeting_id:str
    version:int
    transcript_revision:int
    payload:ReportPayload
    user_edits:bool
    reviewed_at:str|None
    mode:str
    created_at:str
    parent_id:str|None

class MeetingDTO(DTO):
    id:str
    project_id:str
    title:str
    timezone:str
    persistence_mode:str
    demo:bool
    meeting_key:str|None
    status:str
    started_at:str
    ended_at:str|None
    transcript_revision:int
    capture_status:str
    last_caption_at:str|None
    self_speaker:str|None
    auto_mode:bool
    confirmed_segment_ids:list[str]=Field(default_factory=list)

class AIRequestDTO(DTO):
    id:str
    action:str
    status:str
    error:dict[str,Any]|None
    snapshot:AISnapshot

class SnapshotDTO(MeetingDTO):
    segments:list[SegmentDTO]
    suggestions:list[SuggestionDTO]
    requests:list[AIRequestDTO]
    reports:list[ReportDTO]
    gaps:list[dict[str,Any]]
