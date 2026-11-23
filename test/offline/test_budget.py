"""Offline tests for evidenceguard.budget.BudgetLedger."""

from __future__ import annotations

import multiprocessing
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from evidenceguard.budget import BudgetExceeded, BudgetLedger

NOW = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)
DEADLINE = NOW + timedelta(seconds=900)
TOKEN_LIMIT = 100
ATTEMPT_LIMIT = 3
USD_LIMIT = Decimal("1")


def make_ledger(path: Path) -> BudgetLedger:
    return BudgetLedger(
        path,
        token_limit=TOKEN_LIMIT,
        attempt_limit=ATTEMPT_LIMIT,
        usd_limit=USD_LIMIT,
        deadline=DEADLINE,
        clock=lambda: NOW,
    )


def reopen(path: Path) -> BudgetLedger:
    return make_ledger(path)


def snap(ledger: BudgetLedger) -> dict:
    return ledger.snapshot()


def assert_zero(snapshot: dict) -> None:
    assert snapshot["reserved_tokens"] == 0
    assert snapshot["settled_tokens"] == 0
    assert snapshot["attempts"] == 0
    assert snapshot["stopped"] is False
    assert Decimal(snapshot["reserved_usd"]) == Decimal("0")
    assert Decimal(snapshot["settled_usd"]) == Decimal("0")


def reserve(
    ledger: BudgetLedger, attempt_id: str, input_upper=40, output_upper=10, usd_upper=Decimal("0.2")
):
    return ledger.reserve(
        attempt_id,
        input_upper=input_upper,
        output_upper=output_upper,
        usd_upper=usd_upper,
    )


def settle(
    ledger: BudgetLedger,
    attempt_id: str,
    input_tokens=20,
    output_tokens=5,
    actual_usd=Decimal("0.1"),
):
    return ledger.settle(
        attempt_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        actual_usd=actual_usd,
    )


