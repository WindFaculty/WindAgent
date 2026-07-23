"""
URL Sanitization & SSRF Guard for WindAgent Provider Subsystem V3 Test Connect.
Prevents SSRF attacks, cloud metadata scraping, and malicious protocol redirects.
"""

from __future__ import annotations
import ipaddress
from urllib.parse import urlparse

_METADATA_HOSTS = {
    "169.254.169.254",
    "169.254.169.253",
    "metadata.google.internal",
    "instance-data",
    "100.100.100.200",
}

_ALLOWED_SCHEMES = {"http", "https"}


def sanitize_url(raw_url: str, allow_lan: bool = True) -> str:
    """
    Sanitizes and validates base URL against SSRF vulnerabilities.
    Returns normalized clean URL string or raises ValueError.
    """
    if not raw_url:
        raise ValueError("URL cannot be empty")

    url_str = raw_url.strip()

    # Check scheme if explicitly present
    if "://" in url_str:
        scheme_prefix = url_str.split("://")[0].lower()
        if scheme_prefix not in _ALLOWED_SCHEMES:
            raise ValueError(
                f"Prohibited URL scheme '{scheme_prefix}'. Only HTTP and HTTPS are permitted."
            )
    else:
        url_str = f"http://{url_str}"

    parsed = urlparse(url_str)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Prohibited URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("Invalid URL hostname")

    # Check cloud metadata hosts
    if hostname in _METADATA_HOSTS:
        raise ValueError(
            f"SSRF Security Block: Access to metadata host '{hostname}' is forbidden."
        )

    # Check IP addresses
    try:
        ip = ipaddress.ip_address(hostname)
        if ip.is_link_local:
            raise ValueError(
                f"SSRF Security Block: Access to link-local IP '{hostname}' is forbidden."
            )
        if ip.is_multicast:
            raise ValueError(
                f"SSRF Security Block: Access to multicast IP '{hostname}' is forbidden."
            )
        if not allow_lan and (ip.is_private or ip.is_loopback):
            raise ValueError(
                f"LAN/Private IP '{hostname}' is disabled by security policy."
            )
    except ValueError:
        pass

    port_str = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    path_str = parsed.path.rstrip("/")
    clean_url = f"{parsed.scheme}://{hostname}{port_str}{path_str}"
    return clean_url
