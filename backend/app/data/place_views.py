"""Map cards need identity, coordinates and filter fields, not full reviews or galleries."""
import hashlib

CARD_DETAILS = {'google_place_id','display_name','match_status','rating','rating_count','price_level',
                'photo_url','photo_credit'}


def map_summary(place):
    row=place.model_dump(mode='json',exclude={'restaurant_details','photos','notes','notes_en'})
    row['notes']=place.notes if place.category in {'pet_parks','inclusive_parks'} else []
    row['notes_en']=place.notes_en if place.category in {'pet_parks','inclusive_parks'} else []
    row['restaurant_details']=place.restaurant_details.model_dump(mode='json',include=CARD_DETAILS) if place.restaurant_details else None
    row['photos']=[p.model_dump(mode='json',exclude={'authors'}) for p in place.photos[:1]]
    row['detail_loaded']=False
    return row


def revision_of(snapshot):
    payload=snapshot.model_dump_json() if snapshot else 'empty'
    return hashlib.sha256(payload.encode()).hexdigest()[:24]
