"""Behavioral tests for the release gate and review workflow (FR004/FR007).

Test-only preparation artifact. Exercises ONLY the public interfaces documented
in docs/architecture/interface-contracts.md. Independent fixtures inline; no
import of implementation-private functions.

    evidenceguard.contracts.create_manifest
    evidenceguard.evidence.EvidenceLedger
    evidenceguard.claims.validate_debate_turn
    evidenceguard.gate.validate_artifact
    evidenceguard.review.artifact_hash / ReviewStore / publish
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from evidenceguard.claims import validate_debate_turn
from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger
from evidenceguard.gate import validate_artifact
from evidenceguard.review import ReviewStore, artifact_hash, publish

NOW = datetime(2026, 11, 18, 22, 0, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)
MODEL_ID = "CS5351/DeepSeek-V4-Flash"
BASELINE = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
CANDIDATE = "c" * 40
DATASET = "b" * 64
PROMOTIONS = ("execution_status", "validation_status", "review_status", "publication_status")


def _config(**over):
    base = {
        "schema_version": "1.0",
        "run_id": "run-a",
        "revision": 1,
        "ticker": "AAPL",
        "as_of_utc": "2026-11-18T21:00:00Z",
        "analysts": ["market", "news"],
        "baseline_sha": BASELINE,
        "candidate_sha": CANDIDATE,
        "model_id": MODEL_ID,
        "prompt_version": "1.0",
        "policy_version": "1.0",
        "budget": {
            "token_limit": 60000,
            "attempt_limit": 30,
            "deadline_seconds": 900,
            "input_upper_per_call": 8000,
            "output_upper_per_call": 1024,
        },
        "dataset_hash": DATASET,
    }
    base.update(over)
    return base


@pytest.fixture()
def manifest():
    return create_manifest(_config(), now=NOW)


def _market_record(content="Market close 182.50 up 1.2%"):
    return {
        "run_id": "run-a",
        "kind": "market",
        "source_uri": "https://example.test/market",
        "retrieved_at": "2026-11-18T20:30:00Z",
        "published_at": "2026-11-18T20:15:00Z",
        "available_at": "2026-11-18T20:00:00Z",
        "excerpt": content[:40],
        "content": content,
        "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


@pytest.fixture()
def ledger(manifest):
    led = EvidenceLedger(manifest)
    led.add(_market_record())
    return led


def _claims(manifest, ledger):
    entries = list(ledger.entries)
    ids = [e.evidence_id for e in entries]
    turn = validate_debate_turn(
        {
            "cards": [
                {
                    "kind": "fact",
                    "text": "Close reached 182.50.",
                    "evidence_ids": ids,
                    "parent_claim_ids": [],
                    "uncertainty": "low",
                }
            ],
            "reply_to": [],
            "conflicts": [],
            "stop_reason": "completed",
        },
        role="bull",
        manifest=manifest,
        ledger=ledger,
        existing_claims=[],
    )
    return list(turn.to_dict()["cards"])


def _artifact(manifest, ledger):
    claims = _claims(manifest, ledger)
    lead = claims[0]["claim_id"]
    entries = [e.to_dict() for e in ledger.entries]
    out = {
        "schema_version": "1.0",
        "run_id": "run-a",
        "revision": 1,
        "manifest": manifest.to_dict(),
        "evidence": entries,
        "claims": claims,
        "report": f"Apple closed higher. [{lead}]",
        "rating": "Hold",
        "limitations": ["Single fixture source."],
        "policy_version": "1.0",
        "execution_status": "completed",
        "validation_status": "pending",
        "review_status": "draft",
        "publication_status": "draft",
        "gate_results": {"passed": True, "violations": []},
        "measurement": {"duration_ms": 1234, "started_at": "2026-11-18T21:00:00Z"},
    }
    out["artifact_hash"] = artifact_hash(out)
    return out


@pytest.fixture()
def artifact(manifest, ledger):
    return _artifact(manifest, ledger)


def _gate(artifact, manifest, ledger, claims=None):
    return validate_artifact(
        artifact,
        manifest=manifest,
        ledger=ledger,
        claims=list(artifact["claims"] if claims is None else claims),
    )


def _passed(result):
    if isinstance(result, dict):
        return bool(result["passed"])
    return bool(result.passed)


def _store(tmp_path):
    return ReviewStore(tmp_path / "fixtures", test_mode=True)


def _approve(store, artifact, reason="ok", now=NOW):
    return store.record(
        artifact,
        reviewer_id="fixture-reviewer",
        decision="approve",
        reason=reason,
        authorization_source="test_fixture",
        now=now,
    )


# ---------------------------------------------------------------- gate: clean
def test_valid_artifact_passes(artifact, manifest, ledger):
    assert _passed(_gate(artifact, manifest, ledger)) is True


# ------------------------------------------------------------- gate: rejects
def _drop_claim(fn):
    def mut(art, man, led):
        art["claims"] = [c for i, c in enumerate(art["claims"]) if not fn(i)]

    return mut


def _set_claim(**kw):
    def mut(art, man, led):
        art["claims"][0].update(kw)

    return mut


def _set_report(text):
    def mut(art, man, led):
        art["report"] = text

    return mut


def _set_field(**kw):
    def mut(art, man, led):
        art.update(kw)

    return mut


def _mutate_manifest(key, value):
    def mut(art, man, led):
        art["manifest"][key] = value

    return mut


def _mutate_evidence(key, value):
    def mut(art, man, led):
        art["evidence"][0][key] = value

    return mut


def _append_duplicate(art, man, led):
    art["claims"].append(deepcopy(art["claims"][0]))


CASES = {
    "missing_report": _set_report(""),
    "uncited_report": _set_report("No citation here."),
    "unknown_bracket_ref": _set_report("Claim [" + "cl-" + "f" * 64 + "]"),
    "invalid_rating": _set_field(rating="StrongBuy"),
    "no_limitation": _set_field(limitations=[" "]),
    "stopped_execution": _set_field(execution_status="stopped"),
    "fact_without_refs": _set_claim(evidence_ids=[]),
    "nonexistent_refs": _set_claim(evidence_ids=["ev-missing"]),
    "wrong_run": _set_field(run_id="run-z"),
    "wrong_revision": _set_field(revision=2),
    "wrong_policy": _set_field(policy_version="2.0"),
    "wrong_manifest": _mutate_manifest("ticker", "MSFT"),
    "content_tamper": _mutate_evidence("content", "tampered"),
    "duplicate_claims": _append_duplicate,
}

MISSING_FIELDS = ["report", "rating", "limitations", "manifest", "evidence", "claims"]


def _apply(name, artifact, manifest, ledger):
    if name == "parent_cycle":
        art = deepcopy(artifact)
        cid = art["claims"][0]["claim_id"]
        art["claims"][0]["parent_claim_ids"] = [cid]
        return art, manifest, ledger, art.get("claims", [])
    if name.startswith("missing_"):
        art = deepcopy(artifact)
        art.pop(name[len("missing_") :], None)
        return art, manifest, ledger, art.get("claims", [])
    art = deepcopy(artifact)
    CASES[name](art, manifest, ledger)
    return art, manifest, ledger, art.get("claims", [])


@pytest.mark.parametrize("name", sorted(CASES) + ["missing_" + f for f in MISSING_FIELDS])
def test_gate_rejects(name, artifact, manifest, ledger):
    art, man, led, claims = _apply(name, artifact, manifest, ledger)
    assert _passed(_gate(art, man, led, claims)) is False


def test_gate_rejects_unknown_tool_field(artifact, manifest, ledger):
    art = deepcopy(artifact)
    art["claims"][0]["tool_call"] = {"name": "broker_order"}
    assert _passed(_gate(art, manifest, ledger, art["claims"])) is False


def test_malformed_entries_do_not_crash(artifact, manifest, ledger):
    art = deepcopy(artifact)
    art["claims"].append({"claim_id": None, "kind": "weird"})
    result = _gate(art, manifest, ledger, art["claims"])
    assert _passed(result) is False


# ---------------------------------------------------------- review workflow
def test_publish_without_approval_rejected(tmp_path, artifact, manifest, ledger):
    with pytest.raises(ValueError):
        publish(artifact, store=_store(tmp_path), now=LATER)


def test_approval_bound_to_hash_publishes_copy(tmp_path, artifact, manifest, ledger):
    store = _store(tmp_path)
    out = _approve(store, artifact)
    assert out is not None
    released = publish(artifact, store=store, now=LATER)
    assert released["publication_status"] == "released"
    assert artifact["publication_status"] == "draft"


BUSINESS = ["report", "rating", "limitations", "claims", "evidence", "policy_version"]


@pytest.mark.parametrize("field", BUSINESS)
def test_mutated_business_field_voids_old_approval(tmp_path, artifact, field):
    store = _store(tmp_path)
    _approve(store, artifact)
    art = deepcopy(artifact)
    if field == "claims":
        art["claims"][0]["text"] = "Different statement."
    elif field == "evidence":
        art["evidence"][0]["content"] = "other"
    elif field == "rating":
        art["rating"] = "Sell"
    elif field == "limitations":
        art["limitations"].append("Second limitation.")
    else:
        art[field] = art[field] + "-mutated"
    art["artifact_hash"] = artifact_hash(art)
    assert art["artifact_hash"] != artifact_hash(artifact)
    with pytest.raises(ValueError):
        publish(art, store=store, now=LATER)


def test_latest_reject_after_approve_blocks(tmp_path, artifact):
    store = _store(tmp_path)
    _approve(store, artifact)
    store.record(
        artifact,
        reviewer_id="fixture-reviewer",
        decision="reject",
        reason="rechecked",
        authorization_source="test_fixture",
        now=NOW + timedelta(minutes=5),
    )
    with pytest.raises(ValueError):
        publish(artifact, store=store, now=LATER)


def test_invalid_gate_cannot_be_approved_or_published(tmp_path, artifact, manifest, ledger):
    art = deepcopy(artifact)
    art["rating"] = "YOLO"
    art["artifact_hash"] = artifact_hash(art)
    art["gate_results"] = {"passed": True, "violations": []}
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        _approve(store, art)
    with pytest.raises(ValueError):
        publish(art, store=store, now=LATER)


def test_measurement_does_not_affect_hash(artifact):
    art = deepcopy(artifact)
    art["measurement"] = {"duration_ms": 99, "started_at": "2026-11-18T20:00:00Z"}
    assert artifact_hash(art) == artifact_hash(artifact)


@pytest.mark.parametrize("field", ["report", "evidence"])
def test_report_and_content_change_hash(artifact, field):
    art = deepcopy(artifact)
    if field == "report":
        art["report"] = art["report"] + " More."
    else:
        art["evidence"][0]["content"] = "changed"
    assert artifact_hash(art) != artifact_hash(artifact)


def test_test_fixture_refused_by_real_store(tmp_path, artifact):
    real = ReviewStore(tmp_path / "real")
    with pytest.raises(ValueError):
        real.record(
            artifact,
            reviewer_id="fixture-reviewer",
            decision="approve",
            reason="nope",
            authorization_source="test_fixture",
            now=NOW,
        )


def test_mismatched_artifact_hash_rejected(tmp_path, artifact):
    store = _store(tmp_path)
    _approve(store, artifact)
    art = deepcopy(artifact)
    art["artifact_hash"] = "f" * 64
    with pytest.raises(ValueError):
        publish(art, store=store, now=LATER)


def test_future_approval_cannot_publish_at_earlier_now(tmp_path, artifact):
    store = _store(tmp_path)
    _approve(store, artifact, now=LATER)
    with pytest.raises(ValueError):
        publish(artifact, store=store, now=NOW)


def _projection(art):
    return {
        "schema_version": art["schema_version"],
        "run_id": art["run_id"],
        "revision": art["revision"],
        "manifest": art["manifest"],
        "evidence": art["evidence"],
        "claims": art["claims"],
        "report": art["report"],
        "rating": art["rating"],
        "limitations": art["limitations"],
        "policy_version": art["policy_version"],
    }


def test_deterministic_hash_matches_haslib_projection(artifact):
    payload = json.dumps(
        _projection(artifact),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    assert artifact_hash(artifact) == expected
    assert artifact_hash(artifact) == artifact_hash(deepcopy(artifact))


def test_nan_in_business_projection_rejected(artifact):
    art = deepcopy(artifact)
    art["claims"][0]["uncertainty"] = float("nan")
    try:
        h = artifact_hash(art)
    except (ValueError, TypeError):
        return
    assert math.isnan(h) is False and isinstance(h, str) and h != artifact_hash(artifact)
