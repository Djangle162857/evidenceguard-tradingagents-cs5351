# Debt register

Current update 2026-11-20: v0.3 remains unaccepted. See `docs/verification/v0.3/final-review.md` for bound evidence and blockers; older rows below describe their original checkpoints.

| ID | Date | Observation and impact | Treatment / status |
|---|---|---|---|
| DEBT-V03-001 | 2026-11-20 | Structured PM rendering places the first heading inline; candidate gate and UI parser miss it | Open, acceptance blocker BUG-V03-001. Actual upstream-render probe fails. Fix through compliant OpenCode generation and add independent regression; keep gate behavior intact pending repair. |
| DEBT-V03-002 | 2026-11-20 | Independent brief, version wiring/call-count and workbench automated tests absent | Open. Reject incorrect/truncated request-200 tests; 1687 passing tests do not cover all new requirements. Manual synthetic browser QA is supplementary. |
| DEBT-V03-003 | 2026-11-20 | Shared development request limit reached, 200/200 | Open generation blocker. No reset, provider fallback or automatic limit increase. Explicit new request-count authorization required before another model request. |
| DEBT-V03-004 | 2026-11-20 | Repeated missing-brief/duplicate messages and narrow phone navigation | Open minor UX debt. Real desktop/phone screenshots available; no page-wide horizontal overflow observed. |
| DEBT-V03-005 | 2026-11-20 | Source-status helper infers missing news from records and known limitation prefix | Bounded to existing frozen snapshots. No generic source-health proof; custom inputs without failure markers cannot distinguish all failures. Add independent wiring tests before acceptance. |

DEBT-UI-002 update: phone QA was completed in this round at an actual 390×844 CSS viewport. Net JPEG content is 375×812. This closes the old viewport-application blocker; it does not establish a full accessibility audit. DEBT-UI-001 remains open: no real forecast-series exporter or HTTP business API was implemented.

Packaging QA also found trailing whitespace at generated `web/index.html:145` and two inherited README lines. The tracked Git diff check and cumulative patch consistency check pass; the stricter whole-text scan is recorded with findings. No source formatting was performed outside OpenCode at the request limit.

| ID | Date | Observation and impact | Treatment / status |
|---|---|---|---|
| DEBT-001 | 2026-11-19 | Required course tool initially unverified | Closed for local generation: real OpenCode + exact CityU model sessions and request-level cost accounting retained. Live application structured-output compatibility still pending pilot. |
| DEBT-002 | 2026-11-19 | Formal evaluation, GitHub checks/protection and delivery incomplete | Open; no planned number or local test is reported as a formal experiment or a GitHub run. |
| DEBT-003 | 2026-11-19 | Single student's semantic annotation may be biased | Accepted with hidden-arm protocol, delayed recheck and disclosure; actual labels/recheck pending. |
| DEBT-004 | 2026-11-19 | Generated source repeatedly invented public APIs and test fixtures | Corrected through small OpenCode tasks, source attachment and independent checks. Keep failed generations; review current code hashes and regressions before pilot. |
| DEBT-005 | 2026-11-19 | Candidate compaction discards ordinary upstream prompt detail | Explicitly accepted for proposed bounded run design, ADR-003; quality impact unmeasured and a confound, not a proven improvement. |
| DEBT-006 | 2026-11-19 | Source market-update time does not establish vendor publication latency | Use actual supplied source timestamp; retain unknown/future times as excluded. Current download cannot support historical point-in-time performance claims. |
| DEBT-007 | 2026-11-19 | Human-only rules and exact-hash human approvals absent | Pending student action; agents cannot supply these records or backdate them. |

Update 2026-11-19: DEBT-007 is partially resolved by explicit delegated creation of `.opencode/rules.md`; actual Codex authorship is recorded. Independent Human-only authorship and current exact-hash review remain unestablished. Do not interpret the old row as the file still being absent.

| ID | Date | Observation and impact | Treatment / status |
|---|---|---|---|
| DEBT-008 | 2026-11-19 | Restart removed early transient raw sessions | Disclosed; six authentic native exports and source hashes survived, exact harness restored from authentic output, subsequent sessions archived persistently. Lost originals cannot be recreated as raw evidence. |
| DEBT-009 | 2026-11-19 | Governance checks validate declared identity/timestamps, not human identity or semantic truth | Genuine source action and student recheck remain required; synthetic fixture passes are not actual approvals or labels. |
| DEBT-010 | 2026-11-19 | Full catalogue execution mapping and all real GitHub failure/repair cycles incomplete | Preserve candidate tests and current evidence; do not infer protocol acceptance from aggregate test count. |


| ID | Date | Observation and impact | Treatment / status |
|---|---|---|---|
| DEBT-UI-001 | 2026-11-19 | Backend has no forecast price-array exporter | Open. UI imports/refreshes an independent contract; bundled curves visibly synthetic. |
| DEBT-UI-002 | 2026-11-19 | Browser viewport override did not change actual dimensions | Open mobile QA. Verified 1280px/1042px desktop; reset override, no fabricated phone screenshot. |
| DEBT-UI-003 | 2026-11-19 | Iterative CSS retains overridden rules; Canvas has no full accessible table | Reversible design debt; consider cleanup/table after visual direction is accepted. |
