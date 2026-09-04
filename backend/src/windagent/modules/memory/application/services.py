"""Application services and orchestration for the Memory module (Phase 14)."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime

from ..domain.errors import (
    MemoryNotFoundError,
    MemoryStaleVersionError,
    MemoryValidationError,
)
from ..domain.models import (
    LearningMetadata,
    MemoryRecord,
    RetentionPolicy,
)
from ..domain.policy import MemoryWritePolicy
from ..domain.scope import (
    VALIDATED_STATUSES,
    MemoryScope,
    ValidationStatus,
)
from .commands import (
    DeleteMemory,
    EvictExpiredMemories,
    ForgetMemory,
    ForgetMemoryByPattern,
    SaveManyMemories,
    SaveMemory,
    SetMemoryTtl,
)
from .events import memory_events
from .models import MemoryRecordRow, MemoryRecordView, MemoryStatsView
from .ports import MemoryScopeFactory

logger = logging.getLogger("windagent.memory.application.services")


def utc_now() -> datetime:
    return datetime.now(UTC)


def _generate_memory_id() -> str:
    return str(uuid.uuid4())


class MemoryService:
    def __init__(
        self,
        scope_factory: MemoryScopeFactory,
        write_policy: MemoryWritePolicy | None = None,
        retention_policy: RetentionPolicy | None = None,
    ) -> None:
        self._scope_factory = scope_factory
        self._write_policy = write_policy or MemoryWritePolicy()
        self._retention_policy = retention_policy or RetentionPolicy(auto_evict_expired=True)

    # ----------------------------------------------------------------------- #
    # Commands
    # ----------------------------------------------------------------------- #

    async def save_memory(self, cmd: SaveMemory) -> MemoryRecordView:
        scope_val = cmd.scope
        try:
            scope_enum = MemoryScope(scope_val)
        except ValueError:
            raise MemoryValidationError(f"Invalid memory scope: {scope_val}")

        learning_meta = LearningMetadata.from_dict(cmd.learning_metadata)
        mem_id = cmd.memory_id or _generate_memory_id()

        record = MemoryRecord(
            id=mem_id,
            scope=scope_enum,
            key=cmd.key,
            value=cmd.value,
            provenance_source=cmd.provenance_source,
            project_id=cmd.project_id,
            session_id=cmd.session_id,
            tags=dict(cmd.tags),
            ttl_seconds=cmd.ttl_seconds,
            learning_metadata=learning_meta,
        )

        # 1. Enforce write policy (secret exclusion, provenance, scope isolation, admission gate)
        self._write_policy.validate_and_enforce(record)

        content_hash = record.compute_content_hash()
        record.content_hash = content_hash

        async with self._scope_factory() as scope:
            # 2. Handle superseding lineage: mark superseded record as SUPERSEDED
            if learning_meta.supersedes_id:
                old_row = await scope.store.get_by_id(learning_meta.supersedes_id)
                if old_row is not None:
                    old_meta = (
                        json.loads(old_row.learning_metadata_json)
                        if old_row.learning_metadata_json
                        else {}
                    )
                    old_meta["validation_status"] = ValidationStatus.SUPERSEDED.value
                    superseded_row = MemoryRecordRow(
                        memory_id=old_row.memory_id,
                        scope=old_row.scope,
                        key=old_row.key,
                        project_id=old_row.project_id,
                        session_id=old_row.session_id,
                        value_json=old_row.value_json,
                        provenance_source=old_row.provenance_source,
                        tags_json=old_row.tags_json,
                        ttl_seconds=old_row.ttl_seconds,
                        content_hash=old_row.content_hash,
                        learning_metadata_json=json.dumps(old_meta),
                        version=old_row.version + 1,
                        optimistic_version=old_row.optimistic_version + 1,
                        created_at=old_row.created_at,
                        updated_at=utc_now(),
                    )
                    await scope.store.update(superseded_row, old_row.optimistic_version)
                    await scope.record_event(
                        memory_events.memory_superseded(
                            memory_id=old_row.memory_id,
                            superseded_by_id=mem_id,
                            scope=old_row.scope,
                            key=old_row.key,
                        )
                    )

            # 3. Content hash deduplication check
            dup_row = await scope.store.get_by_hash(content_hash)
            if dup_row is not None:
                # Deduplicate: update timestamp and learning metadata
                updated_dup = MemoryRecordRow(
                    memory_id=dup_row.memory_id,
                    scope=dup_row.scope,
                    key=dup_row.key,
                    project_id=dup_row.project_id,
                    session_id=dup_row.session_id,
                    value_json=dup_row.value_json,
                    provenance_source=dup_row.provenance_source,
                    tags_json=dup_row.tags_json,
                    ttl_seconds=dup_row.ttl_seconds,
                    content_hash=dup_row.content_hash,
                    learning_metadata_json=json.dumps(learning_meta.to_dict()),
                    version=dup_row.version,
                    optimistic_version=dup_row.optimistic_version + 1,
                    created_at=dup_row.created_at,
                    updated_at=utc_now(),
                )
                saved_row = await scope.store.update(updated_dup, dup_row.optimistic_version)
                await scope.record_event(
                    memory_events.memory_updated(
                        memory_id=saved_row.memory_id,
                        scope=saved_row.scope,
                        key=saved_row.key,
                        version=saved_row.version,
                        project_id=saved_row.project_id,
                        session_id=saved_row.session_id,
                    )
                )
                await scope.commit()
                return MemoryRecordView.from_row(saved_row)

            # 4. Check existing record with same (scope, key, project_id, session_id)
            existing_row = await scope.store.get(
                scope_enum.value, cmd.key, cmd.project_id, cmd.session_id
            )

            if existing_row is not None:
                if cmd.expected_version is not None and existing_row.optimistic_version != cmd.expected_version:
                    raise MemoryStaleVersionError(
                        f"Memory record version conflict: expected {cmd.expected_version}, got {existing_row.optimistic_version}"
                    )

                new_version = existing_row.version + 1
                updated_row = MemoryRecordRow(
                    memory_id=existing_row.memory_id,
                    scope=existing_row.scope,
                    key=existing_row.key,
                    project_id=cmd.project_id,
                    session_id=cmd.session_id,
                    value_json=json.dumps(cmd.value),
                    provenance_source=cmd.provenance_source,
                    tags_json=json.dumps(cmd.tags),
                    ttl_seconds=cmd.ttl_seconds,
                    content_hash=content_hash,
                    learning_metadata_json=json.dumps(learning_meta.to_dict()),
                    version=new_version,
                    optimistic_version=existing_row.optimistic_version + 1,
                    created_at=existing_row.created_at,
                    updated_at=utc_now(),
                )
                saved_row = await scope.store.update(updated_row, existing_row.optimistic_version)
                await scope.record_event(
                    memory_events.memory_updated(
                        memory_id=saved_row.memory_id,
                        scope=saved_row.scope,
                        key=saved_row.key,
                        version=saved_row.version,
                        project_id=saved_row.project_id,
                        session_id=saved_row.session_id,
                    )
                )
                await scope.commit()
                return MemoryRecordView.from_row(saved_row)

            # 5. Insert new record
            now = utc_now()
            new_row = MemoryRecordRow(
                memory_id=mem_id,
                scope=scope_enum.value,
                key=cmd.key,
                project_id=cmd.project_id,
                session_id=cmd.session_id,
                value_json=json.dumps(cmd.value),
                provenance_source=cmd.provenance_source,
                tags_json=json.dumps(cmd.tags),
                ttl_seconds=cmd.ttl_seconds,
                content_hash=content_hash,
                learning_metadata_json=json.dumps(learning_meta.to_dict()),
                version=1,
                optimistic_version=1,
                created_at=now,
                updated_at=now,
            )
            saved_row = await scope.store.insert(new_row)
            await scope.record_event(
                memory_events.memory_created(
                    memory_id=saved_row.memory_id,
                    scope=saved_row.scope,
                    key=saved_row.key,
                    project_id=saved_row.project_id,
                    session_id=saved_row.session_id,
                )
            )
            await scope.commit()
            return MemoryRecordView.from_row(saved_row)

    async def save_many(self, cmd: SaveManyMemories) -> list[MemoryRecordView]:
        views: list[MemoryRecordView] = []
        for raw in cmd.records:
            save_cmd = SaveMemory(
                key=raw.get("key", ""),
                value=raw.get("value"),
                scope=raw.get("scope", "working"),
                provenance_source=raw.get("provenance_source", ""),
                project_id=raw.get("project_id"),
                session_id=raw.get("session_id"),
                tags=raw.get("tags") or {},
                ttl_seconds=raw.get("ttl_seconds"),
                learning_metadata=raw.get("learning_metadata") or {},
                memory_id=raw.get("id"),
            )
            try:
                view = await self.save_memory(save_cmd)
                views.append(view)
            except Exception as e:
                logger.warning(f"Failed to batch save memory key [{save_cmd.key}]: {e}")
        return views

    async def delete_memory(self, cmd: DeleteMemory | ForgetMemory) -> bool:
        async with self._scope_factory() as scope:
            existing = await scope.store.get(
                cmd.scope, cmd.key, cmd.project_id, cmd.session_id
            )
            if existing is None:
                return False

            deleted = await scope.store.delete(existing.memory_id)
            if deleted:
                await scope.record_event(
                    memory_events.memory_deleted(
                        memory_id=existing.memory_id,
                        scope=existing.scope,
                        key=existing.key,
                        project_id=existing.project_id,
                        session_id=existing.session_id,
                    )
                )
                await scope.commit()
            return deleted

    async def forget_by_pattern(self, cmd: ForgetMemoryByPattern) -> int:
        async with self._scope_factory() as scope:
            rows = await scope.store.list_records(
                scope=cmd.scope,
                project_id=cmd.project_id,
                session_id=cmd.session_id,
                limit=1000,
            )
            count = 0
            for row in rows:
                if row.key.startswith(cmd.key_prefix):
                    deleted = await scope.store.delete(row.memory_id)
                    if deleted:
                        count += 1
                        await scope.record_event(
                            memory_events.memory_deleted(
                                memory_id=row.memory_id,
                                scope=row.scope,
                                key=row.key,
                                project_id=row.project_id,
                                session_id=row.session_id,
                            )
                        )
            if count > 0:
                await scope.commit()
            return count

    async def set_ttl(self, cmd: SetMemoryTtl) -> bool:
        async with self._scope_factory() as scope:
            existing = await scope.store.get(
                cmd.scope, cmd.key, cmd.project_id, cmd.session_id
            )
            if existing is None:
                raise MemoryNotFoundError(
                    f"Memory record not found: scope={cmd.scope}, key={cmd.key}"
                )

            updated = MemoryRecordRow(
                memory_id=existing.memory_id,
                scope=existing.scope,
                key=existing.key,
                project_id=existing.project_id,
                session_id=existing.session_id,
                value_json=existing.value_json,
                provenance_source=existing.provenance_source,
                tags_json=existing.tags_json,
                ttl_seconds=cmd.ttl_seconds,
                content_hash=existing.content_hash,
                learning_metadata_json=existing.learning_metadata_json,
                version=existing.version,
                optimistic_version=existing.optimistic_version + 1,
                created_at=existing.created_at,
                updated_at=utc_now(),
            )
            await scope.store.update(updated, existing.optimistic_version)
            await scope.commit()
            return True

    async def evict_expired(self, cmd: EvictExpiredMemories) -> int:
        async with self._scope_factory() as scope:
            count = await scope.store.evict_expired(
                reference_time=utc_now(),
                scope=cmd.scope,
            )
            if count > 0:
                await scope.record_event(memory_events.memory_evicted(count=count, scope=cmd.scope))
                await scope.commit()
            return count

    # ----------------------------------------------------------------------- #
    # Queries
    # ----------------------------------------------------------------------- #

    async def get_memory(self, scope: str, key: str, project_id: str | None = None, session_id: str | None = None) -> MemoryRecordView | None:
        async with self._scope_factory() as s:
            row = await s.store.get(scope, key, project_id, session_id)
            if row is None:
                return None
            view = MemoryRecordView.from_row(row)
            domain_rec = view.to_domain()
            if domain_rec.is_expired():
                await s.store.delete(row.memory_id)
                await s.commit()
                return None
            return view

    async def get_by_id(self, memory_id: str) -> MemoryRecordView | None:
        async with self._scope_factory() as s:
            row = await s.store.get_by_id(memory_id)
            if row is None:
                return None
            view = MemoryRecordView.from_row(row)
            domain_rec = view.to_domain()
            if domain_rec.is_expired():
                await s.store.delete(row.memory_id)
                await s.commit()
                return None
            return view

    async def list_memories(
        self,
        scope: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(
                scope=scope,
                project_id=project_id,
                session_id=session_id,
                limit=limit,
                offset=offset,
            )
            views: list[MemoryRecordView] = []
            for r in rows:
                v = MemoryRecordView.from_row(r)
                if not v.to_domain().is_expired():
                    views.append(v)
            return views

    async def search_by_tag(
        self,
        tag_key: str,
        tag_value: str,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(scope=scope, limit=500)
            matched: list[MemoryRecordView] = []
            for r in rows:
                v = MemoryRecordView.from_row(r)
                if v.tags.get(tag_key) == tag_value and not v.to_domain().is_expired():
                    matched.append(v)
                    if len(matched) >= limit:
                        break
            return matched

    async def list_by_status(
        self,
        validation_status: str,
        scope: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(scope=scope, limit=500)
            results: list[MemoryRecordView] = []
            for r in rows:
                v = MemoryRecordView.from_row(r)
                if (
                    v.learning_metadata.get("validation_status") == validation_status
                    and not v.to_domain().is_expired()
                ):
                    results.append(v)
                    if len(results) >= limit:
                        break
            return results

    async def list_validated_knowledge(
        self,
        scope: str | None = None,
        min_confidence: float = 0.0,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(scope=scope, project_id=project_id, limit=500)
            results: list[MemoryRecordView] = []
            valid_statuses = {st.value for st in VALIDATED_STATUSES}
            for r in rows:
                v = MemoryRecordView.from_row(r)
                status = v.learning_metadata.get("validation_status")
                conf = float(v.learning_metadata.get("confidence", 0.0))
                if (
                    status in valid_statuses
                    and conf >= min_confidence
                    and not v.to_domain().is_expired()
                ):
                    results.append(v)
            results.sort(
                key=lambda x: float(x.learning_metadata.get("confidence", 0.0)),
                reverse=True,
            )
            return results[:limit]

    async def list_policies(
        self,
        validated_only: bool = True,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(
                scope=MemoryScope.POLICY.value, project_id=project_id, limit=500
            )
            results: list[MemoryRecordView] = []
            valid_statuses = {st.value for st in VALIDATED_STATUSES}
            for r in rows:
                v = MemoryRecordView.from_row(r)
                if validated_only:
                    status = v.learning_metadata.get("validation_status")
                    if status not in valid_statuses:
                        continue
                if not v.to_domain().is_expired():
                    results.append(v)
                    if len(results) >= limit:
                        break
            return results

    async def list_procedural(
        self,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(
                scope=MemoryScope.PROCEDURAL.value, project_id=project_id, limit=limit
            )
            return [
                MemoryRecordView.from_row(r)
                for r in rows
                if not MemoryRecordView.from_row(r).to_domain().is_expired()
            ]

    async def list_episodic(
        self,
        session_id: str | None = None,
        limit: int = 100,
    ) -> list[MemoryRecordView]:
        async with self._scope_factory() as s:
            rows = await s.store.list_records(
                scope=MemoryScope.EPISODIC.value, session_id=session_id, limit=limit
            )
            return [
                MemoryRecordView.from_row(r)
                for r in rows
                if not MemoryRecordView.from_row(r).to_domain().is_expired()
            ]

    async def get_stats(self) -> MemoryStatsView:
        async with self._scope_factory() as s:
            counts = await s.store.count_by_scope()
            total = sum(counts.values())
            return MemoryStatsView(total_records=total, by_scope=counts)
