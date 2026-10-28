# Issue #15 implementation brief — queue freshness comparisons

**Issue:** [#15 — Compare queue freshness under steady and burst congestion](https://github.com/NiketKakkar03/RoverEdge/issues/15)

**Status:** Authorized after #14 merged on 2026-10-28.

## Behavior and public seams

- `ModeledDeviceProfile.queue_policy` selects unchanged FIFO or `latest_pending`.
- Latest-pending replaces waiting work for the same episode and never cancels executing work.
- Run summaries record every scheduled opportunity plus admitted, completed, overflow, replacement,
  expiry, deadline-miss, and aggregate dropped counts. Dispatch events record queue wait; consumed
  decisions record observation age.
- Paired steady and burst fixtures preserve actual mission outcomes while exposing FIFO overflow
  versus latest replacement. Browser replay exposes the latest queue event and depth.

Out of scope: modeled memory admission (#16), configurable experiment validity UX (#18), actual
wall-clock inference (#13), and final-test evaluation.
