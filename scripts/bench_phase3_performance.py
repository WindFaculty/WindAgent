#!/usr/bin/env python3
"""
Phase 3 Performance Guardrails Benchmark
Measures queue claim, lease renew, finalization p95/p99, outbox lag, throughput
"""

import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from windagent_storage.database.connection import DatabaseManager
from windagent_storage.orm.models import BaseORM
from windagent_storage.queue.sql_queue import SqlDurableTaskQueue
from windagent_storage.queue.submission_adapter import SqlWorkSubmissionAdapter
from windagent_core.contracts.workers.models import WorkSubmission


async def benchmark_queue_claim(db_manager, iterations: int = 100) -> dict:
    """Benchmark queue claim p50/p95/p99"""
    queue = SqlDurableTaskQueue(db_manager.session_factory)
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)

    latencies = []

    for i in range(iterations):
        # Submit a task
        task_id = await submitter.submit(
            WorkSubmission(
                prompt=f"Benchmark task {i}",
                tool_name="read_file",
                parameters={"query": "test"},
                workflow_name="benchmark",
            )
        )

        # Measure claim latency
        start = time.perf_counter()
        claimed = await queue.claim_next(
            worker_id=f"bench_worker_{i}", lease_ttl_seconds=10
        )
        end = time.perf_counter()

        if claimed:
            latencies.append((end - start) * 1000)  # ms

    latencies.sort()
    return {
        "p50": latencies[len(latencies) // 2] if latencies else 0,
        "p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
        "mean": statistics.mean(latencies) if latencies else 0,
        "count": len(latencies),
    }


async def benchmark_lease_renew(db_manager, iterations: int = 50) -> dict:
    """Benchmark lease renewal p95"""
    queue = SqlDurableTaskQueue(db_manager.session_factory)
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)

    latencies = []

    for i in range(iterations):
        task_id = await submitter.submit(
            WorkSubmission(
                prompt=f"Renew benchmark {i}",
                tool_name="read_file",
                parameters={"query": "test"},
                workflow_name="benchmark",
            )
        )

        claimed = await queue.claim_next(
            worker_id=f"renew_worker_{i}", lease_ttl_seconds=10
        )
        if claimed:
            start = time.perf_counter()
            renewed = await queue.renew(
                claimed.task_id, f"renew_worker_{i}", claimed.fencing_token
            )
            end = time.perf_counter()

            if renewed:
                latencies.append((end - start) * 1000)

    latencies.sort()
    return {
        "p50": latencies[len(latencies) // 2] if latencies else 0,
        "p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
        "mean": statistics.mean(latencies) if latencies else 0,
        "count": len(latencies),
    }


async def benchmark_finalization(db_manager, iterations: int = 50) -> dict:
    """Benchmark finalization transaction p95"""
    from windagent_storage.unit_of_work.sql_uow import SqlUnitOfWork
    from windagent_core.contracts.finalization import FinalizeTaskExecutionRequest
    from windagent_core.contracts.execution import RuntimeStatusEnum

    queue = SqlDurableTaskQueue(db_manager.session_factory)
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)

    latencies = []

    for i in range(iterations):
        task_id = await submitter.submit(
            WorkSubmission(
                prompt=f"Finalize benchmark {i}",
                tool_name="read_file",
                parameters={"query": "test"},
                workflow_name="benchmark",
            )
        )

        claimed = await queue.claim_next(
            worker_id=f"finalize_worker_{i}", lease_ttl_seconds=10
        )
        if not claimed:
            continue

        # Execute via fake runtime
        from windagent_execution.adapters.fake_runtime_adapter import FakeRuntimeAdapter
        from windagent_execution.registry import ExecutionRuntimeRegistry
        from windagent_core.contracts.execution import ExecutionRequest

        runtime = ExecutionRuntimeRegistry(
            default_adapter=FakeRuntimeAdapter(default_mode="success")
        )
        exec_req = ExecutionRequest(
            step_run_id=claimed.task_id,
            workflow_run_id=f"wf_{claimed.task_id}",
            tool_name=claimed.tool_name,
            parameters={"task_id": claimed.task_id, "prompt": claimed.prompt},
            attempt_id="att_1",
            fencing_token=claimed.fencing_token,
        )

        handle = await runtime.dispatch(exec_req)
        result = await runtime.get_result(handle)

        # Finalize
        start = time.perf_counter()
        async with SqlUnitOfWork(db_manager.session_factory) as uow:
            existing = await uow.task_runs.get_by_id(claimed.task_id)
            expected_version = (existing or {}).get("version", 0) or 1

            req = FinalizeTaskExecutionRequest(
                task_id=claimed.task_id,
                worker_id=f"finalize_worker_{i}",
                lease_id=claimed.lease_id,
                fencing_token=claimed.fencing_token,
                expected_task_version=expected_version,
                execution_result=dict(result.result_data or {}),
                result_artifacts=[],
                terminal_event={
                    "event_type": "task_completed",
                    "task_id": claimed.task_id,
                    "status": result.status.value,
                },
                attempt_id="att_1",
                fencing_generation=1,
                terminal_state="completed",
            )
            fin_res = await uow.finalize_task_execution(req)
        end = time.perf_counter()

        if fin_res.status == "COMPLETED":
            latencies.append((end - start) * 1000)

    latencies.sort()
    return {
        "p50": latencies[len(latencies) // 2] if latencies else 0,
        "p95": latencies[int(len(latencies) * 0.95)] if latencies else 0,
        "p99": latencies[int(len(latencies) * 0.99)] if latencies else 0,
        "mean": statistics.mean(latencies) if latencies else 0,
        "count": len(latencies),
    }


async def benchmark_outbox_processing(db_manager, iterations: int = 100) -> dict:
    """Benchmark outbox processing throughput and lag"""
    from windagent_storage.outbox.sql_repository import SqlOutboxRepository
    from windagent_storage.outbox.processor import TransactionalOutboxManager
    from windagent_observability.events.publisher import OutboxEventPublisher
    from windagent_observability.events.dispatcher import EventDispatcher
    from windagent_core.events.envelope import EventEnvelope
    from windagent_core.domain.types import EventId

    processed_counts = []
    start_time = time.perf_counter()

    dispatcher = EventDispatcher()
    published_events = []

    async def handler(event):
        published_events.append(event)

    repo = SqlOutboxRepository(db_manager.session_factory)
    publisher = OutboxEventPublisher(
        outbox_repo=repo,
        dispatcher=handler,
        batch_size=50,
        poll_interval_seconds=0.01,
    )

    # Submit many tasks to generate outbox events
    submitter = SqlWorkSubmissionAdapter(db_manager.session_factory)
    for i in range(iterations):
        await submitter.submit(
            WorkSubmission(
                prompt=f"Outbox benchmark {i}",
                tool_name="read_file",
                parameters={"query": "test"},
                workflow_name="benchmark",
            )
        )

    # Process outbox
    await publisher.start()
    for _ in range(10):
        count = await publisher.publish_pending()
        processed_counts.append(count)
        await asyncio.sleep(0.05)
    await publisher.stop()

    total_time = time.perf_counter() - start_time
    total_processed = sum(processed_counts)

    return {
        "total_processed": total_processed,
        "throughput_per_sec": total_processed / total_time if total_time > 0 else 0,
        "mean_batch_size": statistics.mean(processed_counts) if processed_counts else 0,
        "batches": len(processed_counts),
    }


async def main():
    print("Starting Phase 3 Performance Benchmarks...")

    db_manager = DatabaseManager("sqlite+aiosqlite:///:memory:")
    await db_manager.create_tables(BaseORM.metadata)

    # Run benchmarks
    print("\n1. Queue Claim Benchmark...")
    claim_results = await benchmark_queue_claim(db_manager, 100)
    print(
        f"   p50: {claim_results['p50']:.2f}ms, p95: {claim_results['p95']:.2f}ms, p99: {claim_results['p99']:.2f}ms"
    )

    print("\n2. Lease Renewal Benchmark...")
    renew_results = await benchmark_lease_renew(db_manager, 50)
    print(
        f"   p50: {renew_results['p50']:.2f}ms, p95: {renew_results['p95']:.2f}ms, p99: {renew_results['p99']:.2f}ms"
    )

    print("\n3. Finalization Transaction Benchmark...")
    finalize_results = await benchmark_finalization(db_manager, 50)
    print(
        f"   p50: {finalize_results['p50']:.2f}ms, p95: {finalize_results['p95']:.2f}ms, p99: {finalize_results['p99']:.2f}ms"
    )

    print("\n4. Outbox Processing Benchmark...")
    outbox_results = await benchmark_outbox_processing(db_manager, 100)
    print(
        f"   Total processed: {outbox_results['total_processed']}, Throughput: {outbox_results['throughput_per_sec']:.1f} events/sec"
    )

    # Save results
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "queue_claim": claim_results,
        "lease_renewal": renew_results,
        "finalization": finalize_results,
        "outbox": outbox_results,
    }

    output_path = (
        Path("artifacts")
        / "architecture_v2_runtime_cutover"
        / "phase_03"
        / "performance_report.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))

    print(f"\nResults saved to {output_path}")

    await db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
