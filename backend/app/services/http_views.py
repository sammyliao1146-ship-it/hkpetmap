"""Version-keyed JSON bytes and cheap conditional responses for immutable published snapshots."""
import hashlib
import json
from fastapi.responses import Response


def versioned_json(request, pets, kind, factory, policy='private, no-cache'):
    revision=pets.data_revision()
    etag='"'+hashlib.sha256((revision+':'+kind).encode()).hexdigest()[:24]+'"'
    if request.headers.get('authorization') or request.headers.get('cookie'):
        policy='private, no-store'
    headers={'ETag':etag,'Cache-Control':policy}
    validators=[v.strip().removeprefix('W/') for v in request.headers.get('if-none-match','').split(',')]
    if etag in validators or '*' in validators:
        return Response(status_code=304,headers=headers)
    if getattr(pets,'_http_revision',None)!=revision:
        pets._http_revision=revision;pets._http_bytes={}
    if kind not in pets._http_bytes:
        pets._http_bytes[kind]=json.dumps(factory(),ensure_ascii=False,separators=(',',':')).encode()
    return Response(pets._http_bytes[kind],media_type='application/json',headers=headers)
