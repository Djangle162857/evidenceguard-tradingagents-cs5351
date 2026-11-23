from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from evidenceguard.evidence import EvidenceLedger
from evidenceguard.research_brief import validate_research_brief

_SCHEMA_VERSIONS = ("1.0",)
_RATINGS = frozenset({"Buy", "Overweight", "Hold", "Underweight", "Sell"})
_BUSINESS = frozenset(
    {
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
    }
)
_ARTIFACT_META = frozenset(
    {
        "artifact_hash",
        "execution_status",
        "validation_status",
        "review_status",
        "publication_status",
        "gate_results",
        "measurement",
    }
)
_CLAIM_KEYS = frozenset(
    {
        "claim_id",
        "kind",
        "text",
        "evidence_ids",
        "parent_claim_ids",
        "uncertainty",
    }
)
_CLAIM_KINDS = frozenset({"fact", "inference"})
_EVIDENCE_KEYS = frozenset(
    {
        "run_id",
        "kind",
        "source_uri",
        "retrieved_at",
        "published_at",
        "available_at",
        "content",
        "content_hash",
        "excerpt",
    }
)
_CLAIM_REF_RE = re.compile(r"\[(cl-[0-9a-f]{64})\]")


class GateResult(tuple):
    __slots__ = ()

    def __new__(cls, passed: bool, violations: tuple[str, ...]) -> GateResult:
        return tuple.__new__(cls, (bool(passed), tuple(violations)))

    @property
    def passed(self) -> bool:
        return self[0]

    @property
    def violations(self) -> tuple[str, ...]:
        return self[1]

    def __repr__(self) -> str:
        return f"GateResult(passed={self.passed!r}, violations={self.violations!r})"


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_claims(claims: Any, eligible_ids: set[str], violations: list[str]) -> None:
    if not isinstance(claims, list):
        violations.append("claims must be a list")
        return
    seen: set[str] = set()
    parsed: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
    for index, claim in enumerate(claims):
        label = f"claims[{index}]"
        if not isinstance(claim, Mapping):
            violations.append(f"{label} must be a mapping")
            continue
        if set(claim) != _CLAIM_KEYS:
            violations.append(f"{label} keys must be exactly {sorted(_CLAIM_KEYS)}")
            continue
        claim_id = claim["claim_id"]
        if not _is_text(claim_id):
            violations.append(f"{label}.claim_id must be a non-empty string")
            continue
        if claim_id in seen:
            violations.append(f"{label}.claim_id is duplicated: {claim_id!r}")
            continue
        seen.add(claim_id)
        kind = claim["kind"]
        if kind not in _CLAIM_KINDS:
            violations.append(f"{label}.kind must be 'fact' or 'inference'")
            continue
        if not _is_text(claim["text"]):
            violations.append(f"{label}.text must be non-empty text")
        if not _is_text(claim["uncertainty"]):
            violations.append(f"{label}.uncertainty must be non-empty text")
        refs = claim["evidence_ids"]
        parents = claim["parent_claim_ids"]
        if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
            violations.append(f"{label}.evidence_ids must be a list of strings")
            refs = []
        elif len(set(refs)) != len(refs):
            violations.append(f"{label}.evidence_ids contains duplicates")
        if not isinstance(parents, list) or not all(isinstance(p, str) for p in parents):
            violations.append(f"{label}.parent_claim_ids must be a list of strings")
            parents = []
        elif len(set(parents)) != len(parents):
            violations.append(f"{label}.parent_claim_ids contains duplicates")
        for ref in refs:
            if ref not in eligible_ids:
                violations.append(f"{label} references unknown or ineligible evidence {ref!r}")
        if kind == "fact" and not refs:
            violations.append(f"{label} fact claim requires evidence")
        if kind == "inference" and not refs and not parents:
            violations.append(f"{label} inference claim requires evidence or parents")
        parsed[claim_id] = (kind, tuple(refs), tuple(parents))
    for claim_id, (_, _, parents) in parsed.items():
        for parent in parents:
            if parent not in seen:
                violations.append(f"claim {claim_id!r} references unknown parent {parent!r}")
    state: dict[str, int] = {}

    def visit(node: str) -> bool:
        mark = state.get(node, 0)
        if mark == 2:
            return True
        if mark == 1:
            return False
        state[node] = 1
        for parent in parsed.get(node, ("", (), ()))[2]:
            if parent in parsed and not visit(parent):
                return False
        state[node] = 2
        return True

    for node in parsed:
        if not visit(node):
            violations.append("parent references contain a cycle")
            break


