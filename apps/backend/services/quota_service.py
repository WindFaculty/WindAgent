"""Service to manage, track, and update provider usage quotas."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from sqlalchemy import select
from db.database import Database
from db.models import ProviderQuotaSnapshotORM

log = logging.getLogger(__name__)


class QuotaService:
    """Manages and monitors model provider quotas and rate limits."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get_latest_quota(self, provider_id: str) -> Optional[ProviderQuotaSnapshotORM]:
        """Fetch the most recent quota snapshot for a provider."""
        async with self.db.session() as session:
            stmt = (
                select(ProviderQuotaSnapshotORM)
                .where(ProviderQuotaSnapshotORM.provider_id == provider_id)
                .order_by(ProviderQuotaSnapshotORM.created_at.desc())
                .limit(1)
            )
            res = await session.execute(stmt)
            return res.scalar_one_or_none()

    async def update_quota_snapshot(
        self,
        provider_id: str,
        quota_mode: str,
        rpm_limit: Optional[int] = None,
        rpd_limit: Optional[int] = None,
        tpm_limit: Optional[int] = None,
        remaining_requests_today: Optional[int] = None,
        remaining_tokens_today: Optional[int] = None,
        remaining_tokens_month: Optional[int] = None,
        remaining_credit: Optional[float] = None,
        reset_at: Optional[datetime] = None,
        source: str = "manual",
        raw_json: str = "{}",
    ) -> ProviderQuotaSnapshotORM:
        """Create a new quota snapshot record for tracking history."""
        async with self.db.session() as session:
            snapshot = ProviderQuotaSnapshotORM(
                provider_id=provider_id,
                quota_mode=quota_mode,
                rpm_limit=rpm_limit,
                rpd_limit=rpd_limit,
                tpm_limit=tpm_limit,
                remaining_requests_today=remaining_requests_today,
                remaining_tokens_today=remaining_tokens_today,
                remaining_tokens_month=remaining_tokens_month,
                remaining_credit=remaining_credit,
                reset_at=reset_at,
                source=source,
                raw_json=raw_json,
            )
            session.add(snapshot)
            await session.commit()
            return snapshot

    def estimate_request_cost(
        self,
        provider_id: str,
        model_id: str,
        prompt_tokens: int,
        max_output_tokens: int,
    ) -> int:
        """Estimate the number of tokens required for this request."""
        # Simple heuristic
        return prompt_tokens + max_output_tokens

    async def check_and_reset_provider_quota(self, provider_id: str) -> None:
        """Check if the quota snapshot for the provider is expired or from a previous day, and reset it."""
        snapshot = await self.get_latest_quota(provider_id)
        if not snapshot:
            return

        now = datetime.now(timezone.utc)
        created_at_utc = snapshot.created_at.replace(tzinfo=timezone.utc) if snapshot.created_at.tzinfo is None else snapshot.created_at
        
        # Check if reset conditions are met:
        # 1. Reset time has passed
        reset_passed = snapshot.reset_at is not None and snapshot.reset_at.replace(tzinfo=timezone.utc) < now
        # 2. Created on a previous calendar day
        prev_day = created_at_utc.date() < now.date()

        if reset_passed or prev_day:
            log.info("Resetting quota snapshot for provider %s: reset_passed=%s, prev_day=%s", 
                     provider_id, reset_passed, prev_day)
            
            # Default limits
            rpd = snapshot.rpd_limit if snapshot.rpd_limit is not None else 1000
            tpm = snapshot.tpm_limit if snapshot.tpm_limit is not None else 1000000
            
            # Create a new snapshot with restored limits
            await self.update_quota_snapshot(
                provider_id=provider_id,
                quota_mode=snapshot.quota_mode,
                rpm_limit=snapshot.rpm_limit,
                rpd_limit=snapshot.rpd_limit,
                tpm_limit=snapshot.tpm_limit,
                remaining_requests_today=rpd,
                remaining_tokens_today=tpm,
                remaining_credit=snapshot.remaining_credit,
                reset_at=None, # Clear reset time
                source="auto_reset",
                raw_json=json.dumps({"reset_at_time": str(now)}),
            )

    async def should_route(
        self,
        provider_id: str,
        estimated_tokens: int,
    ) -> bool:
        """Verify if the provider still has remaining quota to service this request."""
        # Local model is always allowed
        if provider_id == "ollama":
            return True

        # Check and perform reset if needed
        await self.check_and_reset_provider_quota(provider_id)

        snapshot = await self.get_latest_quota(provider_id)
        if not snapshot:
            return True # If no quota recorded yet, assume True

        # Check reset time
        now = datetime.now(timezone.utc)
        if snapshot.reset_at and snapshot.reset_at.replace(tzinfo=timezone.utc) < now:
            # Quota reset has passed, so it's allowed
            return True

        # Check request count
        if snapshot.remaining_requests_today is not None and snapshot.remaining_requests_today <= 0:
            log.warning("Provider %s has depleted remaining requests for today", provider_id)
            return False

        # Check token budget
        if snapshot.remaining_tokens_today is not None and snapshot.remaining_tokens_today < estimated_tokens:
            log.warning("Provider %s has depleted remaining tokens for today. Have %d, need %d", 
                        provider_id, snapshot.remaining_tokens_today, estimated_tokens)
            return False

        # Check credit (ONE_TIME_CREDIT)
        if snapshot.remaining_credit is not None and snapshot.remaining_credit <= 0.0:
            log.warning("Provider %s credit has depleted", provider_id)
            return False

        return True

    async def update_from_response_headers(self, provider_id: str, headers: Dict[str, str]) -> None:
        """Parse rate limit headers from HTTP response to update quota snapshots."""
        # Normalize header keys to lowercase
        h = {k.lower(): v for k, v in headers.items()}
        
        # Look for standard headers
        # x-ratelimit-remaining-requests, x-ratelimit-remaining-tokens, x-ratelimit-reset
        remaining_req = None
        remaining_tok = None
        reset_secs = None

        if "x-ratelimit-remaining-requests" in h:
            try:
                remaining_req = int(h["x-ratelimit-remaining-requests"])
            except ValueError:
                pass
        
        if "x-ratelimit-remaining-tokens" in h:
            try:
                remaining_tok = int(h["x-ratelimit-remaining-tokens"])
            except ValueError:
                pass

        if "x-ratelimit-reset" in h:
            try:
                reset_secs = float(h["x-ratelimit-reset"])
            except ValueError:
                pass

        # If we got any rate limit metadata, update snapshot
        if remaining_req is not None or remaining_tok is not None:
            reset_at = None
            if reset_secs is not None:
                reset_at = datetime.now(timezone.utc) + timedelta(seconds=reset_secs)

            latest = await self.get_latest_quota(provider_id)
            quota_mode = latest.quota_mode if latest else "RPM_RPD"

            await self.update_quota_snapshot(
                provider_id=provider_id,
                quota_mode=quota_mode,
                remaining_requests_today=remaining_req,
                remaining_tokens_today=remaining_tok,
                reset_at=reset_at,
                source="provider_api",
                raw_json=str(headers),
            )
            log.info("Updated rate limit snapshot for provider %s: requests_left=%s, tokens_left=%s",
                     provider_id, remaining_req, remaining_tok)
