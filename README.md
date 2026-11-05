# RoverEdge

RoverEdge is a software experimentation environment for investigating how computation delays affect simulated inspection-rover missions.

The current implementation includes deterministic inspection-and-return missions, obstacle dynamics
and failure evidence, an experimental learned collision-risk controller, and fresh naive,
cache-blocked, and parallel blocked C++20 inference plus an Apple Accelerate comparison. It also
includes explicit virtual queue/freshness/memory modeling and a bounded, zero-provider-call recorded
mission-engineer fixture. Live SAM/provider verification remains manual-only.

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
make compare-native-blocked
make compare-native-parallel
make compare-native-accelerate
```

The Accelerate command is available on supported Apple hosts. The browser always labels and shows
the checked-in M1 Pro result separately from current-host availability. Comparison artifacts record
numerical tolerance results, selected-command disagreements, compiler/platform provenance, warmed
saved-input timing boundaries, and uncontrolled machine-state limitations. These are native replay
measurements, not closed-loop mission-latency or physical-robot claims.

Run all automated checks with:

```sh
make check
```

## Current evidence contract

Each run preserves its scenario version, seed, configuration, declared expectation, trace,
inspection observation, mission outcome, and test verdict. Learned runs also freeze model, cutoff,
candidate-set, and inference-backend identity. Repeating identical input reproduces canonical
evidence; the unique run identifier is intentionally different.

## Demo and evaluation handoff

The three-minute storyboard is in
[docs/demo/three-minute-storyboard.md](docs/demo/three-minute-storyboard.md). Its queue-policy
comparison is real local **modeled** evidence, regenerated and checked with:

```sh
uv run python scripts/create_demo_evidence.py
uv run python scripts/reproduce_evidence.py artifacts/issue-23/queue-policy-comparison.zip
```

The held-out evaluation endpoint is `/api/evaluations/held-out`. It exposes the hash-checked frozen
protocol and the retained execution state. The current v2 run is accurately reported as `stopped`:
all 120 modeled virtual runs and four native runs were retained, but native pacing exceeded its
frozen validity limit, so the remaining native work and saved-input replay were not executed.

The public handoff also includes a
[contribution/license register](docs/demo/contribution-and-license-register.md) and an
[event-requirements check](docs/demo/event-requirements-check.md). The latter confirms the public
deadline but leaves authenticated rule fields for a signed-in manual check.
