"""Debate-turn validation for EvidenceGuard claims (FR-003).

Pure validation: no IO, no provider calls. The program assigns claim IDs;
caller-supplied claim IDs are rejected. Player-facing output is canonical and
deterministic so that release hashes are stable.
"""

from __future__ import annotations

import copy
import hashlib
import json

VALID_ROLES = ("bull", "bear", "risky", "neutral", "safe")
VALID_KINDS = ("fact", "inference")
VALID_STOP_REASONS = ("completed", "limit", "no_evidence", "invalid_output")

_CARD_FIELDS = frozenset(("kind", "text", "evidence_ids", "parent_claim_ids", "uncertainty"))
_CLAIM_FIELDS = frozenset(
    (
        "claim_id",
        "kind",
        "text",
        "evidence_ids",
        "parent_claim_ids",
        "uncertainty",
    )
)
_TURN_FIELDS = frozenset(("cards", "reply_to", "conflicts", "stop_reason"))


def _canonical_json(value) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _require_dict(value, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dict")
    return value


def _require_str_list(value, label: str) -> list:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    out = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise ValueError(f"{label} must contain nonempty strings")
        out.append(item)
    if len(out) != len(set(out)):
        raise ValueError(f"{label} contains duplicates")
    return out


def _require_nonempty_str(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _existing_by_id(existing_claims) -> dict:
    if existing_claims is None:
        raise ValueError("existing_claims must be a list")
    if not isinstance(existing_claims, (list, tuple)):
        raise ValueError("existing_claims must be a list")
    by_id = {}
    for index, raw in enumerate(existing_claims):
        claim = _require_dict(raw, f"existing_claims[{index}]")
        extra = set(claim) - _CLAIM_FIELDS
        if extra:
            raise ValueError(f"existing_claims[{index}] has unknown fields: {sorted(extra)}")
        missing = _CLAIM_FIELDS - set(claim)
        if missing:
            raise ValueError(f"existing_claims[{index}] missing fields: {sorted(missing)}")
        claim_id = _require_nonempty_str(claim["claim_id"], "existing claim_id")
        if claim_id in by_id:
            raise ValueError(f"duplicate existing claim_id: {claim_id}")
        kind = claim["kind"]
        if kind not in VALID_KINDS:
            raise ValueError(f"existing claim kind invalid: {kind!r}")
        text = _require_nonempty_str(claim["text"], "existing claim text")
        evidence_ids = _require_str_list(claim["evidence_ids"], "existing evidence_ids")
        parent_ids = _require_str_list(claim["parent_claim_ids"], "existing parent_claim_ids")
        uncertainty = _require_nonempty_str(claim["uncertainty"], "existing uncertainty")
        by_id[claim_id] = {
            "claim_id": claim_id,
            "kind": kind,
            "text": text,
            "evidence_ids": evidence_ids,
            "parent_claim_ids": parent_ids,
            "uncertainty": uncertainty,
        }
    _check_acyclic(by_id)
    return by_id


def _check_acyclic(claims: dict) -> None:
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(claims, WHITE)
    for start in sorted(claims):
        if colour[start] != WHITE:
            continue
        stack = [(start, iter(claims[start]["parent_claim_ids"]))]
        colour[start] = GREY
        while stack:
            node, parents = stack[-1]
            advanced = False
            for parent in parents:
                if parent not in claims:
                    continue
                state = colour.get(parent, BLACK)
                if state == GREY:
                    raise ValueError("cycle detected in claim graph")
                if state == WHITE:
                    colour[parent] = GREY
                    stack.append((parent, iter(claims[parent]["parent_claim_ids"])))
                    advanced = True
                    break
            if not advanced:
                colour[node] = BLACK
                stack.pop()


def _eligible_evidence_ids(manifest, ledger) -> set:
    run_id = getattr(manifest, "run_id", None)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("manifest.run_id missing")
    getter = getattr(ledger, "get", None)
    if not callable(getter):
        raise ValueError("ledger.get is not callable")
    entries = getattr(ledger, "entries", None)
    if not isinstance(entries, (list, tuple)):
        raise ValueError("ledger.entries not available")
    eligible = set()
    for raw in entries:
        data = raw.to_dict() if hasattr(raw, "to_dict") else raw
        data = _require_dict(data, "ledger entry")
        evidence_id = data.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError("ledger entry missing evidence_id")
        record = _require_dict(getter(evidence_id).to_dict(), "evidence")
        if record.get("run_id") != run_id:
            raise ValueError(f"evidence {evidence_id} belongs to another run")
        if record.get("eligibility") == "eligible":
            eligible.add(evidence_id)
    return eligible


def _resolve_evidence(evidence_id: str, manifest, ledger, eligible: set) -> None:
    try:
        evidence = ledger.get(evidence_id)
    except ValueError:
        raise ValueError(f"unknown evidence_id: {evidence_id}") from None
    record = _require_dict(evidence.to_dict(), "evidence")
    if record.get("run_id") != getattr(manifest, "run_id", None):
        raise ValueError(f"evidence_id {evidence_id} from another run")
    if record.get("eligibility") != "eligible" or evidence_id not in eligible:
        raise ValueError(f"evidence_id {evidence_id} is not eligible")


def _derive_claim_id(manifest, role: str, card: dict) -> str:
    material = {
        "run_id": getattr(manifest, "run_id", None),
        "role": role,
        "kind": card["kind"],
        "text": card["text"],
        "evidence_ids": list(card["evidence_ids"]),
        "parent_claim_ids": list(card["parent_claim_ids"]),
        "uncertainty": card["uncertainty"],
    }
    return "cl-" + _sha256_hex(_canonical_json(material))


def _validate_card(
    raw,
    index: int,
    *,
    role: str,
    manifest,
    ledger,
    existing: dict,
    eligible: set,
) -> dict:
    label = f"cards[{index}]"
    card = _require_dict(raw, label)
    if "claim_id" in card:
        raise ValueError(f"{label} must not supply claim_id (program-assigned)")
    extra = set(card) - _CARD_FIELDS
    if extra:
        raise ValueError(f"{label} has unknown fields: {sorted(extra)}")
    missing = _CARD_FIELDS - set(card)
    if missing:
        raise ValueError(f"{label} missing fields: {sorted(missing)}")

    kind = card["kind"]
    if kind not in VALID_KINDS:
        raise ValueError(f"{label} kind invalid: {kind!r}")
    text = _require_nonempty_str(card["text"], f"{label} text")
    evidence_ids = _require_str_list(card["evidence_ids"], f"{label} evidence_ids")
    parent_ids = _require_str_list(card["parent_claim_ids"], f"{label} parent_claim_ids")
    uncertainty = _require_nonempty_str(card["uncertainty"], f"{label} uncertainty")

    for parent_id in parent_ids:
        if parent_id not in existing:
            raise ValueError(f"{label} parent_claim_id not found: {parent_id}")

    bound_eligible = []
    for evidence_id in evidence_ids:
        _resolve_evidence(evidence_id, manifest, ledger, eligible)
        bound_eligible.append(evidence_id)

    if kind == "fact" and not bound_eligible:
        raise ValueError(f"{label} fact card has no eligible evidence")
    if kind == "inference" and not bound_eligible and not parent_ids:
        raise ValueError(f"{label} inference needs evidence or parent claims")

    return {
        "kind": kind,
        "text": text,
        "evidence_ids": evidence_ids,
        "parent_claim_ids": parent_ids,
        "uncertainty": uncertainty,
    }


def _copy_and_freeze(value):
    if isinstance(value, dict):
        return _FrozenDict(value)
    if isinstance(value, list):
        return tuple(_copy_and_freeze(item) for item in value)
    return copy.deepcopy(value)


class _FrozenDict(dict):
    """Dict that rejects mutation; supports deep copy via to_dict helpers."""

    def _immutable(self, *args, **kwargs):
        raise TypeError("immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __ior__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable

    def __deepcopy__(self, memo):
        return dict(copy.deepcopy(dict(self), memo))

    def __reduce__(self):
        return (dict, (dict(self),))


class DebateTurn:
    """Immutable accepted debate turn with program-assigned claim IDs."""

    __slots__ = ("_role", "_cards", "_reply_to", "_conflicts", "_stop_reason")

    def __init__(self, role, cards, reply_to, conflicts, stop_reason):
        object.__setattr__(self, "_role", role)
        object.__setattr__(self, "_cards", tuple(cards))
        object.__setattr__(self, "_reply_to", tuple(reply_to))
        object.__setattr__(self, "_conflicts", tuple(conflicts))
        object.__setattr__(self, "_stop_reason", stop_reason)

    def __setattr__(self, name, value):
        raise AttributeError("DebateTurn is immutable")

    def __delattr__(self, name):
        raise AttributeError("DebateTurn is immutable")

    @property
    def role(self) -> str:
        return self._role

    @property
    def cards(self) -> tuple:
        return tuple(copy.deepcopy(dict(card)) for card in self._cards)

    @property
    def reply_to(self) -> tuple:
        return self._reply_to

    @property
    def conflicts(self) -> tuple:
        return self._conflicts

    @property
    def stop_reason(self) -> str:
        return self._stop_reason

    def to_dict(self) -> dict:
        return {
            "role": self._role,
            "cards": [copy.deepcopy(dict(card)) for card in self._cards],
            "reply_to": list(self._reply_to),
            "conflicts": list(self._conflicts),
            "stop_reason": self._stop_reason,
        }

    def rendered(self) -> str:
        lines = [f"role={self._role} stop_reason={self._stop_reason}"]
        for card in self._cards:
            evidence = ", ".join(card["evidence_ids"]) or "-"
            parents = ", ".join(card["parent_claim_ids"]) or "-"
            lines.append(
                "claim {} kind={} text={} evidence=[{}] parents=[{}] uncertainty={}".format(
                    card["claim_id"],
                    card["kind"],
                    card["text"],
                    evidence,
                    parents,
                    card["uncertainty"],
                )
            )
        lines.append("reply_to=[{}]".format(", ".join(self._reply_to)))
        lines.append("conflicts=[{}]".format(", ".join(self._conflicts)))
        return "\n".join(lines)

    def __eq__(self, other):
        if not isinstance(other, DebateTurn):
            return NotImplemented
        return self.to_dict() == other.to_dict()

    def __hash__(self):
        return hash(_canonical_json(self.to_dict()))

    def __repr__(self):
        return (
            f"DebateTurn(role={self._role!r}, cards={len(self._cards)}, "
            f"stop_reason={self._stop_reason!r})"
        )


def validate_debate_turn(
    payload: dict,
    *,
    role: str,
    manifest,
    ledger,
    existing_claims: list,
) -> DebateTurn:
    """Validate a debate-turn payload and return a frozen DebateTurn.

    Raises ValueError on any contract violation. Claim IDs are assigned by
    this function from run, role and card business content.
    """
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role!r}")
    payload = _require_dict(payload, "payload")
    extra = set(payload) - _TURN_FIELDS
    if extra:
        raise ValueError(f"payload has unknown fields: {sorted(extra)}")
    missing = _TURN_FIELDS - set(payload)
    if missing:
        raise ValueError(f"payload missing fields: {sorted(missing)}")

    existing = _existing_by_id(existing_claims)
    eligible = _eligible_evidence_ids(manifest, ledger)

    stop_reason = payload["stop_reason"]
    if stop_reason not in VALID_STOP_REASONS:
        raise ValueError(f"invalid stop_reason: {stop_reason!r}")

    raw_cards = payload["cards"]
    if not isinstance(raw_cards, list):
        raise ValueError("cards must be a list")
    if not raw_cards and stop_reason == "completed":
        raise ValueError("empty cards only allowed for non-completed stops")

    validated = []
    for index, raw in enumerate(raw_cards):
        validated.append(
            _validate_card(
                raw,
                index,
                role=role,
                manifest=manifest,
                ledger=ledger,
                existing=existing,
                eligible=eligible,
            )
        )

    reply_to = _require_str_list(payload["reply_to"], "reply_to")
    conflicts = _require_str_list(payload["conflicts"], "conflicts")
    known_ids = set(existing)
    assigned_ids = set()
    cards = []
    for card in validated:
        claim = {
            "claim_id": _derive_claim_id(manifest, role, card),
            "kind": card["kind"],
            "text": card["text"],
            "evidence_ids": list(card["evidence_ids"]),
            "parent_claim_ids": list(card["parent_claim_ids"]),
            "uncertainty": card["uncertainty"],
        }
        if claim["claim_id"] in assigned_ids:
            raise ValueError(f"duplicate claim in turn: {claim['claim_id']}")
        assigned_ids.add(claim["claim_id"])
        cards.append(claim)

    for ref in reply_to:
        if ref not in known_ids:
            raise ValueError(f"reply_to references unknown claim: {ref}")
    for ref in conflicts:
        if ref not in known_ids:
            raise ValueError(f"conflicts references unknown claim: {ref}")

    combined = dict(existing)
    for claim in cards:
        for parent_id in claim["parent_claim_ids"]:
            if parent_id not in existing:
                raise ValueError(f"parent_claim_id not found: {parent_id}")
        combined[claim["claim_id"]] = claim
    _check_acyclic(combined)

    return DebateTurn(role, cards, reply_to, conflicts, stop_reason)
