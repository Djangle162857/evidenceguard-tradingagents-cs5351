from __future__ import annotations

import copy
import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .budget import BudgetExceeded
from .runner import write_artifact
from .snapshot import validate_snapshot
from .transport import TransportError

MODEL_ID = "CS5351/DeepSeek-V4-Flash"
SCHEMA_VERSION = "1.0"

# Fixed preregistered row order and arm assignment per (ticker, repeat).
ROW_PLAN = (
    ("AAPL", 1, "baseline"),
    ("AAPL", 1, "candidate"),
    ("AAPL", 2, "candidate"),
    ("AAPL", 2, "baseline"),
    ("MSFT", 1, "candidate"),
    ("MSFT", 1, "baseline"),
    ("MSFT", 2, "baseline"),
    ("MSFT", 2, "candidate"),
    ("NVDA", 1, "baseline"),
    ("NVDA", 1, "candidate"),
    ("NVDA", 2, "candidate"),
    ("NVDA", 2, "baseline"),
)

TICKERS = ("AAPL", "MSFT", "NVDA")
REPEATS = (1, 2)
ARMS = ("baseline", "candidate")


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _check_sha(value: Any, name: str) -> None:
    if not isinstance(value, str) or len(value) != 40:
        raise ValueError(f"{name} must be a 40-character hex SHA string")
    int(value, 16)


