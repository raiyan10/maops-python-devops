"""Bounded concurrency and deterministic output ordering for ``run_bounded_parallel``."""

from __future__ import annotations

import threading
import time

from maops_pydevops.core.health_runner import run_bounded_parallel


def test_empty_items_returns_empty_tuple() -> None:
    assert run_bounded_parallel([], lambda item: item, max_workers=4) == ()


def test_output_order_matches_input_order_serial() -> None:
    result = run_bounded_parallel([1, 2, 3, 4], lambda item: item * 10, max_workers=1)
    assert result == (10, 20, 30, 40)


def test_workers_1_is_serial() -> None:
    lock = threading.Lock()
    active = 0
    max_active = 0

    def _worker(item: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return item

    run_bounded_parallel(list(range(6)), _worker, max_workers=1)
    assert max_active == 1


def test_workers_never_exceeds_configured_limit() -> None:
    lock = threading.Lock()
    active = 0
    max_active = 0

    def _worker(item: int) -> int:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return item

    run_bounded_parallel(list(range(20)), _worker, max_workers=4)
    assert max_active <= 4
    assert max_active > 1  # proves real concurrency actually happened, not accidental serialization


def test_workers_greater_than_targets_no_semantic_difference() -> None:
    result = run_bounded_parallel([1, 2, 3], lambda item: item, max_workers=32)
    assert result == (1, 2, 3)


def test_output_order_preserved_despite_reversed_completion_order() -> None:
    # Item 0 sleeps the longest, so it *completes* last even though it was
    # *submitted* first -- output order must still match submission order.
    delays = {0: 0.06, 1: 0.03, 2: 0.0}

    def _worker(item: int) -> int:
        time.sleep(delays[item])
        return item

    result = run_bounded_parallel([0, 1, 2], _worker, max_workers=3)
    assert result == (0, 1, 2)


def test_indexes_start_at_1_is_caller_responsibility() -> None:
    # run_bounded_parallel itself is 0-indexed internally (submission
    # index); 1-based "index" fields are assigned by callers
    # (commands/health.py) on the validated target objects, not here.
    result = run_bounded_parallel(["a", "b"], lambda item: item.upper(), max_workers=2)
    assert result == ("A", "B")


def test_result_type_preserved() -> None:
    result = run_bounded_parallel([1, 2, 3], lambda item: str(item), max_workers=2)
    assert result == ("1", "2", "3")
    assert all(isinstance(value, str) for value in result)
