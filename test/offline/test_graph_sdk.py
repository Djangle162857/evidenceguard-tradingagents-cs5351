import json
import re
from datetime import timedelta
from decimal import Decimal

import httpx
from langchain_openai import ChatOpenAI
from test_contracts_preapproval import NOW, _base_config
from test_runner import _raw_record

from evidenceguard.budget import BudgetLedger
from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger
from evidenceguard.integration import IntegrationContext
from evidenceguard.transport import CourseTransport
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup


def test_actual_graph_with_budgeted_sdk(tmp_path):
    manifest = create_manifest(_base_config(), now=NOW)
    ledger = EvidenceLedger(manifest)
    eid = ledger.add(_raw_record()).evidence_id
    ctx = IntegrationContext(manifest, ledger)

    run_budget = BudgetLedger(
        tmp_path / "run.json",
        token_limit=60000,
        attempt_limit=30,
        usd_limit="5",
        deadline=NOW + timedelta(seconds=900),
        clock=lambda: NOW,
    )
    project_budget = BudgetLedger(
        tmp_path / "project.json",
        token_limit=1000000000,
        attempt_limit=200,
        usd_limit="40",
        deadline=NOW + timedelta(seconds=900),
        clock=lambda: NOW,
    )

    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        system = "".join(
            message.get("content", "")
            for message in body.get("messages", [])
            if message.get("role") == "system"
        )
        role_match = re.search(r"Role: (\w+)", system)
        role = role_match.group(1) if role_match else ""
        cids = re.findall(r"cl-[0-9a-f]{64}", system)
        ref = f"[{cids[0]}]" if cids else f"[{eid}]"

        if role in ("bull", "bear", "risky", "safe", "neutral"):
            content = json.dumps(
                {
                    "cards": [
                        {
                            "kind": "fact",
                            "text": "Synthetic observation " + role,
                            "evidence_ids": [eid],
                            "parent_claim_ids": [],
                            "uncertainty": "Synthetic only",
                        }
                    ],
                    "reply_to": [],
                    "conflicts": [],
                    "stop_reason": "completed",
                }
            )
        elif body.get("response_format", {}).get("json_schema", {}).get("name") == "ResearchPlan":
            content = json.dumps(
                {
                    "recommendation": "Hold",
                    "rationale": ref,
                    "strategic_actions": "Review only",
                }
            )
        elif body.get("response_format", {}).get("json_schema", {}).get("name") == "TraderProposal":
            content = json.dumps(
                {
                    "action": "Hold",
                    "reasoning": ref,
                    "entry_price": None,
                    "stop_loss": None,
                    "position_sizing": None,
                }
            )
        elif (
            body.get("response_format", {}).get("json_schema", {}).get("name")
            == "PortfolioDecision"
        ):
            content = json.dumps(
                {
                    "rating": "Hold",
                    "executive_summary": ref,
                    "investment_thesis": ref,
                    "price_target": None,
                    "time_horizon": None,
                }
            )
        else:
            content = "**Rating**: Hold\nSynthetic observation " + ref

        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": "CS5351/DeepSeek-V4-Flash",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": content},
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 10,
                    "total_tokens": 110,
                },
            },
        )

    client = httpx.Client(
        transport=CourseTransport(run_budget, project_budget, inner=httpx.MockTransport(handler))
    )
    try:
        llm = ChatOpenAI(
            model="CS5351/DeepSeek-V4-Flash",
            base_url="https://llm.cs.cityu.edu.hk/v1",
            api_key="offline-placeholder",
            max_tokens=1024,
            max_retries=0,
            temperature=0,
            http_client=client,
        )
        graph = (
            GraphSetup(llm, llm, ConditionalLogic(1, 1), max_tool_rounds=1, boundary=ctx)
            .setup_graph(["market", "news"])
            .compile()
        )
        state = graph.invoke(
            Propagator().create_initial_state("AAPL", "2026-11-19"),
            config={"recursion_limit": 100, "max_concurrency": 1},
        )
    finally:
        client.close()

    assert state["final_rating"] == "Hold"
    assert ctx.claims[0]["claim_id"] in state["final_trade_decision"]
    assert len(ctx.claims) == 5
    assert {t["role"] for t in ctx.turns} == {"bull", "bear", "risky", "safe", "neutral"}
    assert calls

    for budget in (run_budget, project_budget):
        snapshot = budget.snapshot()
        assert snapshot["attempts"] == len(calls)
        assert snapshot["settled_tokens"] == 110 * len(calls)
        assert Decimal(snapshot["settled_usd"]) == Decimal("0.000042") * len(calls)
        assert Decimal(snapshot["reserved_usd"]) == Decimal("0")
        assert snapshot["stopped"] is False
