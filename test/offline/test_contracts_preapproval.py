"""Pre-approval contract tests for ``evidenceguard.contracts.create_manifest``.

Test-only preparation artifact. This file exercises the public contract
documented in docs/architecture/interface-contracts.md and does NOT implement
or stub the application.

Public API under test (only public import):
    from evidenceguard.contracts import create_manifest

create_manifest(config: dict, *, now: datetime) -> RunManifest
  - pure validation, no I/O
  - invalid input raises ValueError
  - manifest is frozen; provides to_dict() (deep copy) and manifest_hash
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta

import pytest

from evidenceguard.contracts import create_manifest

# ---------------------------------------------------------------------------
# Purity guard: contract creation must not perform network I/O.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _forbid_network(monkeypatch):
    def _refuse(*_args, **_kwargs):
        raise AssertionError("create_manifest must not open network sockets")

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


# ---------------------------------------------------------------------------
# Frozen known values
# ---------------------------------------------------------------------------

NOW = datetime(2026, 11, 18, 22, 0, 0, tzinfo=UTC)

MODEL_ID = "CS5351/DeepSeek-V4-Flash"
BASELINE_SHA = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
CANDIDATE_SHA = "c" * 40
DATASET_HASH = "b" * 64


def _base_config() -> dict:
    return {
        "schema_version": "1.0",
        "run_id": "run-a",
        "revision": 1,
        "ticker": "AAPL",
        "as_of_utc": "2026-11-18T21:00:00Z",
        "analysts": ["market", "news"],
        "baseline_sha": BASELINE_SHA,
        "candidate_sha": CANDIDATE_SHA,
        "model_id": MODEL_ID,
        "prompt_version": "1.0",
        "policy_version": "1.0",
        "budget": {
            "token_limit": 60000,
            "attempt_limit": 30,
            "deadline_seconds": 900,
            "input_upper_per_call": 8000,
            "output_upper_per_call": 1024,
        },
        "dataset_hash": DATASET_HASH,
    }


@pytest.fixture
def valid_config() -> dict:
    return _base_config()


# ---------------------------------------------------------------------------
# Valid cases (10)
# ---------------------------------------------------------------------------


def _mutate_none(cfg: dict) -> dict:
    return cfg


def _mutate_ticker_msft(cfg: dict) -> dict:
    cfg["ticker"] = "MSFT"
    return cfg


def _mutate_ticker_nvda(cfg: dict) -> dict:
    cfg["ticker"] = "NVDA"
    return cfg


def _mutate_earlier_as_of(cfg: dict) -> dict:
    cfg["as_of_utc"] = "2026-11-17T13:30:00Z"
    return cfg


def _mutate_as_of_equals_now(cfg: dict) -> dict:
    cfg["as_of_utc"] = "2026-11-18T22:00:00Z"
    return cfg


def _mutate_revision_two(cfg: dict) -> dict:
    cfg["revision"] = 2
    return cfg


def _mutate_token_limit(cfg: dict) -> dict:
    cfg["budget"]["token_limit"] = 100000
    return cfg


def _mutate_attempt_limit_one(cfg: dict) -> dict:
    cfg["budget"]["attempt_limit"] = 1
    return cfg


def _mutate_offset_timezone(cfg: dict) -> dict:
    # 2026-11-19T05:00:00+08:00 == 2026-11-18T21:00:00Z
    cfg["as_of_utc"] = "2026-11-19T05:00:00+08:00"
    return cfg


def _mutate_analysts_market_only(cfg: dict) -> dict:
    cfg["analysts"] = ["market"]
    return cfg


VALID_MUTATIONS = [
    pytest.param(_mutate_none, id="valid-baseline"),
    pytest.param(_mutate_ticker_msft, id="valid-ticker-msft"),
    pytest.param(_mutate_ticker_nvda, id="valid-ticker-nvda"),
    pytest.param(_mutate_earlier_as_of, id="valid-earlier-as-of"),
    pytest.param(_mutate_as_of_equals_now, id="valid-as-of-equals-now"),
    pytest.param(_mutate_revision_two, id="valid-revision-two"),
    pytest.param(_mutate_token_limit, id="valid-token-limit"),
    pytest.param(_mutate_attempt_limit_one, id="valid-attempt-limit-one"),
    pytest.param(_mutate_offset_timezone, id="valid-offset-timezone"),
    pytest.param(_mutate_analysts_market_only, id="valid-analysts-market-only"),
]


@pytest.mark.parametrize("mutate", VALID_MUTATIONS)
def test_create_manifest_accepts_valid_config(valid_config, mutate):
    manifest = create_manifest(mutate(valid_config), now=NOW)

    data = manifest.to_dict()
    assert isinstance(data, dict)
    assert isinstance(manifest.manifest_hash, str)
    assert manifest.manifest_hash


# ---------------------------------------------------------------------------
# Invalid cases (10)
# ---------------------------------------------------------------------------


def _invalidate_unsupported_ticker(cfg: dict) -> dict:
    cfg["ticker"] = "NOT_A_TICKER"
    return cfg


def _invalidate_empty_analysts(cfg: dict) -> dict:
    cfg["analysts"] = []
    return cfg


def _invalidate_duplicate_analysts(cfg: dict) -> dict:
    cfg["analysts"] = ["market", "market"]
    return cfg


def _invalidate_unknown_analyst(cfg: dict) -> dict:
    cfg["analysts"] = ["market", "broker"]
    return cfg


def _invalidate_future_cutoff(cfg: dict) -> dict:
    cfg["as_of_utc"] = "2026-11-18T22:00:01Z"
    return cfg


def _invalidate_naive_cutoff(cfg: dict) -> dict:
    cfg["as_of_utc"] = "2026-11-18T21:00:00"
    return cfg


def _invalidate_zero_token_limit(cfg: dict) -> dict:
    cfg["budget"]["token_limit"] = 0
    return cfg


def _invalidate_bool_attempt_limit(cfg: dict) -> dict:
    cfg["budget"]["attempt_limit"] = True
    return cfg


def _invalidate_unofficial_model(cfg: dict) -> dict:
    cfg["model_id"] = "openai/gpt-4o"
    return cfg


def _invalidate_malformed_baseline(cfg: dict) -> dict:
    cfg["baseline_sha"] = "9fa1196fffbcfd9de5146d2dd2869df84ab9983"
    return cfg


INVALID_MUTATIONS = [
    pytest.param(_invalidate_unsupported_ticker, id="invalid-ticker"),
    pytest.param(_invalidate_empty_analysts, id="invalid-empty-analysts"),
    pytest.param(_invalidate_duplicate_analysts, id="invalid-duplicate-analysts"),
    pytest.param(_invalidate_unknown_analyst, id="invalid-unknown-analyst"),
    pytest.param(_invalidate_future_cutoff, id="invalid-future-cutoff"),
    pytest.param(_invalidate_naive_cutoff, id="invalid-naive-cutoff"),
    pytest.param(_invalidate_zero_token_limit, id="invalid-zero-token-limit"),
    pytest.param(_invalidate_bool_attempt_limit, id="invalid-bool-attempt-limit"),
    pytest.param(_invalidate_unofficial_model, id="invalid-unofficial-model"),
    pytest.param(_invalidate_malformed_baseline, id="invalid-malformed-baseline"),
]


@pytest.mark.parametrize("mutate", INVALID_MUTATIONS)
def test_create_manifest_rejects_invalid_config(valid_config, mutate):
    with pytest.raises(ValueError):
        create_manifest(mutate(valid_config), now=NOW)


# ---------------------------------------------------------------------------
# Immutability, deep-copy isolation and hash stability
# ---------------------------------------------------------------------------


def test_manifest_is_frozen(valid_config):
    manifest = create_manifest(valid_config, now=NOW)

    with pytest.raises((AttributeError, TypeError, ValueError)):
        manifest.run_id = "run-b"


def test_manifest_is_frozen_after_to_dict(valid_config):
    manifest = create_manifest(valid_config, now=NOW)
    data = manifest.to_dict()
    data["run_id"] = "run-b"

    assert manifest.to_dict()["run_id"] == "run-a"


def test_to_dict_returns_deep_copy(valid_config):
    manifest = create_manifest(valid_config, now=NOW)

    first = manifest.to_dict()
    first["run_id"] = "mutated"
    first["budget"]["token_limit"] = 1
    first["analysts"].append("broker")

    second = manifest.to_dict()
    assert second["run_id"] == "run-a"
    assert second["budget"]["token_limit"] == 60000
    assert list(second["analysts"]) == ["market", "news"]
    assert second is not manifest.to_dict()


def test_create_manifest_does_not_alias_input_config(valid_config):
    config = _base_config()
    manifest = create_manifest(config, now=NOW)

    config["run_id"] = "run-b"
    config["budget"]["token_limit"] = 1
    config["analysts"].append("broker")

    data = manifest.to_dict()
    assert data["run_id"] == "run-a"
    assert data["budget"]["token_limit"] == 60000
    assert list(data["analysts"]) == ["market", "news"]


def test_manifest_hash_stable_for_identical_config():
    first = create_manifest(_base_config(), now=NOW)
    second = create_manifest(_base_config(), now=NOW)

    assert first.manifest_hash == second.manifest_hash
    assert first.to_dict() == second.to_dict()


def test_manifest_hash_stable_for_equivalent_config_instances(valid_config):
    # Same logical config, separately constructed, with equivalent UTC time.
    other = _base_config()
    other["as_of_utc"] = "2026-11-19T05:00:00+08:00"

    first = create_manifest(valid_config, now=NOW)
    second = create_manifest(other, now=NOW)

    assert first.manifest_hash == second.manifest_hash


def test_manifest_hash_changes_with_business_config(valid_config):
    first = create_manifest(valid_config, now=NOW)

    changed = _base_config()
    changed["ticker"] = "MSFT"
    second = create_manifest(changed, now=NOW)

    assert first.manifest_hash != second.manifest_hash


def test_create_manifest_accepts_aware_now_datetime(valid_config):
    shifted_now = NOW + timedelta(minutes=5)
    manifest = create_manifest(valid_config, now=shifted_now)

    assert manifest.to_dict()["run_id"] == "run-a"
