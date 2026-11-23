# Durable budget boundary

Session `ses_e0c5615aaffe7zNIpWIWaGEyVz`; local OpenCode, course model `CS5351/DeepSeek-V4-Flash`.

Initial generation had SQLite/transaction defects. Failed tests and the generated repair are recorded in the bug diary; this session alone is not the final implementation.

The adjacent JSON is the authentic `opencode session export --sanitize` output, with local directory names further redacted if present. OpenCode redacts user/assistant text in that export. The assistant text below is copied from the authentic JSON event stream to make the code-generation evidence reviewable. Only local directory strings are redacted; code is not repaired in this transcript. All text parts, including incomplete or repeated candidates, are retained in order.

Instructions were relayed by Codex under the user’s startup authorization. This is not a transcript of the student personally typing in OpenCode, a human approval, or a claim that the model ran tests. Actual validation and subsequent corrections are recorded in `docs/bug-diary.md`, `docs/progress.md` and the checkpoint bundle.

Original sanitized export SHA-256: `5fa511e8750f4a8f10769cdf740c38451d31ee1380079da11eb34e9d17642e94`.

Original event stream SHA-256: `1af34df764607cd9366affcc564695032a0eea8dec99e206742da16429ff2430`.

Preservation update (2026-11-19): the original temporary session directory was lost on system restart. This public annotated text and sanitized native export survive; original hashes below were recorded before the loss. Their presence does not mean the private originals are still available.

## Authentic assistant text

