import hashlib
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import yaml


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_file(path, expected):
    if not path.is_file():
        raise ValueError(f"missing file: {path}")
    actual = sha(path)
    if actual != expected:
        raise ValueError(f"hash mismatch for {path}: {actual} != {expected}")


def check_requirements(root):
    req_dir = root / "docs" / "req"
    with open(req_dir / "requirements.yaml", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    schema = load_json(req_dir / "req-schema.json")
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(data)

    requirements = data["requirements"]
    sources = data["sources"]
    datasets = data["datasets"]

    source_ids = [entry["id"] for entry in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source ids")
    dataset_protocols = {entry["protocol_id"] for entry in datasets}
    known_sources = set(source_ids)
    known_requirements = set()

    for requirement in requirements:
        rid = requirement["id"]
        if rid in known_requirements:
            raise ValueError(f"duplicate requirement id: {rid}")
        known_requirements.add(rid)

    for requirement in requirements:
        rid = requirement["id"]
        for source_id in requirement["source_ids"]:
            if source_id not in known_sources:
                raise ValueError(f"{rid} references unknown source: {source_id}")
        for related in requirement["related_ids"]:
            if related not in known_requirements:
                raise ValueError(f"{rid} references unknown requirement: {related}")
        protocol = requirement["fit_criterion"]["protocol_id"]
        if protocol not in dataset_protocols:
            raise ValueError(f"{rid} references unknown protocol: {protocol}")

    return None


def check_approval(root):
    manifest_path = root / "docs" / "verification" / "current-review-manifest.json"
    approval_path = root / "docs" / "approvals" / "backend-review.json"

    if not manifest_path.is_file():
        raise ValueError(f"missing manifest: {manifest_path}")
    if not approval_path.is_file():
        raise ValueError(f"missing approval record: {approval_path}")

    manifest = load_json(manifest_path)
    approval = load_json(approval_path)

    if approval.get("decision") != "approved":
        raise ValueError("approval decision is not approved")
    for field in ("reviewer_id", "authorization_reference"):
        if not approval.get(field):
            raise ValueError(f"approval field empty: {field}")

    manifest_sha = sha(manifest_path)
    if approval.get("reviewed_manifest_sha256") != manifest_sha:
        raise ValueError("approval does not bind current manifest")

    entries = manifest.get("files", [])
    if not entries:
        raise ValueError("manifest has no files")

    expected_files = set()
    source_root = root / "src" / "evidenceguard"
    if source_root.is_dir():
        for candidate in source_root.rglob("*"):
            if not candidate.is_file():
                continue
            if "__pycache__" in candidate.parts:
                continue
            if candidate.suffix in (".py", ".html", ".css", ".js", ".json"):
                expected_files.add(candidate.relative_to(root).as_posix())
    offline_tests = root / "test" / "offline"
    if offline_tests.is_dir():
        for candidate in offline_tests.rglob("*.py"):
            if not candidate.is_file():
                continue
            if "__pycache__" in candidate.parts:
                continue
            expected_files.add(candidate.relative_to(root).as_posix())
    for literal in (
        "pyproject.toml",
        "tradingagents/graph/setup.py",
        ".opencode/rules.md",
        "AGENTS.md",
        "Blueprint.md",
        "Prompt.md",
        ".github/workflows/course-gates.yml",
    ):
        expected_files.add(literal)
    covered = {entry["path"] for entry in entries}
    missing = sorted(expected_files - covered)
    if missing:
        raise ValueError("approval manifest missing required files: " + ", ".join(missing))
    root_resolved = root.resolve()
    for entry in entries:
        path = (root / entry["path"]).resolve()
        if root_resolved not in path.parents:
            raise ValueError(f"manifest path escapes root: {entry['path']}")
        check_file(path, entry["sha256"])

    return None


def check_ai_log(root):
    log_path = root / "docs" / "ai-use-log.yaml"
    with open(log_path, encoding="utf-8") as handle:
        log = yaml.safe_load(handle)

    model_id = "CS5351/DeepSeek-V4-Flash"
    entries = log.get("entries", [])
    matches = [
        entry
        for entry in entries
        if entry.get("tool") == "local OpenCode" and entry.get("model_id") == model_id
    ]
    if not matches:
        raise ValueError("no matching local OpenCode entry")

    provenance_path = root / "docs" / "architecture" / "source-provenance.json"
    provenance = load_json(provenance_path)
    provenance_files = provenance.get("files", [])
    if not provenance_files:
        raise ValueError("provenance has no files")
    for entry in provenance_files:
        check_file(root / entry["path"], entry["current_sha256"])

    sessions_path = root / "docs" / "ai-sessions" / "manifest.json"
    sessions = load_json(sessions_path).get("sessions", [])
    if len(sessions) < 5:
        raise ValueError("fewer than five sessions")
    seen = set()
    for session in sessions:
        sid = session["session_id"]
        if sid in seen:
            raise ValueError(f"duplicate session id: {sid}")
        seen.add(sid)
        if session.get("model_id") != model_id:
            raise ValueError(f"session {sid} model mismatch")
        for base in ("export", "transcript"):
            path_field = session.get(base)
            hash_field = session.get(f"{base}_sha256")
            if not path_field or not hash_field:
                raise ValueError(f"session {sid} missing {base} data")
            check_file(root / path_field, hash_field)

        export = load_json(root / session["export"])
        info = export.get("info", {})
        if info.get("id") != sid:
            raise ValueError(f"export id mismatch for {sid}")
        if info.get("model", {}).get("id") != model_id:
            raise ValueError(f"export model mismatch for {sid}")

    return None


def check_semantic(root):
    from .evaluation import validate_plan
    from .quality import summarize_quality
    from .review import artifact_hash

    formal = root / "evaluation" / "formal"
    plan = load_json(formal / "plan.json")
    report = load_json(formal / "results.json")
    annotations = load_json(formal / "annotations.json")

    validate_plan(plan)

    if report.get("plan_hash") != plan.get("plan_hash"):
        raise ValueError("results plan_hash does not match plan")

    plan_rows = plan["rows"]
    plan_by_id = {row["run_id"]: row for row in plan_rows}

    report_rows = report["records"]
    for record in report_rows:
        run_id = record["run_id"]
        if run_id not in plan_by_id:
            raise ValueError(f"unknown run in report: {run_id}")
        plan_row = plan_by_id[run_id]
        for field in ("ticker", "repeat", "arm", "snapshot_hash"):
            if record.get(field) != plan_row.get(field):
                raise ValueError(f"run {run_id} field mismatch: {field}")

        artifact_path = formal / f"{run_id}.json"
        expected = record.get("artifact_hash")
        if expected is None:
            if record.get("execution_status") == "completed":
                raise ValueError(f"run {run_id} completed without artifact hash")
            continue

        if not artifact_path.is_file():
            raise ValueError(f"missing artifact for run {run_id}")
        artifact = load_json(artifact_path)
        actual = artifact_hash(artifact)
        if actual != expected:
            raise ValueError(f"run {run_id} artifact hash mismatch")
        if artifact.get("artifact_hash") != actual:
            raise ValueError(f"run {run_id} artifact hash mismatch")
        for field in ("execution_status", "validation_status"):
            if artifact.get(field) != record.get(field):
                raise ValueError(f"run {run_id} {field} mismatch")
        if artifact.get("manifest", {}).get("dataset_hash") != record.get("snapshot_hash"):
            raise ValueError(f"run {run_id} dataset hash mismatch")
        manifest = artifact.get("manifest", {})
        for field in ("baseline_sha", "candidate_sha", "model_id"):
            if manifest.get(field) != plan.get(field):
                raise ValueError(f"run {run_id} {field} mismatch")
        if manifest.get("ticker") != record.get("ticker"):
            raise ValueError(f"run {run_id} ticker mismatch")
        measurement = artifact.get("measurement", {})
        if measurement.get("arm") != record.get("arm"):
            raise ValueError(f"run {run_id} arm mismatch")
        if measurement.get("run_budget") != record.get("run_budget"):
            raise ValueError(f"run {run_id} run_budget mismatch")
        if (
            record.get("arm") == "candidate"
            and record.get("validation_status") == "passed"
            and artifact.get("gate_results", {}).get("passed") is not True
        ):
            raise ValueError(f"run {run_id} gate_results not passed")

    summary = summarize_quality(report, annotations)
    if summary.get("passed") is not True:
        raise ValueError("quality summary did not pass")

    return summary


def run_command(root, command):
    subprocess.run(command, cwd=root, check=True)


def check_static_analysis(root):
    run_command(
        root,
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src/evidenceguard",
            "test/offline",
            "tradingagents/graph/setup.py",
        ],
    )


def check_regression(root):
    run_command(root, [sys.executable, "-m", "pytest", "-q"])


def check_test_approval(root):
    return check_approval(root)


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if not args:
        print("missing check name", file=sys.stderr)
        return 1
    name = args[0]
    root = Path(__file__).resolve().parents[2]
    checks = {
        "test-approval": check_test_approval,
        "static-analysis": check_static_analysis,
        "requirements-schema": check_requirements,
        "semantic-evaluation": check_semantic,
        "regression": check_regression,
        "ai-use-log": check_ai_log,
    }
    handler = checks.get(name)
    if handler is None:
        print(f"{name}: unknown check", file=sys.stderr)
        return 1
    try:
        handler(root)
    except Exception as error:  # noqa: BLE001
        print(f"{name}: {error}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
