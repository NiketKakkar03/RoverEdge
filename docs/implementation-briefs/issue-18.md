# Issue 18 implementation brief

## Contract and baseline

- GitHub issue: #18, `Configure rover and device experiments with validity checks`.
- Fixed baseline: `fcbf43f` (`main` and `origin/main` after issue #16).
- Native blockers: #8, #15, and #16, all closed. #18 blocks #22.
- Scope: edit the supported experiment settings in the browser, reject invalid or
  unsupported combinations, record the successful configuration, and expose
  training-domain and comparison-validity evidence.

## Supported settings

- Rover: radius, linear/angular speed, linear acceleration, braking
  deceleration, and angular acceleration.
- Sensor/planning: range maximum and planning period. Range ray count remains
  fixed at 16 because the model feature structure is fixed at 24 features.
- Runtime: supported inference backend and worker count.
- Virtual device: queue policy/capacity, reporting deadline, maximum observation
  age, dispatch/input-transfer/compute/output-transfer costs, and modeled memory
  budget.

The rover type remains differential drive. Model feature order/count, candidate
set structure, and fixed fixture expectations are not editable.

## Observable acceptance criteria

1. The public runner rejects nonfinite/nonpositive dimensions, motion, sensor,
   planning, worker, queue/age, device-cost, and memory inputs, plus unsupported
   backend/worker/execution combinations, with explicit errors.
2. A successful request records its complete frozen configuration, canonical
   configuration ID, fixed rover/model contract, and training-domain warnings.
3. Browser fields round-trip exactly into the runner. An invalid attempt reports
   the error while preserving the last successful run and its expectation.
4. The browser compares each successful configuration with the previous one:
   one changed setting is labeled controlled; multiple changes are labeled
   exploratory and list every difference. No outcome is causally attributed.
5. Repeating a configuration reproduces its canonical ID and evidence apart
   from the unique run ID.

## Training-domain declaration

The current model was generated with the default differential-drive dynamics,
0.20 m rover radius, 0.60 m/s linear limit, 0.80 rad/s angular candidate limit,
4 m / 16-ray sensing, and the fixed 24-feature order. Changes to model-relevant
settings remain runnable when physically valid but receive explicit
outside-training-conditions warnings. The learned validation gate remains
`not_met` regardless of configuration.

## Pre-agreed public seams and checks

- Experiment runner / `/api/runs`: validation, freeze/round-trip, canonical ID,
  fixed contract, warnings, and reproducibility.
- Browser application: supported field submission, preserved successful state on
  error, visible warnings, and controlled/exploratory classification.

## Constraints

- Preserve modeled-versus-measured provenance and final-test independence.
- Do not add rover types, feature structures, persistent storage, #17 comparison
  presentation, provider work, or visual-design debt.
