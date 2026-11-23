from copy import deepcopy

import pytest

from evidenceguard.quality import prepare_annotations, summarize_quality

"""
Synthetic offline quality-summary fixtures. These are generated fixtures only,
not human approvals, and no course model, network or human transcript is used.
"""

ARMS = ("baseline", "candidate")
TICKERS = ("AAPL", "MSFT", "NVDA")
REPEATS = (1, 2)
HASH = "a" * 64
PLAN = "p" * 64
RUBRIC_KEYS = ("relevance", "completeness", "traceability", "uncertainty", "clarity")


def _facts(count):
    return [
        {
            "fact_id": str(i),
            "text": "Synthetic",
            "initial_label": "supported",
            "label": "supported",
            "reason": "Fixture",
            "evidence_ids": ["synthetic"],
        }
        for i in range(count)
    ]


def _annotation(ticker, repeat, arm):
    return {
        "run_id": f"{ticker}-{repeat}-{arm}",
        "ticker": ticker,
        "repeat": repeat,
        "arm": arm,
        "plan_hash": PLAN,
        "artifact_hash": HASH,
        "first_review_at": "2026-11-18T12:00:00Z",
        "rechecked_at": "2026-11-19T12:00:00Z",
        "facts": _facts(20),
        "rubric": dict.fromkeys(RUBRIC_KEYS, 1),
    }


def pair():
    records = []
    for ticker in TICKERS:
        for repeat in REPEATS:
            for arm in ARMS:
                records.append(
                    {
                        "run_id": f"{ticker}-{repeat}-{arm}",
                        "ticker": ticker,
                        "repeat": repeat,
                        "arm": arm,
                        "plan_hash": PLAN,
                        "artifact_hash": HASH,
                        "execution_status": "completed",
                        "validation_status": ("failed" if arm == "baseline" else "passed"),
                        "run_budget": {
                            "settled_tokens": 100 if arm == "baseline" else 75,
                            "reserved_tokens": 0,
                        },
                    }
                )
    return {"plan_hash": PLAN, "records": records}


def annotated(records=None, **overrides):
    report = records if records is not None else pair()
    ann = prepare_annotations(report or pair())
    ann["reviewer_id"] = "synthetic-fixture"
    ann["provenance"] = "student"
    ann["records"] = [_annotation(t, r, a) for t in TICKERS for r in REPEATS for a in ARMS]
    for key, value in overrides.items():
        ann[key] = value
    return ann


def _set_fact(ann, run_id, index, **changes):
    row = next(r for r in ann["records"] if r["run_id"] == run_id)
    row["facts"][index].update(changes)


def test_empty_template_is_untouched():
    report = pair()
    snapshot = deepcopy(report)
    ann = prepare_annotations(report)
    assert report == snapshot
    assert ann["reviewer_id"] is None
    assert ann["provenance"] == "pending_student"
    assert len(ann["records"]) == 12
    assert all(
        row["facts"] == [] and row["first_review_at"] is None and row["rechecked_at"] is None
        for row in ann["records"]
    )
    summary = summarize_quality(report, ann)
    assert summary["passed"] is False
    assert summary["usable_counts"]["baseline"] == 0
    assert summary["usable_counts"]["candidate"] == 0


def test_all_valid_passes_and_counts():
    report = pair()
    summary = summarize_quality(report, annotated(report))
    assert summary["passed"] is True
    assert summary["usable_counts"]["baseline"] == 6
    assert summary["usable_counts"]["candidate"] == 6
    assert summary["token_totals"]["baseline"] == 600
    assert summary["token_totals"]["candidate"] == 450
    assert summary["token_reduction"] == 0.25
    assert summary["token_saving_target_met"] is True
    assert all(r["usable"] for r in summary["records"] if r["arm"] == "baseline")


