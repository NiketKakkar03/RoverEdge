# Validation safety architecture improvement

## Observable acceptance criteria

On the existing `risk-dataset-v2` validation families, one deterministic controller-selection path
must produce zero selected moving commands with collision labels, an unnecessary-stop rate no more
than 10%, and mean safe progress at least 0.3. The same selection interface must be used by
validation, synchronous runs, virtual queued runs, and native paced runs. The dataset manifest must
continue to state that final families are untouched.

Focused tests cover bounded rollout distance, straight and turning clearance, wrapped ray sectors,
invalid inputs, learned-risk composition, and delayed-runtime paths. The full test suite and static
checks must pass before Issue #22 readiness is reconsidered.

## Architecture

`sensor-stopping-v1` is a deterministic command-admission module. Its interface accepts the 16 range
readings, current linear velocity, and one candidate command and returns an admission decision with
the inspected rays and required/observed clearances. The implementation hides acceleration-limited
rollout distance and swept-sector selection. It performs no simulation, labeling, provider access,
or final-family generation.

The learned model remains the risk-ranking mechanism. A command must pass both its validation-chosen
risk cutoff and `sensor-stopping-v1`; progress, risk, and candidate index then provide deterministic
selection ordering. A zero-linear-velocity candidate remains available for braking.

## Validation-only result

The deterministic 300-epoch run selects a risk cutoff of `0.0001` using validation data. Across 768
validation states and 6,144 candidate labels, the composed policy records zero false negatives, 58
unnecessary stops (7.552%), and mean safe progress `0.3339251055009594`. The final-family status is
`untouched`.

This result makes the model-quality prerequisite viable for review; it is not held-out evidence and
does not by itself complete Issue #22.
