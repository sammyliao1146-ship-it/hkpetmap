import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str
    base_url: str
    cors_origins: list[str]
    database_url: str = field(default="", repr=False)
    trace_admin_token: str = field(default="", repr=False)
    agent_tool_transport: str = "function"
    redis_url: str = "redis://127.0.0.1:6379/0"
    cache_prefix: str = "hkpet"
    snapshot_path: str | None = None
    snapshot_poll_seconds: float = 30
    sync_check_seconds: float = 600
    snapshot_max_age_seconds: float = 21600
    chat_rate_limit: int = 20
    chat_rate_window_seconds: int = 60
    chat_rate_hard_limit: int = 60
    llm_max_concurrency: int = 8
    llm_fallback_concurrency: int = 32
    llm_queue_timeout_seconds: float = .25
    fallback_model: str = 'gpt-5.4-nano'
    main_reasoning_effort: str = 'low'
    intent_model: str = 'gpt-5.4-nano'
    intent_confidence_threshold: float = .75
    intent_timeout_seconds: float = 20
    agent_request_timeout_seconds: float = 120.0
    web_search_model: str = 'gpt-5.4-mini'
    web_search_timeout_seconds: float = 60
    web_search_api_key: str = field(default='',repr=False)
    web_search_base_url: str = ''

    def __post_init__(self):
        if min(self.snapshot_poll_seconds,self.sync_check_seconds,self.snapshot_max_age_seconds)<=0:
            raise ValueError('Snapshot polling, sync check and maximum age must be positive')
        if self.chat_rate_limit < 1 or self.chat_rate_hard_limit < self.chat_rate_limit:
            raise ValueError('CHAT_RATE_HARD_LIMIT must be >= CHAT_RATE_LIMIT >= 1')
        if self.llm_max_concurrency < 1 or self.llm_fallback_concurrency < 1 or self.llm_queue_timeout_seconds <= 0:
            raise ValueError('LLM concurrency settings must be positive')
        if not 0 < self.web_search_timeout_seconds <= 90:
            raise ValueError('WEB_SEARCH_TIMEOUT_SECONDS must be in (0, 90]')
        if not 0 < self.intent_confidence_threshold <= 1:
            raise ValueError('INTENT_CONFIDENCE_THRESHOLD must be in (0, 1]')
        if not 0 < self.intent_timeout_seconds <= 60:
            raise ValueError('INTENT_TIMEOUT_SECONDS must be in (0, 60]')
        if not 0 < self.agent_request_timeout_seconds <= 300:
            raise ValueError('AGENT_REQUEST_TIMEOUT_SECONDS must be in (0, 300]')


@lru_cache
def get_settings() -> Settings:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return Settings(
        database_url=os.getenv("DATABASE_URL", ""),
        trace_admin_token=os.getenv("TRACE_ADMIN_TOKEN", ""),
        agent_tool_transport=os.getenv("AGENT_TOOL_TRANSPORT", "function"),
        snapshot_path=os.getenv('PET_SNAPSHOT_PATH') or None,
        snapshot_poll_seconds=float(os.getenv('SNAPSHOT_POLL_SECONDS','30')),
        sync_check_seconds=float(os.getenv('SYNC_CHECK_SECONDS','600')),
        snapshot_max_age_seconds=float(os.getenv('SNAPSHOT_MAX_AGE_SECONDS','21600')),
        api_key=os.getenv("BAI_API_KEY", ""),
        intent_model=os.getenv('INTENT_MODEL','gpt-5.4-nano'),
        intent_confidence_threshold=float(os.getenv('INTENT_CONFIDENCE_THRESHOLD','0.75')),
        intent_timeout_seconds=float(os.getenv('INTENT_TIMEOUT_SECONDS','20')),
        agent_request_timeout_seconds=float(os.getenv('AGENT_REQUEST_TIMEOUT_SECONDS','120')),
        web_search_model=os.getenv('WEB_SEARCH_MODEL','gpt-5.4-mini'),
        web_search_timeout_seconds=float(os.getenv('WEB_SEARCH_TIMEOUT_SECONDS','60')),
        web_search_api_key=os.getenv('WEB_SEARCH_API_KEY',''),
        web_search_base_url=os.getenv('WEB_SEARCH_BASE_URL',''),
        model=os.getenv("BAI_MODEL", "gpt-5.4-mini"),
        base_url=os.getenv("BAI_BASE_URL", "https://api.b.ai/v1"),
        cors_origins=[origin.strip() for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174"
        ).split(",") if origin.strip()],
        redis_url=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"),
        cache_prefix=os.getenv("CACHE_PREFIX", "hkpet"),
        chat_rate_limit=int(os.getenv("CHAT_RATE_LIMIT", "20")),
        chat_rate_window_seconds=int(os.getenv("CHAT_RATE_WINDOW_SECONDS", "60")),
        chat_rate_hard_limit=int(os.getenv("CHAT_RATE_HARD_LIMIT", "60")),
        llm_max_concurrency=int(os.getenv("LLM_MAX_CONCURRENCY", "8")),
        llm_fallback_concurrency=int(os.getenv("LLM_FALLBACK_CONCURRENCY", "32")),
        llm_queue_timeout_seconds=min(.25,float(os.getenv("LLM_QUEUE_TIMEOUT_SECONDS", ".25"))),
        fallback_model=os.getenv("FALLBACK_MODEL", "gpt-5.4-nano"),
        main_reasoning_effort=os.getenv("MAIN_REASONING_EFFORT", "low"),
    )
