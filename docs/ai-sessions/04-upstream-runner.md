# Upstream candidate and baseline runner

Session `ses_e0c286f12ffeQkjxLkrs1ZD0cH`; local OpenCode, course model `CS5351/DeepSeek-V4-Flash`.

Generated source was reviewed and repaired. Current offline regression includes candidate, baseline and retained failure paths; no paid financial experiment occurred.

The adjacent JSON is the authentic `opencode session export --sanitize` output, with local directory names further redacted if present. OpenCode redacts user/assistant text in that export. The assistant text below is copied from the authentic JSON event stream to make the code-generation evidence reviewable. Only local directory strings are redacted; code is not repaired in this transcript. All text parts, including incomplete or repeated candidates, are retained in order.

Instructions were relayed by Codex under the user’s startup authorization. This is not a transcript of the student personally typing in OpenCode, a human approval, or a claim that the model ran tests. Actual validation and subsequent corrections are recorded in `docs/bug-diary.md`, `docs/progress.md` and the checkpoint bundle.

Original sanitized export SHA-256: `800c2d10e11b6b91346be9c2b4f1c663b0a33644e3e5b67e974a7ae03e9b61f9`.

Original event stream SHA-256: `8d9540f40ddcb197f02f1b145c724833a5554fbfe6e0bb3becb9e45c299ecf25`.

Preservation update (2026-11-19): the original temporary session directory was lost on system restart. This public annotated text and sanitized native export survive; original hashes below were recorded before the loss. Their presence does not mean the private originals are still available.

## Authentic assistant text

```text
```python
"""Public upstream-graph runner for EvidenceGuard.

Runs the genuine upstream TradingAgents analyst graph through the budgeted
CourseTransport, then projects a draft artifact.  Only an independently
gated, human-approved artifact may later be released (not performed here).
"""

from __future__ import annotations

import copy
import traceback
from datetime import datetime
from typing import Any, Dict, List, Optional

from .contracts import create_manifest
from .evidence import EvidenceLedger
from .gate import validate_artifact
from .integration import IntegrationContext
from .review import artifact_hash

from tradingagents.graph.setup import GraphSetup
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.propagation import Propagator


_LIMITATIONS = [
    "Frozen snapshot; indicators not supplied; model reasoning requires "
    "human semantic review; no return/performance inference.",
]

_GRAPH_CONFIG = {"recursion_limit": 100, "max_concurrency": 1}


