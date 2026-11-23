"""EvidenceGuard command-line interface: CLI replay, review, snapshots, live drafts and evaluation plans."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evidenceguard import review, runner
from evidenceguard.live_cli import add_commands


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, sort_keys=True, default=str))


def _summarize_report(artifact: Any) -> str:
    return runner.summarize(artifact)


def _cmd_replay(args: argparse.Namespace) -> int:
    fixture = _load_json(args.fixture)
    now_raw = fixture["now"]
    if isinstance(now_raw, str):
        now = datetime.fromisoformat(now_raw.replace("Z", "+00:00"))
    else:
        now = now_raw
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("fixture 'now' must be a timezone-aware ISO timestamp")
    artifact = runner.replay(
        config=fixture["config"],
        records=fixture["records"],
        turns=fixture["turns"],
        final=fixture["final"],
        now=now,
    )
    runner.write_artifact(artifact, args.out)
    summary = _summarize_report(artifact)
    print(summary)
    return 0 if artifact["gate_results"]["passed"] else 2


def _cmd_inspect(args: argparse.Namespace) -> int:
    artifact = runner.read_artifact(args.artifact)
    summary = _summarize_report(artifact)
    print("Summary:")
    print(summary)
    print("Evidence:")
    for item in artifact.get("evidence", []):
        _print_json(
            {
                "source_uri": item.get("source_uri"),
                "content_hash": item.get("content_hash"),
                "available_at": item.get("available_at"),
                "published_at": item.get("published_at"),
                "eligibility": item.get("eligibility"),
            }
        )
    print("Claims:")
    for claim in artifact.get("claims", []):
        _print_json({"claim_id": claim.get("claim_id")})
    print("Report:")
    print(artifact["report"])
    return 0


def _cmd_review_show(args: argparse.Namespace) -> int:
    artifact = runner.read_artifact(args.artifact)
    summary = _summarize_report(artifact)
    print(summary)
    print("Limitations:")
    _print_json(artifact.get("limitations", []))
    print("Report:")
    print(artifact["report"])
    print("Artifact hash:")
    _print_json(review.artifact_hash(artifact))
    return 0


def _cmd_review_decide(args: argparse.Namespace) -> int:
    artifact = runner.read_artifact(args.artifact)
    actual = review.artifact_hash(artifact)
    if actual != args.expected_hash:
        raise ValueError("expected hash does not match artifact hash; refusing to record review")
    store = review.ReviewStore(args.store)
    event = store.record(
        artifact,
        reviewer_id=args.reviewer,
        decision=args.decision,
        reason=args.reason,
        authorization_source="human_cli",
        now=datetime.now(UTC),
    )
    _print_json(event)
    return 0


def _cmd_review_publish(args: argparse.Namespace) -> int:
    artifact = runner.read_artifact(args.artifact)
    store = review.ReviewStore(args.store)
    released = review.publish(artifact, store=store, now=datetime.now(UTC))
    runner.write_artifact(released, args.out)
    _print_json({"artifact_hash": review.artifact_hash(released), "out": args.out})
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evidenceguard")
    sub = parser.add_subparsers(dest="command", required=True)
    add_commands(sub)

    p = sub.add_parser("replay", help="offline fixture replay")
    p.add_argument("fixture")
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_replay)

    p = sub.add_parser("inspect", help="inspect artifact")
    p.add_argument("artifact")
    p.set_defaults(func=_cmd_inspect)

    review_p = sub.add_parser("review", help="human review actions")
    review_sub = review_p.add_subparsers(dest="review_command", required=True)

    p = review_sub.add_parser("show", help="show review report")
    p.add_argument("artifact")
    p.set_defaults(func=_cmd_review_show)

    for decision in ("approve", "reject"):
        p = review_sub.add_parser(decision, help=f"{decision} artifact")
        p.add_argument("artifact")
        p.add_argument("--reviewer", required=True)
        p.add_argument("--reason", required=True)
        p.add_argument("--expected-hash", required=True)
        p.add_argument("--store", required=True)
        p.set_defaults(func=_cmd_review_decide, decision=decision)

    p = review_sub.add_parser("publish", help="publish approved artifact")
    p.add_argument("artifact")
    p.add_argument("--store", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=_cmd_review_publish)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
