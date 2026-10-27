from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatOrigin(BaseModel):
    latitude: float = Field(ge=-90,le=90,allow_inf_nan=False)
    longitude: float = Field(ge=-180,le=180,allow_inf_nan=False)


class ChatRequest(BaseModel):
    language: Literal["zh-Hant", "en"] = "zh-Hant"
    message: str = Field(min_length=1, max_length=8000, pattern=r"\S")
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)
    origin: ChatOrigin | None = None
    session_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{8,64}$")


class PrefillRequest(ChatOrigin):
    language: Literal["zh-Hant", "en"] = "zh-Hant"


class IntentRouting(BaseModel):
    intent: Literal['map_query','trip_plan','transport','pet_policy','pet_health','restaurant_info','assistant_identity','out_of_scope']
    map_mode: Literal['distance','rating','cuisine','random','general','none']
    confidence: float = Field(ge=0,le=1)
    action: Literal['main_agent','web_agent','self_intro','refuse','clarify']
    classifier_model: str


class KnowledgeSource(BaseModel):
    title: str = ''
    url: str


class PlaceRef(BaseModel):
    id: str
    name: str


class ChatResponse(BaseModel):
    answer: str
    model: str
    routing: IntentRouting | None = None
    sources: list[KnowledgeSource] = Field(default_factory=list)
    degraded: bool = False
    places: list[PlaceRef] = Field(default_factory=list)
