from __future__ import annotations

import hashlib
import os

from test_contracts_preapproval import NOW, _base_config

from evidenceguard import runner
from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger


def _raw_record() -> dict:
    content = "SYNTHETIC fixture price 100"
    return {
        "run_id": "run-a",
        "kind": "market",
        "source_uri": "https://example.test/quote",
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "retrieved_at": NOW.isoformat(),
        "available_at": "2026-11-18T20:00:00Z",
    }


def _turns() -> list[dict]:
    man = create_manifest(_base_config(), now=NOW)
    led = EvidenceLedger(man)
    eid = led.add(_raw_record()).evidence_id
    return [
        {
            "role": "bull",
            "payload": {
                "cards": [
                    {
                        "kind": "fact",
                        "text": "Synthetic price is 100",
                        "evidence_ids": [eid],
                        "parent_claim_ids": [],
                        "uncertainty": "Synthetic data only",
                    }
                ],
                "reply_to": [],
                "conflicts": [],
                "stop_reason": "completed",
            },
        }
    ]


def _final() -> dict:
    return {
        "report": "Synthetic price [claim:0]",
        "rating": "Hold",
        "limitations": ["Synthetic data only"],
    }


def _replay(config: dict, turns=None, final=None) -> dict:
    return runner.replay(
        config,
        [_raw_record()],
        _turns() if turns is None else turns,
        _final() if final is None else final,
        now=NOW,
    )


def test_replay_completed_draft():
    config = _base_config()
    artifact = _replay(config)
    assert artifact["execution_status"] == "completed"
    assert artifact["validation_status"] == "passed"
    assert artifact["publication_status"] == "draft"
    assert artifact["review_status"] == "pending"
    assert artifact["artifact_hash"] is not None
    from evidenceguard import review

    assert review.artifact_hash(artifact) == artifact["artifact_hash"]
    assert "[claim:0]" not in artifact["report"]
    assert "[cl-" in artifact["report"]
    transcript = artifact["measurement"]["transcript"]
    assert transcript and transcript[0]["role"] == "bull"
    assert transcript[0]["rendered"]


def test_replay_deterministic():
    config = _base_config()
    first = _replay(config)
    second = _replay(config)
    assert first["artifact_hash"] == second["artifact_hash"]
    assert first["run_id"] == "run-a"


def test_unknown_evidence_ref_fails():
    config = _base_config()
    turns = _turns()
    turns[0]["payload"]["cards"][0]["evidence_ids"] = ["ev-unknown"]
    artifact = _replay(config, turns=turns)
    assert artifact["execution_status"] == "failed"
    assert artifact["publication_status"] == "draft"
    assert artifact["rating"] is None
    assert artifact["measurement"]["errors"]


def test_stop_reason_halts():
    config = _base_config()
    turns = [
        {
            "role": "bull",
            "payload": {
                "stop_reason": "no_evidence",
                "cards": [],
                "reply_to": [],
                "conflicts": [],
            },
        }
    ]
    artifact = _replay(config, turns=turns)
    assert artifact["execution_status"] == "stopped"
    assert artifact["publication_status"] == "draft"
    assert artifact["rating"] is None


def test_missing_limitations_not_filled():
    config = _base_config()
    final = _final()
    final["limitations"] = []
    artifact = _replay(config, final=final)
    assert artifact["limitations"] == []
    assert not artifact["gate_results"]["passed"]
    assert artifact["validation_status"] == "failed"


def test_write_read_roundtrip(tmp_path):
    artifact = _replay(_base_config())
    path = tmp_path / "artifact.json"
    runner.write_artifact(artifact, path)
    loaded = runner.read_artifact(path)
    assert loaded == artifact
    leftover = [name for name in os.listdir(tmp_path) if name.endswith(".tmp")]
    assert leftover == []


def test_summarize_fields():
    artifact = _replay(_base_config())
    text = runner.summarize(artifact)
    assert "run-a" in text
    assert "AAPL" in text
    assert "draft" in text
