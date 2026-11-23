"""Public upstream-graph runner for EvidenceGuard.

Runs the genuine upstream TradingAgents analyst graph through the budgeted
CourseTransport, then projects a draft artifact.  Only an independently
gated, human-approved artifact may later be released (not performed here).
"""

from __future__ import annotations

import copy
import time
from datetime import datetime
from typing import Any

from langchain_core.runnables import Runnable

from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.setup import GraphSetup

from .contracts import create_manifest
from .evidence import EvidenceLedger
from .gate import validate_artifact
from .integration import IntegrationContext
from .review import artifact_hash

_LIMITATIONS = [
    "Frozen snapshot; indicators not supplied; model reasoning requires "
    "human semantic review; no return/performance inference.",
]

_GRAPH_CONFIG = {"recursion_limit": 100, "max_concurrency": 1}


class _SnapshotRunnable(Runnable):
    """Minimal Runnable for baseline that substitutes frozen tools only.

    It never injects candidate prompts or validates cards: the upstream
    factory's original messages are forwarded unchanged.  ``bind_tools``
    redirects tools through ``IntegrationContext.wrap_tools`` so the baseline
    uses the same frozen snapshot as the candidate, without a prompt boundary.
    """

    def __init__(self, inner: Any, context: IntegrationContext) -> None:
        self._inner = inner
        self._context = context

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> _SnapshotRunnable:
        frozen = self._context.wrap_tools(list(tools))
        bound = self._inner.bind_tools(frozen, **kwargs)
        return _SnapshotRunnable(bound, self._context)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        return self._inner.with_structured_output(schema, **kwargs)

    def invoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        return self._inner.invoke(input, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: dict | None = None, **kwargs: Any) -> Any:
        return await self._inner.ainvoke(input, config=config, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _SnapshotBoundary:
    """Baseline boundary: wraps tools through IntegrationContext only."""

    def __init__(self, context: IntegrationContext) -> None:
        self._context = context

    def wrap_tools(self, tools: list[Any]) -> list[Any]:
        return self._context.wrap_tools(list(tools))

    def wrap(self, llm: Any, role: str | None = None) -> Any:
        return _SnapshotRunnable(llm, self._context)


def _budget_snapshot(ledger: Any) -> dict[str, Any]:
    return copy.deepcopy(ledger.snapshot())


def _sanitize(exc: BaseException) -> dict[str, str]:
    try:
        text = str(exc)
    except Exception:  # noqa: BLE001 - defensive, never raise in handler
        text = "<unprintable>"
    return {"type": type(exc).__name__, "message": text[:2000]}


def _classify(exc: BaseException) -> str:
    names = {type(exc).__name__}
    for base in type(exc).__mro__:
        names.add(base.__name__)
    if "BudgetExceeded" in names or "TransportError" in names:
        return "stopped"
    return "failed"


def _build_graph(context: IntegrationContext, config: dict, arm: str, llm: Any) -> Any:
    if arm == "candidate":
        boundary: Any = context
    else:
        boundary = _SnapshotBoundary(context)
    conditional = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    setup = GraphSetup(
        llm,
        llm,
        conditional,
        max_tool_rounds=1,
        boundary=boundary,
    )
    workflow = setup.setup_graph(config["analysts"])
    return workflow.compile()


def _final_rating(state: dict[str, Any]) -> str | None:
    raw = state.get("final_rating")
    if isinstance(raw, str) and raw:
        return raw
    return None


def run_upstream(
    config: dict,
    records: list[dict],
    *,
    llm: Any,
    run_ledger: Any,
    project_ledger: Any,
    now: datetime,
    arm: str = "candidate",
    source_status: Any = None,
) -> dict[str, Any]:
    """Execute the upstream graph and return a draft, gated artifact dict."""

    if arm not in ("candidate", "baseline"):
        raise ValueError("arm must be 'candidate' or 'baseline'")

    manifest = create_manifest(config, now=now)
    ledger = EvidenceLedger(manifest)

    context = IntegrationContext(
        manifest,
        ledger,
        enable_v03=arm == "candidate",
        source_status=source_status,
    )

    execution_status = "completed"
    errors: list[dict[str, str]] = []
    state: dict[str, Any] = {}
    started = time.monotonic()
    elapsed = 0.0

    try:
        for record in records:
            ledger.add(record)
        if arm == "candidate" and context.v03:
            pack = context.research_context()
            context.logs.append(
                {"research_context_pack": pack}
            )
        graph = _build_graph(context, config, arm, llm)
        initial = Propagator().create_initial_state(config["ticker"], config["as_of_utc"][:10])
        for snapshot in graph.stream(initial, config=_GRAPH_CONFIG, stream_mode="values"):
            if isinstance(snapshot, dict):
                state = snapshot
    except Exception as exc:  # noqa: BLE001 - failures must be preserved
        execution_status = _classify(exc)
        errors.append(_sanitize(exc))

    final_rating = None if execution_status != "completed" else _final_rating(state)

    if arm == "candidate":
        claims = copy.deepcopy(list(getattr(context, "claims", [])))
        turns = copy.deepcopy(list(getattr(context, "turns", [])))
        logs = copy.deepcopy(list(getattr(context, "logs", [])))
    else:
        claims = []
        turns = []
        logs = []

    evidence = [entry.to_dict() for entry in ledger.entries]

    elapsed = time.monotonic() - started

    report = state.get("final_trade_decision")
    if not isinstance(report, str):
        report = "" if report is None else str(report)

    artifact: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": manifest.run_id,
        "revision": manifest.revision,
        "manifest": manifest.to_dict(),
        "evidence": evidence,
        "claims": claims,
        "report": report,
        "rating": final_rating if execution_status == "completed" else None,
        "limitations": list(_LIMITATIONS),
        "policy_version": manifest.to_dict()["policy_version"],
        "execution_status": execution_status,
        "validation_status": "unvalidated",
        "review_status": "pending",
        "publication_status": "draft",
        "gate_results": {"passed": False, "violations": []},
        "measurement": {
            "arm": arm,
            "source_mode": "upstream_graph",
            "errors": errors,
            "transcript": logs,
            "turns": turns,
            "elapsed_seconds": elapsed,
            "run_budget": _budget_snapshot(run_ledger),
            "project_budget": _budget_snapshot(project_ledger),
        },
    }

    result = validate_artifact(artifact, manifest=manifest, ledger=ledger, claims=claims)
    passed = bool(getattr(result, "passed", False))
    violations = list(getattr(result, "violations", []))
    artifact["gate_results"] = {"passed": passed, "violations": violations}
    artifact["validation_status"] = "passed" if passed else "failed"
    artifact["review_status"] = "pending"
    artifact["publication_status"] = "draft"
    artifact["artifact_hash"] = artifact_hash(artifact)
    return artifact


__all__ = ["run_upstream"]
