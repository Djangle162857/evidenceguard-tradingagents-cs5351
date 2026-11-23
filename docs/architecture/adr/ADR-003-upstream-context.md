# ADR-003: Optional upstream boundary and bounded candidate context

Date: 2026-11-19. Status: implemented for offline verification; concrete human review pending.

The candidate uses the pinned TradingAgents graph, including both analysts, bull/bear research, Research Manager, Trader, three risk roles and Portfolio Manager. GraphSetup adds an optional boundary argument; absent that argument, the upstream factories and graph routing are preserved. No parallel replacement graph is used.

A shared IntegrationContext supplies a qualified frozen evidence index and program-assigned claim IDs. Five debate roles return claim-turn JSON in their existing model call; there is no separate extraction model call. Managers retain upstream structured schemas and their one plain-text fallback. The HTTP transport handles actual SDK requests beneath both paths.

The upstream market indicator catalog and repeated histories exceed the proposed 8,000-byte-plus-framing input estimate. Candidate context therefore includes at most four evidence excerpts of 160 characters and ten claim excerpts of 100 characters; complete IDs remain present. Ordinary upstream messages are compacted within a 1,200-byte allowance; tool-call messages and their results preserve their protocol fields. The transport still checks the actual serialized request and refuses oversized calls. The byte allowance is a conservative tokenizer assumption, not a proof of tokenization; actual usage is checked at settlement.

This deliberately changes prompt content. It may discard useful details and is a confound in any quality/token comparison. Frozen tool outputs expose snapshot evidence and explicitly report missing indicators. The baseline keeps original upstream prompts while using the same frozen data and HTTP budgets. Baseline failures under the common limits must be retained; they cannot alone substantiate a claim of better reasoning or market performance.

Offline SDK tests use synthetic evidence and MockTransport, exercise the actual graph and real SDK serialization, and do not establish real-provider structured-output compatibility. Live pilot and paired evaluation remain pending checkpoint 2. Structural citation checks cannot prove semantic support; human annotation remains required.
