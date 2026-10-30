# Issue #7 implementation brief — ordered multi-target missions

**Issue:** [#7 — Inspect multiple targets and exercise mission variants](https://github.com/NiketKakkar03/RoverEdge/issues/7)

## Observable behavior

`multi_target_fixture` requests carry an ordered, unique sequence of at least two required target
identities. The physical runner plans one route chain from dock through each inspection pose and
back to dock. It advances only after the current target is reached, faced, stopped at, and observed
after the configured dwell.

Every required target produces `TargetVisitEvidence` containing its identity, ordinal, captured
pose when available, dwell-completion flag, explicit status, and observation sequence. Timeout,
collision, setup failure, and unreachable planning retain completed observations and mark every
remaining target incomplete; only all visits plus return-to-dock can produce `completed`.

The browser accepts an ordered comma-separated target sequence and displays each required visit's
status, dwell completion, and captured pose. Fixture identities remain explicitly labeled and do
not replace the visual-grounding contract from Issue #4.

## Verification

- Complete two-target missions run over open, narrow, and cluttered built-in routes.
- A bounded timeout captures exactly one target, preserves that observation, marks the second
  incomplete, and reports `timed_out` rather than success.
- Missing and ambiguous required targets stop during setup with explicit per-target evidence.
- The unreachable built-in route records every required visit as unreachable.
- Input validation rejects too-short, duplicate, and empty target sequences.
- Browser and API tests cover ordered submission and per-target progress display.
- `make check` covers the full Python/browser suites, native build, type checks, lint, and web build.
