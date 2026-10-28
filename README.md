# RoverEdge

RoverEdge is a software experimentation environment for investigating how computation delays affect simulated inspection-rover missions.

The current implementation is issue #2's deterministic reference slice: one preset open scene, one geometric inspection-and-return mission, and a browser replay backed by recorded run evidence. It does not use SAM, learned control, native inference, or delayed-inference modeling yet.

## Run locally

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), Node.js, and pnpm.

```sh
make setup
make dev
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000), then:

1. Start the successful mission and inspect every recorded phase.
2. Use play, pause, restart, and the time scrubber to inspect the trace.
3. Run the expected-timeout fixture and observe `mission outcome: timed_out` with `test verdict: passed`.

Run all automated checks with:

```sh
make check
```

## Current evidence contract

Each run preserves its scenario version, seed, configuration, declared expectation, trace, inspection observation, mission outcome, and test verdict. Repeating identical input reproduces canonical evidence; the unique run identifier is intentionally different.
