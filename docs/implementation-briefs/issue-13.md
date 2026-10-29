# Issue 13 implementation brief

## Contract and baseline

- GitHub issue: #13, `Observe actual inference completion in a paced mission`.
- Fixed baseline: `0c5d8d9` (`main` and `origin/main` before implementation).
- Native blocker: #9, closed. #13 blocks #17.
- Scope: actual native closed-loop execution and its measured timing evidence. Keep
  deterministic virtual-device time separate and do not convert host elapsed time
  into modeled time.

## Observable acceptance criteria

1. A native paced execution mode runs one native inference asynchronously while
   physics continues on a wall-clock schedule. The trace identifies the episode,
   observation, request, candidate set, model, dispatch, completion, and accepted
   decision.
2. The mode retains at most the newest pending observation without cancelling the
   executing call. A completed result older than the newest accepted observation
   cannot replace it. Result age equal to the maximum is usable; a strictly older
   result expires and leaves the rover requesting physical braking.
3. Native events expose measured execution latency, observation age, and pacing
   overruns with measured provenance. Tests assert ordering and boundary behavior,
   not exact host scheduling durations.
4. The browser can launch native paced execution and displays measured latency,
   age, overrun, identity, and freshness evidence beside the mission.

## Pre-agreed seams and checks

- Native paced scheduler: focused tests with controlled completion establish
  single-flight, newest-pending, expiry, and older-result precedence behavior.
- Experiment runner / `/api/runs`: a short paced mission establishes wall-clock
  progress, measured trace propagation, braking while output is unavailable, and
  runtime identity without asserting deterministic elapsed timings.
- Browser application: a DOM test establishes visible measured provenance and
  identity; it does not retest scheduler concurrency.

## Constraints

- Keep synchronous native replay and deterministic virtual FIFO behavior unchanged.
- Preserve the learned model, candidate selection rule, and native correctness
  comparison from #9.
- Use one native runtime instance and one executing call; never overlap its reusable
  workspace.
- Do not claim exact wall-clock determinism, physical-robot safety, or modeled-device
  timing from the measured native path.
- Do not touch provider-gated work, final-test families, or unrelated visual design.
