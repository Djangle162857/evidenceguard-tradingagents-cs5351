"""Offline tests for evidenceguard.verification.

All fixtures are synthetic governance data created under pytest's tmp_path.
They are not real approvals, review sessions, AI-usage transcripts or
released evidence.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import jsonschema
import pytest
import yaml

from evidenceguard.verification import (
    check_ai_log,
    check_approval,
    check_requirements,
    check_semantic,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COURSE_MODEL = "CS5351/DeepSeek-V4-Flash"


def save(root: Path, rel: str, obj) -> str:
    """Write obj to root/rel; return the independent SHA-256 of the file bytes."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        path.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    else:
        path.write_text(str(obj), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


APPROVAL_FILES = [
    "pyproject.toml",
    "tradingagents/graph/setup.py",
    ".opencode/rules.md",
    "AGENTS.md",
    "Blueprint.md",
    "Prompt.md",
    ".github/workflows/course-gates.yml",
    "src/evidenceguard/feature.py",
]


def build_approval_fixture(root: Path) -> dict:
    """Create the eight reviewed files plus manifest and approval record."""
    shas = {rel: save(root, rel, f"synthetic content for {rel}\n") for rel in APPROVAL_FILES}
    manifest = {"files": [{"path": rel, "sha256": shas[rel]} for rel in APPROVAL_FILES]}
    manifest_sha = save(root, "docs/verification/current-review-manifest.json", manifest)
    approval = {
        "decision": "approved",
        "reviewer_id": "synthetic-fixture",
        "authorization_reference": "test_fixture",
        "reviewed_manifest_sha256": manifest_sha,
    }
    save(root, "docs/approvals/backend-review.json", approval)
    return {"shas": shas, "manifest": manifest, "manifest_sha": manifest_sha, "approval": approval}


def test_check_approval_valid_returns_none(tmp_path: Path) -> None:
    build_approval_fixture(tmp_path)
    assert check_approval(tmp_path) is None


def test_check_approval_mutated_file_raises(tmp_path: Path) -> None:
    build_approval_fixture(tmp_path)
    save(tmp_path, "src/evidenceguard/feature.py", "# mutated after review\n")
    with pytest.raises(ValueError):
        check_approval(tmp_path)


def test_check_approval_rejected_decision_raises(tmp_path: Path) -> None:
    fixture = build_approval_fixture(tmp_path)
    approval = dict(fixture["approval"], decision="rejected")
    save(tmp_path, "docs/approvals/backend-review.json", approval)
    with pytest.raises(ValueError):
        check_approval(tmp_path)


def test_check_approval_manifest_omits_file_raises(tmp_path: Path) -> None:
    fixture = build_approval_fixture(tmp_path)
    reduced = [
        e for e in fixture["manifest"]["files"] if e["path"] != "src/evidenceguard/feature.py"
    ]
    manifest_sha = save(
        tmp_path, "docs/verification/current-review-manifest.json", {"files": reduced}
    )
    save(
        tmp_path,
        "docs/approvals/backend-review.json",
        dict(fixture["approval"], reviewed_manifest_sha256=manifest_sha),
    )
    with pytest.raises(ValueError):
        check_approval(tmp_path)


def test_check_approval_wrong_reviewed_sha_raises(tmp_path: Path) -> None:
    fixture = build_approval_fixture(tmp_path)
    wrong = "0" * 64
    save(
        tmp_path,
        "docs/approvals/backend-review.json",
        dict(fixture["approval"], reviewed_manifest_sha256=wrong),
    )
    with pytest.raises(ValueError):
        check_approval(tmp_path)


def test_check_approval_missing_approval_raises(tmp_path: Path) -> None:
    build_approval_fixture(tmp_path)
    (tmp_path / "docs/approvals/backend-review.json").unlink()
    with pytest.raises((FileNotFoundError, ValueError)):
        check_approval(tmp_path)


def _copy_requirements(root: Path) -> Path:
    dest = root / "docs/req/requirements.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    for name in ("requirements.yaml", "req-schema.json"):
        src = PROJECT_ROOT / "docs/req" / name
        if src.exists():
            (dest.parent / name).write_bytes(src.read_bytes())
    return dest


def test_check_requirements_actual_copy_valid(tmp_path: Path) -> None:
    _copy_requirements(tmp_path)
    assert check_requirements(tmp_path) is None


def test_check_requirements_mutated_source_ids_raises(tmp_path: Path) -> None:
    dest = _copy_requirements(tmp_path)
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    requirements = (
        data["requirements"] if isinstance(data, dict) and "requirements" in data else data
    )
    requirements[0]["source_ids"] = ["NONEXISTENT"]
    dest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        check_requirements(tmp_path)


def _build_ai_fixture(root: Path, count: int = 5) -> None:
    save(
        root,
        "docs/ai-use-log.yaml",
        {"entries": [{"tool": "local OpenCode", "model_id": COURSE_MODEL}]},
    )
    source_sha = save(root, "source.txt", "synthetic fixture source content\n")
    save(
        root,
        "docs/architecture/source-provenance.json",
        {"files": [{"path": "source.txt", "current_sha256": source_sha}]},
    )
    rows = []
    for i in range(count):
        export_rel = f"docs/verification/exports/synthetic-{i}.json"
        transcript_rel = f"docs/verification/transcripts/synthetic-{i}.txt"
        export_sha = save(
            root, export_rel, {"info": {"id": f"synthetic-{i}", "model": {"id": COURSE_MODEL}}}
        )
        transcript_sha = save(root, transcript_rel, f"synthetic only transcript {i}\n")
        rows.append(
            {
                "session_id": f"synthetic-{i}",
                "model_id": COURSE_MODEL,
                "export": export_rel,
                "transcript": transcript_rel,
                "export_sha256": export_sha,
                "transcript_sha256": transcript_sha,
            }
        )
    save(root, "docs/ai-sessions/manifest.json", {"sessions": rows})


def test_check_ai_log_passes(tmp_path: Path) -> None:
    _build_ai_fixture(tmp_path)
    assert check_ai_log(tmp_path) is None


def test_check_ai_log_altered_transcript_raises(tmp_path: Path) -> None:
    _build_ai_fixture(tmp_path)
    save(tmp_path, "docs/verification/transcripts/synthetic-0.txt", "tampered synthetic text\n")
    with pytest.raises(ValueError):
        check_ai_log(tmp_path)


def test_check_semantic_missing_root_raises(tmp_path: Path) -> None:
    root = tmp_path / "no-semantic-evidence"
    root.mkdir()
    with pytest.raises(FileNotFoundError):
        check_semantic(root)
    assert not any(root.iterdir())
