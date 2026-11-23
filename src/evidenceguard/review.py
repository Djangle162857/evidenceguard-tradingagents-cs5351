from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger
from evidenceguard.gate import validate_artifact

_PROJECTION = (
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
)
_EVENT = (
    "schema_version",
    "run_id",
    "revision",
    "artifact_hash",
    "reviewer_id",
    "decision",
    "reason",
    "authorization_source",
    "reviewed_at",
)
_DECISIONS = ("approve", "reject")
_HUMAN = "human_cli"
_FIXTURE = "test_fixture"
_RATINGS = ("Buy", "Overweight", "Hold", "Underweight", "Sell")


def _canonical(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _utc(value: datetime, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be an aware datetime")
    text = value.astimezone(UTC).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def _parse(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("artifact must be a mapping")
    out: dict[str, Any] = {}
    for name in _PROJECTION:
        if name not in payload:
            raise ValueError(f"artifact missing business field: {name}")
        out[name] = copy.deepcopy(payload[name])
    return out


def artifact_hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(_projection(payload)).encode("utf-8")).hexdigest()


def _ledger(manifest: Any, evidence: Any) -> EvidenceLedger:
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list")
    ledger = EvidenceLedger(manifest)
    for item in evidence:
        if not isinstance(item, Mapping):
            raise ValueError("evidence entries must be mappings")
        record = dict(item)
        record.pop("evidence_id", None)
        record.pop("eligibility", None)
        record.pop("exclusion_reason", None)
        record.pop("qualification_time", None)
        ledger.add(record)
    return ledger


def validate_current(artifact: Mapping[str, Any], *, now: datetime) -> dict[str, Any]:
    _utc(now, "now")
    proj = _projection(artifact)
    manifest = create_manifest(proj["manifest"], now=now)
    ledger = _ledger(manifest, proj["evidence"])
    claims = proj["claims"]
    if not isinstance(claims, list):
        raise ValueError("claims must be a list")
    for card in claims:
        if not isinstance(card, Mapping):
            raise ValueError("claims entries must be mappings")
    gate = validate_artifact(artifact, manifest=manifest, ledger=ledger, claims=claims)
    if not gate.passed:
        raise ValueError(f"gate failed: {gate.violations!r}")
    return {"manifest": manifest, "ledger": ledger, "claims": claims, "gate": gate}


class ReviewStore:
    def __init__(self, root: str | os.PathLike[str], *, test_mode: bool = False) -> None:
        if not isinstance(test_mode, bool):
            raise ValueError("test_mode must be bool")
        self.root = os.fspath(root)
        self.test_mode = test_mode
        os.makedirs(self.root, exist_ok=True)
        self._path = os.path.join(self.root, "reviews.jsonl")

    def _allowed(self, source: str) -> None:
        if source == _FIXTURE:
            if not self.test_mode:
                raise ValueError("test_fixture reviews require a test_mode store")
        elif source == _HUMAN:
            if self.test_mode:
                raise ValueError("human_cli reviews are not accepted in test_mode")
        else:
            raise ValueError("authorization_source must be human_cli or test_fixture")

    def record(
        self,
        artifact: Mapping[str, Any],
        *,
        reviewer_id: str,
        decision: str,
        reason: str,
        authorization_source: str,
        now: datetime,
    ) -> dict[str, Any]:
        proj = _projection(artifact)
        current = artifact_hash(proj)
        reviewed_at = _utc(now, "now")
        if decision not in _DECISIONS:
            raise ValueError("decision must be approve or reject")
        if not isinstance(reviewer_id, str) or not reviewer_id.strip():
            raise ValueError("reviewer_id must be a non-empty string")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("reason must be a non-empty string")
        self._allowed(authorization_source)
        if decision == "approve":
            if artifact.get("artifact_hash") != current:
                raise ValueError("artifact_hash does not match current business projection")
            result = validate_current(artifact, now=now)
            execution = artifact.get("execution_status")
            if execution != "completed":
                raise ValueError("approve requires execution_status completed")
            if result["gate"].passed is not True:
                raise ValueError("approve requires a passing gate")
        event = {
            "schema_version": proj["schema_version"],
            "run_id": proj["run_id"],
            "revision": proj["revision"],
            "artifact_hash": current,
            "reviewer_id": reviewer_id,
            "decision": decision,
            "reason": reason,
            "authorization_source": authorization_source,
            "reviewed_at": reviewed_at,
        }
        line = _canonical(event) + "\n"
        fd = os.open(self._path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            os.write(fd, line.encode("utf-8"))
            os.fsync(fd)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
        return copy.deepcopy(event)

    def reviews(self) -> list[dict[str, Any]]:
        if not os.path.exists(self._path):
            return []
        with open(self._path, encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            try:
                text = handle.read()
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        out = []
        for raw in text.splitlines():
            if not raw.strip():
                continue
            event = json.loads(raw)
            if not isinstance(event, dict) or tuple(sorted(event)) != tuple(sorted(_EVENT)):
                raise ValueError("corrupt review event")
            out.append(event)
        return out


def publish(artifact: Mapping[str, Any], *, store: ReviewStore, now: datetime) -> dict[str, Any]:
    if not isinstance(store, ReviewStore):
        raise ValueError("store must be a ReviewStore")
    proj = _projection(artifact)
    current = artifact_hash(proj)
    supplied = artifact.get("artifact_hash")
    if not isinstance(supplied, str) or supplied != current:
        raise ValueError("supplied artifact_hash does not match recomputed hash")
    validate_current(artifact, now=now)
    if artifact.get("execution_status") != "completed":
        raise ValueError("publish requires execution_status completed")
    when = _utc(now, "now")
    match = None
    for event in store.reviews():
        if (event["run_id"], event["revision"], event["artifact_hash"]) == (
            proj["run_id"],
            proj["revision"],
            current,
        ):
            match = event
    if match is None:
        raise ValueError("no review recorded for current artifact")
    if match["decision"] != "approve":
        raise ValueError("latest review for current artifact is not an approval")
    if (
        match["artifact_hash"] != current
        or match["run_id"] != proj["run_id"]
        or match["revision"] != proj["revision"]
    ):
        raise ValueError("latest review does not bind current artifact")
    store._allowed(match["authorization_source"])
    if not isinstance(match["reviewer_id"], str) or not match["reviewer_id"].strip():
        raise ValueError("review missing reviewer_id")
    if not isinstance(match["reason"], str) or not match["reason"].strip():
        raise ValueError("review missing reason")
    if _parse(match["reviewed_at"]) > _parse(when):
        raise ValueError("review recorded in the future")
    released = copy.deepcopy(proj)
    released.update(
        {
            "execution_status": "completed",
            "validation_status": "passed",
            "review_status": "approved",
            "publication_status": "released",
            "artifact_hash": current,
        }
    )
    return released


__all__ = ["ReviewStore", "artifact_hash", "publish", "validate_current"]