def _snapshot_by_ticker(snapshots: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(snapshots, list) or len(snapshots) != 3:
        raise ValueError("exactly 3 snapshots required")
    by_ticker: dict[str, dict[str, Any]] = {}
    for snap in snapshots:
        if not isinstance(snap, dict):
            raise ValueError("snapshot must be a dict")
        ticker = snap.get("ticker")
        if ticker not in TICKERS:
            raise ValueError(f"unexpected ticker: {ticker!r}")
        if ticker in by_ticker:
            raise ValueError(f"duplicate ticker: {ticker}")
        if validate_snapshot(snap) is not True:
            raise ValueError(f"invalid snapshot for {ticker}")
        by_ticker[ticker] = snap
    if set(by_ticker) != set(TICKERS):
        raise ValueError("snapshots must cover AAPL, MSFT, NVDA")
    return by_ticker


def _plan_hash(plan: dict[str, Any]) -> str:
    body = {k: v for k, v in plan.items() if k != "plan_hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


def prepare_plan(
    snapshots: list[dict[str, Any]],
    *,
    baseline_sha: str,
    candidate_sha: str,
) -> dict[str, Any]:
    _check_sha(baseline_sha, "baseline_sha")
    _check_sha(candidate_sha, "candidate_sha")
    by_ticker = _snapshot_by_ticker(snapshots)

    rows: list[dict[str, Any]] = []
    for ticker, repeat, arm in ROW_PLAN:
        rows.append(
            {
                "run_id": f"{ticker}-{repeat}-{arm}",
                "ticker": ticker,
                "repeat": repeat,
                "arm": arm,
                "snapshot_hash": by_ticker[ticker]["snapshot_hash"],
            }
        )

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "baseline_sha": baseline_sha,
        "candidate_sha": candidate_sha,
        "model_id": MODEL_ID,
        "rows": rows,
        "snapshots": copy.deepcopy(snapshots),
    }
    plan["plan_hash"] = _plan_hash(plan)
    return plan


def validate_plan(plan: dict[str, Any]) -> None:
    if not isinstance(plan, dict):
        raise ValueError("plan must be a dict")
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unexpected schema_version")
    _check_sha(plan.get("baseline_sha"), "baseline_sha")
    _check_sha(plan.get("candidate_sha"), "candidate_sha")
    if plan.get("model_id") != MODEL_ID:
        raise ValueError("unexpected model_id")
    stored = plan.get("plan_hash")
    if not isinstance(stored, str) or stored != _plan_hash(plan):
        raise ValueError("plan_hash mismatch")

    by_ticker = _snapshot_by_ticker(plan.get("snapshots"))

    rows = plan.get("rows")
    if not isinstance(rows, list) or len(rows) != len(ROW_PLAN):
        raise ValueError("plan must contain exactly 12 rows")

    seen = set()
    combo = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("row must be a dict")
        ticker = row.get("ticker")
        repeat = row.get("repeat")
        arm = row.get("arm")
        key = (ticker, repeat, arm)
        if ticker not in TICKERS or repeat not in REPEATS or arm not in ARMS:
            raise ValueError(f"row outside preregistered grid: {key}")
        if key in combo:
            raise ValueError(f"duplicate row combination: {key}")
        combo.add(key)
        expected_id = f"{ticker}-{repeat}-{arm}"
        if row.get("run_id") != expected_id:
            raise ValueError(f"run_id mismatch for {key}")
        snap = by_ticker.get(ticker)
        if snap is None:
            raise ValueError(f"no snapshot for {ticker}")
        if row.get("snapshot_hash") != snap["snapshot_hash"]:
            raise ValueError(f"snapshot_hash mismatch for {ticker}")
        if expected_id in seen:
            raise ValueError(f"duplicate run_id: {expected_id}")
        seen.add(expected_id)

    if len(combo) != len(TICKERS) * len(REPEATS) * len(ARMS):
        raise ValueError("rows must be the full Cartesian product")

    actual_order = tuple((r["ticker"], r["repeat"], r["arm"]) for r in rows)
    if actual_order != ROW_PLAN:
        raise ValueError("rows not in preregistered order")


def _extract_run_budget(artifact: Any) -> Any:
    if isinstance(artifact, dict):
        measurement = artifact.get("measurement")
        if isinstance(measurement, dict):
            if "run_budget" in measurement:
                return measurement["run_budget"]
            project = measurement.get("project_budget")
            if isinstance(project, dict):
                return project
    return None


def _project_stopped(artifact: Any) -> bool:
    if isinstance(artifact, dict):
        measurement = artifact.get("measurement")
        if isinstance(measurement, dict):
            project = measurement.get("project_budget")
            if isinstance(project, dict) and project.get("stopped") is True:
                return True
    return False


def execute_plan(
    plan: dict[str, Any],
    *,
    run_one: Callable[[dict[str, Any], dict[str, Any]], Any],
    output_dir: Path,
) -> dict[str, Any]:
    validate_plan(plan)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=False)

    write_artifact(plan, out / "plan.json")

    snapshots_by_ticker = {s["ticker"]: s for s in plan["snapshots"]}
    records: list[dict[str, Any]] = []
    stopped_reason: str | None = None

    def _save() -> None:
        write_artifact(
            {"plan_hash": plan["plan_hash"], "records": records},
            out / "results.json",
        )

    for row in plan["rows"]:
        base = dict(row)
        if stopped_reason is not None:
            base.update(
                {
                    "execution_status": "not_run",
                    "validation_status": None,
                    "artifact_hash": None,
                    "run_budget": None,
                    "elapsed_seconds": None,
                    "semantic_labels": None,
                    "rubric": None,
                    "error": stopped_reason,
                }
            )
            records.append(base)
            _save()
            continue

        snap = copy.deepcopy(snapshots_by_ticker[row["ticker"]])
        start = time.monotonic()
        try:
            artifact = run_one(dict(row), snap)
        except (BudgetExceeded, TransportError) as exc:
            elapsed = time.monotonic() - start
            base.update(
                {
                    "execution_status": "stopped",
                    "validation_status": None,
                    "artifact_hash": None,
                    "run_budget": None,
                    "elapsed_seconds": elapsed,
                    "semantic_labels": None,
                    "rubric": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            records.append(base)
            stopped_reason = type(exc).__name__
            _save()
            continue
        except Exception as exc:  # noqa: BLE001 - record and continue
            elapsed = time.monotonic() - start
            base.update(
                {
                    "execution_status": "failed",
                    "validation_status": None,
                    "artifact_hash": None,
                    "run_budget": None,
                    "elapsed_seconds": elapsed,
                    "semantic_labels": None,
                    "rubric": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            records.append(base)
            _save()
            continue

        elapsed = time.monotonic() - start
        if not isinstance(artifact, dict):
            base.update(
                {
                    "execution_status": "failed",
                    "validation_status": None,
                    "artifact_hash": None,
                    "run_budget": None,
                    "elapsed_seconds": elapsed,
                    "semantic_labels": None,
                    "rubric": None,
                    "error": {
                        "type": "TypeError",
                        "message": f"run_one returned {type(artifact).__name__}",
                    },
                }
            )
            records.append(base)
            _save()
            stop_due_to_budget = False
        else:
            artifact_path = out / f"{row['run_id']}.json"
            write_artifact(artifact, artifact_path)

            measurement = artifact.get("measurement")
            if not isinstance(measurement, dict):
                measurement = {}
            run_budget = measurement.get("run_budget")

            error = measurement.get("errors") or None
            validation_status = artifact.get("validation_status")
            artifact_hash = artifact.get("artifact_hash")
            exec_status = artifact.get("execution_status", "failed")
            base.update(
                {
                    "execution_status": exec_status,
                    "validation_status": validation_status,
                    "artifact_hash": artifact_hash,
                    "run_budget": run_budget,
                    "elapsed_seconds": elapsed,
                    "semantic_labels": None,
                    "rubric": None,
                    "error": error,
                }
            )
            records.append(base)
            stop_due_to_budget = _project_stopped(artifact)
        _save()

        if stop_due_to_budget:
            stopped_reason = "project_stopped"

    _save()
    return {"plan_hash": plan["plan_hash"], "records": records}