def _check_report(report: Any, claim_ids: set[str], violations: list[str]) -> None:
    if not _is_text(report):
        violations.append("report must be non-empty text")
        return
    refs = _CLAIM_REF_RE.findall(report)
    if not refs:
        violations.append("report must cite at least one claim as [cl-<64 hex>]")
    for ref in refs:
        if ref not in claim_ids:
            violations.append(f"report cites unknown claim {ref!r}")


def validate_artifact(
    artifact: Mapping[str, Any],
    *,
    manifest: Any,
    ledger: EvidenceLedger,
    claims: list[Mapping[str, Any]],
) -> GateResult:
    violations: list[str] = []
    try:
        if not isinstance(artifact, Mapping):
            return GateResult(False, ("artifact must be a mapping",))
        keys = set(artifact)
        for name in sorted(keys - _BUSINESS - _ARTIFACT_META):
            violations.append(f"unknown artifact field: {name!r}")
        for name in sorted(_BUSINESS - keys):
            violations.append(f"missing artifact field: {name!r}")
        if violations:
            return GateResult(False, tuple(violations))
        if artifact["schema_version"] not in _SCHEMA_VERSIONS:
            violations.append("unsupported schema_version")
        expected = manifest.to_dict()
        if artifact["run_id"] != expected.get("run_id"):
            violations.append("run_id does not match manifest")
        if artifact["revision"] != expected.get("revision"):
            violations.append("revision does not match manifest")
        if artifact["policy_version"] != expected.get("policy_version"):
            violations.append("policy_version does not match manifest")
        if artifact["manifest"] != expected:
            violations.append("artifact manifest does not match given manifest")
        if artifact["execution_status"] != "completed":
            violations.append("execution_status must be 'completed'")

        reconstructed = EvidenceLedger(manifest)
        entries = artifact["evidence"]
        if not isinstance(entries, list):
            violations.append("artifact evidence must be a list")
            entries = []
        rebuilt: list[dict[str, Any]] = []
        eligible_ids: set[str] = set()
        for index, entry in enumerate(entries):
            label = f"evidence[{index}]"
            if not isinstance(entry, Mapping):
                violations.append(f"{label} must be a mapping")
                continue
            raw = {name: entry[name] for name in _EVIDENCE_KEYS if name in entry}
            try:
                item = reconstructed.add(raw)
            except ValueError as exc:
                violations.append(f"{label} is invalid: {exc}")
                continue
            serialized = item.to_dict()
            if serialized != dict(entry):
                violations.append(f"{label} does not match reconstructed entry")
            if item.eligibility == "eligible":
                eligible_ids.add(item.evidence_id)
            rebuilt.append(serialized)
        if (
            list(reconstructed.entries)
            and [item.to_dict() for item in reconstructed.entries] != rebuilt
        ):
            violations.append("artifact evidence does not match ledger order")

        ledger_dicts = [item.to_dict() for item in ledger.entries]
        if (
            not isinstance(entries, list)
            or [dict(entry) if isinstance(entry, Mapping) else entry for entry in entries]
            != ledger_dicts
        ):
            violations.append("artifact evidence does not equal ledger entries")

        if artifact["claims"] != claims:
            violations.append("artifact claims do not equal provided claims")
        _check_claims(artifact["claims"], eligible_ids, violations)
        if not any(
            isinstance(claim, Mapping)
            and isinstance(claim.get("evidence_ids"), list)
            and claim["evidence_ids"]
            for claim in claims
        ):
            violations.append("at least one eligible evidence and claim required")

        if artifact["rating"] not in _RATINGS:
            violations.append("rating is not an allowed value")
        limitations = artifact["limitations"]
        if not isinstance(limitations, list) or not limitations:
            violations.append("limitations must be a non-empty list")
        elif not all(_is_text(item) for item in limitations):
            violations.append("limitations must be non-empty strings")
        claim_ids = {
            claim["claim_id"]
            for claim in claims
            if isinstance(claim, Mapping) and isinstance(claim.get("claim_id"), str)
        }
        _check_report(artifact["report"], claim_ids, violations)
        if (
            expected.get("prompt_version") == "evidenceguard-v0.3"
            and expected.get("policy_version") == "v0.3"
        ):
            for item in validate_research_brief(
                artifact["report"],
                claims,
                as_of_utc=expected.get("as_of_utc"),
            ):
                violations.append(f"v03:{item}")
    except Exception as exc:  # malformed input must never escape as an exception
        violations.append(f"artifact validation error: {exc}")
    return GateResult(not violations, tuple(violations))


__all__ = ["GateResult", "validate_artifact"]
