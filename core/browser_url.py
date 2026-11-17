"""HTTP(S) URL and exact HTTPS-origin validation for the workspace browser."""
import ipaddress
import re
from urllib.parse import urlsplit


def validate_browser_url(value):
    if not isinstance(value, str):
        raise ValueError('Invalid URL')
    url = value.strip()
    if not url or len(url) > 4096 or '\\' in url or any(c.isspace() or not c.isprintable() for c in url):
        raise ValueError('Invalid URL')
    try:
        parts = urlsplit(url)
        if (parts.scheme.lower() not in ('http', 'https') or not parts.hostname or not parts.netloc
                or parts.username is not None or parts.password is not None or '%' in parts.hostname
                or parts.port == 0):
            raise ValueError('Invalid URL')
        host = parts.hostname
        try:
            ipaddress.ip_address(host)
        except ValueError:
            encoded = host.encode('idna').decode('ascii').lower()
            if len(encoded) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p)
                                            for p in encoded.rstrip('.').split('.')):
                raise ValueError('Invalid hostname') from None
        return url
    except (ValueError, UnicodeError):
        raise ValueError('Explicit HTTP(S) URL without credentials required') from None


def https_origin(url):
    parts = urlsplit(validate_browser_url(url))
    if parts.scheme.lower() != 'https':
        raise ValueError('HTTPS required')
    try:
        address = ipaddress.ip_address(parts.hostname)
        host = f'[{address.compressed}]' if address.version == 6 else address.compressed
    except ValueError:
        host = parts.hostname.encode('idna').decode('ascii').lower()
    return 'https://' + host + (f':{parts.port}' if parts.port and parts.port != 443 else '')
