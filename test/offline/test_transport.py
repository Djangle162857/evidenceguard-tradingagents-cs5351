from __future__ import annotations

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from evidenceguard.budget import BudgetExceeded, BudgetLedger
from evidenceguard.transport import (
    AsyncCourseTransport,
    CourseTransport,
    TransportError,
)

NOW = datetime(2026, 11, 19, 12, tzinfo=UTC)
DEADLINE = NOW + timedelta(seconds=900)
URL = "https://llm.cs.cityu.edu.hk/v1/chat/completions"
MODEL = "CS5351/DeepSeek-V4-Flash"
BODY = {
    "model": MODEL,
    "messages": [{"role": "user", "content": "hello"}],
    "max_tokens": 1024,
}


def _ledger_path() -> Path:
    return Path(tempfile.mkdtemp()) / "budget.json"


def make_run() -> BudgetLedger:
    return BudgetLedger(
        _ledger_path(),
        token_limit=60000,
        attempt_limit=30,
        usd_limit="5",
        deadline=DEADLINE,
        clock=lambda: NOW,
    )


def make_project() -> BudgetLedger:
    return BudgetLedger(
        _ledger_path(),
        token_limit=10000000,
        attempt_limit=200,
        usd_limit="40",
        deadline=DEADLINE,
        clock=lambda: NOW,
    )


def success_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "usage": {"prompt_tokens": 100, "completion_tokens": 10},
            "choices": [],
        },
    )


def make_client(run, project, handler):
    inner = httpx.MockTransport(handler)
    return httpx.Client(transport=CourseTransport(run, project, inner=inner), timeout=None)


def make_async_client(run, project, handler):
    inner = httpx.MockTransport(handler)
    return httpx.AsyncClient(
        transport=AsyncCourseTransport(run, project, inner=inner), timeout=None
    )


class Recorder:
    def __init__(self, response=None, exc=None):
        self.calls = 0
        self.requests: list[httpx.Request] = []
        self.response = response
        self.exc = exc

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.requests.append(request)
        if self.exc is not None:
            raise self.exc
        return self.response


def assert_success_accounting(run, project) -> None:
    for ledger in (run, project):
        snap = ledger.snapshot()
        assert isinstance(snap["attempts"], int)
        assert snap["attempts"] == 1
        assert isinstance(snap["settled_usd"], str)
        assert Decimal(snap["settled_usd"]) == Decimal("0.000042")
    return


def test_success_single_call_both_ledgers_spent() -> None:
    run, project = make_run(), make_project()
    rec = Recorder(success_response())
    with make_client(run, project, rec) as client:
        response = client.post(URL, json=BODY)
    assert response.status_code == 200
    assert rec.calls == 1
    sent = rec.requests[0]
    assert sent.method == "POST"
    assert str(sent.url) == URL
    assert_success_accounting(run, project)
    tokens = run.snapshot()["settled_tokens"]
    assert tokens == 110
    assert project.snapshot()["settled_tokens"] == 110


@pytest.mark.parametrize(
    "body",
    [
        {**BODY, "model": ""},
        {**BODY, "messages": None},
        {**BODY, "stream": True},
        {k: v for k, v in BODY.items() if k != "max_tokens"},
        {**BODY, "max_tokens": 2048},
        {**BODY, "max_tokens": True},
        {**BODY, "max_tokens": 1024, "max_completion_tokens": 1024},
        {**BODY, "messages": [{"role": "user", "content": "x" * 1000000}]},
    ],
)
def test_invalid_requests_rejected_without_calls(body: dict) -> None:
    run, project = make_run(), make_project()
    rec = Recorder(success_response())
    with make_client(run, project, rec) as client, pytest.raises(TransportError):
        client.post(URL, json=body)
    assert rec.calls == 0
    assert run.snapshot()["attempts"] == 0
    assert project.snapshot()["attempts"] == 0


def test_invalid_url_rejected_without_calls() -> None:
    run, project = make_run(), make_project()
    rec = Recorder(success_response())
    with make_client(run, project, rec) as client, pytest.raises(TransportError):
        client.post("https://elsewhere.example/chat", json=BODY)
    assert rec.calls == 0
    assert run.snapshot()["attempts"] == 0


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "boom"}),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"usage": {"prompt_tokens": "x"}, "choices": []}),
    ],
)
def test_bad_response_exception_stops_both_ledgers(response) -> None:
    run, project = make_run(), make_project()
    rec = Recorder(response)
    with make_client(run, project, rec) as client, pytest.raises(TransportError):
        client.post(URL, json=BODY)
    assert rec.calls == 1
    for ledger in (run, project):
        assert ledger.snapshot()["stopped"] is True
        assert Decimal(ledger.snapshot()["reserved_usd"]) == Decimal("0.7718592")


def test_network_error_stops_both_ledgers() -> None:
    run, project = make_run(), make_project()
    rec = Recorder(exc=httpx.ConnectError("down"))
    with make_client(run, project, rec) as client, pytest.raises(TransportError):
        client.post(URL, json=BODY)
    assert rec.calls == 1
    for ledger in (run, project):
        assert ledger.snapshot()["stopped"] is True
        assert Decimal(ledger.snapshot()["reserved_usd"]) == Decimal("0.7718592")


def test_known_overrun_stops_run_and_settles_project() -> None:
    run, project = make_run(), make_project()
    response = httpx.Response(
        200,
        json={"usage": {"prompt_tokens": 20000, "completion_tokens": 10}, "choices": []},
    )
    rec = Recorder(response)
    with make_client(run, project, rec) as client, pytest.raises(TransportError):
        client.post(URL, json=BODY)
    assert rec.calls == 1
    assert run.snapshot()["stopped"] is True
    assert Decimal(run.snapshot()["reserved_usd"]) > 0
    psnap = project.snapshot()
    assert Decimal(psnap["settled_usd"]) == Decimal("0.006012")
    assert Decimal(psnap["reserved_usd"]) == Decimal("0")


def test_async_success_single_call_accounting() -> None:
    run, project = make_run(), make_project()
    rec = Recorder(success_response())

    async def go():
        async with make_async_client(run, project, rec) as client:
            return await client.post(URL, json=BODY)

    response = asyncio.run(go())
    assert response.status_code == 200
    assert rec.calls == 1
    assert_success_accounting(run, project)


def test_config_output_limit_64_rejects_cap_1024() -> None:
    run, project = make_run(), make_project()
    rec = Recorder(success_response())
    client = httpx.Client(
        transport=CourseTransport(run, project, inner=httpx.MockTransport(rec), output_limit=64),
        timeout=None,
    )
    with client, pytest.raises(TransportError):
        client.post(URL, json=BODY)
    assert rec.calls == 0


def test_run_ledger_limit_rejects_before_network() -> None:
    run = BudgetLedger(
        _ledger_path(),
        token_limit=1,
        attempt_limit=30,
        usd_limit="5",
        deadline=DEADLINE,
        clock=lambda: NOW,
    )
    project = make_project()
    rec = Recorder(success_response())
    with make_client(run, project, rec) as client, pytest.raises((TransportError, BudgetExceeded)):
        client.post(URL, json=BODY)
    assert rec.calls == 0
    psnap = project.snapshot()
    assert psnap["attempts"] == 1
    assert Decimal(psnap["settled_usd"]) == Decimal("0")
    assert Decimal(psnap["reserved_usd"]) == Decimal("0")
