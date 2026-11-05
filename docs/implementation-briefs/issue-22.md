# Issue #22 implementation brief — held-out evaluation protocol and readiness

## Observable acceptance criteria

The browser-readable `GET /api/evaluations/held-out` document must be derived only from checked-in
local evidence and must state that it is readiness, not a final evaluation result. It identifies the
three untouched final-family identifiers, hashes the dataset manifest, records the model/cutoff and
native numerical tolerance actually used by the checked-in evidence, and exposes every unmet or
unrun gate without conversion to a passing result.

The endpoint has no operation that generates data for, runs, relabels, or changes the held-out
families. This preserves their independence while the promised quality-threshold review is pending.
The response embeds the hash-checked proposal in
`artifacts/issue-22/proposed-held-out-protocol-v1.json` so the reviewer can approve or revise exact
criteria, sample counts, evidence policy, and stopping rules without executing the final set.

## Frozen protocol boundary

The current `risk-dataset-v2` model identity (`risk-model-v1`), selected validation cutoff
(`0.0001`), `sensor-stopping-v1` policy, dataset manifest identity, and native numerical tolerance
are recorded as inputs, not approval of their quality. V2 replaces the infeasible v1
route-direction corpus with disjoint route-directed families and retires the v1 final set. The
composed learned-risk and deterministic command-admission policy now meets the proposed validation
requirements; the protocol remains deliberately held in the `awaiting_quality_review` state because
the review itself has not occurred. Final execution requires a review that explicitly freezes
expectations, sample counts, pacing validity, stopping rules, and the final test protocol before
any v2 final family is generated.

The proposal retains the existing strict quality requirements rather than weakening them: zero
accepted unsafe commands, at most a 10% unnecessary-stop rate, at least 0.3 mean safe progress,
zero backend command disagreements, the declared numerical tolerance, and a 20 ms native pacing
overrun limit. It schedules 20 virtual scenarios for each of six FIFO/latest-pending and
uncongested/steady/burst conditions (120 runs); five native-paced runs for every final-family and
native-backend pair (60 runs); and the existing 1,000-batch × three-repetition saved-input replay.
The hash-checked proposal names the three final families, their versioned deterministic mission
scenario generator (open, narrow, and cluttered templates), pairing and ordering rules, pacing
validity rule, all gates, report/export schema, uncertainty calculation, and permitted stop rules.

## Current evidence labels and gates

- The all-four-backend numerical replay gate is `met` from the recorded M1 Pro comparison. Its
  timing provenance remains `measured_saved_input_replay`, not closed-loop timing.
- The validation-quality gate is `met`, from `artifacts/issue-8/validation-report.json`.
- The live-provider/agent gate is `met` from the separately retained Issue #19 Baseten acceptance
  record. The recorded fixture remains a distinct, zero-call boundary.
- The portable-deployment/persistence gate is `met` from the separately retained Issue #21 Modal
  acceptance record. Recorded-local evidence remains distinct from that deployment verification.
- No provider, hosted deployment, or held-out-family execution occurs in this implementation.

## Verification

`tests/test_final_evaluation.py` verifies that the API returns the manifest hash and fixed family
identities while retaining the real `met` and `not_run` gates. It also proves that a `final_test`
dataset request and a direct final-execution authorization request both fail while approval is
pending. It does not execute a final family, and no final pass claim is made.

## Validation-only improvement check — October 30, 2026

The retired v1 corpus had an oracle safe-progress ceiling of 0.218, below the proposed 0.3
requirement. The original V2 learned-only selection reached 0.401 safe progress but recorded 57
false negatives across 768 validation states. The composed `sensor-stopping-v1` selection records
zero false negatives, 58 unnecessary stops (7.552%), and 0.334 mean safe progress on the same
validation split. Details are preserved in
`artifacts/issue-22/validation-improvement-check.json`.

The final families remain untouched. Proceeding still requires explicit review and freezing of the
candidate protocol exactly as proposed; any revision requires a new review before final access.
