# UI scenario audit — 2026-11-04

Executed all nine built-in scenarios through the real simulation under default,
learned synchronous, FIFO and latest-pending configurations. No provider calls.
The confirmed lower-delay matrix is `artifacts/issue-25/verified-low-delay.json`.
Run it with `.venv/bin/python scripts/audit_ui_scenarios.py --compute 0.02`.

## Findings and changes

- All default missions now match their expected outcomes. Open, perception, shifted,
  narrow and cluttered complete. Absent, ambiguous, unreachable and collision fixtures
  report their respective expected failures.
- Perception defaults previously selected a generic container even in the absent and
  ambiguous fixtures. Defaults now request the red toolbox by label using known fixture
  resolution. This is not a live SAM grounding claim.
- At 80 ms compute, the open-lane queue runs accept only one decision and move roughly
  1.7 mm. Expiry dominates the trace. At 20 ms, both queue policies complete the open
  and perception missions. Freshness limits were not loosened.
- Learned runs still time out in shifted, narrow and cluttered scenarios even at
  lower delay. Cluttered traces show stopping selected at a nearby waypoint despite
  zero model risks. A distance-limited progress horizon was tried and rejected because
  it regressed open-lane completion. Files prefixed `rejected-progress-horizon` retain
  experimental results, not accepted implementation evidence.
- UI summaries now report inspections, duration, distance, accepted-decision age
  average/maximum, sample count and expirations. Acceptance-time age is explicitly
  distinguished from the age of a held command. Replay-time age has its own label.
- Scenario switching clears active results and disables exports/investigation while
  preserving the previous completed run for explicitly labeled cross-scenario comparison.
- Camera changes redraw paused scenes. Investigation has a multiline question, explicit
  provider consent and safe text rendering; focused tests use a mocked provider response.

## Video testing

1. Open inspection lane: Run mission, Play, Pause, scrub and reset camera. Expected
   completed/passed with one inspection. Compare both views at a turn.
2. Select absent/ambiguous fixtures: requested target is red toolbox. Run mission.
   Expect the corresponding setup failure and passed verdict, zero inspections.
3. Open lane: compare queues at 20 ms, then at 80 ms. Expect completion at lower delay
   and expiration-dominated timeouts under congestion. Describe the changed compute
   setting separately from the within-pair queue-policy comparison.
4. Narrow/cluttered: default mission completes. Learned variants still expose a
   navigation limitation; do not present them as solved or change expected outcomes.
5. Investigation: without consent no provider request is sent. Live provider execution
   still requires the user's explicit UI action and available server credentials.

## Remaining acceptance work

Learned navigation is unresolved. Full live-provider, deployment, exhaustive browser
interaction, and 3D geometry fidelity checks have not passed in this audit. The generic
presentation target still does not depict all perception objects. No safety or held-out
quality claim follows from these preset results. Issue 25 remains open.
