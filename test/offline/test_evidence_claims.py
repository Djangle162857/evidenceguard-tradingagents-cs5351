import hashlib
from datetime import UTC, datetime

import pytest

from evidenceguard.claims import validate_debate_turn
from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger

NOW = datetime(2026, 11, 18, 22, 0, 0, tzinfo=UTC)

MODEL_ID = "CS5351/DeepSeek-V4-Flash"
BASELINE_SHA = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
CANDIDATE_SHA = "c" * 40
DATASET_HASH = "b" * 64


def _base_config() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run-a",
        "revision": 1,
        "ticker": "AAPL",
        "as_of_utc": "2026-11-18T21:00:00Z",
        "analysts": ["market", "news"],
        "baseline_sha": BASELINE_SHA,
        "candidate_sha": CANDIDATE_SHA,
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
        "dataset_hash": DATASET_HASH,
    }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _manifest(run_id: str = "run-a"):
    cfg = _base_config()
    cfg["run_id"] = run_id
    return create_manifest(cfg, now=NOW)


def _record(
    kind,
    source_uri,
    content,
    *,
    time_field,
    time_value,
    run_id="run-a",
    retrieved_at="2026-11-18T20:30:00Z",
):
    return {
        "run_id": run_id,
        "kind": kind,
        "source_uri": source_uri,
        "retrieved_at": retrieved_at,
        time_field: time_value,
        "content": content,
        "content_hash": _sha(content),
        "excerpt": content[:40],
    }


def _market(
    content="market-body", uri="https://ex.test/market", available_at="2026-11-18T20:00:00Z", **kw
):
    return _record("market", uri, content, time_field="available_at", time_value=available_at, **kw)


def _news(
    content="news-body", uri="https://ex.test/news", published_at="2026-11-18T20:00:00Z", **kw
):
    return _record("news", uri, content, time_field="published_at", time_value=published_at, **kw)


@pytest.fixture
def manifest():
    return _manifest()


@pytest.fixture
def ledger(manifest):
    return EvidenceLedger(manifest)


def _eligible_id(ledger, record) -> str:
    return ledger.add(record).evidence_id


def _card(kind, text, evidence_ids, parent_claim_ids=None):
    return {
        "kind": kind,
        "text": text,
        "evidence_ids": list(evidence_ids),
        "parent_claim_ids": list(parent_claim_ids or []),
        "uncertainty": "low",
    }


def _turn(cards, reply_to=None, conflicts=None, stop_reason="completed"):
    return {
        "cards": list(cards),
        "reply_to": list(reply_to or []),
        "conflicts": list(conflicts or []),
        "stop_reason": stop_reason,
    }


ROLES = ["bull", "bear", "risky", "neutral", "safe"]


# ---- Evidence ----


def test_source_uri_preserved(ledger):
    uri = "https://ex.test/unique/source?q=1"
    entry = ledger.add(_market(uri=uri))
    assert entry.to_dict()["source_uri"] == uri


@pytest.mark.parametrize(
    "kind,time_field,time_value,expected",
    [
        ("market", "available_at", "2026-11-18T20:00:00Z", "eligible"),
        ("market", "available_at", "2026-11-18T21:00:00Z", "eligible"),
        ("market", "available_at", "2026-11-18T21:00:01Z", "excluded"),
        ("market", "available_at", None, "excluded"),
        ("news", "published_at", "2026-11-18T20:00:00Z", "eligible"),
        ("news", "published_at", "2026-11-18T21:00:00Z", "eligible"),
        ("news", "published_at", "2026-11-18T22:00:00Z", "excluded"),
        ("news", "published_at", None, "excluded"),
    ],
)
def test_qualification_uses_kind_time_field(ledger, kind, time_field, time_value, expected):
    rec = _record(kind, "https://ex.test/q", "body", time_field=time_field, time_value=time_value)
    entry = ledger.add(rec)
    assert entry.to_dict()["eligibility"] == expected


def test_late_retrieved_at_does_not_change_qualification(ledger):
    rec = _news(published_at="2026-11-18T20:00:00Z", retrieved_at="2026-11-18T23:00:00Z")
    entry = ledger.add(rec)
    d = entry.to_dict()
    assert d["eligibility"] == "eligible"
    assert d["retrieved_at"] == "2026-11-18T23:00:00Z"


@pytest.mark.parametrize("bad", ["2026-11-18T20:00:00", "not-a-time", "2026-13-01T00:00:00Z"])
def test_malformed_timestamp_rejected(ledger, bad):
    with pytest.raises(ValueError):
        ledger.add(_news(published_at=bad))


def test_wrong_run_rejected(manifest):
    ledger = EvidenceLedger(manifest)
    with pytest.raises(ValueError):
        ledger.add(_market(run_id="run-b"))


def test_content_hash_mismatch_rejected(ledger):
    rec = _market()
    rec["content_hash"] = "f" * 64
    with pytest.raises(ValueError):
        ledger.add(rec)


def test_distinct_sources_not_merged(ledger):
    a = ledger.add(_market(uri="https://ex.test/a", content="same"))
    b = ledger.add(_market(uri="https://ex.test/b", content="same"))
    assert a.evidence_id != b.evidence_id
    assert len(ledger.entries) == 2


