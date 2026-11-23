from test_quality import annotated, pair

from evidenceguard.quality import prepare_annotations, summarize_quality


def _require(summary, name):
    assert name in summary, f"summary missing explicit field {name}"
    return summary[name]


def test_cost_requirement_met_when_quality_and_saving_pass():
    report = pair()
    summary = summarize_quality(report, annotated(report))
    assert summary["passed"] is True
    assert _require(summary, "token_saving_target_met") is True
    assert _require(summary, "cost_requirement_met") is True


def test_cost_requirement_not_met_without_human_labels_even_if_saving_met():
    report = pair()
    blank = prepare_annotations(report)
    summary = summarize_quality(report, blank)
    assert summary["passed"] is False
    assert _require(summary, "token_saving_target_met") is True
    assert _require(summary, "cost_requirement_met") is False


def test_cost_requirement_not_met_when_saving_below_target():
    report = pair()
    for candidate in report["records"]:
        if candidate["arm"] == "candidate":
            candidate["run_budget"]["settled_tokens"] = 100
    summary = summarize_quality(report, annotated(report))
    assert summary["passed"] is True
    assert _require(summary, "token_saving_target_met") is False
    assert _require(summary, "cost_requirement_met") is False


def test_cost_requirement_unknown_when_budget_missing():
    report = pair()
    report["records"][0]["run_budget"] = None
    summary = summarize_quality(report, annotated(report))
    assert _require(summary, "token_saving_target_met") is None
    assert _require(summary, "cost_requirement_met") is None
