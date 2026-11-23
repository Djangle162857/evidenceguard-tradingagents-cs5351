import argparse
import json

import pytest
from test_quality import annotated, pair

from evidenceguard import batch_cli
from evidenceguard.__main__ import _build_parser
from evidenceguard.quality import prepare_annotations
from evidenceguard.runner import write_artifact


def test_parser_registration():
    parser = _build_parser()

    ns_exec = parser.parse_args(["evaluate-run", "plan.json", "--out-dir", "out"])
    assert ns_exec.func is batch_cli.do_execute

    ns_ann = parser.parse_args(["annotate", "results.json", "--out", "ann.json"])
    assert ns_ann.func is batch_cli.do_annotate
    assert ns_ann.results == "results.json"
    assert ns_ann.out == "ann.json"

    ns_qual = parser.parse_args(["quality", "results.json", "ann.json", "--out", "q.json"])
    assert ns_qual.func is batch_cli.do_quality
    assert ns_qual.results == "results.json"
    assert ns_qual.annotations == "ann.json"
    assert ns_qual.out == "q.json"


def test_empty_annotations(tmp_path):
    report = pair()
    results_path = tmp_path / "results.json"
    write_artifact(report, results_path)
    before = results_path.read_bytes()

    out_path = tmp_path / "ann.json"
    code = batch_cli.do_annotate(argparse.Namespace(results=str(results_path), out=str(out_path)))
    assert code == 0

    template = json.loads(out_path.read_text(encoding="utf-8"))
    assert template["reviewer_id"] is None
    assert template["provenance"] == "pending_student"
    assert template["plan_hash"] == report["plan_hash"]
    records = template["records"]
    assert len(records) == 12
    for rec in records:
        assert rec["facts"] == []
        assert rec["rubric"] is None
        assert rec["first_review_at"] is None
        assert rec["rechecked_at"] is None

    assert results_path.read_bytes() == before


@pytest.mark.parametrize("valid", [True, False])
def test_quality_pass_and_fail(tmp_path, valid):
    report = pair()
    ann = annotated(report) if valid else prepare_annotations(report)

    results_path = tmp_path / "results.json"
    ann_path = tmp_path / "ann.json"
    out_path = tmp_path / "q.json"
    write_artifact(report, results_path)
    write_artifact(ann, ann_path)

    code = batch_cli.do_quality(
        argparse.Namespace(results=str(results_path), annotations=str(ann_path), out=str(out_path))
    )
    assert code == (0 if valid else 2)

    quality = json.loads(out_path.read_text(encoding="utf-8"))
    summary = quality
    assert summary["passed"] is valid
    assert summary["token_totals"] == {"baseline": 600, "candidate": 450}
    if valid:
        assert summary["usable_counts"] == {"baseline": 6, "candidate": 6}
    else:
        assert summary["usable_counts"] == {"baseline": 0, "candidate": 0}
