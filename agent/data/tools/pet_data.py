from agents import function_tool
from typing import Literal
from agent.data.data_access import PetDataAccess

def make_pet_queries(access: PetDataAccess):
    async def get_pet_catalog() -> dict:
        """Get Hong Kong time, supported pet categories, cuisine labels and source freshness. Only call if the supplied map_context catalogue is missing."""
        return await access.catalog()

    async def search_pet_places(mode: str='', category: str='', cuisine: str='', district: str='', query: str='', limit: int=5,
                                sort_by: Literal['default','distance','rating','random']='default',
                                latitude: float | None=None, longitude: float | None=None, origin_place_id: str='',
                                radius_m: float | None=None, min_rating: float | None=None, max_price: float | None=None) -> dict:
        """Filter the ENTIRE local map by catalogue cuisine/category, district and query, then order/sample before returning limit results.
        sort_by=distance: nearest first by straight-line metres (not walking/driving), requires explicit origin coordinates or origin_place_id; shared chat location is used automatically for function tools.
        sort_by=rating: highest stored Google rating first, ties by rating_count; unrated places excluded. Never call this a live rating.
        sort_by=random: unbiased sample without replacement from ALL matching places, not the first page. Combine any mode with cuisine/district, min_rating (0..5), and radius_m (positive metres, up to 100km).
        max_price=HKD per person budget cap (e.g. 'under 200' -> 200), matched against the stored Google price range upper bound; restaurants without price data are excluded and counted in excluded_without_price. Tell the user prices are Google estimates, not menu prices.
        To find highest rated nearby places, use sort_by=rating AND radius_m with an origin. For a named start point, first find its actual map ID and set origin_place_id; never invent coordinates. If query_status=needs_location, ask the user for a location instead of guessing. Missing results are not proof of absence. Candidate match_status=needs_review remains unverified.
        """
        return await access.search_places(mode,category,cuisine,district,query,limit,sort_by=sort_by,latitude=latitude,longitude=longitude,origin_place_id=origin_place_id,radius_m=radius_m,min_rating=min_rating,max_price=max_price)

    async def get_pet_place_details(place_id: str, include_reviews: bool=False) -> dict:
        """Read a place's address, policy, provenance, phone and source link. Does not reserve or confirm opening. Set include_reviews only for an explicit review request; returns at most two excerpts."""
        return await access.place_details(place_id,include_reviews=include_reviews)

    async def search_pet_activities(query: str='', category: str='', district: str='', limit: int=5) -> dict:
        """Find pet training courses and activities from connected organizers. Dates may be free text; remaining places are unknown unless explicitly published."""
        return await access.search_activities(query,category,district,limit)

    async def get_pet_activity_details(activity_id: str) -> dict:
        """Read a course's original dates, fees, eligibility and organizer registration link."""
        return await access.activity_details(activity_id)

    async def get_pet_transport() -> dict:
        """Get sourced pet transport rules and known boarding points. No live vehicle availability or route estimates."""
        return await access.transport()

    async def get_pet_directions(place_id: str) -> dict:
        """Get walking/driving Google Maps links to a saved map venue, plus pet transport restrictions.
        Resolve the destination's actual place ID first. Ask which venue if history contains multiple candidates.
        Shared origin coordinates are included when available; otherwise Maps asks for a start point.
        Present the returned URLs as clickable Markdown links, e.g. [Walking directions](url).
        Links do not verify route access for pets, travel times, fares or availability. Do not recommend transit by default.
        """
        return await access.directions(place_id)
    async def get_pet_parking(place_id: str, limit: int=5) -> dict:
        """Read published car parks within 1,000 straight-line metres of a saved venue. Query each planned stop; a shared parking ID proves per-stop radius coverage only, never walkability. Never treat a mall as parking unless an actual parking: ID is returned. Saved vacancy may be unknown/stale; this does not confirm venue pet access."""
        return await access.nearby_parking(place_id,limit)
    return [get_pet_catalog,search_pet_places,get_pet_place_details,search_pet_activities,get_pet_activity_details,get_pet_transport,get_pet_directions,get_pet_parking]

def make_pet_tools(access):
    return [function_tool(query) for query in make_pet_queries(access)]
