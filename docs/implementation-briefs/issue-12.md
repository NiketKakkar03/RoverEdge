# Issue #12 implementation brief — Apple Accelerate inference

**Issue:** [#12 — Add Apple Accelerate to the same-machine comparison](https://github.com/NiketKakkar03/RoverEdge/issues/12)

**Status:** Authorized on 2026-10-28; native blocker #9 is closed.

## Behavior and public seams

Add an Apple Accelerate FP32 backend using `cblas_sgemm` for the existing resident
`24 → 64 → 32 → 1` model. Reuse the frozen model, candidate, cutoff, owned-workspace, and saved-input
contracts from issues #8–#11.

- Numerical runtime: `accelerate_matmul` and
  `NativeRiskModel(..., backend="native-accelerate")` on supported Apple hosts.
- Experiment runner: learned missions select the Accelerate backend and record availability,
  framework/compiler/hardware provenance, and reference command agreement.
- Comparison evidence: hash-validate issue #9's frozen 192×8×24 workload, correctness-gate
  Accelerate against the naive backend, then measure warmed distributions for all available custom
  backends and Accelerate on the same M1 Pro.
- Browser: select the live Accelerate backend when available and display the checked-in M1 result
  with recorded-local provenance even on unsupported hosts.

Unsupported hosts must identify Accelerate as unavailable rather than silently falling back. The
checked-in comparison remains viewable because it is evidence from a recorded local run, not a
claim about the current host.

## TDD slices

1. Rectangular Accelerate multiplication matches the public naive reference, including non-square
   shapes; unsupported builds expose an explicit availability result and reject live calls.
2. Accelerate hidden layers, logits, scores, and selected commands agree with the trusted reference;
   overlapping calls cannot share the owned workspace.
3. An open-preset mission completes with Accelerate selection and provenance preserved.
4. A reproducible comparison records samples, warmup, compiler/platform/model/input identity, all
   available custom backends, and honest measured distributions; timings are withheld on
   correctness failure.
5. Browser evidence distinguishes live availability from the recorded M1 comparison and exposes
   correctness, saved-input evidence, and measured provenance.

Out of scope: provider work, persistent thread pools, asynchronous mission execution, queue/device
modeling, closed-loop latency attribution, non-Apple acceleration, and final-test evaluation.
