# Issue #8 implementation brief — learned collision-risk control

**Issue:** [#8 — Run a learned collision-risk controller with validation evidence](https://github.com/NiketKakkar03/RoverEdge/issues/8)

**Status:** Authorized for credit-free sequential implementation on 2026-10-28.

## Behavior and boundary

Generate deterministic synthetic state/candidate samples from separated scene and episode families,
train the specified FP32 risk MLP locally, export a versioned artifact, and run learned versus
geometric controllers through the existing experiment runner and browser evidence view.

This issue freezes the specification's declared model and command contracts:

- Features, in order: 16 ranges; current linear/angular velocity; next waypoint in rover
  coordinates; candidate linear/angular command; previous linear/angular command.
- Architecture: `24 → 64 → 32 → 1`, ReLU hidden activations, sigmoid risk score.
- Candidate order: `(0,0)`, `(0.2,0)`, `(0.4,0)`, `(0.6,0)`, `(0.3,0.8)`,
  `(0.3,-0.8)`, `(0,0.8)`, `(0,-0.8)`.
- Label: collision during a one simulated-second immediate-action rollout under issue #3 dynamics.
- Selection: among candidates at or below the validation-selected risk cutoff, maximize predicted
  kinematic progress; break ties by lower risk then candidate index. Brake if none qualifies.

The cutoff is a controller setting selected from validation data. It is not a final evaluation
acceptance threshold and the score is not called a calibrated probability.

## Data and evaluation contracts

- Define scene/episode family identity before sampling. Allocate complete families to train,
  validation, or final-test manifests; never split neighboring states from one family.
- Generate ordinary route-following and difficult near-obstacle/recovery states using fixed seeds.
- Fit mean/scale normalization from training rows only and store it with the exact feature order.
- Use validation only to select the risk cutoff and report missed hazards, unnecessary stops, and
  progress. Do not load labels from the final-test manifest during issue #8.
- Proposed local corpus: 8 train families, 3 validation families, 3 untouched final families, with
  64 states × 8 candidates per family. These are bounded engineering fixtures, not a final sample
  size or a quality claim.
- Proposed cutoff search: fixed grid `0.05..0.95` in `0.05` steps; rank by fewest validation false
  negatives, then fewer unnecessary stops, then higher progress, then lower cutoff.
- Preserve dataset manifest, split hashes, seeds, label semantics, feature order, normalization,
  training configuration, package versions, model shapes/dtype/activations, metrics, artifact hash,
  and whether Modal was used. This implementation uses local CPU training and records
  `modal_execution: not_used`.

The untouched final manifest is retained for issue #22. No final-test metric is computed here.

## Public interfaces and structure

```text
DatasetManifest
  version / generator / feature order / label contract
  train / validation / final family IDs and row artifacts

RiskModelArtifact
  version / architecture / dtype / activations
  feature order / normalization / weights / biases / SHA-256
  training provenance / selected validation cutoff

LearnedControllerConfiguration
  model artifact identity / risk cutoff / candidate-set identity

RunResult additions
  controller kind / model identity / candidate evaluations
  selected command, predicted progress/risk, brake reason
  validation evidence reference
```

Modules:

- `learning`: feature extraction, rollout labels, family generation, split enforcement, training,
  validation metrics, and artifact export.
- `risk_model`: strict artifact loading and reference FP32 batch inference.
- `controller`: deterministic candidate progress/risk/tie selection and brake fallback.
- `physical`: consumes a controller decision at planning ticks while preserving issue #3 dynamics,
  braking, swept collision, and trace contracts.
- `api` / browser: select geometric or learned control and display model/candidate evidence.

Use PyTorch for local training and NumPy-compatible FP32 artifact values. Native kernels remain issue
#9 onward; issue #8's reference inference is Python/PyTorch and is not a performance result.

## TDD and acceptance

Use the already-approved seams:

- Primary runner: learned/geometric mission outcomes, traces, decisions, comparisons, and evidence.
- Focused model/artifact interface: exact feature order, shapes, finite values, reference inference,
  deterministic candidate selection, and malformed input rejection.
- Small browser suite: controller selection and learned-decision/validation evidence.

Vertical slices:

1. Manifest construction rejects family leakage and exposes an untouched final manifest.
2. Literal feature and rollout fixtures preserve ordering and one-second collision-label semantics.
3. Training-only normalization and seeded local training export a deterministic versioned artifact.
4. Artifact inference returns eight finite scores; malformed/nonfinite artifacts and inputs fail.
5. Literal candidate fixtures prove progress/risk/index ordering and all-rejected braking.
6. Learned open/narrow/cluttered missions run in the existing runner and retain physical evidence.
7. Validation report shows false negatives, unnecessary stops, progress, and proposed requirements
   without reading final labels.
8. Browser evidence distinguishes geometric and learned runs and shows model/cutoff/decisions.

Completion requires focused checks, full `make check`, separate Standards and Spec reviews, and one
scoped commit. No API credits, provider calls, deployment, issue #4 behavior, native C++, delayed
inference, queues, final evaluation, or broad visual redesign are included.

## Recorded validation outcome

The locally trained artifact selects cutoff `0.05` from the declared validation grid. Across 192
validation states (1,536 state/candidate rows), the controller recorded 17 accepted commands whose
one-second rollout label was collision, two unnecessary brake selections, and a 0.195 mean
dimensionless distance-and-alignment progress score for safe selections. The proposed validation
requirements are zero accepted unsafe commands, at most a 10% unnecessary-stop rate, and at least a
0.3 mean safe progress score. The progress
stop requirement passes; the safety and progress requirements do not, so the report explicitly
records `quality_gate_status: not_met`. These are validation results, not final-test results or measured
device timings.

The learned artifact completes the open preset and produces replayable candidate evidence. On the
narrow and cluttered issue #3 presets it conservatively brakes until timeout rather than colliding.
That limitation remains visible in recorded mission outcomes; issue #8 does not silently present the
model as production-ready, and the held-out final families remain untouched for issue #22.
