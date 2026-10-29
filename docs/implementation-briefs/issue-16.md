# Issue 16 implementation brief

## Contract and baseline

- GitHub issue: #16, `Expose modeled memory admission and recovery`.
- Fixed baseline: `fbbdbc7` (`main` and `origin/main` before implementation).
- Native blocker: #14, closed. #16 blocks #18 and #22.
- Scope: virtual-device modeled memory only. Do not describe values as process RSS,
  allocator telemetry, cache behavior, or physical-device measurement.
- Preserve resident model weights, one bounded reusable workspace, pending payloads,
  and the executing request's in-flight payload as separate modeled categories.

## Observable acceptance criteria

1. The public modeled-device seam accepts explicit byte sizes and a modeled
   allocation budget. A budget equal to the required allocation admits work;
   one byte less rejects it with an explicit event.
2. Allocation, category transition, rejection, and release evidence appears in
   the experiment trace with current/peak/budget byte totals and `modeled`
   provenance.
3. Replacement, overflow, pre-dispatch expiry, and completion recover request
   payload bytes without growing the reusable workspace. Repeated identical
   runs reproduce the trace and memory summary apart from run identity.
4. The browser displays a modeled-memory breakdown and rejection/recovery
   evidence without using RSS or hardware-measurement language.

## Pre-agreed public seams and checks

- `FifoDevice`: focused exact-boundary and lifecycle tests catch scheduler
  accounting errors; they do not prove end-to-end trace/report propagation.
- Experiment runner / `/api/runs`: representative virtual missions catch
  configuration round-trip, trace, summary, and reproducibility regressions;
  they do not prove browser presentation.
- Browser application: a small DOM test catches visible provenance and memory
  evidence regressions; it does not retest scheduler arithmetic.

## Constraints

- Keep the one-lane dispatch and queue-order semantics from #14/#15 unchanged.
- Host elapsed time never contributes to modeled time or modeled bytes.
- The resident and reusable baseline must fit before any request can be admitted.
- Do not touch provider-gated work, final-test families, or visual-design debt.
