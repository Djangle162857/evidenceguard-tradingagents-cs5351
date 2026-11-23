"""Tests for the v0.3 research context builder (deterministic, public API only)."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest

from evidenceguard.research_context import build_research_context

AS_OF = "2026-11-18T21:00:00Z"

BASE_KEYS = (
    "run_id",
    "kind",
    "eligibility",
    "available_at",
    "published_at",
    "source_uri",
    "content",
    "excerpt",
)


def _evidence(evidence_id, run_id, kind, eligibility, available_at, published_at,
              source_uri, content, excerpt):
    return {
        "evidence_id": evidence_id,
        "run_id": run_id,
        "kind": kind,
        "eligibility": eligibility,
        "available_at": available_at,
        "published_at": published_at,
        "source_uri": source_uri,
        "content": content,
        "excerpt": excerpt,
    }


def _ev(n):
    return f"ev-{n:064x}"


def _mk_manifest(as_of=AS_OF, run_id="r1"):
    def to_dict():
        return {"run_id": run_id, "as_of_utc": as_of}

    return SimpleNamespace(to_dict=to_dict)


def _mk_ledger(records):
    entries = [SimpleNamespace(to_dict=(lambda f=dict(rec): f)) for rec in records]
    return SimpleNamespace(entries=entries)


def _base_records():
    return [
        _evidence(_ev(1), "r1", "market", "eligible", "2026-11-18T19:00:00Z",
                  "2026-11-18T17:00:00Z", "https://a.example/m1", "m1", "m1 excerpt"),
        _evidence(_ev(2), "r1", "market", "eligible", "2026-11-18T20:00:00Z",
                  "2026-11-18T16:00:00Z", "https://a.example/m2", "m2", "m2 excerpt"),
        _evidence(_ev(4), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T20:00:00Z", "https://a.example/n4", "n4", "n4 excerpt"),
        _evidence(_ev(5), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T20:00:00Z", "https://a.example/n5", "n5", "n5 excerpt"),
        _evidence(_ev(6), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T19:00:00Z", "https://a.example/n6", "n6", "n6 excerpt"),
        _evidence(_ev(7), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T18:00:00Z", "https://a.example/n7", "n7", "n7 excerpt"),
    ]


def test_selected_ids_exact_expected():
    result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()))
    assert result["selected_evidence_ids"] == [_ev(2), _ev(4), _ev(5), _ev(6)]


def test_selected_ids_are_strings_not_objects():
    result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()))
    assert all(isinstance(x, str) for x in result["selected_evidence_ids"])


def test_policy_and_window_metadata():
    result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()))
    assert result["policy_version"] == "v0.3"
    assert result["run_id"] == "r1"
    assert result["as_of_utc"] == AS_OF
    assert result["window_start"] == "2026-11-19"
    assert result["window_end"] == "2026-11-25"


def test_context_hash_is_hex_digest():
    result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()))
    h = result["context_hash"]
    assert isinstance(h, str) and len(h) == 64
    int(h, 16)


def test_shuffle_determinism_and_ledger_unchanged():
    records = _base_records()
    original = [dict(rec) for rec in records]
    base = build_research_context(_mk_manifest(), _mk_ledger(records))
    rng = random.Random(7)
    for _ in range(12):
        rng.shuffle(records)
        ledger = _mk_ledger(records)
        snapshot = [dict(e.to_dict()) for e in ledger.entries]
        again = build_research_context(_mk_manifest(), ledger)
        assert again == base
        assert again["context_hash"] == base["context_hash"]
        assert [e.to_dict() for e in ledger.entries] == snapshot
    assert sorted(records, key=lambda r: r["evidence_id"]) == sorted(
        original, key=lambda r: r["evidence_id"]
    )


def _negative_records():
    return _base_records() + [
        _evidence(_ev(10), "r1", "market", "eligible", "2026-11-19T09:00:00Z",
                  "2026-11-18T18:00:00Z", "https://a.example/future", "SECRET-future",
                  "SECRET-future"),
        _evidence(_ev(11), "r1", "news", "eligible", "not-a-timestamp",
                  "not-a-timestamp", "https://a.example/badtime", "SECRET-time", "SECRET-time"),
        _evidence(_ev(12), "r1", "news", "excluded", "2026-11-18T18:00:00Z",
                  "2026-11-18T18:00:00Z", "https://a.example/excluded", "SECRET-excluded",
                  "SECRET-excluded"),
        _evidence(_ev(13), "r2", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T18:00:00Z", "https://a.example/crossrun", "SECRET-crossrun",
                  "SECRET-crossrun"),
    ]


def test_negative_records_not_selected_or_leaked():
    result = build_research_context(_mk_manifest(), _mk_ledger(_negative_records()))
    assert result["selected_evidence_ids"] == [_ev(2), _ev(4), _ev(5), _ev(6)]
    for n in (10, 11, 12, 13):
        assert _ev(n) not in result["selected_evidence_ids"]
    text = result["context_text"]
    for marker in ("SECRET-future", "SECRET-time", "SECRET-excluded", "SECRET-crossrun"):
        assert marker not in text
    for uri in ("a.example/future", "a.example/badtime", "a.example/excluded",
                "a.example/crossrun"):
        assert uri not in text


def test_same_time_utc_offsets_sorted_by_id():
    records = [
        _evidence(_ev(21), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T22:00:00+04:00", "https://a.example/x", "x", "x"),
        _evidence(_ev(20), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T20:00:00+02:00", "https://a.example/y", "y", "y"),
        _evidence(_ev(22), "r1", "news", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T13:00:00-05:00", "https://a.example/z", "z", "z"),
    ]
    result = build_research_context(_mk_manifest(), _mk_ledger(records))
    assert result["selected_evidence_ids"] == [_ev(20), _ev(21), _ev(22)]


def test_coverage_shape_and_source_status_values():
    status = {"market": "ok", "news": "error"}
    result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()),
                                    source_status=status)
    coverage = result["coverage"]
    assert coverage["market"]["status"] == "eligible"
    assert coverage["market"]["eligible_count"] == 2
    assert coverage["market"]["selected_count"] == 1
    assert coverage["market"]["source_status"] == "ok"
    assert coverage["news"]["status"] == "eligible"
    assert coverage["news"]["eligible_count"] == 4
    assert coverage["news"]["selected_count"] == 3
    assert coverage["news"]["source_status"] == "error"


def test_coverage_all_excluded_and_not_supplied():
    records = [
        _evidence(_ev(30), "r1", "market", "excluded", "2026-11-18T18:00:00Z",
                  "2026-11-18T18:00:00Z", "https://a.example/m", "m", "m"),
    ]
    result = build_research_context(_mk_manifest(), _mk_ledger(records))
    coverage = result["coverage"]
    assert coverage["market"]["status"] == "all_excluded"
    assert coverage["market"]["source_status"] == "unknown"
    assert coverage["news"]["status"] == "not_supplied"
    assert coverage["news"]["source_status"] == "unknown"
    assert result["selected_evidence_ids"] == []


def test_coverage_source_status_unknown_empty_error():
    for value in ("unknown", "empty", "error"):
        result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()),
                                        source_status={"news": value})
        assert result["coverage"]["news"]["source_status"] == value
        assert result["coverage"]["market"]["source_status"] == "unknown"


def test_missing_data_explicit_gaps():
    result = build_research_context(_mk_manifest(), _mk_ledger(_base_records()))
    assert result["coverage"]["missing_data"] == [
        "fundamentals", "historical_indicators", "multiweek_news"
    ]
    assert len(result["coverage"]["missing_data"]) == 3


def test_excerpt_truncated_to_160():
    long_text = "X" * 400
    records = [
        _evidence(_ev(40), "r1", "market", "eligible", "2026-11-18T18:00:00Z",
                  "2026-11-18T18:00:00Z", "https://a.example/long", long_text, long_text),
    ]
    result = build_research_context(_mk_manifest(), _mk_ledger(records))
    assert ("X" * 160) in result["context_text"]
    assert ("X" * 161) not in result["context_text"]


def test_hash_changes_when_text_changes():
    first = _base_records()
    second = _base_records()
    target = _ev(2)
    for rec in second:
        if rec["evidence_id"] == target:
            rec["content"] = "different text"
            rec["excerpt"] = "different text"
    a = build_research_context(_mk_manifest(), _mk_ledger(first))
    b = build_research_context(_mk_manifest(), _mk_ledger(second))
    assert a["context_hash"] != b["context_hash"]


@pytest.mark.parametrize("bad", ["okay", "OK", "", "pending", "valid"])
def test_invalid_source_status_value_rejected(bad):
    with pytest.raises(ValueError):
        build_research_context(_mk_manifest(), _mk_ledger(_base_records()),
                               source_status={"news": bad})
