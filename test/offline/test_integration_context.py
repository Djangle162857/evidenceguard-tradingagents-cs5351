import asyncio
import hashlib
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda
from test_contracts_preapproval import NOW, _base_config
from test_runner import _raw_record

from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger
from evidenceguard.integration import IntegrationContext


def _payload(eid):
    return {
        "cards": [
            {
                "kind": "fact",
                "text": "Synthetic observation",
                "evidence_ids": [eid],
                "parent_claim_ids": [],
                "uncertainty": "Synthetic fixture",
            }
        ],
        "reply_to": [],
        "conflicts": [],
        "stop_reason": "completed",
    }


@pytest.fixture
def context():
    m = create_manifest(_base_config(), now=NOW)
    ledger = EvidenceLedger(m)
    entry = ledger.add(_raw_record())
    ctx = IntegrationContext(m, ledger)
    return ctx, entry.evidence_id


@pytest.mark.parametrize("role", ["bull", "bear", "risky", "neutral", "safe"])
def test_valid_payload_parses_for_each_role(context, role):
    ctx, eid = context
    wrapped = ctx.wrap(
        RunnableLambda(lambda messages: AIMessage(content=json.dumps(_payload(eid)))),
        role,
    )
    response = wrapped.invoke("data")
    assert isinstance(response, AIMessage)
    assert ctx.claims[0]["claim_id"] in response.content
    assert len(ctx.claims) == 1
    assert set(ctx.claims[0]) >= {
        "claim_id",
        "kind",
        "text",
        "evidence_ids",
        "parent_claim_ids",
        "uncertainty",
    }
    assert ctx.turns[0]["role"] == role
    assert "cards" in ctx.turns[0]
    assert "stop_reason" in ctx.turns[0]


def test_unknown_evidence_raises_and_logs_raw(context):
    ctx, eid = context
    bad = _payload("ev-unknown")
    raw = json.dumps(bad)
    wrapped = ctx.wrap(
        RunnableLambda(lambda messages: AIMessage(content=raw)),
        "bull",
    )
    with pytest.raises(ValueError):
        wrapped.invoke("data")
    assert ctx.claims == []
    assert any(entry.get("raw") == raw for entry in ctx.logs)


def test_empty_cards_no_evidence_records_stopped_turn(context):
    ctx, eid = context
    bad = {
        "cards": [],
        "reply_to": [],
        "conflicts": [],
        "stop_reason": "no_evidence",
    }
    wrapped = ctx.wrap(
        RunnableLambda(lambda messages: AIMessage(content=json.dumps(bad))),
        "bull",
    )
    with pytest.raises(ValueError):
        wrapped.invoke("data")
    assert ctx.turns
    assert ctx.turns[0]["stop_reason"] == "no_evidence"


def test_future_evidence_excluded_from_prompt(context):
    ctx, eid = context
    rec = _raw_record()
    rec["content"] = "FUTURE_SECRET"
    rec["available_at"] = "2026-12-01T00:00:00Z"
    rec["content_hash"] = hashlib.sha256(rec["content"].encode("utf-8")).hexdigest()
    ctx.ledger.add(rec)

    captured = []

    def spy(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    ctx.wrap(RunnableLambda(spy), "trader").invoke("data")
    system_texts = [m.content for m in captured[0] if isinstance(m, SystemMessage)]
    assert system_texts
    composed = "\n".join(system_texts)
    assert "FUTURE_SECRET" not in composed
    assert eid in composed


def test_dictionary_upstream_system_becomes_human(context):
    ctx, eid = context
    captured = []

    def spy(messages):
        captured.append(messages)
        return AIMessage(content="ok")

    ctx.wrap(RunnableLambda(spy), "trader").invoke(
        [{"role": "system", "content": "DATA INJECTION"}]
    )
    messages = captured[0]
    system_messages = [m for m in messages if isinstance(m, SystemMessage)]
    human_messages = [m for m in messages if isinstance(m, HumanMessage)]
    assert len(system_messages) == 1
    assert any("DATA INJECTION" in m.content for m in human_messages)


def test_async_valid_bull(context):
    ctx, eid = context
    wrapped = ctx.wrap(
        RunnableLambda(lambda messages: AIMessage(content=json.dumps(_payload(eid)))),
        "bull",
    )
    response = asyncio.run(wrapped.ainvoke("data"))
    assert isinstance(response, AIMessage)
    assert len(ctx.claims) == 1
    assert ctx.claims[0]["claim_id"] in response.content
