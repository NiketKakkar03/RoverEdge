# Issue #11 implementation brief — parallel blocked native inference

**Issue:** [#11 — Compare parallel inference and worker settings](https://github.com/NiketKakkar03/RoverEdge/issues/11)

**Status:** Authorized on 2026-10-28; native blocker #10 is closed.

## Behavior and public seams

Add a fresh parallel blocked FP32 backend whose explicit worker count partitions output rows. Each
call creates and joins its workers; persistent pools remain deferred. Reuse the frozen model,
candidate, cutoff, block-size, owned-workspace, and saved-input contracts from issues #9 and #10.

- Numerical runtime: `parallel_blocked_matmul` and
  `NativeRiskModel(..., backend="native-parallel-blocked", worker_count=...)`.
- Experiment runner: learned missions select the parallel backend, validate and preserve workers,
  and record backend/worker provenance and reference command disagreements.
- Comparison evidence: hash-validate issue #9's frozen 192×8×24 workload, correctness-gate each
  supported worker setting against the serial blocked backend, then measure warmed distributions.
- Browser: select the parallel backend and display correctness, saved-input evidence, workers,
  and measured comparison without implying that parallelism must be faster.

## TDD slices

1. Rectangular parallel blocked multiplication with non-divisible tails matches the public naive
   reference for worker counts 1, 2, and 4; non-positive counts are rejected.
2. Parallel native layer/logit/score output and selected commands agree for each supported count;
   overlapping calls cannot share the owned workspace.
3. An open-preset mission completes with worker selection preserved in request and result evidence.
4. A reproducible comparison records samples, warmup, compiler/platform/model/input identity, and
   honest measured distributions for serial blocked and each worker count; timings are withheld on
   correctness failure.
5. Browser evidence exposes the recorded comparison and worker setting with measured provenance.

Out of scope: persistent thread pools, Accelerate, asynchronous mission execution, queue/device
modeling, closed-loop latency attribution, and final-test evaluation.
