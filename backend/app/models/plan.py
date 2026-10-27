from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field
from backend.app.models.assistant import ChatOrigin


class PlanRequest(BaseModel):
    date: Date
    region: Literal['hong_kong_island', 'kowloon', 'new_territories', 'any'] = 'any'
    interests: list[Literal['park', 'vet', 'activity', 'mall']] = Field(default_factory=lambda: ['park'], min_length=1, max_length=4)
    cuisine: str = Field(default='', max_length=80)
    random: bool = False
    destination_id: str | None = Field(default=None, max_length=100)
    origin: ChatOrigin | None = None
    language: Literal['en', 'zh-Hant'] = 'en'
