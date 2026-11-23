# Course CI evidence guide

The generated workflow has six matrix jobs with fixed check names. It needs no API key and must never invoke live models. Run a local check with:

```bash
.venv/bin/python -m evidenceguard.verification requirements-schema
.venv/bin/python -m evidenceguard.verification static-analysis
.venv/bin/python -m evidenceguard.verification regression
.venv/bin/python -m evidenceguard.verification ai-use-log
.venv/bin/python -m evidenceguard.verification test-approval
.venv/bin/python -m evidenceguard.verification semantic-evaluation
```

The last two require actual evidence that does not yet exist. A nonzero exit for missing approval or formal experiments is an expected block, not a completed course acceptance test or an implementation failure to hide.

## Approval binding

`docs/verification/current-review-manifest.json` inventories current application/test/governance files. A real review record, when actually authorized, belongs at `docs/approvals/backend-review.json` and contains decision, reviewer_id, authorization_reference and reviewed_manifest_sha256. The latter hashes the exact manifest file bytes. Every listed source hash and the required coverage are checked. No approved example record is installed by the agent.

This checks a recorded authorization, not cryptographic reviewer identity. Preserve the genuine user/GitHub action referenced by the record. A review after implementation cannot establish missing preimplementation timing. The delegated creation of rules.md remains disclosed separately.

## Formal semantic evidence

The semantic check reads `evaluation/formal/plan.json`, `results.json`, `annotations.json` and each produced artifact. Rows bind ticker, repeat, arm and snapshot hash to the frozen plan. Produced artifact hashes, statuses and dataset hashes must match the report. Quality thresholds and the delayed student recheck are then verified deterministically. Missing results or labels must not be replaced with synthetic fixtures from the offline tests.

## Evidence still to capture on GitHub

After the sanitized repository is published, retain real run URLs, commit SHAs and logs for each check. Exercise an actual failure and repair without changing the test oracle. Configure all six named checks as required on the protected branch, then verify that an incomplete PR cannot merge. Do not claim enforcement from a screenshot of local YAML or from an administrator's unchecked bypass capability.

Public upload excludes keys, account finance metadata, course originals, private raw sessions, personal identifiers, environments, caches and submission archives. Session exports and published experiment data require a separate sanitization review. This guide does not record any upload, protected-branch setting, approval or formal quality result.