```text
"""Durable per-run budget ledger.

State lives in a single SQLite row as a JSON document. Every mutation runs
inside ``BEGIN IMMEDIATE`` plus a process-wide ``threading.RLock`` so both
in-process threads and cross-process writers serialize instead of racing.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


class BudgetExceeded(ValueError):
    """Raised when a budget limit or a durable stop forbids an operation."""


@dataclass(frozen=True)
class Reservation:
    attempt_id: str
    input_upper: int
    output_upper: int
    usd_upper: Decimal


@dataclass(frozen=True)
class _Limits:
    token_limit: int
    attempt_limit: int
    usd_limit: Decimal
    deadline: datetime


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("deadline must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    if value < 0:
        raise ValueError(f"{name} must not be negative")
    return value


def _money(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (int, str, Decimal)):
        raise ValueError(f"{name} must be a Decimal, int or str")
    try:
        amount = Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} is not a valid decimal") from exc
    if not amount.is_finite():
        raise ValueError(f"{name} must be finite")
    if amount < 0:
        raise ValueError(f"{name} must not be negative")
    return amount


def _reject_constant(token: str) -> Any:
    raise ValueError(f"invalid JSON constant {token}")


def _canonical_usage(supplied: dict) -> dict:
    """Canonical stored usage for all three keys; None preserved."""
    out: dict[str, Any] = {}
    for key in ("input_tokens", "output_tokens", "actual_usd"):
        value = supplied[key]
        out[key] = None if value is None else str(value)
    return out


def _same_usage(left: dict, right: dict) -> bool:
    if set(left.keys()) != set(right.keys()):
        return False
    for key in left:
        if left[key] is None or right[key] is None:
            if left[key] is not right[key]:
                return False
            continue
        if key == "actual_usd":
            if Decimal(str(left[key])) != Decimal(str(right[key])):
                return False
        else:
            if str(left[key]) != str(right[key]):
                return False
    return True


class BudgetLedger:
    def __init__(
        self,
        path: str | Path,
        *,
        token_limit: int,
        attempt_limit: int,
        usd_limit: Decimal | int | str,
        deadline: datetime,
        clock,
    ) -> None:
        if not callable(clock):
            raise ValueError("clock must be callable")
        limits = _Limits(
            token_limit=_positive_int(token_limit, "token_limit"),
            attempt_limit=_positive_int(attempt_limit, "attempt_limit"),
            usd_limit=_money(usd_limit, "usd_limit"),
            deadline=_utc(deadline),
        )
        if limits.usd_limit <= 0:
            raise ValueError("usd_limit must be positive")
        self._clock = clock
        self._limits = limits
        self._lock = threading.RLock()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(path), isolation_level=None, timeout=30.0, check_same_thread=False
        )
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)"
        )
        with self._txn() as state:
            if state is None:
                self._conn.execute(
                    "INSERT INTO ledger (id, payload) VALUES (1, ?)",
                    (self._dump(self._initial()),),
                )
                state = self._load()
            self._verify(state)

    def _initial(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "config": {
                "token_limit": self._limits.token_limit,
                "attempt_limit": self._limits.attempt_limit,
                "usd_limit": str(self._limits.usd_limit),
                "deadline": self._limits.deadline.isoformat(),
            },
            "stopped": False,
            "stop_reason": None,
            "attempts": {},
            "events": [],
        }

    def _verify(self, state: dict) -> None:
        config = state["config"]
        if (
            config["token_limit"] != self._limits.token_limit
            or config["attempt_limit"] != self._limits.attempt_limit
            or Decimal(config["usd_limit"]) != self._limits.usd_limit
            or datetime.fromisoformat(config["deadline"]) != self._limits.deadline
        ):
            raise ValueError("ledger configuration does not match the existing ledger")

    @staticmethod
    def _dump(state: dict) -> str:
        return json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))

    def _load(self) -> dict | None:
        row = self._conn.execute("SELECT payload FROM ledger WHERE id = 1").fetchone()
        if row is None:
            return None
        return json.loads(row[0], parse_float=Decimal, parse_constant=_reject_constant)

    def _save(self, state: dict) -> None:
        self._conn.execute("UPDATE ledger SET payload = ? WHERE id = 1", (self._dump(state),))

    @contextmanager
    def _txn(self):
        """Yield mutable state; BudgetExceeded still commits, other errors roll back.

        The in-process RLock is held for the whole transaction so parallel
        threads sharing this ledger serialize. ``BEGIN IMMEDIATE`` keeps
        cross-process writers serialized as well.
        """
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN IMMEDIATE")
            state = None
            try:
                state = self._load()
            except Exception:
                cur.execute("ROLLBACK")
                raise
            try:
                yield state
            except BudgetExceeded:
                try:
                    if state is not None:
                        self._save(state)
                    cur.execute("COMMIT")
                except Exception:
                    cur.execute("ROLLBACK")
                    raise
                raise
            except BaseException:
                cur.execute("ROLLBACK")
                raise
            else:
                if state is not None:
                    self._save(state)
                cur.execute("COMMIT")

    def _now(self) -> datetime:
        return _utc(self._clock())

    @staticmethod
    def _event(state: dict, kind: str, attempt_id: str | None, **fields: Any) -> None:
        record = {"type": kind, "attempt_id": attempt_id, "at": None, **fields}
        state["events"].append(record)

    def _halt(self, state: dict, reason: str, attempt_id: str | None = None, **fields: Any) -> None:
        state["stopped"] = True
        state["stop_reason"] = reason
        self._event(state, "stop", attempt_id, reason=reason, **fields)

    @staticmethod
    def _unresolved(state: dict) -> list[dict]:
        return [entry for entry in state["attempts"].values() if entry["state"] == "reserved"]

    @classmethod
    def _reserved_usd(cls, state: dict) -> Decimal:
        return sum(
            (Decimal(entry["reservation"]["usd_upper"]) for entry in cls._unresolved(state)),
            Decimal(0),
        )

    @classmethod
    def _reserved_tokens(cls, state: dict) -> int:
        return sum(
            (
                entry["reservation"]["input_upper"] + entry["reservation"]["output_upper"]
                for entry in cls._unresolved(state)
            ),
            0,
        )

    @staticmethod
    def _settled_totals(state: dict) -> tuple[int, Decimal]:
        tokens = 0
        usd = Decimal(0)
        for entry in state["attempts"].values():
            if entry["state"] != "settled":
                continue
            usage = entry.get("usage") or {}
            tokens += int(usage["input_tokens"]) + int(usage["output_tokens"])
            usd += Decimal(usage["actual_usd"])
        return tokens, usd

    @classmethod
    def _consumed_totals(cls, state: dict) -> tuple[int, Decimal]:
        settled_tokens, settled_usd = cls._settled_totals(state)
        return (
            settled_tokens + cls._reserved_tokens(state),
            settled_usd + cls._reserved_usd(state),
        )

    def reserve(
        self,
        attempt_id: str,
        *,
        input_upper: int,
        output_upper: int,
        usd_upper: Decimal | int,
    ) -> Reservation:
        if not isinstance(attempt_id, str) or not attempt_id:
            raise ValueError("attempt_id must be a non-empty string")
        input_tokens = _int(input_upper, "input_upper")
        output_tokens = _positive_int(output_upper, "output_upper")
        usd = _money(usd_upper, "usd_upper")
        if usd <= 0:
            raise ValueError("usd_upper must be positive")
        reservation = Reservation(attempt_id, input_tokens, output_tokens, usd)
        tokens = input_tokens + output_tokens
        with self._txn() as state:
            if state is None:
                raise ValueError("ledger is not initialized")
            if attempt_id in state["attempts"]:
                raise ValueError(f"attempt {attempt_id!r} already reserved")
            started = len(state["attempts"])
            now = self._now()
            if state["stopped"]:
                raise BudgetExceeded(f"ledger stopped: {state['stop_reason']}")
            if now >= self._limits.deadline:
                self._halt(state, "deadline_exceeded", attempt_id)
                raise BudgetExceeded("deadline exceeded")
            if started + 1 > self._limits.attempt_limit:
                self._halt(state, "attempt_limit_exceeded", attempt_id)
                raise BudgetExceeded("attempt limit exceeded")
            consumed_tokens, consumed_usd = self._consumed_totals(state)
            if consumed_tokens + tokens > self._limits.token_limit:
                self._halt(state, "token_limit_exceeded", attempt_id)
                raise BudgetExceeded("token limit exceeded")
            if consumed_usd + usd > self._limits.usd_limit:
                self._halt(state, "usd_limit_exceeded", attempt_id)
                raise BudgetExceeded("usd limit exceeded")
            reservation_doc = {
                "input_upper": input_tokens,
                "output_upper": output_tokens,
                "usd_upper": str(usd),
            }
            state["attempts"][attempt_id] = {
                "state": "reserved",
                "reservation": reservation_doc,
                "started_at": now.isoformat(),
                "settled_at": None,
                "usage": None,
            }
            self._event(
                state,
                "reserve",
                attempt_id,
                state="reserved",
                reservation=dict(reservation_doc),
                tokens=tokens,
                usd=str(usd),
            )
        return reservation

    def settle(
        self,
        attempt_id: str,
        *,
        input_tokens: int | None,
        output_tokens: int | None,
        actual_usd: Decimal | int | str | None,
    ) -> None:
        supplied = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "actual_usd": actual_usd,
        }
        known: dict[str, Any] = {}
        for key, value in supplied.items():
            if value is None:
                continue
            known[key] = _money(value, key) if key == "actual_usd" else _int(value, key)
        canonical = _canonical_usage(
            {key: known.get(key) for key in ("input_tokens", "output_tokens", "actual_usd")}
        )
        usable_known = all(canonical[key] is not None for key in ("input_tokens", "output_tokens", "actual_usd"))

        with self._txn() as state:
            if state is None:
                raise ValueError("ledger is not initialized")
            entry = state["attempts"].get(attempt_id)
            if entry is None:
                raise ValueError(f"attempt {attempt_id!r} is not reserved")
            current = entry["state"]
            if current != "reserved":
                stored = entry.get("usage") or {}
                if _same_usage(canonical, stored):
                    return
                raise ValueError(f"conflicting settlement for attempt in state {current}")
            now = self._now()
            reservation = entry["reservation"]
            reservation_doc = dict(reservation)

            if not usable_known:
                entry["state"] = "unknown"
                entry["usage"] = canonical
                entry["settled_at"] = now.isoformat()
                self._halt(
                    state,
                    "unknown_usage",
                    attempt_id,
                    state="unknown",
                    reservation=reservation_doc,
                    usage=dict(canonical),
                )
                return

            overrun = {
                "input_tokens": known["input_tokens"] > reservation["input_upper"],
                "output_tokens": known["output_tokens"] > reservation["output_upper"],
                "actual_usd": known["actual_usd"] > Decimal(reservation["usd_upper"]),
            }
            if any(overrun.values()):
                entry["state"] = "overrun"
                entry["usage"] = canonical
                entry["settled_at"] = now.isoformat()
                self._halt(
                    state,
                    "usage_overrun",
                    attempt_id,
                    state="overrun",
                    reservation=reservation_doc,
                    usage=dict(canonical),
                    dimensions=sorted(overrun),
                )
                raise BudgetExceeded("settled usage exceeds reservation")

            entry["state"] = "settled"
            entry["usage"] = canonical
            entry["settled_at"] = now.isoformat()
            self._event(
                state,
                "settle",
                attempt_id,
                state="settled",
                reservation=reservation_doc,
                usage=dict(canonical),
            )

    def stop(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        with self._txn() as state:
            if state is None:
                raise ValueError("ledger is not initialized")
            if state["stopped"]:
                return
            self._halt(state, reason)

    def snapshot(self) -> dict:
        with self._txn() as state:
            if state is None:
                raise ValueError("ledger is not initialized")
            settled_tokens, settled_usd = self._settled_totals(state)
            reserved_tokens = self._reserved_tokens(state)
            reserved_usd = self._reserved_usd(state)
            attempt_records = []
            for attempt_id, entry in state["attempts"].items():
                usage = entry.get("usage")
                attempt_records.append(
                    {
                        "attempt_id": attempt_id,
                        "state": entry["state"],
                        "reservation": dict(entry["reservation"]),
                        "started_at": entry.get("started_at"),
                        "settled_at": entry.get("settled_at"),
                        "usage": None if usage is None else dict(usage),
                    }
                )
            return {
                "reserved_tokens": reserved_tokens,
                "settled_tokens": settled_tokens,
                "attempt_count": len(state["attempts"]),
                "attempts": [record["attempt_id"] for record in attempt_records],
                "attempt_records": attempt_records,
                "stopped": state["stopped"],
                "stop_reason": state["stop_reason"],
                "reserved_usd": str(reserved_usd),
                "settled_usd": str(settled_usd),
                "config": dict(state["config"]),
                "events": json.loads(
                    json.dumps(state["events"], sort_keys=True, ensure_ascii=False, default=str)
                ),
            }

    def close(self) -> None:
        with self._lock:
            self._conn.close()
```
