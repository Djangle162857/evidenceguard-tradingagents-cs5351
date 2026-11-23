"""Command-line entry point for EvidenceGuard live runs."""

import argparse
import asyncio
import contextlib
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import review, runner, snapshot as snapshot_mod
from .budget import BudgetLedger
from .contracts import create_manifest
from .transport import make_chat_model
from .upstream_runner import run_upstream

ROOT = Path(__file__).resolve().parents[2]
PROJECT_LEDGER_PATH = ROOT / ".private" / "application-budget.sqlite"
RUNS_DIR = ROOT / ".private" / "runs"
API_KEY_PATH = Path.home() / ".config" / "cs5351" / "course-api-key"

BASELINE_SHA = "9fa1196fffbcfd9de5146d2dd2869df84ab99838"
MODEL_ID = "CS5351/DeepSeek-V4-Flash"
PROMPT_VERSION = "evidenceguard-v0.2"
POLICY_VERSION = "v0.2"
POLICY_VERSIONS = ("v0.2", "v0.3")
DEFAULT_POLICY_VERSION = "v0.3"

PROJECT_TOKEN_LIMIT = 2_000_000_000
PROJECT_ATTEMPT_LIMIT = 1000
PROJECT_USD_LIMIT = "40"
PROJECT_DEADLINE = datetime(2026, 11, 25, 15, 59, 59, tzinfo=UTC)

RUN_TOKEN_LIMIT = 60000
RUN_ATTEMPT_LIMIT = 30
RUN_USD_LIMIT = "5"
RUN_DEADLINE_SECONDS = 900
INPUT_UPPER_PER_CALL = 8000
OUTPUT_UPPER_PER_CALL = 1024


def _now():
    return datetime.now(UTC)


def _parse_utc(value):
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_manifest():
    files = sorted((ROOT / "src" / "evidenceguard").glob("*.py"))
    extra = [ROOT / "tradingagents" / "graph" / "setup.py", ROOT / "pyproject.toml"]
    manifest = {}
    for path in list(files) + extra:
        if not path.is_file():
            continue
        try:
            key = str(path.relative_to(ROOT))
        except ValueError:
            key = str(path)
        manifest[key] = _sha256_file(path)
    return manifest


def _source_dirty():
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return bool(proc.stdout.strip())


def _close_llm(llm):
    if llm is None:
        return
    client = getattr(llm, "http_client", None)
    if client is not None:
        with contextlib.suppress(Exception):
            client.close()
    async_client = getattr(llm, "http_async_client", None)
    if async_client is not None:
        with contextlib.suppress(Exception):
            asyncio.run(async_client.aclose())


def _build_config(snap, candidate_sha, run_id, arm, *, policy_version="v0.2"):
    if policy_version not in POLICY_VERSIONS:
        raise ValueError(
            f"policy_version must be one of {POLICY_VERSIONS}, got {policy_version!r}"
        )
    if arm == "baseline":
        policy_version = POLICY_VERSION
        prompt_version = PROMPT_VERSION
    else:
        prompt_version = f"evidenceguard-{policy_version}"
    config = {
        "analysts": ["market", "news"],
        "as_of_utc": str(snap["as_of_utc"]),
        "baseline_sha": BASELINE_SHA,
        "budget": {
            "attempt_limit": RUN_ATTEMPT_LIMIT,
            "deadline_seconds": RUN_DEADLINE_SECONDS,
            "input_upper_per_call": INPUT_UPPER_PER_CALL,
            "output_upper_per_call": OUTPUT_UPPER_PER_CALL,
            "token_limit": RUN_TOKEN_LIMIT,
        },
        "candidate_sha": candidate_sha,
        "dataset_hash": str(snap["snapshot_hash"]),
        "model_id": MODEL_ID,
        "policy_version": policy_version,
        "prompt_version": prompt_version,
        "revision": 1,
        "run_id": run_id,
        "schema_version": "1.0",
        "ticker": str(snap["ticker"]),
    }
    if arm not in ("candidate", "baseline"):
        raise ValueError("arm must be 'candidate' or 'baseline'")
    return config


def _derive_source_status(snap):
    market = "unknown"
    news = "unknown"
    kinds = set()
    records = snap.get("records", [])
    if isinstance(records, list):
        for record in records:
            if isinstance(record, dict):
                kind = record.get("kind")
                if isinstance(kind, str):
                    kinds.add(kind)
    if "market" in kinds:
        market = "ok"
    limitations = snap.get("limitations") or []
    news_raised = False
    if isinstance(limitations, list):
        for item in limitations:
            if isinstance(item, str) and item.startswith("news retrieval raised "):
                news_raised = True
                break
    if news_raised:
        news = "error"
    elif "news" in kinds:
        news = "ok"
    else:
        news = "empty"
    return {"market": market, "news": news}


def _do_snapshot(args):
    snap = snapshot_mod.freeze_snapshot(args.ticker, clock=_now)
    snapshot_mod.validate_snapshot(snap)
    out = Path(args.out)
    runner.write_artifact(snap, out)
    print(f"ticker: {snap.get('ticker')}")
    print(f"snapshot_hash: {snap.get('snapshot_hash') or snap.get('hash')}")
    limitations = snap.get("limitations") or []
    print(f"limitations: {len(limitations)}")
    for item in limitations:
        print(f"  - {item}")
    return 0


