"""Bounded, ordered parallel execution for one-target-per-worker health checks.

The only module in ``src/maops_pydevops`` permitted to import
``concurrent.futures``. Generic over the item/result type -- carries no
HTTP/TCP-specific knowledge, so retries for one target happening
sequentially inside its worker, and "no nested thread pools", are both
structural properties of the caller (neither ``core/health_http.py`` nor
``core/health_tcp.py`` imports ``concurrent.futures`` at all), not of this
module.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable, Sequence
from typing import TypeVar, cast

T = TypeVar("T")
R = TypeVar("R")


def run_bounded_parallel(
    items: Sequence[T], worker_fn: Callable[[T], R], *, max_workers: int
) -> tuple[R, ...]:
    """Run ``worker_fn`` once per item, bounded to ``max_workers`` concurrent workers.

    Output order always matches ``items`` order, regardless of completion
    order: each future's result is written into a pre-sized, index-
    addressed list at its *original* submission index, never appended in
    completion order, and the tuple is only returned once every future has
    resolved.
    """
    if not items:
        return ()
    worker_count = max(1, min(max_workers, len(items)))
    results: list[R | None] = [None] * len(items)
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_index = {
            executor.submit(worker_fn, item): index for index, item in enumerate(items)
        }
        for future in concurrent.futures.as_completed(future_to_index):
            results[future_to_index[future]] = future.result()
    # Every future has resolved by this point (the `with` block only exits
    # after all submitted work completes), so every slot is populated --
    # the cast reflects that runtime guarantee to the type checker.
    return cast("tuple[R, ...]", tuple(results))
