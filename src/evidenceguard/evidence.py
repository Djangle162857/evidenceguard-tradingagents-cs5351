from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def _parse_iso(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not _ISO_RE.match(value):
        raise ValueError(f"{field} must be an aware ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} is not a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    text = value.astimezone(UTC).isoformat()
    return text[:-6] + "Z" if text.endswith("+00:00") else text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _validate_uri(value: Any) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("source_uri must be a non-empty string")
    if not value.startswith("https://") or len(value) <= len("https://"):
        raise ValueError("source_uri must be an https URL")
    authority = value[len("https://") :].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if not authority:
        raise ValueError("source_uri must include a host")
    if "@" in authority:
        raise ValueError("source_uri must not contain credentials")
    return value


@dataclass(frozen=True)
class Evidence:
    _payload_json: str
    content: str = ""
    excerpt: str | None = None

    def _payload(self) -> dict[str, Any]:
        return json.loads(self._payload_json)

    @property
    def evidence_id(self) -> str:
        return self._payload()["evidence_id"]

    @property
    def run_id(self) -> str:
        return self._payload()["run_id"]

    @property
    def kind(self) -> str:
        return self._payload()["kind"]

    @property
    def source_uri(self) -> str:
        return self._payload()["source_uri"]

    @property
    def retrieved_at(self) -> str:
        return self._payload()["retrieved_at"]

    @property
    def published_at(self) -> str | None:
        return self._payload()["published_at"]

    @property
    def available_at(self) -> str | None:
        return self._payload()["available_at"]

    @property
    def qualification_time(self) -> str | None:
        return self._payload()["qualification_time"]

    @property
    def content_hash(self) -> str:
        return self._payload()["content_hash"]

    @property
    def eligibility(self) -> str:
        return self._payload()["eligibility"]

    @property
    def exclusion_reason(self) -> str | None:
        return self._payload()["exclusion_reason"]

    def to_dict(self) -> dict[str, Any]:
        payload = self._payload()
        payload["content"] = self.content
        payload["excerpt"] = self.excerpt
        return payload


_REQUIRED = (
    "run_id",
    "kind",
    "source_uri",
    "retrieved_at",
    "content",
    "content_hash",
)
_OPTIONAL = ("published_at", "available_at", "excerpt")
_ALLOWED = set(_REQUIRED) | set(_OPTIONAL)


class EvidenceLedger:
    def __init__(self, manifest: Any) -> None:
        self._manifest = manifest
        self._entries: list[Evidence] = []
        self._index: dict[str, Evidence] = {}

    @property
    def run_id(self) -> str:
        return self._manifest.run_id

    @property
    def entries(self) -> tuple[Evidence, ...]:
        return tuple(self._entries)

    def get(self, evidence_id: str) -> Evidence:
        try:
            return self._index[evidence_id]
        except KeyError as exc:
            raise ValueError(f"unknown evidence_id: {evidence_id!r}") from exc

    def add(self, record: Mapping[str, Any]) -> Evidence:
        if not isinstance(record, Mapping):
            raise ValueError("record must be a mapping")
        unknown = set(record) - _ALLOWED
        if unknown:
            raise ValueError(f"unknown record fields: {sorted(unknown)}")
        missing = [name for name in _REQUIRED if name not in record]
        if missing:
            raise ValueError(f"missing record fields: {missing}")

        run_id = record["run_id"]
        if not isinstance(run_id, str) or run_id != self._manifest.run_id:
            raise ValueError("record run_id does not match manifest run_id")

        kind = record["kind"]
        if kind not in ("market", "news"):
            raise ValueError("kind must be 'market' or 'news'")

        source_uri = _validate_uri(record["source_uri"])

        content = record["content"]
        if not isinstance(content, str):
            raise ValueError("content must be a str")

        content_hash = record["content_hash"]
        expected_hash = _sha256(content)
        if not isinstance(content_hash, str) or content_hash.lower() != expected_hash:
            raise ValueError("content_hash does not match content")

        retrieved_at = _parse_iso(record["retrieved_at"], "retrieved_at")

        published_at = None
        if record.get("published_at") is not None:
            published_at = _parse_iso(record["published_at"], "published_at")
        available_at = None
        if record.get("available_at") is not None:
            available_at = _parse_iso(record["available_at"], "available_at")

        excerpt = record.get("excerpt")
        if excerpt is not None and not isinstance(excerpt, str):
            raise ValueError("excerpt must be a str or None")

        cutoff = _parse_iso(self._manifest.as_of_utc, "manifest.as_of_utc")
        relevant_field = "available_at" if kind == "market" else "published_at"
        relevant_time = available_at if kind == "market" else published_at

        if relevant_time is None:
            eligibility = "excluded"
            exclusion_reason = f"missing_{relevant_field}"
        elif relevant_time > cutoff:
            eligibility = "excluded"
            exclusion_reason = f"{relevant_field}_after_as_of_utc"
        else:
            eligibility = "eligible"
            exclusion_reason = None

        qualification_time = _format_utc(relevant_time) if relevant_time is not None else None

        evidence_id = "ev-" + _sha256(
            _canonical_json(
                {
                    "run_id": run_id,
                    "source_uri": source_uri,
                    "kind": kind,
                    "qualification_time": qualification_time,
                    "content_hash": expected_hash,
                }
            )
        )

        existing = self._index.get(evidence_id)
        if existing is not None:
            return existing

        payload = {
            "evidence_id": evidence_id,
            "run_id": run_id,
            "kind": kind,
            "source_uri": source_uri,
            "retrieved_at": _format_utc(retrieved_at),
            "published_at": _format_utc(published_at) if published_at is not None else None,
            "available_at": _format_utc(available_at) if available_at is not None else None,
            "qualification_time": qualification_time,
            "content_hash": expected_hash,
            "eligibility": eligibility,
            "exclusion_reason": exclusion_reason,
        }
        evidence = Evidence(
            _payload_json=_canonical_json(payload),
            content=content,
            excerpt=excerpt,
        )
        self._index[evidence_id] = evidence
        self._entries.append(evidence)
        return evidence


__all__ = ["Evidence", "EvidenceLedger"]
