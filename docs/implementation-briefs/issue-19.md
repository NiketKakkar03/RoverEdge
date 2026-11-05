# Issue #19 implementation brief — bounded mission-engineer tool boundary

## Observable behavior

An explicitly `recorded_fixture`-labeled investigation can read immutable recorded grounding,
inspect trace and latency evidence, prepare one validated backend or queue-policy change, execute at
most three follow-up runs, and compare runs through the existing controlled-comparison contract.
The complete mission objective, scenario, seeds, model, controller, and expected outcome remain
frozen. Every explanation contains evidence citations that resolve to real run IDs and trace-event
sequences.

The offline boundary has independent tool-call and follow-up-execution budgets and fixes provider
calls at zero. Invalid tool names or arguments, unsupported settings, exhausted budgets, missing
evidence, false improvement claims, and established-cause claims are rejected. A bounded comparison
can test a runtime change but cannot by itself establish a general cause.

## Provider status

Automated tests use only recorded fixtures and recorded grounding. The result labels the live
provider gate `not_run` and records zero provider calls. The live path is server-only at
`POST /api/investigations/live`; it requires `confirm_live_provider_call: true`, uses the Modal
Secret's `Baseten_API_KEY`, and makes exactly two bounded Baseten Chat Completion requests: one
tool-plan request and one final-explanation request. It is not exercised by automated tests.

Run the manual smoke check only after explicitly approving those two provider requests:

```zsh
uv run python scripts/smoke_mission_engineer.py \
  --endpoint 'https://YOUR_MODAL_ENDPOINT' \
  --confirm-live-provider-call
```

The command prints only source/model identifiers, request counts, run identities, comparison
validity, and the controlled finding. It stops on a non-200 response or timeout and never prints
credentials or raw provider responses.

## Acceptance — November 2, 2026

The manual Baseten smoke test completed one live bounded investigation with
`meta-models/muse-spark-open-1026`. It used two provider requests, produced one valid controlled
comparison and one follow-up run, and reported `cause_not_established`, preserving the bounded
causal limit. The full `make check` suite passed afterwards: 163 Python tests, mypy, Ruff, 22
browser tests, and the production web build. Sanitized evidence is in
`artifacts/issue-19/acceptance-2026-11-02.json`.

## Verification

- Execute an offline controlled queue-policy investigation and verify the single changed path.
- Assert objectives, model/controller identity, and criteria remain frozen.
- Reject invalid settings, extra arguments, exhausted tool/run budgets, nonexistent citations,
  unsupported improvement claims, and unsupported causal claims.
- Confirm the HTTP response preserves the recorded-fixture and not-run provider labels.
