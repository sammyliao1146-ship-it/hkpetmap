"""Shared region/district matching for saved place and activity queries."""
REGIONS = {
    'kowloon': {'九龍城','觀塘','深水埗','黃大仙','油尖旺'},
    'hong_kong_island': {'中西','東','南','灣仔'},
    'new_territories': {'離島','葵青','北','西貢','沙田','大埔','荃灣','屯門','元朗'},
}
REGION_ALIASES = {'九龍':'kowloon','九龙':'kowloon','港島':'hong_kong_island','港岛':'hong_kong_island',
    '香港島':'hong_kong_island','香港岛':'hong_kong_island','hong kong island':'hong_kong_island',
    '新界':'new_territories','new territories':'new_territories'}
DISTRICTS = dict(zip(('central and western','eastern','southern','wan chai','kowloon city','kwun tong',
    'sham shui po','wong tai sin','yau tsim mong','islands','kwai tsing','north','sai kung','sha tin',
    'tai po','tsuen wan','tuen mun','yuen long'),
    ('中西','東','南','灣仔','九龍城','觀塘','深水埗','黃大仙','油尖旺','離島','葵青','北','西貢','沙田','大埔','荃灣','屯門','元朗')))


def district_matches(saved, requested):
    key=' '.join((requested or '').strip().casefold().split())
    if not key:return True
    if key.endswith(' district'):key=key[:-9]
    if key in {'hong kong','all hong kong','全港','香港','any'}:return True
    key=key.removesuffix('區')
    value=(saved or '').strip().removesuffix('區')
    value=DISTRICTS.get(value.casefold().removesuffix(' district'),value)
    region=REGION_ALIASES.get(key,key)
    if region in REGIONS:return value in REGIONS[region]
    district=DISTRICTS.get(key,key.removesuffix('區'))
    return bool(value and district in value.casefold())
