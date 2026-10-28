# Issue #9 implementation brief — fresh naive C++ inference

**Issue:** [#9 — Execute a mission with fresh naive C++ inference](https://github.com/NiketKakkar03/RoverEdge/issues/9)

**Status:** Authorized for credit-free sequential implementation on 2026-10-28. Native blocker #8 is closed.

## Behavior and boundaries

Add a C++20 numerical runtime that evaluates the frozen issue #8 model without changing its feature,
normalization, activation, candidate, cutoff, or selection contracts. `native-naive` is an inference
backend, not a different controller or model.

Public seams agreed by the issue/specification:

- `roveredge.native`: rectangular FP32 multiplication and versioned artifact-backed batch inference.
- Experiment runner: a learned-controller run selects `python-reference` or `native-naive`, records
  runtime provenance, and exposes command disagreements from identical saved decision inputs.
- CMake/Make commands: build and reproduce the native correctness/comparison evidence on a
  compatible host.

## Runtime ownership

`NativeRiskModel` copies validated FP32 normalization, weights, and biases once at construction. It
owns reusable input, hidden-layer, logit, and score buffers sized for the fixed eight-candidate batch.
An evaluation holds a non-blocking workspace guard while the Python GIL is released; an overlapping
call fails instead of sharing writable buffers. Matrix operands are copied into owned C++ storage at
the public multiplication boundary, so aliased Python containers cannot create overlapping output.

The naive kernel computes row-major rectangular `A[M,K] × B[K,N]` with explicit FP32 accumulation.
Aggressive floating-point optimization remains disabled. The exported PyTorch weights are converted
once from `[out,in]` to the kernel's `[in,out]` orientation.

## TDD slices and acceptance

1. Rectangular multiplication matches an independent literal/NumPy reference and rejects malformed
   dimensions and nonfinite values.
2. Artifact construction rejects malformed/nonfinite contracts already enforced by the public loader.
3. Native layer outputs, logits, and scores agree with the Python reference under the proposed
   `1e-5 + 1e-4*abs(reference)` tolerance.
4. Identical saved candidate batches produce the same selected commands; every disagreement is
   counted and preserved in `artifacts/issue-9/native-naive-comparison.json`.
5. A learned open-preset mission using `native-naive` records backend, compiler, platform, model,
   and comparison provenance alongside its existing mission evidence.
6. `make build-native`, focused tests, and `make check` provide portable reproduction commands.

Correctness gates all comparison evidence. This slice records command agreement and runtime
provenance but makes no performance claim and does not implement blocked, parallel, Accelerate,
asynchronous, modeled-delay, or held-out-final evaluation work.
