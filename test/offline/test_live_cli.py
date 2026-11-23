import argparse
import json

import pytest
from test_contracts_preapproval import NOW
from test_snapshot import _quote, _Source
from test_upstream_runner import FakeModel, _raw_record

import evidenceguard.live_cli as mod
import evidenceguard.review as review
from evidenceguard.snapshot import freeze_snapshot


def _namespaces(**kw):
    return argparse.Namespace(**kw)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_now", lambda: NOW)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(mod, "RUNS_DIR", runs)
    monkeypatch.setattr(mod, "PROJECT_LEDGER_PATH", tmp_path / "shared.sqlite")
    monkeypatch.setattr(mod, "_source_dirty", lambda: False)
    return tmp_path


def _valid_snap():
    return freeze_snapshot("AAPL", clock=lambda: NOW, source=_Source(_quote()))


def test_snapshot_callback(frozen, monkeypatch, tmp_path):
    monkeypatch.setattr(mod.snapshot_mod, "freeze_snapshot", lambda ticker, clock: _valid_snap())
    out = tmp_path / "snap.json"
    args = _namespaces(ticker="AAPL", out=str(out))
    assert mod._do_snapshot(args) == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert "snapshot_hash" in data and data["snapshot_hash"]


def test_build_config(frozen):
    from evidenceguard import contracts

    snap = _valid_snap()
    snap_path = frozen / "snap.json"
    mod.runner.write_artifact(snap, str(snap_path))
    cfg = mod._build_config(snap, "c" * 40, "run-1", "candidate")
    assert isinstance(cfg, dict)
    assert cfg["dataset_hash"] == snap["snapshot_hash"]
    contracts.create_manifest(cfg, now=NOW)


def test_run_callback(frozen, monkeypatch):
    snap = _valid_snap()
    snap_path = frozen / "snap.json"
    mod.runner.write_artifact(snap, str(snap_path))
    out = frozen / "out.json"
    monkeypatch.setattr(
        mod, "make_chat_model", lambda *a, **k: FakeModel(_raw_record(), "candidate")
    )
    monkeypatch.setattr(mod, "_close_llm", lambda m: None)
    args = _namespaces(
        snapshot=str(snap_path),
        out=str(out),
        candidate_sha="c" * 40,
        arm="candidate",
    )
    assert mod._do_run(args) == 0
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["execution_status"] == "completed"
    assert data["validation_status"] == "passed"
    assert data["publication_status"] == "draft"
    assert data["gate_results"]["passed"] is True
    assert set(snap["limitations"]) <= set(data["limitations"])
    assert isinstance(data["measurement"]["source_manifest"], dict)
    assert data["artifact_hash"] == review.artifact_hash(data)
    assert (frozen / "shared.sqlite").exists()


def test_invalid_snapshot(frozen, monkeypatch, tmp_path):
    snap = _valid_snap()
    snap_path = tmp_path / "tamper.json"
    mod.runner.write_artifact(snap, str(snap_path))
    text = snap_path.read_text()
    tampered = text.replace("AAPL", "MSFT") if "AAPL" in text else text + "x"
    snap_path.write_text(tampered)

    def boom(*a, **k):
        raise AssertionError("make_chat_model must not be called")

    monkeypatch.setattr(mod, "make_chat_model", boom)
    out = tmp_path / "out.json"
    args = _namespaces(
        snapshot=str(snap_path),
        out=str(out),
        candidate_sha="c" * 40,
        arm="candidate",
    )
    with pytest.raises(ValueError):
        mod._do_run(args)
    assert not out.exists()