def test_duplicate_same_source_same_id(ledger):
    first = ledger.add(_market(uri="https://ex.test/dup", content="dup-body"))
    second = ledger.add(_market(uri="https://ex.test/dup", content="dup-body"))
    assert first.evidence_id == second.evidence_id
    d = first.to_dict()
    d["source_uri"] = "tampered"
    assert ledger.get(first.evidence_id).to_dict()["source_uri"] != "tampered"


# ---- Claims ----


def _validate(payload, role, manifest, ledger, existing=None):
    return validate_debate_turn(
        payload, role=role, manifest=manifest, ledger=ledger, existing_claims=list(existing or [])
    )


@pytest.mark.parametrize("role", ROLES)
def test_fact_with_one_valid_evidence_all_roles(role, manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/r-" + role))
    turn = _validate(_turn([_card("fact", "x", [eid])]), role, manifest, ledger)
    cards = turn.to_dict()["cards"]
    assert len(cards) == 1
    assert cards[0]["kind"] == "fact"
    assert cards[0]["evidence_ids"] == [eid]


def test_inference_with_existing_parent(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/parent"))
    first = _validate(_turn([_card("fact", "f", [eid])]), "bull", manifest, ledger)
    parent_id = first.to_dict()["cards"][0]["claim_id"]
    second = _validate(
        _turn([_card("inference", "i", [], [parent_id])]),
        "bear",
        manifest,
        ledger,
        [first.to_dict()["cards"][0]],
    )
    assert second.to_dict()["cards"][0]["parent_claim_ids"] == [parent_id]


def test_deterministic_ids(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/det"))
    payload = _turn([_card("fact", "same", [eid])])
    a = _validate(payload, "neutral", manifest, ledger).to_dict()["cards"][0]["claim_id"]
    b = _validate(payload, "neutral", manifest, ledger).to_dict()["cards"][0]["claim_id"]
    assert a == b


@pytest.mark.parametrize(
    "card",
    [
        _card("fact", "no-evidence", []),
        _card("fact", "unknown-evidence", ["evid-unknown"]),
    ],
)
def test_rejected_invalid_evidence(card, manifest, ledger):
    _eligible_id(ledger, _market(uri="https://ex.test/other"))
    with pytest.raises(ValueError):
        _validate(_turn([card]), "bull", manifest, ledger)


def test_rejected_excluded_evidence(manifest, ledger):
    eid = _eligible_id(
        ledger, _news(published_at="2026-11-18T22:30:00Z", uri="https://ex.test/future")
    )
    assert ledger.get(eid).to_dict()["eligibility"] == "excluded"
    with pytest.raises(ValueError):
        _validate(_turn([_card("fact", "f", [eid])]), "bull", manifest, ledger)


@pytest.mark.parametrize(
    "card",
    [
        _card("inference", "missing-parent", [], ["parent-unknown"]),
    ],
)
def test_rejected_missing_parent(card, manifest, ledger):
    with pytest.raises(ValueError):
        _validate(_turn([card]), "bull", manifest, ledger)


def test_rejected_untrusted_claim_id(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/trust"))
    card = _card("fact", "f", [eid])
    card["claim_id"] = "attacker-chosen"
    with pytest.raises(ValueError):
        _validate(_turn([card]), "bull", manifest, ledger)


def test_rejected_unknown_reply(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/reply"))
    with pytest.raises(ValueError):
        _validate(
            _turn([_card("fact", "f", [eid])], reply_to="claim-unknown"), "bull", manifest, ledger
        )


def test_rejected_unknown_conflict(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/conflict"))
    with pytest.raises(ValueError):
        _validate(
            _turn([_card("fact", "f", [eid])], conflicts=["claim-unknown"]),
            "bull",
            manifest,
            ledger,
        )


def test_rejected_duplicate_cards(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/dupcard"))
    card = _card("fact", "same", [eid])
    with pytest.raises(ValueError):
        _validate(_turn([card, dict(card)]), "bull", manifest, ledger)


def test_rejected_cycle_in_existing_graph(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/cycle"))
    first = _validate(_turn([_card("fact", "f", [eid])]), "bull", manifest, ledger)
    c1 = first.to_dict()["cards"][0]
    second = _validate(
        _turn([_card("inference", "i", [], [c1["claim_id"]])]), "bear", manifest, ledger, [c1]
    )
    c2 = second.to_dict()["cards"][0]
    c1["parent_claim_ids"] = [c2["claim_id"]]
    with pytest.raises(ValueError):
        _validate(
            _turn([_card("inference", "i", [], [c2["claim_id"]])]),
            "bull",
            manifest,
            ledger,
            [c2, dict(c1)],
        )


def test_to_dict_mutation_does_not_mutate_turn(manifest, ledger):
    eid = _eligible_id(ledger, _market(uri="https://ex.test/immutable"))
    turn = _validate(_turn([_card("fact", "f", [eid])]), "safe", manifest, ledger)
    snapshot = turn.to_dict()
    mutated = turn.to_dict()
    mutated["cards"].clear()
    assert turn.to_dict()["cards"] == snapshot["cards"]
