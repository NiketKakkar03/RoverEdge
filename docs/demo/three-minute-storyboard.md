# RoverEdge three-minute evidence storyboard

This is a handoff script for recorded local evidence, not a held-out evaluation result. Separate
Issue #19 live-provider and Issue #21 deployment acceptance records exist; do not substitute their
evidence, make new live calls, or edit criteria while recording.

| Time | Screen / asset | Spoken evidence | Required label |
| --- | --- | --- | --- |
| 0:00–0:25 | Browser replay of `preset-open-v2` | “RoverEdge asks when execution delay changes an inspection-and-return mission. The rover approaches the storage container, captures an observation, then returns to the dock.” | Deterministic local run; mission outcome and test verdict shown separately. |
| 0:25–0:55 | Queue panel: steady modeled congestion, FIFO then latest-pending | “This is declared modeled congestion, not a hardware measurement. The queue policy is the only controlled change.” | `modeled`; controlled comparison; fixed scenario/model/controller/criteria. |
| 0:55–1:20 | Recorded investigation audit | “The mission engineer reads immutable recorded trace evidence, changes only queue policy, and performs a bounded rerun. Its result may be unchanged or worse; it cannot establish a general cause.” | `recorded_fixture`; provider gate `not_run`; zero provider calls. |
| 1:20–1:50 | `artifacts/issue-23/queue-policy-comparison.zip` and its JSON sidecar | “Show the actual paired mission outcome, test verdict, overflow/replacement counts, and declared factor. Both recorded runs time out as expected, so this is explicitly unchanged mission behavior—not an improvement.” | Exported local comparison; `modeled` timing provenance. |
| 1:50–2:20 | `artifacts/issue-12/native-accelerate-comparison.json` | “On the recorded Apple M1 Pro replay, all compared kernels pass the numerical gate. These microsecond figures are saved-input replay measurements, not portable hosted or closed-loop latency.” | `measured_saved_input_replay`; recorded local M1 evidence. |
| 2:20–2:45 | Evidence ZIP and `scripts/reproduce_evidence.py` | “The ZIP contains report, request, trace, outcomes, comparison, manifest, and hashes; reproduction reuses recorded grounding and makes no provider calls.” | Exportable evidence; recorded grounding only. |
| 2:45–3:00 | Held-out readiness endpoint and limitations | “Final held-out evaluation is blocked: validation quality is not met and the quality review has not happened. The separate live-provider and portable-hosting acceptance records passed; neither substitutes for an untouched final result.” | `awaiting_quality_review`; `not_met` / `met`. |

## Recording checklist

- [ ] Use only local recorded or modeled evidence; show provenance at the point it is interpreted.
- [ ] Regenerate the committed queue-policy asset with `uv run python scripts/create_demo_evidence.py`
  only when its deterministic request contract changes, then verify its ZIP with
  `uv run python scripts/reproduce_evidence.py artifacts/issue-23/queue-policy-comparison.zip`.
- [ ] State the queue policy, modeled compute/load values, scenario, seed, model, and frozen
  expectations before showing the comparison.
- [ ] Export the actual comparison bundle shown on screen and run its reproduction command.
- [ ] Show the backend artifact's hardware and timing limitations; do not imply live Apple
  execution from a portable host.
- [ ] State that #19 live-provider and #21 deployment/persistence have separate accepted records,
  while #22 held-out acceptance remains open pending the quality review and manual final run.
- [ ] Do not submit, deploy, change repository visibility, or claim a final public handoff until
  the outstanding gates are completed.
- [ ] Review `docs/demo/contribution-and-license-register.md` and resolve both perception-asset
  provenance entries before public distribution.
- [ ] Complete the signed-in checklist in `docs/demo/event-requirements-check.md`; the public
  recheck confirms the deadline but cannot access the authenticated participant rules.
