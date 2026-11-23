"""EvidenceGuard research context builder (v0.3)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

POLICY_VERSION = "v0.3"
EXPLICIT_GAPS = ["fundamentals", "historical_indicators", "multiweek_news"]
VALID_STATUS = ("ok", "empty", "error", "unknown")
VALID_KINDS = ("market", "news")
PICKS = {"market": 1, "news": 3}


def _parse_time(raw):
    if not raw:
        raise ValueError("missing timestamp")
    dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("naive timestamp")
    return dt.astimezone(UTC)


def _norm_utc(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm_status(source_status):
    status = dict(source_status or {})
    for key in status:
        if key not in VALID_KINDS:
            raise ValueError("invalid source_status key")
    for value in status.values():
        if value not in VALID_STATUS:
            raise ValueError("invalid source_status value")
    return status


def _kind_time(entry):
    return _parse_time(entry["available_at" if entry["kind"] == "market" else "published_at"])


def _render(entry, dt):
    text = entry.get("excerpt") or entry.get("content") or ""
    return f"[{entry['evidence_id']}] {entry['source_uri']} {_norm_utc(dt)} {text[:160]}"


def build_research_context(manifest, ledger, *, source_status=None):
    """Build deterministic research context from manifest and ledger."""
    run_id = manifest.to_dict()["run_id"]
    as_of = _parse_time(manifest.to_dict()["as_of_utc"])
    status = _norm_status(source_status)
    same_run = {kind: [] for kind in VALID_KINDS}
    for entry in ledger.entries:
        rec = entry.to_dict()
        if rec["run_id"] != run_id or rec["kind"] not in VALID_KINDS:
            continue
        same_run[rec["kind"]].append(rec)
    qualified = {}
    for kind in VALID_KINDS:
        rows = []
        for rec in same_run[kind]:
            if rec["eligibility"] != "eligible":
                continue
            try:
                dt = _kind_time(rec)
            except (ValueError, TypeError):
                continue
            if dt <= as_of:
                rows.append((dt, rec))
        rows.sort(key=lambda item: item[0], reverse=True)
        rows.sort(key=lambda item: (-item[0].timestamp(), item[1]["evidence_id"]))
        qualified[kind] = rows

    selected = []
    coverage = {}
    for kind in VALID_KINDS:
        picked = qualified[kind][: PICKS[kind]]
        selected.extend(picked)
        if picked:
            cov = "eligible"
        elif same_run[kind]:
            cov = "all_excluded"
        else:
            cov = "not_supplied"
        coverage[kind] = {
            "eligible_count": len(qualified[kind]),
            "selected_count": len(picked),
            "status": cov,
            "source_status": status.get(kind, "unknown"),
        }
    coverage["missing_data"] = list(EXPLICIT_GAPS)

    lines = [
        f"Research context for {run_id} as of {_norm_utc(as_of)}",
        f"Window: {(as_of.date() + timedelta(days=1)).isoformat()} to "
        f"{(as_of.date() + timedelta(days=7)).isoformat()}",
        "Explicit gaps: " + ", ".join(EXPLICIT_GAPS),
        "Coverage: " + json.dumps(coverage, sort_keys=True, ensure_ascii=False),
    ]
    for kind in VALID_KINDS:
        lines.append(f"{kind}:")
        for dt, rec in qualified[kind][: PICKS[kind]]:
            lines.append(_render(rec, dt))
    context_text = "\n".join(lines)

    result = {
        "policy_version": POLICY_VERSION,
        "run_id": run_id,
        "as_of_utc": _norm_utc(as_of),
        "window_start": (as_of.date() + timedelta(days=1)).isoformat(),
        "window_end": (as_of.date() + timedelta(days=7)).isoformat(),
        "selected_evidence_ids": [rec["evidence_id"] for _, rec in selected],
        "context_text": context_text,
        "coverage": coverage,
    }
    canonical = json.dumps(
        result, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    result["context_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return result
