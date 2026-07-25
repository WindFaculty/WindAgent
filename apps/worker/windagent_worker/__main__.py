"""Independent worker process entrypoint."""

import asyncio

from windagent_worker.runner import ProductionWorker


async def main() -> None:
    worker = ProductionWorker()
    await worker.start()
    try:
        while True:
            await worker.poll_and_execute_tick()
            await asyncio.sleep(0.5)
    finally:
        await worker.stop()


if __name__ == "__main__":
    asyncio.run(main())
