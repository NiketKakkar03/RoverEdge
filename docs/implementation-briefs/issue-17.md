# Issue 17 implementation brief

## Contract and baseline

- GitHub issue: #17, `Demonstrate controlled and exploratory before/after comparisons`.
- Fixed baseline: `f0ff051` (`main` and `origin/main` before implementation).
- Native blockers: #13 and #15, both closed. #17 blocks #19.
- Scope: comparison classification, evidence, and aligned replay of already recorded
  runs. Do not rerun, rewrite, or discard a negative result while constructing a
  comparison.

## Observable acceptance criteria

1. A controlled comparison names one declared request path and is valid only when
   exactly that path differs. Scenario, mission target, model identity, criteria,
   seed, and every other request path remain frozen unless one is the declared
   factor. A mismatch is explicit and cannot be presented as controlled.
2. An exploratory comparison lists every request difference and explicitly forbids
   isolated-cause interpretation. Unchanged, worse, failed, and inconclusive results
   remain visible.
3. The comparison record presents both runs' numerical agreement, runtime evidence,
   mission outcome, test verdict, and run identity together without relabeling
   measured or modeled timing.
4. The browser retains both recorded runs and uses shared play, pause, restart, and
   scrub time for aligned before/after playback.

## Pre-agreed seams and checks

- Public comparison module: tests cover valid/invalid controlled declarations,
  complete exploratory differences, preserved negative outcomes, and explicit
  causal-language limits.
- Browser application: DOM tests cover a declared controlled factor, exploratory
  disclosure, paired evidence, and shared replay time.
- Existing experiment runner remains the owner of run production; comparisons are
  immutable views over its recorded `RunResult` values.

## Constraints

- Do not mutate results or infer improvement from configuration alone.
- Do not merge timing provenance across native measured, saved-input measured,
  synchronous unmeasured, and modeled execution.
- Backend and modeled-memory evidence are optional per run and displayed when
  present; their absence does not block the comparison feature.
- Do not touch provider-gated work, final-test families, exports, or agent behavior.
