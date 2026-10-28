# Issue #14 implementation brief — deterministic delayed inference

**Issue:** [#14 — Run a deterministic delayed-inference experiment](https://github.com/NiketKakkar03/RoverEdge/issues/14)

**Status:** Authorized on 2026-10-28; blocker #8 is closed.

## Behavior and public seams

- `FifoDevice` models one execution lane, resident weights, serial dispatch/input/compute/output,
  two pending requests, overflow, pre-dispatch expiry, and consumption expiry.
- `RunConfiguration.execution_mode="virtual_fifo"` applies declared modeled timing without adding
  host inference duration to simulated time.
- Trace events preserve episode, observation, request, candidate-set, and model identity; event
  order is completion, request creation, consumption, then dispatch at a planning timestamp.
- Deadline and age equality are accepted; only values greater than a limit miss or expire.
- Browser replay exposes prediction age with modeled provenance. Identical input reproduces trace,
  queue events, mission outcome, and summary.

## Acceptance checks

1. Public scheduler tests freeze stage completion, FIFO capacity, overflow, expiry, and equality.
2. A baseline learned mission completes with a deterministic 50 ms prediction-age timeline.
3. A delayed fixture records overflow and expiry while preserving its expected timeout verdict.
4. Full Python, type, lint, browser, and production-build checks pass.

Out of scope: latest-pending replacement and load-family comparisons (#15), modeled memory (#16),
actual wall-clock asynchronous inference (#13), and final-test evaluation.
