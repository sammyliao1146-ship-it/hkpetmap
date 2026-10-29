"""Resize existing local photos in worker threads; never fetch or re-download Google content."""
from collections import OrderedDict
import hashlib
from io import BytesIO
from pathlib import Path
import threading
import os
import tempfile

from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi.responses import FileResponse, Response

_lock = threading.Lock()
_resize_slots = threading.BoundedSemaphore(2)
_variants = OrderedDict()
_variant_bytes = 0
MAX_BYTES = 8 * 1024 * 1024
MAX_ENTRIES = 64
_fingerprints = OrderedDict()


def variant_path(path, size):
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _lock:
        digest = _fingerprints.get(key)
    if digest is None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:24]
        with _lock:
            if len(_fingerprints) >= 2048:
                _fingerprints.popitem(last=False)
            _fingerprints[key] = digest
    return path.parent / '.variants' / f'{path.name}-{digest}-webp76-v1-{size}.webp'


def prepare_variants(path):
    """Materialise both sizes beside a validated local original; no network access."""
    written = 0
    for size in ('thumb', 'detail'):
        target = variant_path(path, size)
        if target.is_file():
            continue
        response = photo_response(path, size)
        if not hasattr(response, 'body') or response.media_type != 'image/webp':
            continue
        target.parent.mkdir(exist_ok=True)
        # Atomic replacement also makes concurrent manual builds safe.
        fd, temporary = tempfile.mkstemp(dir=target.parent, suffix='.tmp')
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(response.body)
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        written += 1
    return written


def photo_response(path: Path, size: str, if_none_match: str | None = None):
    global _variant_bytes
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size, size)
    etag = '"' + hashlib.sha256(repr(key).encode()).hexdigest()[:24] + '"'
    # Preserve source-specific browser-only policy; no shared-cache extension for Google photos.
    headers = {'Cache-Control':'private, max-age=86400','ETag':etag,'X-Content-Type-Options':'nosniff'}
    if if_none_match and (etag in if_none_match.split(', ') or if_none_match == '*'):
        return Response(status_code=304,headers=headers)
    if size == 'original':
        return FileResponse(path,headers=headers)
    prepared = variant_path(path, size)
    if prepared.is_file():
        return FileResponse(prepared, media_type='image/webp', headers=headers)
    with _lock:
        body = _variants.get(key)
        if body is not None:
            _variants.move_to_end(key)
    if body is None:
        try:
            with _resize_slots, Image.open(path) as image:
                if image.width*image.height>24_000_000:
                    return FileResponse(path,headers=headers)
                image = ImageOps.exif_transpose(image)
                edge = 240 if size == 'thumb' else 768
                image.thumbnail((edge,edge),Image.Resampling.LANCZOS)
                if image.mode not in ('RGB','RGBA'):
                    image=image.convert('RGBA' if 'transparency' in image.info else 'RGB')
                output=BytesIO()
                image.save(output,format='WEBP',quality=76,method=4)
                body=output.getvalue()
        except (OSError,UnidentifiedImageError,Image.DecompressionBombError):
            return FileResponse(path,headers=headers)
        with _lock:
            if key not in _variants and len(body)<=MAX_BYTES:
                while _variants and (len(_variants)>=MAX_ENTRIES or _variant_bytes+len(body)>MAX_BYTES):
                    _,old=_variants.popitem(last=False);_variant_bytes-=len(old)
                _variants[key]=body;_variant_bytes+=len(body)
    return Response(body,media_type='image/webp',headers=headers)
