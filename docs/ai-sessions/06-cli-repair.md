# Evaluation plan CLI repair

Session `ses_e0be7af2effeI5iGI7COCp9pYU`; local OpenCode, course model `CS5351/DeepSeek-V4-Flash`.

Earlier patch candidates had incorrect anchors or paths and were rejected. The final reviewed patch adds plan preparation only; it does not run paid evaluation.

The adjacent JSON is the authentic `opencode session export --sanitize` output, with local directory names further redacted if present. OpenCode redacts user/assistant text in that export. The assistant text below is copied from the authentic JSON event stream to make the code-generation evidence reviewable. Only local directory strings are redacted; code is not repaired in this transcript. All text parts, including incomplete or repeated candidates, are retained in order.

Instructions were relayed by Codex under the user’s startup authorization. This is not a transcript of the student personally typing in OpenCode, a human approval, or a claim that the model ran tests. Actual validation and subsequent corrections are recorded in `docs/bug-diary.md`, `docs/progress.md` and the checkpoint bundle.

Original sanitized export SHA-256: `06c3b66e5e95788687dff33986178f05f1c2be824acd4155e57722a6da68813d`.

Original event stream SHA-256: `c2929da3a283a8e0672afcd9cdc098b33109f6f63e1a107e1f9d61db024d076d`.

Preservation update (2026-11-19): the original temporary session directory was lost on system restart. This public annotated text and sanitized native export survive; original hashes below were recorded before the loss. Their presence does not mean the private originals are still available.

## Authentic assistant text

```text
```python
from pathlib import Path
import ast

live_path = Path("src/evidenceguard/live_cli.py")
live = live_path.read_text(encoding="utf-8")

anchor = "    run_parser.set_defaults(func=_do_run)"
assert live.count(anchor) == 1
addition = (
    anchor + "\n"
    "    eval_parser = subparsers.add_parser(\"evaluate\", help=\"prepare a paired evaluation plan; no model calls\")\n"
    "    eval_parser.add_argument(\"snapshots\", nargs=3)\n"
    "    eval_parser.add_argument(\"--candidate-sha\", required=True)\n"
    "    eval_parser.add_argument(\"--out\", required=True)\n"
    "    eval_parser.set_defaults(func=_do_evaluate)"
)
new_live = live.replace(anchor, addition, 1)

if not new_live.endswith("\n"):
    new_live += "\n"
new_live += (
    "\n"
    "def _do_evaluate(args):\n"
    "    from .evaluation import prepare_plan\n"
    "    snapshots = [json.loads(Path(p).read_text(encoding=\"utf-8\")) for p in args.snapshots]\n"
    "    plan = prepare_plan(snapshots, baseline_sha=BASELINE_SHA, candidate_sha=args.candidate_sha)\n"
    "    runner.write_artifact(plan, args.out)\n"
    "    print(plan[\"plan_hash\"])\n"
    "    print(len(plan[\"rows\"]))\n"
    "    return 0\n"
)

main_path = Path("src/evidenceguard/__main__.py")
main_src = main_path.read_text(encoding="utf-8")
close = main_src.index('"""', 3) + 3
new_doc = (
    '"""EvidenceGuard command-line interface: CLI replay, review, snapshots, '
    'live drafts and evaluation plans."""'
)
new_main = new_doc + main_src[close:]

old_line = '                "qualification_time": item.get("qualification_time"),'
assert new_main.count(old_line) == 1
repl = (
    '                "available_at": item.get("available_at"),\n'
    '                "published_at": item.get("published_at"),'
)
new_main = new_main.replace(old_line, repl, 1)

ast.parse(new_live)
ast.parse(new_main)

live_path.write_text(new_live, encoding="utf-8")
main_path.write_text(new_main, encoding="utf-8")
print("patched")
```
```
