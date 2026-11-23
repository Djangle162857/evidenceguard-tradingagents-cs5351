import pytest
from test_contracts_preapproval import NOW
from test_snapshot import _quote, _Source

from evidenceguard.budget import BudgetExceeded
from evidenceguard.evaluation import execute_plan, prepare_plan, validate_plan
from evidenceguard.snapshot import freeze_snapshot

BASELINE = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
CANDIDATE = "c" * 40


def _snapshots():
    return [
        freeze_snapshot(ticker, clock=lambda: NOW, source=_Source(_quote()))
        for ticker in ("AAPL", "MSFT", "NVDA")
    ]


def _plan():
    return prepare_plan(_snapshots(), baseline_sha=BASELINE, candidate_sha=CANDIDATE)


def _artifact(execution_status="completed", validation_status="passed", digest="a" * 64):
    return {
        "execution_status": execution_status,
        "validation_status": validation_status,
        "artifact_hash": digest,
        "measurement": {
            "run_budget": {"settled_tokens": 110, "settled_usd": "0.000042"},
            "project_budget": {"stopped": False},
        },
    }


def _run_one(row, snapshot):
    return _artifact()


def test_plan_is_full_independent_cartesian_grid():
    plan = _plan()
    assert set(plan) == {
        "schema_version",
        "model_id",
        "baseline_sha",
        "candidate_sha",
        "snapshots",
        "rows",
        "plan_hash",
    }
    rows = plan["rows"]
    assert len(rows) == 12
    ids = [row["run_id"] for row in rows]
    assert len(set(ids)) == 12
    keys = {(row["ticker"], row["repeat"], row["arm"]) for row in rows}
    assert len(keys) == 12
    assert keys == {
        (t, r, a)
        for t in ("AAPL", "MSFT", "NVDA")
        for r in (1, 2)
        for a in ("baseline", "candidate")
    }
    first = [(r["ticker"], r["repeat"], r["arm"]) for r in rows[:4]]
    assert first == [
        ("AAPL", 1, "baseline"),
        ("AAPL", 1, "candidate"),
        ("AAPL", 2, "candidate"),
        ("AAPL", 2, "baseline"),
    ]
    by_ticker = {s["ticker"]: s["snapshot_hash"] for s in plan["snapshots"]}
    for row in rows:
        assert row["snapshot_hash"] == by_ticker[row["ticker"]]
    assert validate_plan(plan) is None
    assert plan["baseline_sha"] == BASELINE
    assert plan["candidate_sha"] == CANDIDATE


def test_unrehashed_tamper_detected():
    plan = _plan()
    plan["rows"][0]["arm"] = "candidate"
    with pytest.raises(ValueError):
        validate_plan(plan)


def test_snapshot_identity_validation():
    snaps = _snapshots()
    with pytest.raises(ValueError):
        prepare_plan(snaps[:2], baseline_sha=BASELINE, candidate_sha=CANDIDATE)
    with pytest.raises(ValueError):
        prepare_plan(
            [snaps[0], snaps[1], snaps[1]],
            baseline_sha=BASELINE,
            candidate_sha=CANDIDATE,
        )


def test_execute_plan_records_and_artifacts(tmp_path):
    calls = []

    def run_one(row, snapshot):
        calls.append((row["run_id"], snapshot))
        return _artifact()

    out = tmp_path / "out"
    result = execute_plan(_plan(), run_one=run_one, output_dir=out)
    assert len(calls) == 12
    assert {c[0] for c in calls} == {r["run_id"] for r in _plan()["rows"]}
    records = result["records"]
    assert len(records) == 12
    for record in records:
        assert record["execution_status"] == "completed"
        assert record["validation_status"] == "passed"
        assert record["semantic_labels"] is None
        assert record["rubric"] is None
    json_files = list(out.glob("*.json"))
    assert len(json_files) == 14
    assert out.joinpath("plan.json").exists()
    assert out.joinpath("results.json").exists()
    artifacts = [p for p in json_files if p.name not in {"plan.json", "results.json"}]
    assert len(artifacts) == 12
    for record in records:
        assert record["run_budget"] == {
            "settled_tokens": 110,
            "settled_usd": "0.000042",
        }


def test_budget_exceeded_stops_remaining_rows(tmp_path):
    calls = []

    def run_one(row, snapshot):
        calls.append(row["run_id"])
        raise BudgetExceeded("stop")

    out = tmp_path / "out"
    result = execute_plan(_plan(), run_one=run_one, output_dir=out)
    assert len(calls) == 1
    records = result["records"]
    assert len(records) == 12
    assert records[0]["execution_status"] == "stopped"
    assert records[0]["validation_status"] is None
    assert records[0]["error"]
    for record in records[1:]:
        assert record["execution_status"] == "not_run"
        assert record["validation_status"] is None
    assert out.joinpath("results.json").exists()


def test_existing_output_dir_rejected_before_callback(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    calls = []

    def run_one(row, snapshot):
        calls.append(row["run_id"])
        return _artifact()

    with pytest.raises(FileExistsError):
        execute_plan(_plan(), run_one=run_one, output_dir=out)
    assert calls == []


def test_failed_artifact_is_authoritative(tmp_path):
    failed = _artifact("failed", "failed", "b" * 64)
    failed["measurement"]["errors"] = [{"type": "RuntimeError", "message": "upstream failed"}]
    failed["measurement"]["execution_status"] = "completed"
    failed["measurement"]["validation_status"] = "passed"
    failed["measurement"]["artifact_hash"] = "f" * 64

    def run_one(row, snapshot):
        return failed

    out = tmp_path / "out"
    result = execute_plan(_plan(), run_one=run_one, output_dir=out)
    records = result["records"]
    assert len(records) == 12
    for record in records:
        assert record["execution_status"] == "failed"
        assert record["validation_status"] == "failed"
        assert record["artifact_hash"] == "b" * 64
        assert record["error"] == [{"type": "RuntimeError", "message": "upstream failed"}]
