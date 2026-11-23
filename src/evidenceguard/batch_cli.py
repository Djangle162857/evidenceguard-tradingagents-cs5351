"""Serial batch execution and annotation/quality CLI helpers (FR006).

This module only wires plan execution, annotation template preparation and
quality summarisation. It performs no paid model calls at import time and no
network access. Git inspection is strictly read-only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from . import live_cli
from .evaluation import execute_plan, validate_plan
from .quality import prepare_annotations, summarize_quality
from .runner import read_artifact, write_artifact

ROOT = Path(__file__).resolve().parents[2]

_SOURCE_PATHS = ("src/evidenceguard", "pyproject.toml", "tradingagents/graph/setup.py")


def _git(*argv: str) -> str:
    result = subprocess.run(
        ["git", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"git {' '.join(argv)} failed: {result.stderr.strip()}")
    return result.stdout


def _check_version(plan: dict) -> None:
    """Assert frozen committed sources match the plan's candidate SHA."""
    head = _git("rev-parse", "HEAD").strip()
    expected = plan.get("candidate_sha")
    if not isinstance(expected, str) or head != expected:
        raise ValueError(f"candidate_sha mismatch: HEAD={head!r} plan={expected!r}")
    diff = subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", *_SOURCE_PATHS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if diff.returncode != 0:
        raise ValueError("uncommitted changes in frozen source paths")
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", *_SOURCE_PATHS)
    if untracked.strip():
        raise ValueError(f"untracked files in frozen source paths: {untracked.strip()}")


def _load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def do_execute(args: argparse.Namespace) -> int:
    plan = _load(args.plan)
    validate_plan(plan)
    _check_version(plan)

    out_dir = Path(args.out_dir)
    private = ROOT / ".private"
    private.mkdir(parents=True, exist_ok=True)

    candidate_sha = plan["candidate_sha"]

    with tempfile.TemporaryDirectory(dir=private) as tmp_name:
        tmp = Path(tmp_name)

        def run_one(row, snapshot):
            input_path = tmp / f"{row['run_id']}-input.json"
            artifact_path = tmp / f"{row['run_id']}-artifact.json"
            write_artifact(snapshot, input_path)
            exit_code = live_cli._do_run(
                argparse.Namespace(
                    snapshot=str(input_path),
                    candidate_sha=candidate_sha,
                    out=str(artifact_path),
                    arm=row["arm"],
                    policy_version="v0.3",
                )
            )
            actual = read_artifact(artifact_path)
            if exit_code not in (0, 2):
                raise RuntimeError(f"unexpected _do_run exit code {exit_code}")
            return actual

        result = execute_plan(plan, run_one=run_one, output_dir=out_dir)

    records = result["records"]
    print(f"plan_hash: {result['plan_hash']}")
    print(f"rows: {len(records)}")

    ok = True
    for record in records:
        if record.get("execution_status") != "completed":
            ok = False
        if record.get("arm") == "candidate" and record.get("validation_status") != "passed":
            ok = False
    return 0 if ok else 2


def do_annotate(args: argparse.Namespace) -> int:
    report = _load(args.results)
    template = prepare_annotations(report)
    out = Path(args.out)
    write_artifact(template, out)
    print(str(out))
    return 0


def do_quality(args: argparse.Namespace) -> int:
    report = _load(args.results)
    annotations = _load(args.annotations)
    summary = summarize_quality(report, annotations)
    out = Path(args.out)
    write_artifact(summary, out)
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary.get("passed") is True else 2


def add_commands(subparsers) -> None:
    run = subparsers.add_parser(
        "evaluate-run",
        help="execute the plan serially (explicit PAID model calls)",
    )
    run.add_argument("plan")
    run.add_argument("--out-dir", required=True)
    run.set_defaults(func=do_execute)

    annotate = subparsers.add_parser(
        "annotate",
        help="write an empty student annotation template",
    )
    annotate.add_argument("results")
    annotate.add_argument("--out", required=True)
    annotate.set_defaults(func=do_annotate)

    quality = subparsers.add_parser(
        "quality",
        help="summarise quality against annotations",
    )
    quality.add_argument("results")
    quality.add_argument("annotations")
    quality.add_argument("--out", required=True)
    quality.set_defaults(func=do_quality)
