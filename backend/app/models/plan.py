from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from backend.app.models.assistant import ChatOrigin


class PlanRequest(BaseModel):
    date: Date
    region: Literal['hong_kong_island', 'kowloon', 'new_territories', 'any'] = 'any'
    district: str = Field(default='', max_length=80)
    interests: list[Literal['park', 'vet', 'activity', 'mall']] = Field(default_factory=lambda: ['park'], max_length=4)
    cuisine: str = Field(default='', max_length=80)
    random: bool = False
    destination_id: str | None = Field(default=None, max_length=100)
    origin: ChatOrigin | None = None
    language: Literal['en', 'zh-Hant'] = 'en'


class PlanPreferences(BaseModel):
    """User choices only; unknown/unsupported constraints must retain the general Agent path."""
    model_config = ConfigDict(extra='forbid')
    date: Date | None = None
    region: Literal['hong_kong_island', 'kowloon', 'new_territories', 'any'] = 'any'
    district: str = Field(default='', max_length=80)
    interests: list[Literal['park', 'vet', 'activity', 'mall']] | None = Field(default=None, max_length=4)
    cuisine: str = Field(default='', max_length=80)
    random: bool = False
    destination_id: Literal['west-kowloon','science-park','stanley','kwun-tong-waterfront',
                            'central-waterfront','tseung-kwan-o','tai-po-waterfront',
                            'tung-chung','lam-tei'] | None = None
    unsupported_constraints: list[str] = Field(default_factory=list, max_length=8)
