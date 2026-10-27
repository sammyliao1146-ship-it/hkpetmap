from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator, field_validator


class PlacePhoto(BaseModel):
    url: HttpUrl | Annotated[str, Field(pattern=r"^/api/v1/facility-photos/[0-9a-f]{24}$")]
    source_url: HttpUrl
    credit: str
    alt: str
    authors: list[dict] = Field(default_factory=list)


class MallPolicy(BaseModel):
    tier: Literal['on_leash_full', 'designated_zone', 'carrier_only', 'unknown']
    verification: Literal['official_checked', 'third_party']
    listing_url: HttpUrl
    listing_updated_at: str
    checked_at: str | None = None
    official_policy_url: HttpUrl | None = None
    venue_kind: Literal['shopping_mall', 'retail_precinct', 'department_store', 'commercial_building', 'retail_destination'] = 'shopping_mall'

    @model_validator(mode='after')
    def official_evidence(self):
        if self.verification == 'official_checked' and (not self.checked_at or not self.official_policy_url):
            raise ValueError('Official checks require a policy URL and check date')
        return self


class RestaurantDetails(BaseModel):
    google_place_id: str
    display_name: str | None = None
    display_name_language: str | None = None
    google_address: str | None = None
    match_status: str = 'matched'
    match_distance_m: float | None = None
    rating: float | None = None
    rating_count: int | None = None
    price_level: str | None = None
    price_range: dict | None = None
    website: HttpUrl | None = None
    telephone: str | None = None
    hours: list[str] = Field(default_factory=list)
    reservable: bool | None = None
    booking_url: HttpUrl | None = None
    menu_url: HttpUrl | None = None
    google_maps_url: HttpUrl | None = None
    reviews_url: HttpUrl | None = None
    reviews: list[dict] = Field(default_factory=list)
    dish_photo_url: str | None = None
    dish_photo_source_url: HttpUrl | None = None
    dish_photo_credit: str | None = None
    dish_photo_kind: str | None = None
    photo_url: str | None = None
    photo_source_url: HttpUrl | None = None
    photo_credit: str | None = None
    photo_authors: list[dict] = Field(default_factory=list)
    fetched_at: str | None = None


class Place(BaseModel):
    id: str
    category: str
    name: str
    name_en: str | None = None
    restaurant_details: RestaurantDetails | None = None
    mall_policy: MallPolicy | None = None
    photos: list[PlacePhoto] = Field(default_factory=list)
    district: str | None = None
    address: str | None = None
    address_en: str | None = None
    latitude: float | None = Field(default=None, ge=22.1, le=22.6)
    longitude: float | None = Field(default=None, ge=113.8, le=114.5)
    coordinate_source: str | None = None
    cuisines: list[str] = Field(default_factory=list)
    cuisine_source: HttpUrl | None = None
    telephone: str | None = None
    opening_hours_en: str | None = None
    opening_hours: str | None = None
    website: HttpUrl | None = None
    website_en: HttpUrl | None = None
    source_url: HttpUrl
    source_name: str
    source_name_en: str | None = None
    source_updated_at: str | None = None
    licence_number: str | None = None
    pet_policy: Literal['dogs_permitted', 'designated_area', 'boarding', 'veterinary', 'conditional', 'unknown'] = 'unknown'
    notes: list[str] = Field(default_factory=list)
    notes_en: list[str] = Field(default_factory=list)
    rules_url: HttpUrl | None = None
    rules_url_en: HttpUrl | None = None

    @field_validator('district')
    @classmethod
    def standard_district(cls, value):
        if not value: return None
        value = value.replace('香港', '')
        if value in {'港島東區','香港東區'}: value = '東區'
        return value if value.endswith('區') else value+'區'

    @model_validator(mode='after')
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError('Both coordinates must be present or absent')
        if self.cuisines and not self.cuisine_source:
            raise ValueError('Cuisine labels require a source')
        return self


class Activity(BaseModel):
    id: str
    name: str
    name_en: str | None = None
    category: str = '訓練課程'
    dates_text: str
    start_date: str | None = None
    end_date: str | None = None
    venue_name: str | None = None
    place_id: str | None = None
    district: str | None = None
    language: str | None = None
    fee_text: str | None = None
    description_en: str | None = None
    eligibility_en: str | None = None
    fee_text_en: str | None = None
    language_en: str | None = None
    venue_name_en: str | None = None
    description: str
    eligibility: str | None = None
    registration_status: Literal['unknown', 'open', 'full', 'cancelled'] = 'unknown'
    remaining: int | None = Field(default=None, ge=0)
    source_url: HttpUrl
    booking_url: HttpUrl | None = None
    source_name: str
    source_name_en: str | None = None


class Snapshot(BaseModel):
    published_at: datetime | None = None
    fetched_at: datetime
    places: list[Place]
    activities: list[Activity]
    sources: list[dict]
