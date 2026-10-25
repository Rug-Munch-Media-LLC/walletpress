"""CWE-362: the free-tier quota must survive concurrent reservation.

The pre-fix gate read SUM(wallets) and inserted in separate statements, so N
racing requests could each observe the same usage and all be granted. These
tests drive the primitive directly — no HTTP layer, no wallet generation.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from core import x402_store

CLIENT = "10.0.0.1"


@pytest.fixture
def db(tmp_path):
    return tmp_path / "x402.db"


def test_reserve_grants_exactly_the_quota_under_8_threads(db):
    """8 threads asking for 1 wallet each, limit 3 → exactly 3 grants."""
    limit = 3
    barrier = threading.Barrier(8)
    seen: list[int] = []
    lock = threading.Lock()

    def worker(_index: int) -> bool:
        barrier.wait()  # maximise the overlap the old read-then-insert lost to
        granted, used_before = x402_store.reserve_free_quota(db, CLIENT, 1, limit)
        if granted:
            with lock:
                seen.append(used_before)
        return granted

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, range(8)))

    assert sum(results) == limit, f"quota over-granted: {results}"
    assert x402_store.free_wallets_used(db, CLIENT) == limit
    # Every winner observed a distinct pre-state: no two grants shared a read.
    assert sorted(seen) == [0, 1, 2]


def test_reserve_refuses_an_order_larger_than_the_remainder(db):
    """A 5-wallet order on a 3-wallet quota is refused and consumes nothing."""
    assert x402_store.reserve_free_quota(db, CLIENT, 2, 3) == (True, 0)
    granted, used = x402_store.reserve_free_quota(db, CLIENT, 2, 3)
    assert (granted, used) == (False, 2)
    assert x402_store.free_wallets_used(db, CLIENT) == 2


def test_release_returns_reserved_wallets_and_never_goes_negative(db):
    x402_store.reserve_free_quota(db, CLIENT, 2, 3)
    x402_store.release_free_quota(db, CLIENT, 2)
    assert x402_store.free_wallets_used(db, CLIENT) == 0
    x402_store.release_free_quota(db, CLIENT, 5)
    assert x402_store.free_wallets_used(db, CLIENT) == 0
