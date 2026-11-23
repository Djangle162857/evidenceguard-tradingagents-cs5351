"""Budget-enforcing course transport for the CityU CS5351 model endpoint.

Wraps an inner httpx transport (real or injected mock) and settles the
run/project budget ledgers around every non-streaming chat-completion call.

The input reservation is a conservative serialized byte count plus a framing
margin under the current-tokenizer assumption; each actual usage is checked and
any overrun is retained/stopped. Financial reservation uses the metadata
worst case independently. This is not a proven tokenizer bound.
"""

from __future__ import annotations

import contextlib
import json
import threading
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

EXACT_URL = "https://llm.cs.cityu.edu.hk/v1/chat/completions"
EXACT_MODEL = "CS5351/DeepSeek-V4-Flash"
INPUT_PRICE = Decimal("3e-7")
OUTPUT_PRICE = Decimal("1.2e-6")
PROVIDER_INPUT_MAX = 1_000_000
PROVIDER_OUTPUT_MAX = 393_216
WORST_USD = Decimal("0.7718592")
FRAMING = 512


class TransportError(RuntimeError):
    """Sanitized transport failure."""


class BudgetExceeded(RuntimeError):
    """Raised when settlement overruns a reservation."""


def _byte_upper(content: bytes) -> int:
    try:
        req = httpx.Request("POST", EXACT_URL, content=content)
        body = json.loads(req.content)
    except (ValueError, TypeError, httpx.HTTPError):
        raise TransportError("malformed request body") from None
    if not isinstance(body, dict):
        raise TransportError("malformed request body")
    messages = body.get("messages")
    tools = body.get("tools", [])
    if not isinstance(messages, list) or not isinstance(tools, list):
        raise TransportError("malformed messages/tools")
    return len(content) + 256 * len(messages) + FRAMING * len(tools) + FRAMING


def _validate(content: bytes, output_limit: int) -> int:
    try:
        body = json.loads(content)
    except (ValueError, TypeError):
        raise TransportError("malformed request body") from None
    if not isinstance(body, dict):
        raise TransportError("malformed request body")
    if body.get("model") != EXACT_MODEL:
        raise TransportError("unexpected model")
    if body.get("stream", False) is not False:
        raise TransportError("streaming not permitted")
    caps = []
    for key in ("max_tokens", "max_completion_tokens"):
        if key in body:
            val = body[key]
            if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                raise TransportError("invalid token cap")
            caps.append(val)
    if len(caps) != 1:
        raise TransportError("exactly one token cap required")
    cap = caps[0]
    if cap > output_limit or output_limit > 1024:
        raise TransportError("token cap exceeds limit")
    if output_limit > PROVIDER_OUTPUT_MAX:
        raise TransportError("configured output limit too high")
    return cap


class _LedgerGuard:
    """Serialize ledger critical sections (async runs off the event loop)."""

    def __init__(self, run_ledger: Any, project_ledger: Any) -> None:
        self.run_ledger = run_ledger
        self.project_ledger = project_ledger
        self._lock = threading.Lock()

    def prepare(self, request: httpx.Request, output_limit: int, input_limit: int) -> str:
        if request.method != "POST" or str(request.url) != EXACT_URL:
            raise TransportError("unexpected endpoint or method")
        cap = _validate(request.content, output_limit)
        upper = _byte_upper(request.content)
        if upper > input_limit or input_limit > 8000:
            raise TransportError("input exceeds limit")
        attempt = str(uuid.uuid4())
        with self._lock:
            self.project_ledger.reserve(
                attempt,
                input_upper=PROVIDER_INPUT_MAX,
                output_upper=PROVIDER_OUTPUT_MAX,
                usd_upper=WORST_USD,
            )
            try:
                self.run_ledger.reserve(
                    attempt,
                    input_upper=upper,
                    output_upper=cap,
                    usd_upper=WORST_USD,
                )
            except Exception:
                self.project_ledger.settle(
                    attempt,
                    input_tokens=0,
                    output_tokens=0,
                    actual_usd=Decimal(0),
                )
                raise
        return attempt

    def _settle_unknown(self, attempt: str) -> None:
        for ledger in (self.project_ledger, self.run_ledger):
            with contextlib.suppress(Exception):
                ledger.settle(
                    attempt,
                    input_tokens=None,
                    output_tokens=None,
                    actual_usd=None,
                )

    def _settle_known(self, attempt: str, itok: int, otok: int) -> None:
        cost = INPUT_PRICE * itok + OUTPUT_PRICE * otok
        errors = []
        for ledger in (self.project_ledger, self.run_ledger):
            try:
                ledger.settle(
                    attempt,
                    input_tokens=itok,
                    output_tokens=otok,
                    actual_usd=cost,
                )
            except Exception as exc:  # pragma: no cover - collected below
                errors.append(exc)
        if errors:
            raise TransportError("ledger settlement failed") from None

    @staticmethod
    def _usage(body: bytes) -> tuple[int, int]:
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            raise TransportError("unparseable response body") from None
        if not isinstance(data, dict):
            raise TransportError("unparseable response body")
        usage = data.get("usage")
        if not isinstance(usage, dict):
            raise TransportError("missing usage")
        vals = []
        for key in ("prompt_tokens", "completion_tokens"):
            val = usage.get(key)
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise TransportError("invalid usage")
            vals.append(val)
        return vals[0], vals[1]

    def _wrap(self, response: httpx.Response, request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )


class CourseTransport(httpx.BaseTransport):
    def __init__(
        self,
        run_ledger: Any,
        project_ledger: Any,
        *,
        inner: httpx.BaseTransport | None = None,
        input_limit: int = 8000,
        output_limit: int = 1024,
    ) -> None:
        self._guard = _LedgerGuard(run_ledger, project_ledger)
        self._inner = inner if inner is not None else httpx.HTTPTransport(retries=0)
        self._input_limit = input_limit
        self._output_limit = output_limit

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        attempt = self._guard.prepare(request, self._output_limit, self._input_limit)
        try:
            response = self._inner.handle_request(request)
        except Exception:
            self._guard._settle_unknown(attempt)
            raise TransportError("network transport failed") from None
        try:
            body = response.read()
            itok, otok = self._guard._usage(body)
        except Exception:
            with contextlib.suppress(Exception):
                response.close()
            self._guard._settle_unknown(attempt)
            raise TransportError("response read failed") from None
        if not (200 <= response.status_code < 300):
            with contextlib.suppress(Exception):
                response.close()
            self._guard._settle_unknown(attempt)
            raise TransportError("non-success response") from None
        try:
            wrapped = self._guard._wrap(response, request)
            self._guard._settle_known(attempt, itok, otok)
        finally:
            with contextlib.suppress(Exception):
                response.close()
        return wrapped

    def close(self) -> None:
        self._inner.close()


class AsyncCourseTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        run_ledger: Any,
        project_ledger: Any,
        *,
        inner: httpx.AsyncBaseTransport | None = None,
        input_limit: int = 8000,
        output_limit: int = 1024,
    ) -> None:
        self._guard = _LedgerGuard(run_ledger, project_ledger)
        self._inner = inner if inner is not None else httpx.AsyncHTTPTransport(retries=0)
        self._input_limit = input_limit
        self._output_limit = output_limit

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        attempt = self._guard.prepare(request, self._output_limit, self._input_limit)
        try:
            response = await self._inner.handle_async_request(request)
        except Exception:
            self._guard._settle_unknown(attempt)
            raise TransportError("network transport failed") from None
        try:
            body = await response.aread()
            itok, otok = self._guard._usage(body)
        except Exception:
            with contextlib.suppress(Exception):
                await response.aclose()
            self._guard._settle_unknown(attempt)
            raise TransportError("response read failed") from None
        if not (200 <= response.status_code < 300):
            with contextlib.suppress(Exception):
                await response.aclose()
            self._guard._settle_unknown(attempt)
            raise TransportError("non-success response") from None
        try:
            wrapped = self._guard._wrap(response, request)
            self._guard._settle_known(attempt, itok, otok)
        finally:
            with contextlib.suppress(Exception):
                await response.aclose()
        return wrapped

    async def aclose(self) -> None:
        await self._inner.aclose()


def make_chat_model(
    run_ledger: Any,
    project_ledger: Any,
    key_path: str | Path,
) -> Any:
    from langchain_openai import ChatOpenAI

    api_key = Path(key_path).read_text(encoding="utf-8").strip()
    sync_client = httpx.Client(
        transport=CourseTransport(run_ledger, project_ledger),
    )
    async_client = httpx.AsyncClient(
        transport=AsyncCourseTransport(run_ledger, project_ledger),
    )
    return ChatOpenAI(
        model=EXACT_MODEL,
        base_url=EXACT_URL.rsplit("/chat/completions", 1)[0],
        api_key=api_key,
        max_tokens=1024,
        max_retries=0,
        temperature=0,
        streaming=False,
        timeout=90,
        http_client=sync_client,
        http_async_client=async_client,
    )