class _SnapshotRunnable:
    """Minimal Runnable for baseline that substitutes frozen tools only.

    It never injects candidate prompts or validates cards: the upstream
    factory's original messages are forwarded unchanged.  ``bind_tools``
    redirects tools through ``IntegrationContext.wrap_tools`` so the baseline
    uses the same frozen snapshot as the candidate, without a prompt boundary.
    """

    def __init__(self, inner: Any, context: IntegrationContext) -> None:
        self._inner = inner
        self._context = context

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> "_SnapshotRunnable":
        frozen = self._context.wrap_tools(list(tools))
        bound = self._inner.bind_tools(frozen, **kwargs)
        return _SnapshotRunnable(bound, self._context)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        return self._inner.with_structured_output(schema, **kwargs)

    def invoke(self, input: Any, config: Optional[dict] = None, **kwargs: Any) -> Any:
        return self._inner.invoke(input, config=config, **kwargs)

    async def ainvoke(
        self, input: Any, config: Optional[dict] = None, **kwargs: Any
    ) -> Any:
        return await self._inner.ainvoke(input, config=config, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _SnapshotBoundary:
    """Baseline boundary: wraps tools through IntegrationContext only."""

    def __init__(self, context: IntegrationContext) -> None:
        self._context = context

    def wrap_tools(self, tools: List[Any]) -> List[Any]:
        return self._context.wrap_tools(list(tools))

    def wrap(self, llm: Any, role: Optional[str] = None) -> Any:
        return _SnapshotRunnable(llm, self._context)


def _budget_snapshot(ledger: Any) -> Dict[str, Any]:
    snap = ledger.snapshot()
    if not isinstance(snap, dict):
        return {"snapshot": repr(snap)}
    safe: Dict[str, Any] = {}
    for key in (
        "settled_tokens",
        "settled_usd",
        "reserved_tokens",
        "reserved_usd",
        "token_limit",
        "attempt_limit",
        "requests",
        "attempts",
        "deadline_utc",
    ):
        if key in snap:
            value = snap[key]
            safe[key] = value.isoformat() if isinstance(value, datetime) else value
    return safe


def _sanitize(exc: BaseException) -> Dict[str, str]:
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


def _build_graph(context: IntegrationContext, config: dict, arm: str) -> Any:
    if arm == "candidate":
        boundary: Any = context
    else:
        boundary = _SnapshotBoundary(context)
    conditional = ConditionalLogic(max_debate_rounds=1, max_risk_discuss_rounds=1)
    setup = GraphSetup(
        context.llm,
        context.llm,
        conditional,
        max_tool_rounds=1,
        boundary=boundary,
    )
    workflow = setup.setup_graph(config["analysts"])
    return workflow.compile()


def _final_rating(state: Dict[str, Any]) -> Optional[str]:
    raw = state.get("final_rating")
    if isinstance(raw, str) and raw:
        return raw
    return None


def run_upstream(
    config: dict,
    records: List[dict],
    *,
    llm: Any,
    run_ledger: Any,
    project_ledger: Any,
    now: datetime,
    arm: str = "candidate",
) -> Dict[str, Any]:
    """Execute the upstream graph and return a draft, gated artifact dict."""

    if arm not in ("candidate", "baseline"):
        raise ValueError("arm must be 'candidate' or 'baseline'")

    manifest = create_manifest(config, now=now)
    ledger = EvidenceLedger(manifest)
    for record in records:
        ledger.add(record)

    context = IntegrationContext(manifest, ledger)

    execution_status = "completed"
    errors: List[Dict[str, str]] = []
    state: Dict[str, Any] = {}
    started = now
    elapsed = 0.0

    try:
        graph = _build_graph(context, config, arm)
        initial = Propagator().create_initial_state(
            config["ticker"], config["as_of_utc"][:10]
        )
        for snapshot in graph.stream(
            initial, config=_GRAPH_CONFIG, stream_mode="values"
        ):
            if isinstance(snapshot, dict):
                state = snapshot
    except Exception as exc:  # noqa: BLE001 - failures must be preserved
        execution_status = _classify(exc)
        errors.append(_sanitize(exc))
        errors.append({"trace": traceback.format_exc()[-4000:]})
        if arm == "candidate" and not state:
            state = {}

    if execution_status != "completed":
        final_rating = None
    else:
        final_rating = _final_rating(state)

    if arm == "candidate":
        claims = copy.deepcopy(list(getattr(context, "claims", [])))
        turns = copy.deepcopy(list(getattr(context, "turns", [])))
        logs = copy.deepcopy(list(getattr(context, "logs", [])))
    else:
        claims = []
        turns = []
        logs = []

    evidence = [entry.to_dict() for entry in ledger.entries()]

    if isinstance(started, datetime) and started.tzinfo is not None:
        elapsed = (datetime.now(started.tzinfo) - started).total_seconds()

    report = state.get("final_trade_decision")
    if not isinstance(report, str):
        report = "" if report is None else str(report)

    artifact: Dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": manifest.run_id,
        "revision": manifest.revision,
        "manifest": manifest.to_dict(),
        "evidence": evidence,
        "claims": claims,
        "report": report,
        "rating": final_rating if execution_status == "completed" else None,
        "limitations": list(_LIMITATIONS),
        "policy_version": manifest.policy_version,
        "execution_status": execution_status,
        "validation_status": "unvalidated",
        "review_status": "pending",
        "publication_status": "draft",
        "gate_results": {"passed": [], "violations": []},
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

    result = validate_artifact(
        artifact, manifest=manifest, ledger=ledger, claims=claims
    )
    passed = list(getattr(result, "passed", []))
    violations = list(getattr(result, "violations", []))
    artifact["gate_results"] = {"passed": passed, "violations": violations}
    artifact["validation_status"] = "passed" if violations == [] else "failed"
    artifact["review_status"] = "pending"
    artifact["publication_status"] = "draft"
    artifact["business_hash"] = artifact_hash(artifact)
    artifact["limitations"] = list(_LIMITATIONS)
    return artifact


__all__ = ["run_upstream"]
```
```
