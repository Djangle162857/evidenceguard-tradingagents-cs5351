from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "1.0"
SUPPORTED_TICKERS = ("AAPL", "MSFT", "NVDA")
_NEWS_LIMIT = 3

_LIMITATION_MARKET = (
    "market quote is a point-in-time snapshot as returned by the vendor while "
    "downloading now; available_at reflects the declared last market update "
    "source timestamp (regularMarketTime), not proof of exact vendor "
    "publication latency, and is not a historical archived availability record."
)
_LIMITATION_NEWS = (
    "news items are limited summaries/headlines from the vendor list response; "
    "no article body was fetched and no full article is represented. "
    "published_at comes only from the supplied pubDate and is never inferred."
)
_LIMITATION_UNKNOWN_TIME = (
    "one or more source timestamps were missing or invalid and were preserved "
    "as unknown (available_at/published_at None); retrieval time was not "
    "substituted for an unknown source time."
)


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _epoch_to_utc(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        return None
    try:
        return datetime.fromtimestamp(number, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _parse_pubdate(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(UTC)


def _freeze_quote(ticker: str, info: Mapping[str, Any]) -> dict[str, Any]:
    price = _finite_number(info.get("regularMarketPrice"))
    if price is None:
        raise ValueError("quote response missing finite regularMarketPrice")
    content: dict[str, Any] = {"ticker": ticker, "regularMarketPrice": price}
    optional_fields = (
        "regularMarketTime",
        "regularMarketOpen",
        "regularMarketDayHigh",
        "regularMarketDayLow",
        "regularMarketVolume",
        "regularMarketPreviousClose",
    )
    for field in optional_fields:
        raw = info.get(field)
        if field == "regularMarketTime":
            stamp = _epoch_to_utc(raw)
            if stamp is not None:
                content[field] = stamp.isoformat()
        else:
            number = _finite_number(raw)
            if number is not None:
                content[field] = number
    currency = info.get("currency")
    if isinstance(currency, str) and currency:
        content["currency"] = currency
    event = _epoch_to_utc(info.get("regularMarketTime"))
    return {
        "kind": "market",
        "source_uri": f"https://finance.yahoo.com/quote/{ticker}/",
        "content": content,
        "content_hash": _sha256_text(_canonical_json(content)),
        "retrieved_at": None,
        "available_at": event.isoformat() if event is not None else None,
        "excerpt": None,
    }


def _news_url(item: Mapping[str, Any]) -> str | None:
    for key in ("canonicalUrl", "url"):
        candidate = item.get(key)
        if isinstance(candidate, str) and candidate.startswith("https://"):
            return candidate
        if isinstance(candidate, Mapping):
            nested = candidate.get("url")
            if isinstance(nested, str) and nested.startswith("https://"):
                return nested
    return None


def _freeze_news(ticker: str, items: Iterable[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in items:
        if len(records) >= _NEWS_LIMIT:
            break
        if not isinstance(item, Mapping):
            continue
        payload = item.get("content", item)
        if not isinstance(payload, Mapping):
            continue
        item = payload
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        summary = item.get("summary")
        summary_text = summary.strip() if isinstance(summary, str) else ""
        content: dict[str, Any] = {"ticker": ticker, "title": title}
        if summary_text:
            content["summary"] = summary_text
        published = _parse_pubdate(item.get("pubDate"))
        url = _news_url(item)
        if url is None:
            url = f"https://finance.yahoo.com/quote/{ticker}/news/"
        excerpt = title if summary_text else f"{title} (headline only; no summary supplied)"
        records.append(
            {
                "kind": "news",
                "source_uri": url,
                "content": content,
                "content_hash": _sha256_text(_canonical_json(content)),
                "retrieved_at": None,
                "published_at": published.isoformat() if published is not None else None,
                "excerpt": excerpt,
            }
        )
    return records


def freeze_snapshot(
    ticker: str,
    *,
    clock: Callable[[], datetime],
    source: Any = None,
) -> dict[str, Any]:
    if ticker not in SUPPORTED_TICKERS:
        raise ValueError(f"unsupported ticker: {ticker!r}")
    if source is None:
        import yfinance  # imported lazily; no network at module import

        source = yfinance.Ticker(ticker)

    info = source.get_info()
    if not isinstance(info, Mapping):
        raise ValueError("quote response was not a mapping")
    market_record = _freeze_quote(ticker, info)

    limitations = [_LIMITATION_MARKET, _LIMITATION_NEWS]
    news_records: list[dict[str, Any]] = []
    try:
        raw_news = source.get_news(count=_NEWS_LIMIT)
        news_records = _freeze_news(ticker, raw_news or ())
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed silently
        limitations.append(
            f"news retrieval raised {type(exc).__name__}; no news records were captured this run."
        )

    retrieved = clock()
    if not isinstance(retrieved, datetime):
        raise TypeError("clock must return a datetime")
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("clock must return a timezone-aware datetime")
    retrieved = retrieved.astimezone(UTC)
    retrieved_iso = retrieved.isoformat()

    records = [market_record] + news_records
    unknown_time = market_record["available_at"] is None or any(
        record.get("published_at") is None for record in news_records
    )
    if unknown_time:
        limitations.append(_LIMITATION_UNKNOWN_TIME)

    for record in records:
        record["retrieved_at"] = retrieved_iso
        if isinstance(record.get("content"), Mapping):
            record["content"] = _canonical_json(record["content"])
        record["content_hash"] = _sha256_text(record["content"])
        if "excerpt" not in record:
            record["excerpt"] = record["content"][:350]

    snapshot: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ticker": ticker,
        "retrieved_at": retrieved_iso,
        "as_of_utc": retrieved_iso,
        "records": records,
        "limitations": limitations,
    }
    snapshot["snapshot_hash"] = _sha256_text(_canonical_json(snapshot))
    return snapshot


def validate_snapshot(snapshot: Mapping[str, Any]) -> bool:
    if not isinstance(snapshot, Mapping):
        raise ValueError("snapshot must be a mapping")
    stored_hash = snapshot.get("snapshot_hash")
    if not isinstance(stored_hash, str):
        raise ValueError("snapshot missing snapshot_hash")
    if snapshot.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported schema_version")
    if snapshot.get("ticker") not in SUPPORTED_TICKERS:
        raise ValueError("unsupported ticker")
    body = {key: value for key, value in snapshot.items() if key != "snapshot_hash"}
    try:
        expected = _sha256_text(_canonical_json(body))
    except (TypeError, ValueError) as exc:
        raise ValueError("snapshot is not canonical JSON") from exc
    if expected != stored_hash:
        raise ValueError("snapshot_hash mismatch")
    if not isinstance(snapshot.get("records"), list):
        raise ValueError("snapshot records must be a list")
    return True


def records_for_run(snapshot: Mapping[str, Any], run_id: str) -> list[dict[str, Any]]:
    validate_snapshot(snapshot)
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("run_id must be a non-empty string")
    records = copy.deepcopy(snapshot["records"])
    for record in records:
        record["run_id"] = run_id
    return records
