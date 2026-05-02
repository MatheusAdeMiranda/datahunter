"""Benchmark: sync sequential requests vs async concurrent requests.

Simulates I/O-bound work (network latency) with time.sleep / asyncio.sleep to
show why asyncio matters for scrapers: the bottleneck is waiting for responses,
not CPU. Async lets the event loop issue all N requests and process each as it
arrives instead of waiting for one before starting the next.

Run:
    uv run python -m scraper.app.benchmarks.sync_vs_async
"""

from __future__ import annotations

import asyncio
import time

REQUESTS = 20
LATENCY_S = 0.05  # 50 ms — representative of a fast API over the internet


def _sync_fetch(i: int) -> str:
    time.sleep(LATENCY_S)
    return f"page-{i}"


async def _async_fetch(i: int) -> str:
    await asyncio.sleep(LATENCY_S)
    return f"page-{i}"


def run_sync() -> float:
    start = time.perf_counter()
    for i in range(REQUESTS):
        _sync_fetch(i)
    return time.perf_counter() - start


async def run_async() -> float:
    start = time.perf_counter()
    await asyncio.gather(*[_async_fetch(i) for i in range(REQUESTS)])
    return time.perf_counter() - start


def main() -> None:
    print(f"\nBenchmark: {REQUESTS} requests x {LATENCY_S * 1000:.0f} ms simulated latency")
    print("-" * 52)

    sync_time = run_sync()
    print(f"sync  (sequential):  {sync_time:.3f} s")

    async_time = asyncio.run(run_async())
    print(f"async (concurrent):  {async_time:.3f} s")

    print(f"\nspeedup: {sync_time / async_time:.1f}x")
    print(
        "\nNote: real-world speedup scales with network latency and number of"
        " concurrent requests. CPU-bound work sees no benefit from asyncio."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
