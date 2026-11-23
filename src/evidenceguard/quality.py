"""Quality-review preparation and summary for EvidenceGuard (FR006, QUAL001/002, COST001).

Pure functions only: no I/O, no API calls, no approvals or labels are created.
Annotations are prepared as an empty, honest template for the student reviewer.
Summary computation never infers fact labels and never releases anything.
"""

from datetime import UTC

SCHEMA_VERSION = "1.0"
MIN_SUPPORT_RATE = 0.95
MIN_RUBRIC_TOTAL = 4
MIN_CANDIDATE_USABLE = 5
TOKEN_SAVING_TARGET = 0.20

# Independent shape constants (deliberately not imported from elsewhere).
_EXPECTED_TICKERS = ("AAPL", "MSFT", "NVDA")
_EXPECTED_ARMS = ("baseline", "candidate")

_RUBRIC_KEYS = ("relevance", "completeness", "traceability", "uncertainty", "clarity")
_LABELS = ("supported", "unsupported", "unverifiable")
_COMPLETED = "completed"

LIMITATION_NOTE = (
    "Descriptive small sample; single student recheck is not an independent second rater."
)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def prepare_annotations(report):
    """Return an empty annotation template bound to the report's plan and rows."""
    if not isinstance(report, dict):
        raise ValueError("report must be a dict")
    plan_hash = report.get("plan_hash")
    records = report.get("records")
    if not isinstance(records, list):
        raise ValueError("report.records must be a list")
    out = []
    for row in records:
        out.append(
            {
                "run_id": row.get("run_id"),
                "artifact_hash": row.get("artifact_hash"),
                "first_review_at": None,
                "rechecked_at": None,
                "facts": [],
                "rubric": None,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_hash": plan_hash,
        "reviewer_id": None,
        "provenance": "pending_student",
        "records": out,
    }


def _validate_report(report):
    if not isinstance(report, dict):
        raise ValueError("report must be a dictionary")
    records = report.get("records")
    if not isinstance(records, list):
        raise ValueError("report records must be a list")
    if len(records) != 12:
        raise ValueError("report must contain exactly 12 records")
    run_ids = set()
    observed = set()
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("each report record must be a dictionary")
        run_id = row.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("each report record must have a non-empty run_id")
        if run_id in run_ids:
            raise ValueError(f"duplicate run_id: {run_id}")
        run_ids.add(run_id)
        ticker = row.get("ticker")
        repeat = row.get("repeat")
        arm = row.get("arm")
        if not isinstance(repeat, int) or isinstance(repeat, bool) or repeat not in (1, 2):
            raise ValueError(f"invalid repeat for run_id {run_id}: {repeat!r}")
        key = (ticker, repeat, arm)
        if key in observed:
            raise ValueError(f"duplicate grid cell: {key!r}")
        observed.add(key)
    expected = {
        (ticker, repeat, arm)
        for ticker in _EXPECTED_TICKERS
        for repeat in (1, 2)
        for arm in _EXPECTED_ARMS
    }
    if observed != expected:
        missing = sorted(expected - observed)
        extra = sorted(observed - expected)
        raise ValueError(f"report grid mismatch; missing={missing!r} extra={extra!r}")


def _parse_timestamp(value):
    """Return a normalized epoch from an aware ISO-8601 string, else None."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime

        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC).timestamp()


def _validate_fact(fact):
    if not isinstance(fact, dict):
        return False
    for key in ("fact_id", "text", "reason"):
        value = fact.get(key)
        if not isinstance(value, str) or not value.strip():
            return False
    if fact.get("initial_label") not in _LABELS:
        return False
    if fact.get("label") not in _LABELS:
        return False
    evidence = fact.get("evidence_ids")
    if not isinstance(evidence, list):
        return False
    return all(isinstance(item, str) for item in evidence)


def _validate_rubric(rubric):
    if not isinstance(rubric, dict):
        return False
    if set(rubric.keys()) != set(_RUBRIC_KEYS):
        return False
    for key in _RUBRIC_KEYS:
        value = rubric.get(key)
        if not _is_int(value) or value not in (0, 1):
            return False
    return True


def _review_complete(annotation):
    reviewer = annotation.get("reviewer_id")
    if not isinstance(reviewer, str) or not reviewer.strip():
        return False
    if annotation.get("provenance") != "student":
        return False
    first = _parse_timestamp(annotation.get("first_review_at"))
    again = _parse_timestamp(annotation.get("rechecked_at"))
    if first is None or again is None:
        return False
    if again - first < 86400:
        return False
    facts = annotation.get("facts")
    if not isinstance(facts, list) or not facts:
        return False
    seen = set()
    for fact in facts:
        if not _validate_fact(fact):
            return False
        fact_id = fact.get("fact_id")
        if fact_id in seen:
            return False
        seen.add(fact_id)
    return _validate_rubric(annotation.get("rubric"))


def _support_rate(annotation):
    facts = annotation.get("facts")
    if not isinstance(facts, list) or not facts:
        return None
    for fact in facts:
        if not _validate_fact(fact):
            return None
    supported = sum(1 for f in facts if f.get("label") == "supported")
    return supported / len(facts)


def _rubric_total(annotation):
    rubric = annotation.get("rubric")
    if not _validate_rubric(rubric):
        return None
    return sum(rubric[k] for k in _RUBRIC_KEYS)


def _settled_tokens(run_budget):
    if not isinstance(run_budget, dict):
        return None
    settled = run_budget.get("settled_tokens")
    reserved = run_budget.get("reserved_tokens")
    if not _is_int(settled) or settled < 0:
        return None
    if not _is_int(reserved) or reserved != 0:
        return None
    return settled


def summarize_quality(report, annotations):
    """Compute deterministic quality metrics from the report and annotations."""
    _validate_report(report)
    if not isinstance(annotations, dict):
        raise ValueError("annotations must be a dict")
    if annotations.get("plan_hash") != report.get("plan_hash"):
        raise ValueError("annotations plan_hash does not match report")
    rows_by_run = {row["run_id"]: row for row in report["records"]}
    ann_records = annotations.get("records")
    if not isinstance(ann_records, list):
        raise ValueError("annotations.records must be a list")
    by_run = {}
    for ann in ann_records:
        if not isinstance(ann, dict):
            raise ValueError("each annotation record must be a dict")
        run_id = ann.get("run_id")
        if run_id not in rows_by_run:
            raise ValueError(f"unknown annotation run_id: {run_id!r}")
        if run_id in by_run:
            raise ValueError(f"duplicate annotation run_id: {run_id!r}")
        if ann.get("artifact_hash") != rows_by_run[run_id].get("artifact_hash"):
            raise ValueError(f"artifact_hash mismatch for run_id: {run_id!r}")
        by_run[run_id] = ann
    if set(by_run.keys()) != set(rows_by_run.keys()):
        raise ValueError("annotations do not cover every report run_id")

    records = []
    usable_counts = {"baseline": 0, "candidate": 0}
    completed_all_complete = True
    for run_id, row in rows_by_run.items():
        ann = by_run[run_id]
        arm = row.get("arm")
        status = row.get("execution_status")
        complete = _review_complete(
            {
                **ann,
                "reviewer_id": annotations.get("reviewer_id"),
                "provenance": annotations.get("provenance"),
            }
        )
        rate = _support_rate(ann)
        total = _rubric_total(ann)
        gate = arm == "baseline" or row.get("validation_status") == "passed"
        usable = (
            status == _COMPLETED
            and complete
            and rate is not None
            and rate >= MIN_SUPPORT_RATE
            and total is not None
            and total >= MIN_RUBRIC_TOTAL
            and gate
        )
        if usable and arm in usable_counts:
            usable_counts[arm] += 1
        if status == _COMPLETED and not complete:
            completed_all_complete = False
        records.append(
            {
                "run_id": run_id,
                "arm": arm,
                "execution_status": status,
                "review_complete": complete,
                "support_rate": rate,
                "rubric_total": total,
                "usable": bool(usable),
            }
        )

    passed = (
        usable_counts["candidate"] >= MIN_CANDIDATE_USABLE
        and usable_counts["candidate"] >= usable_counts["baseline"]
        and completed_all_complete
    )

    token_totals = {}
    for arm in _EXPECTED_ARMS:
        arm_rows = [row for row in report["records"] if row.get("arm") == arm]
        tokens = [_settled_tokens(row.get("run_budget")) for row in arm_rows]
        if len(arm_rows) != 6 or any(t is None for t in tokens):
            token_totals[arm] = None
        else:
            token_totals[arm] = sum(tokens)

    baseline_tokens = token_totals["baseline"]
    candidate_tokens = token_totals["candidate"]
    reduction = None
    target_met = None
    if baseline_tokens is not None and candidate_tokens is not None and baseline_tokens > 0:
        reduction = 1.0 - (candidate_tokens / baseline_tokens)
        target_met = candidate_tokens * 5 <= baseline_tokens * 4

    return {
        "plan_hash": report.get("plan_hash"),
        "passed": passed,
        "usable_counts": usable_counts,
        "records": records,
        "token_totals": token_totals,
        "token_reduction": reduction,
        "token_saving_target_met": target_met,
        "cost_requirement_met": None if target_met is None else bool(passed and target_met),
        "limitations": [LIMITATION_NOTE],
    }
