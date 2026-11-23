# src/evidenceguard/runner.py
"""Offline-first deterministic orchestration for EvidenceGuard (FR001/2/3/4/7).

Public replay() creates a draft DecisionArtifact from recorded turns; it makes no
network calls and never fabricates approval, ratings or missing data. Upstream
candidate integration is added separately through run_upstream.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
from collections.abc import Iterable
from datetime import datetime

from . import claims as _claims, gate as _gate, review as _review
from .contracts import create_manifest
from .evidence import EvidenceLedger

_SCHEMA_VERSION = "1.0"
_RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")
_ROLES = ("bull", "bear", "risky", "neutral", "safe")
_ALLOWED_FIELDS = (
    "schema_version",
    "run_id",
    "revision",
    "manifest",
    "evidence",
    "claims",
    "report",
    "rating",
    "limitations",
    "policy_version",
    "metadata",
)


def _replace_aliases(report: str, canonical_cards: Iterable[dict]) -> str:
    """Replace ``[claim:N]`` fixture aliases with real ``[cl-<sha>]`` ids.

    Aliases only resolve against the recorded fixture cards; unknown aliases are
    left untouched so no reference is silently dropped or invented.
    """
    ids = [card.get("claim_id") for card in canonical_cards]
    out = report or ""
    for index, claim_id in enumerate(ids):
        if isinstance(claim_id, str) and claim_id:
            out = out.replace(f"[claim:{index}]", f"[{claim_id}]")
    return out


def _metadata() -> dict:
    return {
        "execution_status": "completed",
        "validation_status": "pending",
        "review_status": "pending",
        "publication_status": "draft",
        "gate_results": {"passed": False, "violations": []},
        "measurement": {"transcript": [], "errors": [], "source_mode": "offline_replay"},
    }


def replay(
    config: dict,
    records: Iterable[dict],
    turns: Iterable[dict],
    final: dict,
    *,
    now: datetime,
) -> dict:
    """Deterministically rebuild a draft artifact from recorded inputs (no network)."""
    manifest = create_manifest(config, now=now)
    ledger = EvidenceLedger(manifest)
    errors: list[dict] = []
    canonical: list[dict] = []
    transcript: list[dict] = []

    try:
        for record in records:
            ledger.add(record)
    except (ValueError, TypeError) as exc:
        errors.append({"class": type(exc).__name__, "message": str(exc)})

    stopped = False
    if not errors:
        for turn in turns:
            role = turn.get("role")
            if role not in _ROLES:
                errors.append({"class": "ValueError", "message": "invalid turn role"})
                break
            try:
                parsed = _claims.validate_debate_turn(
                    turn.get("payload", {}),
                    role=role,
                    manifest=manifest,
                    ledger=ledger,
                    existing_claims=canonical,
                )
            except (ValueError, TypeError) as exc:
                errors.append({"class": type(exc).__name__, "message": str(exc)})
                break
            data = parsed.to_dict()
            canonical.extend(data.get("cards", []))
            rendered = parsed.rendered()
            transcript.append(
                {
                    "role": role,
                    "cards": data.get("cards", []),
                    "reply_to": data.get("reply_to"),
                    "conflicts": data.get("conflicts", []),
                    "stop_reason": data.get("stop_reason"),
                    "rendered": rendered,
                }
            )
            if data.get("stop_reason") != "completed":
                stopped = True
                break

    report = _replace_aliases(str(final.get("report", "")), canonical)
    rating = final.get("rating")
    if rating not in _RATINGS:
        rating = None
    limitations = [str(item) for item in final.get("limitations", []) if str(item).strip()]

    metadata = _metadata()
    metadata["measurement"]["transcript"] = transcript
    metadata["measurement"]["errors"] = errors

    failed = bool(errors)
    if failed:
        metadata["execution_status"] = "failed"
    elif stopped:
        metadata["execution_status"] = "stopped"
    else:
        metadata["execution_status"] = "completed"

    manifest_dict = manifest.to_dict()
    artifact = {
        "schema_version": _SCHEMA_VERSION,
        "run_id": manifest_dict["run_id"],
        "revision": manifest_dict["revision"],
        "manifest": manifest_dict,
        "evidence": [entry.to_dict() for entry in ledger.entries],
        "claims": canonical,
        "report": report,
        "rating": rating if metadata["execution_status"] == "completed" else None,
        "limitations": limitations,
        "policy_version": manifest_dict["policy_version"],
    }
    artifact.update(metadata)

    try:
        result = _gate.validate_artifact(
            artifact, manifest=manifest, ledger=ledger, claims=canonical
        )
        metadata["gate_results"] = {
            "passed": bool(getattr(result, "passed", False)),
            "violations": list(getattr(result, "violations", ())),
        }
        metadata["validation_status"] = "passed" if metadata["gate_results"]["passed"] else "failed"
    except (ValueError, TypeError) as exc:
        errors.append({"class": type(exc).__name__, "message": str(exc)})
        metadata["validation_status"] = "failed"
        metadata["execution_status"] = "failed"

    artifact.update(metadata)
    try:
        artifact["artifact_hash"] = _review.artifact_hash(artifact)
    except (ValueError, TypeError):
        artifact["artifact_hash"] = None
    return artifact


def write_artifact(artifact: dict, path: str | os.PathLike) -> None:
    """Atomically write a UTF-8 JSON artifact into the target directory."""
    target = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(target)) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".artifact-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(
                artifact, handle, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_artifact(path: str | os.PathLike) -> dict:
    """Read a JSON artifact from disk as a dict."""
    with open(os.fspath(path), encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("artifact must be a JSON object")
    return data


def summarize(artifact: dict) -> str:
    """Return a concise human-readable artifact summary."""
    metadata = artifact
    gate = metadata.get("gate_results", {}) or {}
    manifest = artifact.get("manifest", {}) or {}
    violations = gate.get("violations", []) or []
    lines = [
        "run_id: {}".format(artifact.get("run_id")),
        "ticker: {}".format(manifest.get("ticker")),
        "execution_status: {}".format(metadata.get("execution_status")),
        "validation_status: {}".format(metadata.get("validation_status")),
        "publication_status: {}".format(metadata.get("publication_status")),
        "artifact_hash: {}".format(artifact.get("artifact_hash")),
        f"claims: {len(artifact.get('claims', []) or [])}",
        f"evidence: {len(artifact.get('evidence', []) or [])}",
        f"violations: {len(violations)}",
    ]
    for item in violations:
        lines.append(f"  - {item}")
    return "\n".join(lines)
