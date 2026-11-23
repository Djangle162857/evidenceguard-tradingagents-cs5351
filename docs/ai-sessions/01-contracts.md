# Immutable run manifests

Session `ses_e0c7a18caffe0lmlXNwSHmzd0Y`; local OpenCode, course model `CS5351/DeepSeek-V4-Flash`.

Initial generated contract module; current source also contains later generated repairs and formatting.

The adjacent JSON is the authentic `opencode session export --sanitize` output, with local directory names further redacted if present. OpenCode redacts user/assistant text in that export. The assistant text below is copied from the authentic JSON event stream to make the code-generation evidence reviewable. Only local directory strings are redacted; code is not repaired in this transcript. All text parts, including incomplete or repeated candidates, are retained in order.

Instructions were relayed by Codex under the user’s startup authorization. This is not a transcript of the student personally typing in OpenCode, a human approval, or a claim that the model ran tests. Actual validation and subsequent corrections are recorded in `docs/bug-diary.md`, `docs/progress.md` and the checkpoint bundle.

Original sanitized export SHA-256: `4f94111a762a04468a86602a97ed2cfaf02bd42b43d34547b2701a55101a0986`.

Original event stream SHA-256: `9802bba7ed3cd23d1c17a15408a7b553b2a49f3afe5492694a0f4050597e82e9`.

Preservation update (2026-11-19): the original temporary session directory was lost on system restart. This public annotated text and sanitized native export survive; original hashes below were recorded before the loss. Their presence does not mean the private originals are still available.

## Authentic assistant text

```text
```python
"""Immutable run manifest contract for EvidenceGuard.

Pure validation and canonical hashing of a run manifest configuration.
No file or network I/O is performed.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = "1.0"
COURSE_MODEL_ID = "CS5351/DeepSeek-V4-Flash"
TICKERS = ("AAPL", "MSFT", "NVDA")
ANALYSTS = ("market", "news")
BUDGET_KEYS = (
    "token_limit",
    "attempt_limit",
    "deadline_seconds",
    "input_upper_per_call",
    "output_upper_per_call",
)
_SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
_SHA64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _canonical_json(payload: dict) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _parse_utc(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("as_of_utc must be a non-empty ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("as_of_utc is not valid ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("as_of_utc must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _format_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive non-bool integer")
    return value


def _normalize(config: dict, now: datetime) -> dict:
    if not isinstance(config, dict):
        raise ValueError("config must be a dict")
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")

    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("schema_version must be 1.0")

    run_id = config.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("run_id must be a non-empty string")

    revision = _positive_int(config.get("revision"), "revision")

    ticker = config.get("ticker")
    if ticker not in TICKERS:
        raise ValueError("ticker must be one of AAPL, MSFT, NVDA")

    as_of = _parse_utc(config.get("as_of_utc"))
    if as_of > now.astimezone(timezone.utc):
        raise ValueError("as_of_utc must not be after now")

    analysts = config.get("analysts")
    if not isinstance(analysts, (list, tuple)) or not analysts:
        raise ValueError("analysts must be a non-empty sequence")
    analysts = list(analysts)
    for analyst in analysts:
        if analyst not in ANALYSTS:
            raise ValueError("analysts restricted to market/news")
    if len(set(analysts)) != len(analysts):
        raise ValueError("analysts must not contain duplicates")

    baseline = config.get("baseline_sha")
    candidate = config.get("candidate_sha")
    if not isinstance(baseline, str) or not _SHA40.match(baseline):
        raise ValueError("baseline_sha must be 40 hex characters")
    if not isinstance(candidate, str) or not _SHA40.match(candidate):
        raise ValueError("candidate_sha must be 40 hex characters")

    dataset_hash = config.get("dataset_hash")
    if not isinstance(dataset_hash, str) or not _SHA64.match(dataset_hash):
        raise ValueError("dataset_hash must be 64 hex characters")

    model_id = config.get("model_id")
    if model_id != COURSE_MODEL_ID:
        raise ValueError("model_id must be the configured course model")

    for key in ("prompt_version", "policy_version"):
        value = config.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")

    budget = config.get("budget")
    if not isinstance(budget, dict):
        raise ValueError("budget must be a dict")
    normalized_budget = {}
    for key in BUDGET_KEYS:
        if key not in budget:
            raise ValueError(f"budget missing {key}")
        normalized_budget[key] = _positive_int(budget[key], f"budget.{key}")

    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "revision": revision,
        "ticker": ticker,
        "as_of_utc": _format_utc(as_of),
        "analysts": analysts,
        "baseline_sha": baseline,
        "candidate_sha": candidate,
        "model_id": model_id,
        "prompt_version": config["prompt_version"],
        "policy_version": config["policy_version"],
        "budget": normalized_budget,
        "dataset_hash": dataset_hash,
    }


@dataclass(frozen=True)
class RunManifest:
    """Frozen, hashable run manifest storing canonical normalized JSON."""

    _canonical: str = field(repr=False)
    _manifest_hash: str = field(repr=False)

    @classmethod
    def _from_payload(cls, payload: dict) -> "RunManifest":
        canonical = _canonical_json(payload)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return cls(_canonical=canonical, _manifest_hash=digest)

    @property
    def manifest_hash(self) -> str:
        return self._manifest_hash

    def to_dict(self) -> dict:
        return copy.deepcopy(json.loads(self._canonical))

    @property
    def run_id(self) -> str:
        return json.loads(self._canonical)["run_id"]

    @property
    def ticker(self) -> str:
        return json.loads(self._canonical)["ticker"]

    @property
    def as_of_utc(self) -> str:
        return json.loads(self._canonical)["as_of_utc"]

    @property
    def revision(self) -> int:
        return json.loads(self._canonical)["revision"]

    @property
    def model_id(self) -> str:
        return json.loads(self._canonical)["model_id"]

    @property
    def budget(self) -> dict:
        return copy.deepcopy(json.loads(self._canonical)["budget"])


def create_manifest(config: dict, *, now: datetime) -> RunManifest:
    """Validate ``config`` and return a frozen :class:`RunManifest`.

    Pure function: performs no file or network I/O. Invalid configuration
    raises :class:`ValueError`.
    """
    payload = _normalize(config, now)
    return RunManifest._from_payload(payload)
```
```
