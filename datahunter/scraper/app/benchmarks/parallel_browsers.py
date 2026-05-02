"""Benchmark: sequential vs parallel browser contexts.

Simulates Playwright page fetches with asyncio.sleep to model the I/O cost
of browser navigation (JS rendering + network). Shows that max_concurrent=N
reduces wall time from O(N * latency) to O(latency) when N contexts run in
parallel.

Run:
    uv run python -m scraper.app.benchmarks.parallel_browsers
"""

from __future__ import annotations

import asyncio
import time

PAGES = 6
LATENCY_S = 0.2  # 200 ms — plausible render time for a JS-heavy page


async def _fake_fetch(url: str, semaphore: asyncio.Semaphore) -> str:
    """Simulate a browser fetch: acquire semaphore, wait, release."""
    async with semaphore:
        await asyncio.sleep(LATENCY_S)
        return f"<html>{url}</html>"


async def run_parallel(max_concurrent: int) -> float:
    sem = asyncio.Semaphore(max_concurrent)
    urls = [f"https://example.com/page/{i}" for i in range(PAGES)]
    start = time.perf_counter()
    await asyncio.gather(*[_fake_fetch(url, sem) for url in urls])
    return time.perf_counter() - start


def main() -> None:
    print(f"\nBenchmark: {PAGES} pages x {LATENCY_S * 1000:.0f} ms simulated render time")
    print("-" * 54)

    for concurrency in (1, 2, 3, PAGES):
        elapsed = asyncio.run(run_parallel(concurrency))
        label = f"max_concurrent={concurrency}"
        print(f"{label:<22}  {elapsed:.3f} s")

    print(
        "\nNote: real speedup with Playwright scales with render latency."
        " Memory usage grows with concurrent contexts — tune max_concurrent"
        " based on available RAM (approx 50-150 MB per context)."
    )


if __name__ == "__main__":  # pragma: no cover
    main()
