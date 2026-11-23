# Paired evaluation CLI

Status: the implementation and offline wiring can be reviewed now. Real course-provider pilot and formal experiments remain pending the student's review of the current artifact manifest. The commands below are reproducibility instructions, not a record that paid experiments have occurred.

## Prepare and freeze

After the genuine review, freeze one actual current snapshot per ticker with `evidenceguard snapshot AAPL --out ...`, and likewise for MSFT and NVDA. The collector retains unknown/future source times for exclusion; a retrieval timestamp is not substituted for a publication timestamp. These commands read market/news data and do not call a model.

Commit the reviewed source before freezing the candidate SHA. Prepare the fixed 12-row plan with:

```bash
evidenceguard evaluate aapl.json msft.json nvda.json --candidate-sha COMMITTED_40_HEX_SHA --out plan.json
```

This command makes no model requests. It binds the three snapshots, source versions, course model, row order and plan hash. AAPL uses B/C then C/B; MSFT C/B then B/C; NVDA B/C then C/B.

## Execute after real authorization

```bash
evidenceguard evaluate-run plan.json --out-dir evaluation/formal
```

This is the paid command. It checks HEAD, tracked changes and untracked files in the source paths before starting. The output directory must be new. It uses the existing course transport and USD40 application allocation within the USD95 project ceiling; it does not reset either ledger or use a fallback provider.

Execution is serial. Every row is retained, including failed, stopped and not_run rows. Actual artifacts are saved under the experiment cell ID; their internal run IDs remain the unique IDs produced by the runner. A failed draft returned with exit code 2 is read and preserved. The batch exits 0 only when every run completed and every candidate passed its structural gate. Baseline schema failure alone does not establish semantic failure. A zero batch exit does not establish manual quality, approval or publication.

Do not rerun into the same directory, delete failures, or select only successful rows for the denominator. Pilot results belong in a separate directory and must not be relabelled as formal repeats.

## Student annotation and deterministic summary

```bash
evidenceguard annotate evaluation/formal/results.json --out evaluation/formal/annotations.json
```

The template binds the plan and each produced artifact hash. Reviewer identity, first review time, recheck time and rubric are null; facts are empty. The command never creates a student's labels.

The actual student records important facts with fact_id, text, evidence_ids, initial_label, final label and reason. Labels are supported, unsupported or unverifiable; the latter two count against support. The student fills the five binary rubric fields: relevance, completeness, traceability, uncertainty and clarity. Preserve the initial labels and perform the second review at least 24 hours later. Record genuine timestamps and provenance `student`; do not infer a second reviewer from a delayed self-review.

```bash
evidenceguard quality evaluation/formal/results.json evaluation/formal/annotations.json --out evaluation/formal/quality.json
```

The summary requires the full grid, matching artifact hashes and complete review data for completed rows. A usable report completed, contains at least one reviewed important fact, has support at least 0.95 and rubric at least 4/5; candidates also need gate passed. At least five candidates must be usable, and their usable count must be no lower than baseline. The exact 20% token boundary is compared using integer totals. Unknown or reserved usage makes savings unknown. A numerical savings target is a cost observation; COST-001 is achieved only together with the required quality outcomes.

`evidenceguard.verification semantic-evaluation` additionally checks plan/record/artifact version, dataset, group, status, budget and hash bindings. It fails when genuine formal results or annotations are missing. Offline synthetic governance fixtures prove checker behavior only; they are never copied into `evaluation/formal`.
