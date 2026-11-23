import pytest
from test_semantic_evidence import build, digest, save

from evidenceguard.verification import check_semantic


def _case_annotation_hash(report, ann, artifacts, key):
    for rec in ann["records"]:
        if rec["run_id"] == key:
            rec["artifact_hash"] = "0" * 64
            break


def _case_plan_hash(report, ann, artifacts, key):
    report["plan_hash"] = "0" * 64


def _case_ticker(report, ann, artifacts, key):
    report["records"][1]["ticker"] = "MSFT"


def _case_budget(report, ann, artifacts, key):
    report["records"][1]["run_budget"] = {
        "settled_tokens": 999,
        "reserved_tokens": 0,
    }


def _case_text(report, ann, artifacts, key):
    artifacts[key]["report"] = "altered synthetic text"


def _case_version(report, ann, artifacts, key):
    a = artifacts[key]
    a["manifest"]["candidate_sha"] = "f" * 40
    a["artifact_hash"] = digest(a)
    report["records"][1]["artifact_hash"] = a["artifact_hash"]
    for rec in ann["records"]:
        if rec["run_id"] == key:
            rec["artifact_hash"] = a["artifact_hash"]
            break


def _case_arm(report, ann, artifacts, key):
    artifacts[key]["measurement"]["arm"] = "baseline"


def _case_gate(report, ann, artifacts, key):
    artifacts[key]["gate_results"]["passed"] = False


_CASES = {
    "annotation_hash": _case_annotation_hash,
    "plan_hash": _case_plan_hash,
    "ticker": _case_ticker,
    "budget": _case_budget,
    "text": _case_text,
    "version": _case_version,
    "arm": _case_arm,
    "gate": _case_gate,
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_semantic_tamper_detected(tmp_path, case):
    plan, report, ann, artifacts = build(tmp_path)
    row = report["records"][1]
    key = row["run_id"]
    _CASES[case](report, ann, artifacts, key)
    save(tmp_path, plan, report, ann, artifacts)
    with pytest.raises(ValueError):
        check_semantic(tmp_path)


def test_semantic_missing_artifact(tmp_path):
    plan, report, ann, artifacts = build(tmp_path)
    save(tmp_path, plan, report, ann, artifacts)
    key = report["records"][1]["run_id"]
    (tmp_path / "evaluation" / "formal" / (f"{key}.json")).unlink()
    with pytest.raises(ValueError):
        check_semantic(tmp_path)
