#!/usr/bin/env python3
import asyncio
import os
import signal

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
BROKER = os.getenv("BROKER", True)
WORKERS = os.getenv("WORKERS", True)
    
async def main():
    futures = []
    # check if need to start NorFab broker process
    if BROKER is True and WORKERS is not True:
        futures.append(await asyncio.create_subprocess_exec("nfcli", '-b', '-l', LOG_LEVEL))
    # check if need to start NorFab workers processes
    elif WORKERS is True and BROKER is not True:
        futures.append(await asyncio.create_subprocess_exec("nfcli", '-w', '-l', LOG_LEVEL))
    # check if need to start NorFab workers and broker processes
    elif WORKERS is True and BROKER is True:
        futures.append(await asyncio.create_subprocess_exec("nfcli", '-b', '-w', '-l', LOG_LEVEL))
    await asyncio.gather(*[future.communicate() for future in futures])

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    for signame in {"SIGINT", "SIGTERM"}:
        loop.add_signal_handler(getattr(signal, signame), loop.stop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()