# Issue #10 implementation brief — cache-blocked native inference

**Issue:** [#10 — Compare blocked inference with the naive backend](https://github.com/NiketKakkar03/RoverEdge/issues/10)

**Status:** Authorized on 2026-10-28; native blocker #9 is closed.

## Behavior and public seams

Add a fresh row-major cache-blocked FP32 multiplication backend with explicit block size and correct
rectangular tail handling. Reuse issue #9's resident weights, owned guarded workspace, frozen model,
candidate, cutoff, and saved-input contracts.

- Numerical runtime: `blocked_matmul` and `NativeRiskModel(..., backend="native-blocked")`.
- Experiment runner: learned missions select `native-blocked`, preserve backend/block configuration,
  and record reference command disagreements.
- Comparison evidence: hash-validate issue #9's frozen 192×8×24 workload, correctness-gate naive
  and blocked outputs/commands, then measure 1,000 warmed batches in three interleaved repetitions.
- Browser: select the blocked backend and display correctness, saved-input evidence, backend
  configuration, and measured warmed comparison. Withhold latency values if correctness fails.

## TDD slices

1. Rectangular blocked multiplication with non-divisible `M/K/N` tails matches the public naive
   reference and rejects invalid block sizes.
2. Native blocked layer/logit/score output and selected commands agree at the frozen tolerance.
3. Open-preset mission completes with unchanged controller/model contracts and zero disagreements.
4. Reproducible comparison records samples, warmup, interleaving, compiler/platform/model/input
   identity, and measured distributions; no speedup claim is made on correctness failure.
5. Browser evidence exposes the recorded comparison without calling modeled time measured.

Out of scope: parallel workers, Accelerate, asynchronous mission execution, queue/device modeling,
and final-test evaluation.
