# RoverEdge

**Evidence-driven AI debugging for autonomous rover missions.**

RoverEdge is a robotics experimentation environment for studying how inference latency, stale
observations, and runtime policy affect a simulated inspection rover. It combines deterministic
mission execution with an interactive 3D replay and a bounded Meta-powered mission engineer that
can inspect a completed run, test one controlled change, and explain whether the recorded evidence
shows an improvement.

> An AI model may propose and explain an experiment. RoverEdge executes the experiment and decides
> whether the evidence supports the conclusion.

## What the demo shows

1. Run an inspection-and-return mission in the **Open inspection lane**.
2. Compare FIFO and Latest Pending queues at **20 ms modeled compute**. Both missions complete.
3. Repeat at **80 ms modeled compute**. Both missions time out as inference results become stale.
4. Ask the mission engineer why the congested run stopped.
5. RoverEdge changes only the queue policy, executes one local follow-up simulation, and validates
   that the failed verdict did not improve.

This is a useful negative result: Latest Pending discards more obsolete work, but queue policy alone
cannot rescue a mission whose inference pipeline consistently misses its reporting deadline.

## Highlights

- Interactive 3D mission replay with synchronized technical map and trace timeline.
- Deterministic inspection, return-to-dock, collision, unreachable-target, missing-target, and
  ambiguous-target scenarios.
- Explicit modeled-device costs, finite pending queues, freshness limits, memory admission, and
  timing provenance.
- Controlled comparisons that declare the single changed factor and preserve all other mission
  inputs.
- A Meta Muse Spark mission engineer served through Baseten, with explicit consent and a fixed
  two-request budget.
- Evidence validation that rejects unsupported improvement, citation, or causal claims.
- A learned collision-risk controller plus Python reference, naive C++20, cache-blocked, parallel
  blocked, and Apple Accelerate inference paths.
- Exportable, hash-checked run and comparison bundles.
- A portable FastAPI deployment entry point with durable Modal Volume storage.

## How the AI investigation works

```text
Recorded mission trace
        │
        ▼
Meta Muse Spark through Baseten
  proposes a bounded tool plan
        │
        ▼
RoverEdge validates the plan
  changes one supported factor
  runs a deterministic follow-up
  creates a controlled comparison
        │
        ▼
Meta model explains the result
        │
        ▼
RoverEdge validates the explanation
  against recorded outcomes and citations
```

The model never supplies wheel commands, changes the controller during a run, relaxes the test
criteria, or determines whether its own proposal succeeded.

## Platform responsibilities

| Component | Role |
| --- | --- |
| Meta Muse Spark | Trace interpretation, bounded experiment planning, and result explanation |
| Baseten | OpenAI-compatible inference endpoint for the Meta model |
| RoverEdge | Simulation, tool execution, controlled comparison, evidence validation, and replay |
| Modal | Portable FastAPI hosting and durable artifact storage |
| TypeScript + Canvas | Interactive 3D presentation, experiment controls, and technical evidence UI |
| Python + C++20 | Deterministic simulation, learned controller, and native inference implementations |

## Run locally

### Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Node.js and pnpm
- A C++20 compiler
- CMake for the optional native extension

Install dependencies and build the native runtime:

```sh
make setup
```

Build the browser bundle and start FastAPI:

```sh
make dev
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

The deterministic missions and queue experiments do not require provider credentials. A live
mission-engineer investigation additionally requires `Baseten_API_KEY` in the server process. Never
expose provider credentials to the browser or commit them to the repository.

## Suggested demo path

1. Select **Open inspection lane** and run the reference mission.
2. Run the queue comparison at **20 ms compute** and show both completed outcomes.
3. Run it again at **80 ms compute (congested)** and show both timeouts.
4. Ask:

   > Why did the rover time out at 80 ms of modeled compute time? Inspect the recorded trace,
   > change only the queue policy, run one controlled follow-up, and explain whether that change
   > improved the mission outcome.

5. Confirm the live result reports two provider requests and one follow-up simulation.

The complete three-minute recording plan is in
[`docs/demo/three-minute-storyboard.md`](docs/demo/three-minute-storyboard.md).

## Verification

Run the full project checks:

```sh
make check
```

The check target builds the native extension, runs the Python test suite, type-checks and lints the
Python code, runs the browser tests, and creates the production web build.

Reproduce the compact queue-policy evidence bundle:

```sh
uv run python scripts/create_demo_evidence.py
uv run python scripts/reproduce_evidence.py artifacts/issue-23/queue-policy-comparison.zip
```

Each run preserves its scenario version, seed, configuration, expected outcome, trace, inspection
observations, mission outcome, and test verdict. Learned runs additionally freeze model, cutoff,
candidate-set, and inference-backend identity. Unique run IDs differ; canonical evidence remains
reproducible for identical inputs.

## Native inference comparisons

```sh
make compare-native-naive
make compare-native-blocked
make compare-native-parallel
make compare-native-accelerate
```

Apple Accelerate is available only on supported Apple hosts. Checked-in M1 Pro results are labeled
as recorded local measurements and remain separate from modeled-device timing and portable hosted
execution. Native saved-input timing is not presented as closed-loop robot latency.

## Deploy on Modal

RoverEdge includes [`modal_app.py`](modal_app.py), which packages the production browser bundle and
FastAPI application, mounts a named persistent Volume, and commits hosted run artifacts after
writes.

Build the web application before deployment:

```sh
pnpm build:web
```

Provision the named Volume and server-side Secret, then deploy:

```sh
uvx --from modal modal volume create --version=2 roveredge-artifacts-v1
uv run modal deploy modal_app.py
```

The Modal Secret must be named `roveredge-provider-credentials`. Store provider credentials in that
secret—not in source files or command arguments. Deployment is cost-bearing; follow the acceptance
and rollback procedure in
[`docs/manual-verification/modal-deployment.md`](docs/manual-verification/modal-deployment.md).

Portable hosting cannot produce Apple Accelerate measurements. Hosted, recorded-local, and modeled
artifacts retain distinct execution labels.

## Scope and limitations

RoverEdge is an engineering prototype for deterministic simulation and early-stage civilian
inspection research. It is not a physical robot controller or a safety-certification system. It
uses known pose, known scene geometry, and idealized range sensing. A controlled comparison tests
one factor in one scenario; it does not establish a universal cause.

Additional design decisions, terminology, and evaluation boundaries are documented in
[`project.md`](project.md), [`GLOSSARY.md`](GLOSSARY.md), and
[`docs/design-consensus.md`](docs/design-consensus.md).
