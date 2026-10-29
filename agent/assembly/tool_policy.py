"""Only offer tools needed by the validated intent; ambiguous routes retain read tools."""
PLACE = {'search_pet_places', 'get_pet_place_details'}
ACTIVITY = {'search_pet_activities', 'get_pet_activity_details'}
TRANSPORT = {'get_pet_transport', 'get_pet_directions', 'get_pet_parking'}


def tool_names(intent):
    return {
        'map_query': PLACE | ACTIVITY | {'get_pet_parking'},
        'transport': PLACE | TRANSPORT,
        'pet_policy': PLACE | {'get_pet_transport', 'search_pet_web_knowledge'},
        'trip_plan': PLACE | ACTIVITY | TRANSPORT | {'search_pet_web_knowledge'},
    }.get(intent, PLACE | ACTIVITY | TRANSPORT | {'search_pet_web_knowledge'})
