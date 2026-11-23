import re
from datetime import UTC, datetime, timedelta


def validate_research_brief(report, claims, *, as_of_utc):
    violations = []

    if isinstance(as_of_utc, datetime):
        parsed = as_of_utc
    elif isinstance(as_of_utc, str):
        raw = as_of_utc.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return ["as_of_invalid"]
    else:
        return ["as_of_invalid"]
    if parsed.tzinfo is None:
        return ["as_of_invalid"]
    try:
        as_of_date = parsed.astimezone(UTC).date()
    except Exception:
        return ["as_of_invalid"]

    if not isinstance(report, str):
        return ["report_not_text"]

    known_ids = set()
    if isinstance(claims, list):
        for claim in claims:
            if isinstance(claim, dict):
                cid = claim.get("claim_id")
                if isinstance(cid, str) and re.fullmatch(r"cl-[0-9a-f]{64}", cid):
                    known_ids.add(cid)

    cited = re.findall(r"cl-[0-9a-f]{64}", report)
    for cid in cited:
        if cid not in known_ids:
            violations.append("unknown_claim_reference")

    match = re.search(
        r"\*\*Executive Summary\*\*:\s*(.*?)\s*\*\*Investment Thesis\*\*:",
        report,
        re.DOTALL,
    )
    if match is None:
        match = re.search(
            r"##\s*Executive Summary\s*\n(.*?)\n##\s*Investment Thesis",
            report,
            re.DOTALL,
        )
    if match is None:
        violations.append("executive_summary_missing")
        return violations

    summary_text = match.group(1).strip()
    summary_body = re.sub(r"\[cl-[0-9a-f]{64}\]", "", summary_text).strip()
    if not summary_body or not re.search(r"[\u4e00-\u9fff]", summary_body):
        violations.append("executive_summary_invalid")
    elif not re.fullmatch(r"[^。！？]*[。！？]", summary_body):
        violations.append("executive_summary_sentence")

    headings = ["利好因素", "风险因素", "关键分歧", "未来一周观察", "数据缺口"]
    heading_lines = re.findall(r"^### (.*)$", report, re.MULTILINE)
    if heading_lines != headings:
        violations.append("section_headings_invalid")

    bodies = {}
    ordered = True
    for _index, heading in enumerate(headings):
        pattern = r"^### " + re.escape(heading) + r"\s*$"
        found = re.search(pattern, report, re.MULTILINE)
        if found is None:
            ordered = False
            continue
        start = found.end()
        remainder = report[start:]
        stops = []
        for other in headings:
            if other == heading:
                continue
            other_found = re.search(
                r"^### " + re.escape(other) + r"\s*$", remainder, re.MULTILINE
            )
            if other_found is not None:
                stops.append(other_found.start())
        if heading == headings[-1]:
            for marker in [r"\*\*Price Target\*\*", r"\*\*Time Horizon\*\*"]:
                meta = re.search(marker, remainder)
                if meta is not None:
                    stops.append(meta.start())
        end = min(stops) if stops else len(remainder)
        bodies[heading] = remainder[:end].strip()

    if not ordered:
        return violations

    insufficient = ["信息不足", "信息不足。", "信息不足！", "信息不足？"]
    for heading in headings[:4]:
        body = bodies.get(heading, "")
        if not body:
            violations.append("section_empty")
            continue
        stripped = re.sub(r"\[cl-[0-9a-f]{64}\]", "", body).strip()
        if stripped in insufficient:
            continue
        refs = re.findall(r"\[(cl-[0-9a-f]{64})\]", body)
        if not refs:
            violations.append("section_requires_citation")
        for ref in refs:
            if ref not in known_ids:
                violations.append("unknown_claim_reference")

    if not bodies.get(headings[-1], ""):
        violations.append("section_empty")

    future_body = bodies.get(headings[3], "")
    future_stripped = re.sub(r"\[cl-[0-9a-f]{64}\]", "", future_body).strip()
    if future_stripped not in insufficient:
        for token in ["推断", "上行", "下行", "观察"]:
            if token not in future_body:
                violations.append("future_observation_incomplete")
        day_one = (as_of_date + timedelta(days=1)).isoformat()
        day_seven = (as_of_date + timedelta(days=7)).isoformat()
        if day_one not in future_body:
            violations.append("future_observation_dates")
        if day_seven not in future_body:
            violations.append("future_observation_dates")

    for line in report.splitlines():
        if re.match(r"\s*\-?\s*\*?\*?Price Target", line):
            value = line.split(":", 1)[-1].strip() if ":" in line else ""
            value = value.replace("*", "").strip()
            if value == "":
                continue
            lowered = value.lower()
            if lowered in ["null", "none", "not provided", "未提供", "信息不足"]:
                continue
            violations.append("price_target_invalid")

    return violations
