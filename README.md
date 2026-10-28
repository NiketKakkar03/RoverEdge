# RoverEdge

RoverEdge is a software experimentation environment for investigating how computation delays affect simulated inspection-rover missions.

The current implementation includes deterministic inspection-and-return missions, obstacle dynamics
and failure evidence, an experimental learned collision-risk controller, and fresh naive C++20
inference. SAM grounding remains deferred pending live provider verification, and delayed-inference
modeling is not implemented yet.

## Run locally

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), a C++20 compiler, Node.js, and pnpm. CMake
and pybind11 are installed into the project development environment.

```sh
make setup
make dev
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), then:

1. Start a successful geometric mission and inspect every recorded phase.
2. Use play, pause, restart, and the time scrubber to inspect the trace.
3. Run the learned controller with Python reference or native naive inference and inspect the model,
   backend, and command-agreement evidence.
4. Run the expected-timeout fixture and observe `mission outcome: timed_out` with `test verdict: passed`.

Build the native extension and reproduce its correctness comparison on the frozen saved inputs with:

```sh
make build-native
make compare-native-naive
```

The comparison artifact records numerical tolerance results, selected-command disagreements,
compiler/platform provenance, and `performance_claim: not measured`. It does not claim a speedup.

Run all automated checks with:

```sh
make check
```

## Current evidence contract

Each run preserves its scenario version, seed, configuration, declared expectation, trace,
inspection observation, mission outcome, and test verdict. Learned runs also freeze model, cutoff,
candidate-set, and inference-backend identity. Repeating identical input reproduces canonical
evidence; the unique run identifier is intentionally different.
