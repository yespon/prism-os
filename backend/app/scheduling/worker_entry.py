"""Cron worker container entry: boot the scheduler and keep the process alive."""

import asyncio
import logging

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    from app.scheduling.worker import CronWorker

    worker = CronWorker()
    count = await worker.boot()
    print(f"cron worker booted with {count} job(s)", flush=True)
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await worker.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