def _do_run(args):
    snap_path = Path(args.snapshot)
    with open(snap_path, encoding="utf-8") as handle:
        snap = json.load(handle)
    snapshot_mod.validate_snapshot(snap)
    candidate_sha = str(args.candidate_sha).strip()
    if not candidate_sha:
        raise ValueError("--candidate-sha is required")
    run_id = str(uuid.uuid4())
    config = _build_config(
        snap,
        candidate_sha,
        run_id,
        args.arm,
        policy_version=getattr(args, "policy_version", "v0.2"),
    )
    create_manifest(config, now=_now())

    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_ledger_path = run_dir / "budget.sqlite"
    now = _now()
    project_ledger = BudgetLedger(
        PROJECT_LEDGER_PATH,
        token_limit=PROJECT_TOKEN_LIMIT,
        attempt_limit=PROJECT_ATTEMPT_LIMIT,
        usd_limit=PROJECT_USD_LIMIT,
        deadline=PROJECT_DEADLINE,
        clock=_now,
    )
    run_ledger = BudgetLedger(
        run_ledger_path,
        token_limit=RUN_TOKEN_LIMIT,
        attempt_limit=RUN_ATTEMPT_LIMIT,
        usd_limit=RUN_USD_LIMIT,
        deadline=now + timedelta(seconds=RUN_DEADLINE_SECONDS),
        clock=_now,
    )

    records = snapshot_mod.records_for_run(snap, run_id)
    upstream_kwargs = {}
    if args.arm == "candidate" and config["policy_version"] == "v0.3":
        upstream_kwargs["source_status"] = _derive_source_status(snap)
    llm = None
    try:
        llm = make_chat_model(run_ledger, project_ledger, API_KEY_PATH)
        artifact = run_upstream(
            config,
            records,
            llm=llm,
            run_ledger=run_ledger,
            project_ledger=project_ledger,
            now=_now(),
            arm=args.arm,
            **upstream_kwargs,
        )
    finally:
        _close_llm(llm)

    measurement = artifact.get("measurement")
    if not isinstance(measurement, dict):
        measurement = {}
        artifact["measurement"] = measurement
    manifest = _source_manifest()
    measurement["source_manifest"] = manifest
    measurement["source_content_hash"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    dirty = _source_dirty()
    if dirty is not None:
        measurement["source_dirty"] = dirty

    extra_limitations = snap.get("limitations") or []
    if extra_limitations:
        existing = artifact.get("limitations")
        if not isinstance(existing, list):
            existing = []
        merged = list(existing)
        for item in extra_limitations:
            if item not in merged:
                merged.append(item)
        artifact["limitations"] = merged

    artifact_hash = review.artifact_hash(artifact)
    artifact["artifact_hash"] = artifact_hash

    out_path = Path(args.out)
    runner.write_artifact(artifact, out_path)
    print(runner.summarize(artifact))

    execution_status = artifact.get("execution_status")
    gate_results = artifact.get("gate_results") or {}
    gate_passed = bool(gate_results.get("passed"))
    if execution_status == "completed" and (args.arm == "baseline" or gate_passed):
        return 0
    return 2


def add_commands(subparsers):
    from .batch_cli import add_commands as add_batch_commands

    add_batch_commands(subparsers)
    snap_parser = subparsers.add_parser("snapshot", help="freeze a data snapshot")
    snap_parser.add_argument("ticker")
    snap_parser.add_argument("--out", required=True)
    snap_parser.set_defaults(func=_do_snapshot)

    run_parser = subparsers.add_parser("run", help="run an upstream analysis")
    run_parser.add_argument("snapshot")
    run_parser.add_argument("--out", required=True)
    run_parser.add_argument("--candidate-sha", required=True)
    run_parser.add_argument("--arm", default="candidate", choices=["candidate", "baseline"])
    run_parser.add_argument(
        "--policy-version",
        default=DEFAULT_POLICY_VERSION,
        choices=list(POLICY_VERSIONS),
    )
    run_parser.set_defaults(func=_do_run)
    eval_parser = subparsers.add_parser(
        "evaluate", help="prepare a paired evaluation plan; no model calls"
    )
    eval_parser.add_argument("snapshots", nargs=3)
    eval_parser.add_argument("--candidate-sha", required=True)
    eval_parser.add_argument("--out", required=True)
    eval_parser.set_defaults(func=_do_evaluate)


def main(argv=None):
    parser = argparse.ArgumentParser(prog="evidenceguard")
    subparsers = parser.add_subparsers(dest="command", required=True)
    add_commands(subparsers)
    args = parser.parse_args(argv)
    return args.func(args)


def _do_evaluate(args):
    from .evaluation import prepare_plan

    snapshots = [json.loads(Path(p).read_text(encoding="utf-8")) for p in args.snapshots]
    plan = prepare_plan(snapshots, baseline_sha=BASELINE_SHA, candidate_sha=args.candidate_sha)
    runner.write_artifact(plan, args.out)
    print(plan["plan_hash"])
    print(len(plan["rows"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