def test_new_ledger_zero_snapshot(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    assert_zero(snap(ledger))


def test_reserve_then_settle_accounting(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.2"))
    after = snap(ledger)
    assert after["reserved_tokens"] == 50
    assert Decimal(after["reserved_usd"]) == Decimal("0.2")
    assert after["attempts"] == 1
    assert after["stopped"] is False
    settle(ledger, "a1", 20, 5, Decimal("0.1"))
    final = snap(ledger)
    assert final["settled_tokens"] == 25
    assert Decimal(final["settled_usd"]) == Decimal("0.1")
    assert final["reserved_tokens"] == 0
    assert Decimal(final["reserved_usd"]) == Decimal("0")
    assert final["attempts"] == 1


@pytest.mark.parametrize(
    "input_upper,output_upper,usd_upper",
    [
        (60, 40, Decimal("0.5")),
        (99, 1, Decimal("0.5")),
        (0, 100, Decimal("0.5")),
        (10, 10, Decimal("1")),
    ],
)
def test_exact_caps_allowed(tmp_path, input_upper, output_upper, usd_upper):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", input_upper, output_upper, usd_upper)
    after = snap(ledger)
    assert after["reserved_tokens"] == input_upper + output_upper
    assert after["attempts"] == 1


@pytest.mark.parametrize(
    "input_upper,output_upper,usd_upper",
    [
        (60, 41, Decimal("0.2")),
        (40, 61, Decimal("0.2")),
        (40, 10, Decimal("1.01")),
        (0, 101, Decimal("0.2")),
    ],
)
def test_reservation_over_limit_rejected_and_stopped(
    tmp_path, input_upper, output_upper, usd_upper
):
    ledger = make_ledger(tmp_path / "budget.json")
    with pytest.raises(BudgetExceeded):
        reserve(ledger, "a1", input_upper, output_upper, usd_upper)
    after = snap(ledger)
    assert after["stopped"] is True
    assert after["attempts"] == 0
    assert after["reserved_tokens"] == 0
    assert Decimal(after["reserved_usd"]) == Decimal("0")


def test_attempt_limit_rejected(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    for i in range(ATTEMPT_LIMIT):
        reserve(ledger, f"a{i}", 5, 5, Decimal("0.01"))
        settle(ledger, f"a{i}", 1, 1, Decimal("0"))
    with pytest.raises(BudgetExceeded):
        reserve(ledger, "a3", 5, 5, Decimal("0.01"))
    after = snap(ledger)
    assert after["stopped"] is True
    assert after["attempts"] == ATTEMPT_LIMIT


def test_deadline_rejected(tmp_path):
    make_ledger(tmp_path / "budget.json")
    late = BudgetLedger(
        tmp_path / "budget.json",
        token_limit=TOKEN_LIMIT,
        attempt_limit=ATTEMPT_LIMIT,
        usd_limit=USD_LIMIT,
        deadline=DEADLINE,
        clock=lambda: DEADLINE,
    )
    with pytest.raises(BudgetExceeded):
        reserve(late, "a1")
    after = snap(late)
    assert after["stopped"] is True
    assert after["attempts"] == 0


def test_rejected_reservation_creates_no_attempt(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    with pytest.raises(BudgetExceeded):
        reserve(ledger, "a1", 200, 1, Decimal("0.01"))
    with pytest.raises(BudgetExceeded):
        reserve(ledger, "a2", 1, 1, Decimal("0.01"))
    assert snap(ledger)["attempts"] == 0


def test_duplicate_reservation_id_rejected(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1")
    with pytest.raises(ValueError):
        reserve(ledger, "a1")
    assert snap(ledger)["attempts"] == 1


def test_same_settlement_idempotent(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1")
    settle(ledger, "a1")
    settle(ledger, "a1")
    after = snap(ledger)
    assert after["settled_tokens"] == 25
    assert Decimal(after["settled_usd"]) == Decimal("0.1")
    assert after["reserved_tokens"] == 0


def test_conflicting_settlement_rejected(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1")
    settle(ledger, "a1", 20, 5, Decimal("0.1"))
    with pytest.raises(ValueError):
        settle(ledger, "a1", 21, 5, Decimal("0.1"))
    after = snap(ledger)
    assert after["settled_tokens"] == 25


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "actual_usd"])
def test_none_usage_stops_and_retains(tmp_path, field):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.2"))
    values = {"input_tokens": 20, "output_tokens": 5, "actual_usd": Decimal("0.1")}
    values[field] = None
    ledger.settle("a1", **values)
    after = snap(ledger)
    assert after["stopped"] is True
    assert after["reserved_tokens"] == 50
    assert Decimal(after["reserved_usd"]) == Decimal("0.2")
    assert after["settled_tokens"] == 0


def test_stop_durable_on_reopen(tmp_path):
    path = tmp_path / "budget.json"
    ledger = make_ledger(path)
    ledger.stop("manual")
    reopened = reopen(path)
    after = snap(reopened)
    assert after["stopped"] is True
    with pytest.raises(BudgetExceeded):
        reserve(reopened, "a1")


def test_reopen_does_not_reset_limits(tmp_path):
    path = tmp_path / "budget.json"
    ledger = make_ledger(path)
    for i in range(ATTEMPT_LIMIT):
        reserve(ledger, f"a{i}", 5, 5, Decimal("0.01"))
        settle(ledger, f"a{i}", 1, 1, Decimal("0"))
    reopened = reopen(path)
    assert snap(reopened)["attempts"] == ATTEMPT_LIMIT
    with pytest.raises(BudgetExceeded):
        reserve(reopened, "a3", 5, 5, Decimal("0.01"))


@pytest.mark.parametrize(
    "input_tokens,output_tokens,actual_usd",
    [
        (45, 10, Decimal("0.1")),
        (40, 11, Decimal("0.1")),
        (40, 10, Decimal("0.21")),
        (100, 100, Decimal("0.1")),
    ],
)
def test_settlement_over_input_output_usd(tmp_path, input_tokens, output_tokens, actual_usd):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.2"))
    with pytest.raises(BudgetExceeded):
        ledger.settle(
            "a1", input_tokens=input_tokens, output_tokens=output_tokens, actual_usd=actual_usd
        )
    after = snap(ledger)
    assert after["stopped"] is True
    assert after["reserved_tokens"] == 50
    assert Decimal(after["reserved_usd"]) == Decimal("0.2")


def test_known_remaining_request_settles_while_stopped(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.2"))
    reserve(ledger, "a2", 10, 10, Decimal("0.1"))
    ledger.stop("provider_error")
    assert snap(ledger)["stopped"] is True
    settle(ledger, "a1", 20, 5, Decimal("0.1"))
    after = snap(ledger)
    assert after["stopped"] is True
    assert after["settled_tokens"] == 25
    assert after["reserved_tokens"] == 20


@pytest.mark.parametrize(
    "attempt_id,input_upper,output_upper,usd_upper",
    [
        ("", 40, 10, Decimal("0.2")),
        (None, 40, 10, Decimal("0.2")),
        ("neg", -1, 10, Decimal("0.2")),
        ("bool", True, 10, Decimal("0.2")),
        ("nan", 40, 10, Decimal("NaN")),
        ("inf", 40, 10, Decimal("Infinity")),
        ("float", 40, 10, 0.2),
    ],
)
def test_malformed_reservation_rejected(tmp_path, attempt_id, input_upper, output_upper, usd_upper):
    ledger = make_ledger(tmp_path / "budget.json")
    with pytest.raises((ValueError, TypeError)):
        ledger.reserve(
            attempt_id,
            input_upper=input_upper,
            output_upper=output_upper,
            usd_upper=usd_upper,
        )
    assert_zero(snap(ledger))


def _fork_worker(path: str, attempt_id: str, queue) -> None:
    from evidenceguard.budget import (
        BudgetExceeded as WorkerBudgetExceeded,
        BudgetLedger as WorkerLedger,
    )

    ledger = WorkerLedger(
        path,
        token_limit=100,
        attempt_limit=3,
        usd_limit=Decimal("1"),
        deadline=DEADLINE,
        clock=lambda: NOW,
    )
    try:
        ledger.reserve(attempt_id, input_upper=40, output_upper=20, usd_upper=Decimal("0.1"))
    except WorkerBudgetExceeded:
        queue.put((attempt_id, False))
    else:
        queue.put((attempt_id, True))


def test_concurrent_fork_reservation_exactly_one(tmp_path):
    ctx = multiprocessing.get_context("fork")
    path = tmp_path / "budget.json"
    ledger = make_ledger(path)
    reserve(ledger, "pre", 1, 1, Decimal("0.01"))
    settle(ledger, "pre", 0, 0, Decimal("0"))
    queue = ctx.Queue()
    procs = [ctx.Process(target=_fork_worker, args=(str(path), f"w{i}", queue)) for i in range(2)]
    for proc in procs:
        proc.start()
    for proc in procs:
        proc.join(timeout=30)
        assert proc.exitcode == 0
    results = [queue.get(timeout=5), queue.get(timeout=5)]
    successes = [attempt for attempt, ok in results if ok]
    assert len(successes) == 1
    reopened = reopen(path)
    after = snap(reopened)
    assert after["reserved_tokens"] == 60
    assert after["attempts"] == 2


def test_reserve_after_settle_full_output_exhausts_tokens(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 40, Decimal("0.2"))
    settle(ledger, "a1", 40, 40, Decimal("0.1"))
    with pytest.raises(BudgetExceeded):
        reserve(ledger, "a2", 21, 1, Decimal("0.05"))
    after = snap(ledger)
    assert after["stopped"] is True
    assert after["settled_tokens"] == 80
    assert after["attempts"] == 1


def test_reserve_after_settle_usd_exhausted(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.9"))
    settle(ledger, "a1", 20, 5, Decimal("0.9"))
    with pytest.raises(BudgetExceeded):
        reserve(ledger, "a2", 5, 5, Decimal("0.2"))
    after = snap(ledger)
    assert after["stopped"] is True
    assert Decimal(after["settled_usd"]) == Decimal("0.9")


def test_unknown_settlement_repeat_idempotent_but_later_known(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.2"))
    ledger.settle("a1", input_tokens=None, output_tokens=5, actual_usd=Decimal("0.1"))
    first = snap(ledger)
    assert first["stopped"] is True
    assert first["reserved_tokens"] == 50
    ledger.settle("a1", input_tokens=None, output_tokens=5, actual_usd=Decimal("0.1"))
    repeat = snap(ledger)
    assert repeat == first
    with pytest.raises(ValueError):
        ledger.settle("a1", input_tokens=20, output_tokens=5, actual_usd=Decimal("0.1"))
    final = snap(ledger)
    assert final["stopped"] is True
    assert final["reserved_tokens"] == 50
    assert Decimal(final["reserved_usd"]) == Decimal("0.2")


def test_string_and_tiny_usd_reservations_exact(tmp_path):
    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 5, 5, "0.1")
    reserve(ledger, "a2", 5, 5, Decimal("0.0000003"))
    after = snap(ledger)
    assert Decimal(after["reserved_usd"]) == Decimal("0.1000003")
    assert after["reserved_tokens"] == 20
    assert after["attempts"] == 2


def test_snapshot_is_json_serialisable(tmp_path):
    import json

    ledger = make_ledger(tmp_path / "budget.json")
    reserve(ledger, "a1", 40, 10, Decimal("0.2"))
    settle(ledger, "a1", 20, 5, Decimal("0.1"))
    snapshot = snap(ledger)
    encoded = json.dumps(snapshot)
    decoded = json.loads(encoded)
    assert Decimal(decoded["settled_usd"]) == Decimal("0.1")
    assert decoded["settled_tokens"] == 25
