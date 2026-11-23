import json
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_evaluation import _artifact, _plan

from evidenceguard import batch_cli
from evidenceguard.runner import write_artifact


def test_version_clean_and_rejections(monkeypatch):
    plan = _plan()

    def fake_run(argv, **kwargs):
        if "rev-parse" in argv:
            return SimpleNamespace(stdout=head + "\n", stderr="", returncode=0)
        if "diff" in argv:
            return SimpleNamespace(stdout="", stderr="", returncode=dirty)
        if "ls-files" in argv:
            return SimpleNamespace(stdout=untracked, stderr="", returncode=0)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    cases = [
        ("c" * 40, 0, "", False),
        ("b" * 40, 0, "", True),
        ("c" * 40, 1, "", True),
        ("c" * 40, 0, "src/evidenceguard/new.py", True),
    ]
    for head, dirty, untracked, expect_error in cases:  # noqa: B007 - fake_run closes over these values
        monkeypatch.setattr(batch_cli.subprocess, "run", fake_run)
        if expect_error:
            with pytest.raises(ValueError):
                batch_cli._check_version(plan)
        else:
            batch_cli._check_version(plan)


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("clean", 0),
        ("candidate_failed", 2),
        ("baseline_schema_failed", 0),
    ],
)
def test_execute(tmp_path, monkeypatch, mode, expected):
    plan = _plan()
    planpath = tmp_path / "plan.json"
    write_artifact(plan, planpath)
    monkeypatch.setattr(batch_cli, "ROOT", tmp_path)
    monkeypatch.setattr(batch_cli, "_check_version", lambda plan: None)
    calls = []

    def fake_do_run(args):
        snapshot = json.loads(Path(args.snapshot).read_text())
        calls.append((snapshot["ticker"], args.arm, args.candidate_sha))
        payload = _artifact()
        if mode == "candidate_failed" and args.arm == "candidate":
            payload = _artifact("failed", "failed")
        if mode == "baseline_schema_failed" and args.arm == "baseline":
            payload = _artifact("completed", "failed")
        write_artifact(payload, args.out)
        return 0 if payload.get("validation_status") == "passed" else 2

    monkeypatch.setattr(batch_cli.live_cli, "_do_run", fake_do_run)
    args = Namespace(plan=str(planpath), out_dir=str(tmp_path / "out"))
    assert batch_cli.do_execute(args) == expected
    assert calls == [(r["ticker"], r["arm"], plan["candidate_sha"]) for r in plan["rows"]]
    out = tmp_path / "out"
    results = json.loads((out / "results.json").read_text())
    assert len(results["records"]) == 12
    assert (out / "plan.json").exists()
    for r in plan["rows"]:
        assert (out / f"{r['run_id']}.json").exists()
    if mode == "candidate_failed":
        failed = json.loads((out / f"{plan['rows'][1]['run_id']}.json").read_text())
        assert failed["execution_status"] == "failed"
        assert failed["validation_status"] == "failed"
    if mode == "baseline_schema_failed":
        failed = json.loads((out / f"{plan['rows'][0]['run_id']}.json").read_text())
        assert failed["validation_status"] == "failed"


def test_existing_output_and_invalid_plan_no_callback(tmp_path, monkeypatch):
    monkeypatch.setattr(batch_cli, "ROOT", tmp_path)
    monkeypatch.setattr(batch_cli, "_check_version", lambda plan: None)

    def fake_do_run(args):
        raise AssertionError("_do_run must not be called")

    monkeypatch.setattr(batch_cli.live_cli, "_do_run", fake_do_run)
    plan = _plan()
    planpath = tmp_path / "plan.json"
    write_artifact(plan, planpath)

    existing = tmp_path / "out_existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        batch_cli.do_execute(Namespace(plan=str(planpath), out_dir=str(existing)))

    plan["rows"][0]["ticker"] = "INVALID"
    write_artifact(plan, planpath)
    fresh = tmp_path / "out_fresh"
    with pytest.raises(ValueError):
        batch_cli.do_execute(Namespace(plan=str(planpath), out_dir=str(fresh)))
