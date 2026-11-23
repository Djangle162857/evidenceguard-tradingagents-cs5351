from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from test_contracts_preapproval import NOW, _base_config
from test_runner import _raw_record

from evidenceguard.budget import BudgetExceeded, BudgetLedger
from evidenceguard.review import artifact_hash
from evidenceguard.upstream_runner import run_upstream

CLAIM_RE = re.compile(r"cl-[0-9a-f]{64}")
EVIDENCE_RE = re.compile(r"ev-[0-9a-f]{64}")
ROLE_RE = re.compile(r"Role: (\w+)")


def _first_system_text(messages: list[Any]) -> str:
    for message in messages:
        if isinstance(message, BaseMessage):
            if message.type == "system":
                return str(message.content)
            continue
        if isinstance(message, dict) and message.get("role") == "system":
            return str(message.get("content", ""))
    return ""


def _candidate_payload(role: str, bad_id: str = "ev-" + "a" * 64) -> str:
    card = {
        "kind": "fact",
        "text": "Synthetic " + role,
        "evidence_ids": [bad_id],
        "parent_claim_ids": [],
        "uncertainty": "Synthetic",
    }
    payload = {
        "cards": [card],
        "reply_to": [],
        "conflicts": [],
        "stop_reason": "completed",
    }
    return json.dumps(payload)


class FakeModel(Runnable):
    def __init__(self, record: dict, mode: str) -> None:
        self._record = record
        self._mode = mode
        self.calls = 0

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> FakeModel:
        return self

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("structured output unused in this test")

    def invoke(self, input: Any, config: Any = None, **kwargs: Any) -> Any:
        self.calls += 1
        if hasattr(input, "to_messages"):
            messages = input.to_messages()
        elif isinstance(input, list):
            messages = input
        else:
            messages = []
        scan_messages = messages
        if isinstance(input, str):
            scan_messages = []
        system_text = _first_system_text(scan_messages)
        if self._mode == "stopped":
            raise BudgetExceeded("synthetic budget stop")
        role_match = ROLE_RE.search(system_text)
        role = role_match.group(1) if role_match else "Unknown"
        evidence_ids = EVIDENCE_RE.findall(system_text)
        actual_eid = evidence_ids[0] if evidence_ids else None
        if self._mode == "invalid" and role in ("bull", "bear", "risky", "safe", "neutral"):
            return AIMessage(content=_candidate_payload(role, "ev-unknown"))
        if self._mode == "candidate" and role in ("bull", "bear", "risky", "safe", "neutral"):
            target = actual_eid if actual_eid is not None else "ev-" + "a" * 64
            return AIMessage(content=_candidate_payload(role, target))
        if role in ("bull", "bear", "risky", "safe", "neutral"):
            return AIMessage(content="**Rating**: Hold\nBalanced [" + "no evidence" + "]")
        claim_match = CLAIM_RE.search(system_text)
        if claim_match is not None:
            tail = claim_match.group(0)
        elif actual_eid is not None:
            tail = actual_eid
        else:
            tail = "no evidence"
        return AIMessage(content="**Rating**: Hold\nBalanced [" + tail + "]")


def _budgets(tmp_path):
    run_ledger = BudgetLedger(
        tmp_path / "run.sqlite",
        token_limit=60000,
        attempt_limit=30,
        usd_limit="5",
        deadline=NOW + timedelta(seconds=900),
        clock=lambda: NOW,
    )
    project_ledger = BudgetLedger(
        tmp_path / "project.sqlite",
        token_limit=1_000_000_000,
        attempt_limit=500,
        usd_limit="40",
        deadline=NOW + timedelta(seconds=900),
        clock=lambda: NOW,
    )
    return run_ledger, project_ledger


def _run(tmp_path, mode: str, arm: str = "candidate"):
    run_ledger, project_ledger = _budgets(tmp_path)
    model = FakeModel(_raw_record(), mode)
    artifact = run_upstream(
        _base_config(),
        [_raw_record()],
        llm=model,
        run_ledger=run_ledger,
        project_ledger=project_ledger,
        now=NOW,
        arm=arm,
    )
    return artifact, model


def test_candidate_completes_with_gate_passed_draft(tmp_path):
    artifact, model = _run(tmp_path, "candidate")

    assert artifact["execution_status"] == "completed"
    assert artifact["validation_status"] == "passed"
    assert artifact["gate_results"]["passed"] is True
    assert artifact["review_status"] == "pending"
    assert artifact["publication_status"] == "draft"
    assert isinstance(artifact["artifact_hash"], str) and artifact["artifact_hash"]
    assert artifact["artifact_hash"] == artifact_hash(artifact)
    assert len(artifact["claims"]) == 5
    assert artifact["rating"] == "Hold"
    turns = artifact["measurement"]["turns"]
    assert [t["role"] for t in turns] == [
        "bull",
        "bear",
        "risky",
        "safe",
        "neutral",
    ]
    assert artifact["measurement"]["errors"] == []
    assert model.calls >= 1


def test_baseline_completes_without_claims(tmp_path):
    artifact, model = _run(tmp_path, "baseline", arm="baseline")

    assert artifact["execution_status"] == "completed"
    assert artifact["claims"] == []
    assert artifact["publication_status"] == "draft"
    assert isinstance(artifact["report"], str) and artifact["report"]
    assert model.calls >= 1


def test_malformed_second_record_is_failed_and_retains_evidence(tmp_path):
    run_ledger, project_ledger = _budgets(tmp_path)
    good = _raw_record()
    bad = dict(good)
    bad["content_hash"] = "bad-" + str(good.get("content_hash", ""))
    model = FakeModel(good, "candidate")
    artifact = run_upstream(
        _base_config(),
        [good, bad],
        llm=model,
        run_ledger=run_ledger,
        project_ledger=project_ledger,
        now=NOW,
        arm="candidate",
    )

    assert artifact["execution_status"] == "failed"
    assert artifact["publication_status"] == "draft"
    assert artifact["rating"] is None
    assert len(artifact["evidence"]) == 1
    assert artifact["measurement"]["errors"]
    assert model.calls == 0


def test_invalid_evidence_id_response_is_rejected(tmp_path):
    artifact, model = _run(tmp_path, "invalid")

    assert model.calls >= 1
    assert artifact["execution_status"] == "failed"
    assert artifact["claims"] == []
    assert artifact["rating"] is None
    assert artifact["gate_results"]["passed"] is False
    assert artifact["validation_status"] == "failed"
    assert artifact["publication_status"] == "draft"
    assert artifact["review_status"] == "pending"
    assert "ev-unknown" in json.dumps(artifact["measurement"]["transcript"])


def test_budget_exceeded_stops_run(tmp_path):
    artifact, model = _run(tmp_path, "stopped")

    assert model.calls >= 1
    assert artifact["execution_status"] == "stopped"
    assert artifact["publication_status"] == "draft"
    assert artifact["rating"] is None
    assert artifact["measurement"]["errors"]
    assert artifact["measurement"]["errors"][0]["type"] == "BudgetExceeded"


def test_invalid_arm_raises_value_error(tmp_path):
    run_ledger, project_ledger = _budgets(tmp_path)

    with pytest.raises(ValueError):
        run_upstream(
            _base_config(),
            [_raw_record()],
            llm=FakeModel(_raw_record(), "candidate"),
            run_ledger=run_ledger,
            project_ledger=project_ledger,
            now=NOW,
            arm="shadow",
        )
