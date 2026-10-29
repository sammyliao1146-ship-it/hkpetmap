"""Reject secret-file probes before routing, including direct origin requests."""
import re
from urllib.parse import unquote


def is_secret_probe(path: str) -> bool:
    for _ in range(4):
        if re.search(r'%(?![0-9a-fA-F]{2})', path):
            return True
        try:
            decoded = unquote(path, errors='strict')
        except UnicodeError:
            return True
        if decoded == path:
            break
        path = decoded
    if re.search(r'%(?:25|2e|2f|5c)', path, re.I):
        return True
    for segment in path.replace('\\', '/').split('/'):
        name = segment.lower().split(';')[0].rstrip(' .')
        if re.search(r'^\.(?:env|dev\.vars)(?:[.~]|$)', name) or re.search(
            r'^\.(?:git|svn|hg|aws|ssh|docker|npmrc|pypirc|netrc|htpasswd|htaccess|ds_store)(?:[.~]|$)', name
        ) or re.search(r'^(?:id_rsa|id_dsa|id_ecdsa|id_ed25519|wp-config\.php)(?:[.~]|$)', name):
            return True
    return False
