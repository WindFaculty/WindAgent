"""Independent worker process entrypoint (PHASE 7 - Process-specific composition).

Worker runs as SEPARATE process with its own composition root.
Does NOT share any state or container with API or Desktop processes.
"""

import asyncio
import logging

from windagent_worker.composition import WorkerContainer
from windagent_worker.runner import ProductionWorker

logger = logging.getLogger("windagent.worker.main")


async def main() -> None:
    # Initialize Worker-specific composition root
    worker_container = WorkerContainer()
    await worker_container.bootstrap()
    
    logger.info("Worker process starting with independent composition root (PHASE 7)")
    
    # Create production worker with its own container
    worker = ProductionWorker(worker_container=worker_container)
    
    await worker.start()
    
    try:
        while True:
            await worker.poll_and_execute_tick()
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Worker received keyboard interrupt")
    except Exception as e:
        logger.error(f"Worker encountered unexpected error: {e}")
    finally:
        await worker.stop()
        await worker_container.shutdown()
        logger.info("Worker process shut down gracefully")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
