"""
AssetDownloadService (plan 02 §21.1) — SSRF-safe acquisition.

Download rules:
- HTTP/HTTPS only; the URL is validated BEFORE any connection;
- DNS resolution blocks localhost / link-local / private / reserved IPs and
  DNS rebinding (every resolved address must be public);
- redirects are bounded (MAX_REDIRECTS) and EACH hop is validated with the
  same SSRF checks BEFORE the next request is made — the transport never
  auto-follows a redirect to a private IP;
- timeout, max bytes, and concurrency are configured;
- the payload is buffered in memory under the max-bytes bound and handed to
  validation — nothing is written to the canonical store until validation
  succeeds.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol

from windagent_tools.media_assets.errors import DownloadFailedError
from windagent_tools.media_assets.security import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_REDIRECTS,
    validate_download_url,
    validate_redirect_target,
)


class _RedirectSignal(Exception):
    """Internal signal: the transport hit a redirect and did NOT follow it."""

    def __init__(self, location: str) -> None:
        super().__init__(location)
        self.location = location


@dataclass(frozen=True)
class DownloadReceipt:
    """Result of a successful (validated-safe) download."""

    url: str
    final_url: str
    data: bytes
    redirect_count: int
    content_length: Optional[int] = None


class TransportPort(Protocol):
    """A transport fetches ONE URL and returns its body.

    Redirects are reported via a _RedirectSignal rather than followed, so the
    service can validate every hop before the next connection. Implementations
    may be injected (fakes for offline verification) or the default urllib
    transport.
    """

    async def fetch(self, url: str, *, max_bytes: int, timeout: float) -> bytes:
        """Return the body, or raise _RedirectSignal(location)."""
        ...


class _NoFollowOpenerTransport:
    """Default transport built on urllib with auto-redirect DISABLED.

    A redirect raises _RedirectSignal(location) so the service validates the
    target with the full SSRF policy BEFORE the next fetch.
    """

    def __init__(self) -> None:
        self._opener = self._build_opener()

    @staticmethod
    def _build_opener():
        from urllib.request import HTTPRedirectHandler, build_opener

        class _NoFollow(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
                raise _RedirectSignal(newurl)

        return build_opener(_NoFollow())

    async def fetch(self, url: str, *, max_bytes: int, timeout: float) -> bytes:
        from urllib.request import Request

        req = Request(url, headers={"User-Agent": "windagent-asset-pipeline/0.1"})
        loop = asyncio.get_event_loop()

        def _get() -> bytes:
            try:
                with self._opener.open(req, timeout=timeout) as resp:
                    raw = resp.read(max_bytes + 1)
                    if len(raw) > max_bytes:
                        raise DownloadFailedError(
                            "Download exceeded max bytes.",
                            details={"max_bytes": max_bytes},
                        )
                    return raw
            except _RedirectSignal:
                raise
            except DownloadFailedError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise DownloadFailedError(
                    f"Download failed: {exc}",
                    details={"url": url},
                ) from exc

        try:
            return await loop.run_in_executor(None, _get)
        except _RedirectSignal:
            raise
        except DownloadFailedError:
            raise


class AssetDownloadService:
    """SSRF-safe, bounded asset downloader."""

    def __init__(
        self,
        *,
        transport: Optional[TransportPort] = None,
        max_bytes: int = DEFAULT_MAX_BYTES,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_redirects: int = MAX_REDIRECTS,
        max_concurrency: int = 4,
    ) -> None:
        self.transport = transport or _NoFollowOpenerTransport()
        self.max_bytes = max_bytes
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.max_concurrency = max_concurrency

    async def download(self, url: str) -> DownloadReceipt:
        """Validate URL, follow bounded validated redirects, return bytes.

        Each redirect hop is re-validated with the SSRF checks BEFORE the next
        request, so a redirect to a private IP is never fetched.
        """
        current = validate_download_url(url)
        redirects = 0

        while True:
            try:
                data = await self.transport.fetch(
                    current,
                    max_bytes=self.max_bytes,
                    timeout=self.timeout,
                )
            except _RedirectSignal as signal:
                redirects += 1
                if redirects > self.max_redirects:
                    raise DownloadFailedError(
                        "Too many redirects.",
                        details={"max_redirects": self.max_redirects},
                    )
                # Validate the hop BEFORE fetching it (SSRF, no auto-follow).
                current = validate_redirect_target(signal.location)
                continue

            if len(data) > self.max_bytes:
                raise DownloadFailedError(
                    "Download exceeded max bytes.",
                    details={"max_bytes": self.max_bytes, "actual": len(data)},
                )
            return DownloadReceipt(
                url=url,
                final_url=current,
                data=data,
                redirect_count=redirects,
                content_length=len(data),
            )

    async def download_many(self, urls: List[str]) -> List[DownloadReceipt]:
        """Concurrent downloads bounded by max_concurrency."""
        semaphore = asyncio.Semaphore(self.max_concurrency)

        async def _one(u: str) -> DownloadReceipt:
            async with semaphore:
                return await self.download(u)

        return list(await asyncio.gather(*(_one(u) for u in urls)))


__all__ = ["AssetDownloadService", "DownloadReceipt", "TransportPort"]
