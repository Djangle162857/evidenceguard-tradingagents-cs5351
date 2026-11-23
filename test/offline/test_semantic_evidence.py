import hashlib
import json

import pytest
from test_evaluation import _plan
from test_quality import annotated

from evidenceguard.quality import prepare_annotations
from evidenceguard.verification import check_semantic


def digest(artifact):
    projection = {
        key: artifact[key]
        for key in (
            "schema_version",
            "run_id",
            "revision",
            "manifest",
            "evidence",
            "claims",
            "report",
            "rating",
            "limitations",
            "policy_version",
        )
    }
    text = json.dumps(
        projection,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def save(root, plan, report, ann, artifacts):
    formal = root / "evaluation" / "formal"
    formal.mkdir(parents=True, exist_ok=True)
    (formal / "plan.json").write_text(
        json.dumps(plan, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    (formal / "results.json").write_text(
        json.dumps(report, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    (formal / "annotations.json").write_text(
        json.dumps(ann, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    for run_id, artifact in artifacts.items():
        (formal / f"{run_id}.json").write_text(
            json.dumps(artifact, sort_keys=True, ensure_ascii=False),
            encoding="utf-8",
        )


def build(root):
    plan = _plan()
    report = {"plan_hash": plan["plan_hash"], "records": []}
    artifacts = {}
    formal = root / "evaluation" / "formal"
    formal.mkdir(parents=True, exist_ok=True)
    for row in plan["rows"]:
        manifest = {field: plan[field] for field in ("baseline_sha", "candidate_sha", "model_id")}
        manifest["ticker"] = row["ticker"]
        manifest["dataset_hash"] = row["snapshot_hash"]
        artifact = {
            "schema_version": "1.0",
            "run_id": "synthetic-" + row["run_id"],
            "revision": 1,
            "manifest": manifest,
            "evidence": [],
            "claims": [],
            "report": "SYNTHETIC ONLY",
            "rating": "Hold",
            "limitations": ["synthetic governance fixture"],
            "policy_version": "1.0",
            "execution_status": "completed",
            "validation_status": ("failed" if row["arm"] == "baseline" else "passed"),
            "gate_results": {"passed": True},
            "measurement": {
                "arm": row["arm"],
                "run_budget": {
                    "settled_tokens": 100 if row["arm"] == "baseline" else 75,
                    "reserved_tokens": 0,
                },
            },
        }
        artifact["artifact_hash"] = digest(artifact)
        artifacts[row["run_id"]] = artifact
        report["records"].append(
            {
                **row,
                "execution_status": artifact["execution_status"],
                "validation_status": artifact["validation_status"],
                "artifact_hash": artifact["artifact_hash"],
                "run_budget": artifact["measurement"]["run_budget"],
            }
        )
    ann = annotated(report)
    ann["plan_hash"] = plan["plan_hash"]
    for item in ann["records"]:
        item["artifact_hash"] = artifacts[item["run_id"]]["artifact_hash"]
    save(root, plan, report, ann, artifacts)
    return plan, report, ann, artifacts


def test_positive(tmp_path):
    build(tmp_path)
    summary = check_semantic(tmp_path)
    assert summary["passed"] is True
    assert summary["usable_counts"] == {"baseline": 6, "candidate": 6}


def test_blank_labels(tmp_path):
    plan, report, ann, artifacts = build(tmp_path)
    blank = prepare_annotations(report)
    save(tmp_path, plan, report, blank, artifacts)
    with pytest.raises(ValueError):
        check_semantic(tmp_path)
