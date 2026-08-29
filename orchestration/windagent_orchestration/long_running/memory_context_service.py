"""Memory & Context Orchestration Service (Phase 6 — ban_ke_hoach_v1 §11).

Coordinates Memory V2, Context Compaction, and Durable Checkpointing at
compaction boundaries adhering strictly to Core/Ports architecture without
cross-package direct imports.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from windagent_core.domain.memory_v2 import (
    MemoryRecordV2,
    MemoryScope,
    ValidationStatus,
)

logger = logging.getLogger("windagent.orchestration.long_running.memory_context")


class MemoryContextService:
    """Orchestration seam coordinating Memory V2, ContextCompactor, and CheckpointService."""

    def __init__(
        self,
        store: Optional[Any] = None,
        compactor: Optional[Any] = None,
        builder: Optional[Any] = None,
        memory_repo_factory: Optional[Callable[[Any], Any]] = None,
        session_factory: Optional[Callable[[], Any]] = None,
        item_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.store = store
        self.compactor = compactor
        self.builder = builder
        self._memory_repo_factory = memory_repo_factory
        self._session_factory = session_factory
        self._item_factory = item_factory

    # ---------------------------------------------------------------
    # Memory V2 Operations
    # ---------------------------------------------------------------

    async def save_memory(
        self,
        record: Union[MemoryRecordV2, Any, Dict[str, Any]],
        expected_version: Optional[int] = None,
    ) -> MemoryRecordV2:
        """Saves memory record to MemoryStore and durable repository if configured."""
        if isinstance(record, dict):
            record = MemoryRecordV2.model_validate(record)
        elif hasattr(record, "to_v2"):
            record = record.to_v2()

        # Save to in-memory store if present
        if self.store is not None:
            self.store.save(record)

        # Durable persistence via repository if session_factory and memory_repo_factory are provided
        if self._session_factory and self._memory_repo_factory:
            async with self._session_factory() as session:
                repo = self._memory_repo_factory(session)
                saved = await repo.save_record(record, expected_version=expected_version)
                await session.commit()
                if saved:
                    record = saved

        return record

    async def get_memory(
        self,
        scope: MemoryScope,
        key: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Optional[MemoryRecordV2]:
        if self.store is not None:
            rec = self.store.get(scope, key, project_id, session_id)
            if rec:
                return rec.to_v2() if hasattr(rec, "to_v2") else rec

        if self._session_factory and self._memory_repo_factory:
            async with self._session_factory() as session:
                repo = self._memory_repo_factory(session)
                durable_rec = await repo.get_by_key(
                    scope=scope.value if hasattr(scope, "value") else str(scope),
                    key=key,
                    project_id=project_id,
                    session_id=session_id,
                )
                if durable_rec:
                    if self.store is not None:
                        try:
                            self.store.save(durable_rec)
                        except Exception:
                            pass
                    return durable_rec
        return None

    async def get_memory_by_id(self, memory_id: str) -> Optional[MemoryRecordV2]:
        if self.store is not None:
            rec = self.store.get_by_id(memory_id)
            if rec:
                return rec.to_v2() if hasattr(rec, "to_v2") else rec

        if self._session_factory and self._memory_repo_factory:
            async with self._session_factory() as session:
                repo = self._memory_repo_factory(session)
                durable_rec = await repo.get_by_id(memory_id)
                if durable_rec:
                    if self.store is not None:
                        try:
                            self.store.save(durable_rec)
                        except Exception:
                            pass
                    return durable_rec
        return None

    async def query_memories(
        self,
        scope: Optional[MemoryScope] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        validation_status: Optional[ValidationStatus] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[MemoryRecordV2]:
        if self.store is None:
            return []

        results = []
        if validation_status:
            recs = self.store.list_by_status(validation_status, scope=scope)
        elif scope == MemoryScope.POLICY:
            recs = self.store.list_policies(validated_only=False, project_id=project_id)
        elif scope == MemoryScope.PROCEDURAL:
            recs = self.store.list_procedural(project_id=project_id)
        elif scope == MemoryScope.EPISODIC:
            recs = self.store.list_episodic(session_id=session_id)
        elif scope is not None:
            recs = self.store.list_by_scope(scope, limit=limit)
        elif project_id:
            recs = self.store.list_records_for_project(project_id)
        elif session_id:
            recs = self.store.list_records_for_session(session_id)
        else:
            recs = list(self.store._store.values()) if hasattr(self.store, "_store") else []

        for rec in recs:
            if project_id and getattr(rec, "project_id", None) and rec.project_id != project_id:
                continue
            if session_id and getattr(rec, "session_id", None) and rec.session_id != session_id:
                continue
            conf = rec.learning_metadata.confidence if getattr(rec, "learning_metadata", None) else 0.0
            if conf < min_confidence:
                continue
            results.append(rec.to_v2() if hasattr(rec, "to_v2") else rec)

        return results[:limit]

    async def supersede_memory(
        self,
        old_memory_id: str,
        new_record: Union[MemoryRecordV2, Any, Dict[str, Any]],
    ) -> MemoryRecordV2:
        """Saves new_record as superseding old_memory_id, marking the old memory SUPERSEDED."""
        if isinstance(new_record, dict):
            new_record = MemoryRecordV2.model_validate(new_record)
        elif hasattr(new_record, "to_v2"):
            new_record = new_record.to_v2()

        # Set supersedes_id on new_record
        new_meta = new_record.learning_metadata.model_copy(
            update={"supersedes_id": old_memory_id}
        )
        new_record.learning_metadata = new_meta

        return await self.save_memory(new_record)

    # ---------------------------------------------------------------
    # Compaction & Durable Checkpoint Integration
    # ---------------------------------------------------------------

    async def compact_and_checkpoint(
        self,
        agent_run_id: str,
        messages: List[Dict[str, Any]],
        max_keep_recent: int = 4,
        checkpoint_service: Optional[Any] = None,
        session_id: Optional[str] = None,
        artifact_refs: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[Any]]:
        """Compacts messages and persists a durable compaction checkpoint."""
        if self.compactor is not None:
            before_count = len(messages)
            compacted = self.compactor.compact_conversation(messages, max_keep_recent=max_keep_recent)
            after_count = len(compacted)
            preserved_count = sum(
                1 for m in compacted
                if hasattr(self.compactor, "is_critical_message") and self.compactor.is_critical_message(str(m.get("content", "")))
            )
            snapshot = (
                self.compactor.create_compaction_checkpoint_payload(
                    messages_before=before_count,
                    messages_after=after_count,
                    preserved_critical_count=preserved_count,
                    artifact_refs=artifact_refs,
                )
                if hasattr(self.compactor, "create_compaction_checkpoint_payload")
                else {
                    "stage": "compaction",
                    "messages_before": before_count,
                    "messages_after": after_count,
                    "compacted_count": max(0, before_count - after_count),
                    "preserved_critical_count": preserved_count,
                    "artifact_refs": list(artifact_refs or []),
                }
            )
        else:
            compacted = list(messages)
            snapshot = {
                "stage": "compaction",
                "messages_before": len(messages),
                "messages_after": len(messages),
                "compacted_count": 0,
                "preserved_critical_count": 0,
                "artifact_refs": list(artifact_refs or []),
            }

        checkpoint_rec = None
        if checkpoint_service is not None:
            checkpoint_rec = await checkpoint_service.at_compaction(
                agent_run_id=agent_run_id,
                snapshot=snapshot,
                session_id=session_id,
            )

        return compacted, checkpoint_rec

    # ---------------------------------------------------------------
    # Context Building with Prioritized Memory Layers
    # ---------------------------------------------------------------

    async def assemble_prompt_context(
        self,
        task_prompt: str,
        messages: Optional[List[Dict[str, Any]]] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        file_items: Optional[List[Any]] = None,
        tool_items: Optional[List[Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Any], bool, Optional[Any]]:
        """Assembles context using the configured builder."""
        if self.builder is None:
            return messages or [], [], False, None

        memory_items: List[Any] = []

        if self.store is not None:
            # 1. POLICY memories
            policies = self.store.list_policies(validated_only=True, project_id=project_id) if hasattr(self.store, "list_policies") else []
            for p in policies:
                memory_items.append(self._make_item(
                    item_id=f"policy_{p.id}",
                    content=f"[POLICY RULE] {p.key}: {p.value}",
                    source=getattr(p, "provenance_source", "policy"),
                    source_type="policy_memory",
                    retrieval_reason="Promoted behavioral policy",
                    confidence=p.learning_metadata.confidence if getattr(p, "learning_metadata", None) else 1.0,
                ))

            # 2. SEMANTIC & PROCEDURAL memories
            knowledge = self.store.list_validated_knowledge(project_id=project_id) if hasattr(self.store, "list_validated_knowledge") else []
            for k in knowledge:
                if getattr(k, "scope", None) == MemoryScope.POLICY:
                    continue
                stype = "semantic_memory" if getattr(k, "scope", None) == MemoryScope.SEMANTIC else "procedural_memory"
                memory_items.append(self._make_item(
                    item_id=f"knowledge_{k.id}",
                    content=f"[KNOWLEDGE] {k.key}: {k.value}",
                    source=getattr(k, "provenance_source", "knowledge"),
                    source_type=stype,
                    retrieval_reason="Validated reusable knowledge",
                    confidence=k.learning_metadata.confidence if getattr(k, "learning_metadata", None) else 0.8,
                ))

            # 3. SESSION memories
            if session_id and hasattr(self.store, "list_records_for_session"):
                for rm in self.store.list_records_for_session(session_id):
                    memory_items.append(self._make_item(
                        item_id=f"session_{rm.id}",
                        content=f"[SESSION MEMORY] {rm.key}: {rm.value}",
                        source=getattr(rm, "provenance_source", "session"),
                        source_type="session_context",
                        retrieval_reason="Session continuity",
                    ))

            # 4. EPISODIC memories
            if hasattr(self.store, "list_episodic"):
                for ep in self.store.list_episodic(session_id=session_id)[:3]:
                    memory_items.append(self._make_item(
                        item_id=f"episodic_{ep.id}",
                        content=f"[EPISODIC EXPERIENCE] {ep.key}: {ep.value}",
                        source=getattr(ep, "provenance_source", "episode"),
                        source_type="episodic_memory",
                        retrieval_reason="Past experience trace",
                    ))

        return self.builder.assemble_context(
            task_prompt=task_prompt,
            messages=messages,
            file_items=file_items,
            tool_output_items=tool_items,
            memory_items=memory_items,
        )

    def _make_item(
        self,
        item_id: str,
        content: str,
        source: str,
        source_type: str,
        retrieval_reason: str,
        confidence: float = 1.0,
    ) -> Any:
        if self._item_factory is not None:
            return self._item_factory(
                item_id=item_id,
                content=content,
                source=source,
                source_type=source_type,
                retrieval_reason=retrieval_reason,
                confidence=confidence,
            )
        if hasattr(self.builder, "create_context_item"):
            return self.builder.create_context_item(
                item_id=item_id,
                content=content,
                source=source,
                source_type=source_type,
                retrieval_reason=retrieval_reason,
                confidence=confidence,
            )
        return {"item_id": item_id, "content": content, "source": source}
