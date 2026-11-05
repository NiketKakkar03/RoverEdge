# Compose learned risk with deterministic command admission

## Status

Accepted for validation; held-out evaluation remains gated.

## Context

The `risk-dataset-v2` model reached the proposed validation progress requirement but selected 57
commands whose one-second simulator rollout collided. Lowering the learned-risk cutoff alone could
not meet all three proposed quality requirements. The runtime also had a separate single-forward-ray
braking check that validation did not exercise and that did not cover turning sweeps.

The learned model is useful for ranking local candidate commands, but sparse range sensing and model
error prevent its score from acting as a safety guarantee. The simulator must remain the collision
label authority, while runtime driving decisions may combine the local model with deterministic
safety logic under ADR 0005.

## Decision

Place one versioned `sensor-stopping-v1` module at the command-admission seam. For every candidate
with positive linear velocity, it computes the bounded one-second travel distance using the declared
acceleration or braking limit. It inspects the five 16-ray sensor directions spanning the candidate's
turning sweep and requires measured clearance greater than travel distance, rover radius, and one
additional rover-radius margin for sparse angular sampling. Stationary candidates remain available
for braking.

The learned risk cutoff and deterministic admission decision are both required before progress and
risk tie-breaking. Validation cutoff selection, synchronous execution, virtual queued execution,
and native paced execution use the same interface. Delayed results retain the sensor state that
created their inference request, so command admission is reproducible and does not silently use a
newer observation.

The safety-envelope version is part of run configuration and validation evidence. Simulator rollout
labels remain unchanged. Model output is not relabeled, and neither model nor safety-envelope output
is a test verdict.

## Consequences

This architecture can reject commands that the learned model scores below its cutoff, increasing
unnecessary stops in exchange for a deterministic sensor-derived clearance requirement. Validation
must still meet the separately reviewed progress and stop-rate requirements. Sparse rays can miss
geometry between their directions, so this is prototype command admission rather than a physical
robot safety certification.

Any parameter or algorithm change requires a new safety-envelope version and fresh validation.
Final families remain untouched until the complete Issue #22 protocol is explicitly reviewed and
frozen.
