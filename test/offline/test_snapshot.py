from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timedelta

import pytest
from test_contracts_preapproval import NOW, _base_config

from evidenceguard.contracts import create_manifest
from evidenceguard.evidence import EvidenceLedger
from evidenceguard.snapshot import (
    SUPPORTED_TICKERS,
    freeze_snapshot,
    records_for_run,
    validate_snapshot,
)

ONE_HOUR = timedelta(hours=1)


def _canonical(payload):
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _epoch(moment):
    return int(moment.timestamp())


class _Source:
    def __init__(self, info, news=None, news_exc=None):
        self._info = info
        self._news = news if news is not None else []
        self._news_exc = news_exc
        self.info_calls = 0
        self.news_calls = 0

    def get_info(self):
        self.info_calls += 1
        return self._info

    def get_news(self, count=3):
        self.news_calls += 1
        if self._news_exc is not None:
            raise self._news_exc
        return self._news


def _quote(**overrides):
    info = {
        "regularMarketPrice": 190.5,
        "regularMarketTime": _epoch(NOW - ONE_HOUR),
        "currency": "USD",
    }
    info.update(overrides)
    return info


def _news_item(title, when, summary="Body."):
    content = {
        "title": title,
        "pubDate": when.isoformat(),
        "canonicalUrl": {"url": "https://example.com/a"},
    }
    if summary is not None:
        content["summary"] = summary
    return {"content": content}


def _freeze(source, ticker="AAPL"):
    return freeze_snapshot(ticker, clock=lambda: NOW, source=source)


def _kinds(snapshot):
    return [record["kind"] for record in snapshot["records"]]


def test_quote_uses_actual_source_time_and_full_hashes():
    source = _Source(_quote())
    snapshot = _freeze(source)
    market = snapshot["records"][0]
    assert market["kind"] == "market"
    assert market["available_at"] == (NOW - ONE_HOUR).isoformat()
    assert datetime.fromisoformat(market["available_at"]) == NOW - ONE_HOUR
    assert datetime.fromisoformat(snapshot["retrieved_at"]) == NOW
    assert datetime.fromisoformat(snapshot["as_of_utc"]) == NOW
    text = market["content"]
    assert isinstance(text, str)
    assert market["content_hash"] == _sha(text)
    body = {k: v for k, v in snapshot.items() if k != "snapshot_hash"}
    assert snapshot["snapshot_hash"] == _sha(_canonical(body))
    assert "quote" not in _kinds(snapshot)
    assert validate_snapshot(snapshot) is True


def test_records_for_run_is_deep_copy_and_binds_run_id():
    source = _Source(_quote())
    snapshot = _freeze(source)
    bound = records_for_run(snapshot, "run-a")
    assert all(record["run_id"] == "run-a" for record in bound)
    original = copy.deepcopy(snapshot)
    bound[0]["content_hash"] = "tampered"
    assert snapshot == original
    assert (
        records_for_run(snapshot, "run-a")[0]["content_hash"]
        == (original["records"][0]["content_hash"])
    )


def test_tampered_content_fails_validation():
    source = _Source(_quote())
    snapshot = _freeze(source)
    snapshot["records"][0]["content"] = '{"ticker":"AAPL","regularMarketPrice":1.0}'
    with pytest.raises(ValueError):
        validate_snapshot(snapshot)


def test_missing_and_future_news_times_are_not_eligible():
    missing_market = _Source(_quote(regularMarketTime=None))
    no_pub = {
        "content": {
            "title": "No date",
            "canonicalUrl": {"url": "https://example.com/n1"},
        }
    }
    future = _news_item("Future", NOW + ONE_HOUR)
    past = _news_item("Past", NOW - ONE_HOUR)
    source = _Source(_quote(regularMarketTime=None), news=[no_pub, future, past])
    snapshot = _freeze(source)
    market = snapshot["records"][0]
    missing = _freeze(missing_market)["records"][0]
    assert market["kind"] == "market" and market["available_at"] is None
    assert missing["available_at"] is None
    news = snapshot["records"][1:]
    assert [r["kind"] for r in news] == ["news", "news", "news"]
    assert news[0]["published_at"] is None
    assert datetime.fromisoformat(news[1]["published_at"]) == NOW + ONE_HOUR
    assert datetime.fromisoformat(news[2]["published_at"]) == NOW - ONE_HOUR
    assert any("unknown" in text.lower() for text in snapshot["limitations"])
    eligible = []
    for record in snapshot["records"]:
        if record["kind"] == "market" and record["available_at"] is not None:
            eligible.append(record)
        if record["kind"] == "news" and record["published_at"] is not None:
            moment = datetime.fromisoformat(record["published_at"])
            if moment <= NOW:
                eligible.append(record)
    assert [record["kind"] for record in eligible] == ["news"]
    assert eligible[0]["content"].find("Past") != -1

    manifest = create_manifest(_base_config(), now=NOW)
    ledger = EvidenceLedger(manifest)
    for record in records_for_run(snapshot, "run-a"):
        ledger.add(record)
    assert [entry.to_dict()["eligibility"] for entry in ledger.entries] == [
        "excluded",
        "excluded",
        "excluded",
        "eligible",
    ]


def test_news_exception_keeps_market_and_records_limitation():
    source = _Source(_quote(), news_exc=RuntimeError("network down"))
    snapshot = _freeze(source)
    assert _kinds(snapshot) == ["market"]
    assert source.news_calls == 1
    assert all("available_at" in record for record in snapshot["records"])
    assert any("RuntimeError" in text for text in snapshot["limitations"])
    assert validate_snapshot(snapshot) is True


def test_unsupported_ticker_and_missing_price_raise():
    forbidden = _Source(_quote())
    with pytest.raises(ValueError):
        freeze_snapshot("ZZZZ", clock=lambda: NOW, source=forbidden)
    assert forbidden.info_calls == 0
    assert forbidden.news_calls == 0
    assert "AAPL" in SUPPORTED_TICKERS
    bad = _Source({"regularMarketTime": _epoch(NOW - ONE_HOUR)})
    with pytest.raises(ValueError):
        _freeze(bad)
    assert bad.info_calls == 1
    assert bad.news_calls == 0


def test_missing_summary_preserves_headline_and_no_invented_date():
    item = {
        "content": {
            "title": "Headline only",
            "canonicalUrl": {"url": "https://example.com/h"},
        }
    }
    source = _Source(_quote(), news=[item])
    snapshot = _freeze(source)
    news = snapshot["records"][1]
    assert news["kind"] == "news"
    assert "published_at" in news and news["published_at"] is None
    assert "available_at" not in news
    assert "Headline only" in news["excerpt"]
    text = news["content"]
    assert "Headline only" in text
    assert "summary" not in json.loads(text)
    assert news["content_hash"] == _sha(text)