def test_candidate_support_rate_must_not_be_below_baseline():
    report = pair()
    ann = annotated(report)
    _set_fact(ann, "AAPL-1-candidate", 0, label="unsupported")
    _set_fact(ann, "AAPL-1-candidate", 1, label="unverifiable")
    summary = summarize_quality(report, ann)
    assert next(r for r in summary["records"] if r["run_id"] == "AAPL-1-candidate")[
        "support_rate"
    ] == pytest.approx(0.9)
    assert summary["usable_counts"]["candidate"] == 5
    assert summary["usable_counts"]["baseline"] == 6
    assert summary["passed"] is False

    report = pair()
    ann = annotated(report)
    _set_fact(ann, "AAPL-1-candidate", 0, label="unsupported")
    summary = summarize_quality(report, ann)
    assert next(r for r in summary["records"] if r["run_id"] == "AAPL-1-candidate")[
        "support_rate"
    ] == pytest.approx(0.95)
    assert summary["passed"] is True


def test_invalid_review_states_block_pass():
    report = pair()
    ann = annotated(report)
    report["records"][0]["validation_status"] = "passed"
    ann["records"][0]["rechecked_at"] = "2026-11-19T11:59:00Z"
    summary = summarize_quality(report, ann)
    assert summary["usable_counts"]["baseline"] == 5
    assert summary["records"][0]["review_complete"] is False
    assert summary["passed"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r, a: a["records"][0].update(first_review_at="2026-11-18"),
        lambda r, a: a["records"][0].update(rechecked_at="2026-11-19T12:00:00"),
        lambda r, a: a["records"][0]["facts"][0].update(label="maybe"),
        lambda r, a: a["records"][0]["rubric"].update(relevance=True),
        lambda r, a: a.update(reviewer_id=None),
    ],
    ids=["shortdate", "naivedate", "invalidlabel", "boolrubric", "reviewernone"],
)
def test_malformed_annotation_rejected(mutation):
    report = pair()
    ann = annotated(report)
    mutation(report, ann)
    summary = summarize_quality(report, ann)
    assert summary["passed"] is False


def test_missing_budget_disables_target_but_not_quality():
    report = pair()
    for record in report["records"]:
        if record["arm"] == "candidate":
            record["run_budget"] = None
    summary = summarize_quality(report, annotated(report))
    assert summary["token_totals"]["candidate"] is None
    assert summary["token_reduction"] is None
    assert summary["token_saving_target_met"] is None
    assert summary["passed"] is True

    report = pair()
    for record in report["records"]:
        if record["arm"] == "candidate":
            record["run_budget"]["settled_tokens"] = 90
    summary = summarize_quality(report, annotated(report))
    assert summary["token_reduction"] == pytest.approx(0.1)
    assert summary["token_saving_target_met"] is False
    assert summary["passed"] is True


@pytest.mark.parametrize(
    "corrupt",
    [
        "missing",
        "duplicate",
        "planmismatch",
        "hashmismatch",
    ],
)
def test_structure_errors_raise(corrupt):
    report = pair()
    ann = annotated(report)
    if corrupt == "missing":
        report["records"].pop()
    elif corrupt == "duplicate":
        report["records"].append(deepcopy(report["records"][0]))
    elif corrupt == "planmismatch":
        report["plan_hash"] = "q" * 64
    else:
        report["records"][0]["artifact_hash"] = "b" * 64
    with pytest.raises(ValueError):
        summarize_quality(report, ann)


def test_failed_and_stopped_runs_reduce_usable_counts():
    report = pair()
    report["records"][0]["execution_status"] = "failed"
    report["records"][1]["execution_status"] = "stopped"
    summary = summarize_quality(report, annotated(report))
    assert len(report["records"]) == 12
    assert summary["usable_counts"]["baseline"] == 5
    assert summary["usable_counts"]["candidate"] == 5
    assert summary["passed"] is True
    assert summary["token_totals"]["baseline"] == 600
    assert summary["token_totals"]["candidate"] == 450


def test_exact_twenty_percent_target():
    report = pair()
    for row in report["records"]:
        if row["arm"] == "candidate":
            row["run_budget"]["settled_tokens"] = 80
    summary = summarize_quality(report, annotated(report))
    assert summary["passed"] is True
    assert summary["token_reduction"] == pytest.approx(0.2)
    assert summary["token_saving_target_met"] is True
