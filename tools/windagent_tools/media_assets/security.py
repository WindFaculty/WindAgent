"""
SSRF-safe URL/IP validation and MIME sniffing (plan 02 §21.1-§21.2).

Security controls implemented here:
- download accepts HTTP/HTTPS only;
- DNS resolution blocks localhost, link-local, private/reserved IPs and
  DNS rebinding (every resolved address must be public);
- redirects are bounded and re-validated;
- MIME is sniffed from magic bytes — the file extension is never evidence;
- zero-byte, polyglot, executable and archive payloads are rejected;
- SVG is banned in Release 0.1 (no verified sanitizer yet).
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from windagent_tools.media_assets.errors import UrlBlockedError

ALLOWED_SCHEMES = ("http", "https")
MAX_REDIRECTS = 5
DEFAULT_MAX_BYTES = 20 * 1024 * 1024  # 20 MiB
DEFAULT_TIMEOUT_SECONDS = 15.0

# ---------------------------------------------------------------------------
# URL / IP validation (SSRF)
# ---------------------------------------------------------------------------


def is_public_ip(address_text: str) -> bool:
    """True when the address is a valid public IPv4/IPv6 literal.

    Blocks loopback (127.0.0.0/8, ::1), link-local (169.254.0.0/16, fe80::/10),
    private (10/8, 172.16/12, 192.168/16, fc00::/7), reserved (0.0.0.0/8,
    100.64.0.0/10, 192.0.0.0/24, 198.18.0.0/15, 224.0.0.0/4, multicast,
    2001:db8::/32 documentation, unspecified ::/128) and other non-global
    ranges via ipaddress.is_global.
    """
    try:
        ip = ipaddress.ip_address(address_text)
    except ValueError:
        return False
    return ip.is_global


def validate_host_ips(host: str, resolver=None) -> List[str]:
    """Resolve a host and ensure EVERY address is public.

    DNS rebinding protection: we resolve all A/AAAA records and reject the
    host unless every single resolved address is a public IP.
    """
    import socket

    if resolver is None:
        resolver = socket.getaddrinfo

    try:
        infos = resolver(host, None)
    except OSError as exc:
        raise UrlBlockedError(
            f"Host {host!r} could not be resolved (fail closed).",
            details={"error": str(exc)[:200]},
        ) from exc

    addresses: List[str] = []
    for info in infos:
        # getaddrinfo returns (family, type, proto, canonname, sockaddr)
        sockaddr = info[4]
        ip_text = sockaddr[0]
        if ip_text not in addresses:
            addresses.append(ip_text)

    if not addresses:
        raise UrlBlockedError(
            f"Host {host!r} resolved to no addresses (fail closed).",
            details={"host": host},
        )
    if not all(is_public_ip(addr) for addr in addresses):
        raise UrlBlockedError(
            f"Host {host!r} resolves to a non-public IP (SSRF blocked).",
            details={"addresses": addresses},
        )
    return addresses


def validate_download_url(url: str, *, resolver=None) -> str:
    """Validate a download URL; returns the normalized URL or raises."""
    from urllib.parse import urlparse

    if not url or not isinstance(url, str):
        raise UrlBlockedError("Download URL is missing.")
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise UrlBlockedError(
            f"Scheme {parsed.scheme!r} is not allowed (http/https only).",
            details={"scheme": parsed.scheme},
        )
    if not parsed.hostname:
        raise UrlBlockedError("Download URL has no host.")
    if parsed.username or parsed.password:
        raise UrlBlockedError("Download URL must not embed credentials.")

    # Reject obvious IP literals that are non-public before DNS.
    host = parsed.hostname
    if re.match(r"^[0-9a-fA-F:.]+$", host) and not is_public_ip(host):
        raise UrlBlockedError(
            f"IP literal {host!r} is not public (SSRF blocked).",
            details={"host": host},
        )

    validate_host_ips(host, resolver=resolver)
    return url


def validate_redirect_target(url: str, *, resolver=None) -> str:
    """Redirects must pass the exact same checks as the original URL."""
    return validate_download_url(url, resolver=resolver)


# ---------------------------------------------------------------------------
# MIME sniffing and payload classification (plan 02 §21.2)
# ---------------------------------------------------------------------------

# Magic-byte signatures: (label, startswith bytes)
MAGIC_SIGNATURES: Tuple[Tuple[str, bytes], ...] = (
    ("image/png", b"\x89PNG\r\n\x1a\n"),
    ("image/jpeg", b"\xff\xd8\xff"),
    ("image/gif", b"GIF87a"),
    ("image/gif", b"GIF89a"),
    ("image/webp", b"RIFF"),
    ("image/bmp", b"BM"),
)

EXECUTABLE_MAGIC = (
    b"MZ",            # PE / DOS executable
    b"\x7fELF",       # ELF
    b"#!",            # shebang script
)

ARCHIVE_MAGIC = (
    b"PK\x03\x04",    # zip
    b"Rar!",          # rar
    b"7z\xbc\xaf\x27\x1c",  # 7z
    b"\x1f\x8b",      # gzip
    b"BZh",           # bzip2
)

# Strong foreign signatures used for embedded-magic polyglot detection.
# Only multi-byte (>= 4) signatures are matched inside the header window so a
# legitimate image is not flagged by a coincidental 2-byte sequence (e.g.
# b"MZ" or b"\x1f\x8b") inside compressed pixel data.
POLYGLOT_EMBED_SIGNATURES = (
    b"\x7fELF",          # ELF
    b"PK\x03\x04",       # zip
    b"Rar!",             # rar
    b"7z\xbc\xaf\x27\x1c",  # 7z
)

_SVG_XML_RE = re.compile(rb"<svg[\s>]", re.IGNORECASE)


@dataclass(frozen=True)
class PayloadFingerprint:
    """Result of payload classification."""

    sniffed_mime: str
    is_svg: bool
    is_executable: bool
    is_archive: bool
    is_zero_byte: bool
    looks_polyglot: bool
    size_bytes: int


def sniff_mime(data: bytes) -> str:
    """Sniff MIME type from magic bytes (never trusts the extension)."""
    if not data:
        return ""
    for label, signature in MAGIC_SIGNATURES:
        if data.startswith(signature):
            return label
    # WebP files start with RIFF but carry a WEBP sub-chunk.
    if data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "application/octet-stream"


def classify_payload(data: bytes, *, extension: str = "") -> PayloadFingerprint:
    """Classify payload bytes for the ordered validation pipeline.

    Polyglot heuristic (plan 02 §21.2 / §22): a payload that starts with one
    file family but embeds the magic signature of another family inside the
    4 KiB header window — e.g. a PNG that also carries a zip/ELF stub, or an
    MZ/ELF executable with an embedded image header. Position-0 `startswith`
    matching alone cannot detect these because the first bytes belong to only
    one family, so we additionally scan the header window for strong foreign
    signatures. Fail-closed: a suspicious payload is rejected rather than
    accepted.
    """
    size = len(data)
    header = data[:4096]
    is_zero = size == 0
    is_svg = bool(_SVG_XML_RE.search(header)) or extension.lower() == ".svg"
    is_exec = any(data.startswith(sig) for sig in EXECUTABLE_MAGIC) and not is_svg
    is_archive = any(data.startswith(sig) for sig in ARCHIVE_MAGIC)

    image_signatures = [sig for _, sig in MAGIC_SIGNATURES]
    starts_with_image = any(data.startswith(sig) for sig in image_signatures)
    embeds_foreign = any(sig in header for sig in POLYGLOT_EMBED_SIGNATURES)
    embeds_image = any(sig in header for sig in image_signatures)
    # Image-start + embedded strong foreign signature, OR exec/archive-start
    # + embedded image magic.
    looks_polyglot = (starts_with_image and embeds_foreign) or (
        (is_exec or is_archive) and embeds_image
    )

    sniffed = sniff_mime(data)
    return PayloadFingerprint(
        sniffed_mime=sniffed,
        is_svg=is_svg,
        is_executable=is_exec,
        is_archive=is_archive,
        is_zero_byte=is_zero,
        looks_polyglot=looks_polyglot,
        size_bytes=size,
    )


__all__ = [
    "ALLOWED_SCHEMES",
    "MAX_REDIRECTS",
    "DEFAULT_MAX_BYTES",
    "DEFAULT_TIMEOUT_SECONDS",
    "is_public_ip",
    "validate_host_ips",
    "validate_download_url",
    "validate_redirect_target",
    "sniff_mime",
    "classify_payload",
    "PayloadFingerprint",
]
