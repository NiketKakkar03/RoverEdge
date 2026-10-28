# Issue #2 implementation brief — deterministic inspection mission and replay

**Issue:** [#2 — Run and replay a deterministic inspection mission](https://github.com/NiketKakkar03/RoverEdge/issues/2)

**Status:** Approved; Phase B implementation and verification complete on `codex/issue-2`.

**Implementation boundary:** One preset, deterministic, pre-perception geometric inspection-and-return mission with a recorded browser replay.

## User-visible behavior

1. The browser presents one built-in open scenario and its preset inspection target.
2. The user starts a run. The browser sends a complete run request through the experiment runner rather than animating an independent browser-only simulation.
3. The runner records a deterministic mission trace containing the rover pose, mission phase, and phase-specific events at fixed simulated timestamps.
4. The browser replays the recorded trace and visibly distinguishes approach, target-facing alignment, stopped inspection dwell, observation capture, return, dock, and the terminal outcome.
5. The completed run shows its run identity, scenario version, seed set, configuration, declared expectation, mission outcome, and test verdict.
6. Running the same saved input again produces the same canonical trace and outcome. Run identity may differ, but it is not part of the determinism comparison.
7. A demonstrated timeout fixture ends with a `timed_out` mission outcome. When that outcome was declared as expected, the test verdict is `passed`, preserving the distinction between mission outcome and test verdict.

This slice is a pre-perception reference path: the preset target and its geometric inspection pose are part of the fixed scenario version. It does not claim that SAM recognized the target.

## Source contracts

- `project.md` §4, **Architecture**: keep simulator, experiment runner, recorder, and browser responsibilities separate, using ordinary modules.
- `project.md` §5, **Technical stack and platform responsibilities**: Python/NumPy for deterministic simulation and experiments; FastAPI for the web boundary; TypeScript/Canvas for replay. Package versions remain to be verified during setup.
- `project.md` §6, **Robotics and perception contract**: a successful mission reaches a standoff, faces the target, remains stopped for the dwell, saves an observation, and returns to dock before timeout. Mission outcome is separate from test verdict.
- `project.md` §11, **Testing and evaluation**: use the experiment runner as the primary behavioral boundary and require deterministic simulation and expected-failure handling.
- `project.md` §13, **Demo plan**: show a recognizable mission and replay evidence without presenting unimplemented perception, learned control, timing experiments, or native measurements.
- `docs/roveredge-spec.md` **Implementation Decisions** and **Testing Decisions**: preserve scenario/configuration identity, expectations, traces, outcomes, verdicts, and reproducibility metadata; test observable contracts rather than private structure.
- `docs/adr/0004-preserve-experiment-evidence.md`: record fixed inputs and frozen expectations; preserve unsuccessful mission outcomes even when the test verdict passes.
- `GLOSSARY.md`: use **mission**, **run**, **scenario version**, **inspection observation**, **mission outcome**, and **test verdict** as distinct terms.

ADR 0002 constrains later visual grounding but does not require perception in this slice. ADRs 0001 and 0003 do not govern issue #2 because there is no measured/modeled timing experiment or mission engineer.

## Proposed public interfaces

The experiment runner is the primary public interface. Its transport-independent request and result are adapted to HTTP for the browser.

```text
RunRequest
  scenario_version: string
  mission: { target_id: string }
  seeds: { simulation: integer }
  configuration:
    simulation_step_s: number
    motion: { max_linear_speed_mps, max_angular_speed_radps }
    inspection: { position_tolerance_m, heading_tolerance_rad, dwell_s }
    dock: { position_tolerance_m, heading_tolerance_rad }
    timeout_s: number
  expectations: { mission_outcome: completed | timed_out }

RunResult
  run_id: string
  input: RunRequest
  trace: ordered TraceEvent[]
  observations: InspectionObservation[]
  mission_outcome: completed | timed_out
  test_verdict: passed | failed
  terminal_reason: string
```

`TraceEvent` carries a monotonically increasing sequence number, simulated timestamp, mission phase, rover pose, and an event kind. Canonical trace comparison excludes `run_id` and wall-clock creation metadata. The observation records the preset target identity, capture pose, capture time, and completion status; it is not a defect diagnosis.

The initial browser API is deliberately small:

- `GET /api/scenarios/preset-open`: retrieve the fixed scenario and mission presentation data.
- `POST /api/runs`: execute a saved `RunRequest` and return the complete recorded `RunResult` for replay.

Exact serialization names may be adjusted during the first TDD cycle only if the observable contract remains equivalent and the brief is updated before commit.

## Minimal implementation structure

- A framework-independent Python experiment module owns scenario loading, mission execution, trace recording, outcome evaluation, and verdict evaluation.
- A thin FastAPI adapter validates requests and exposes the experiment runner.
- A small TypeScript/Canvas browser client starts a run and renders only the returned scenario and trace; it does not recompute rover motion.
- Recorded fixture inputs support the successful and expected-timeout demonstrations.
- No database is required. Run results may be immutable in-memory values and checked-in demonstration fixtures in this slice; durable artifact storage belongs to later export/hosting work.

## Scenario geometry and mission state transitions

The single built-in scenario is an obstacle-free, top-down metric rectangle with one dock, one rover start pose, and one preset target with a declared inspection standoff. Geometry is part of the scenario version and never inferred from the displayed target.

Proposed deterministic state sequence:

```text
approaching_target
  -> aligning_to_target
  -> stopping_for_inspection
  -> dwelling
  -> observation_captured
  -> returning_to_dock
  -> aligning_at_dock
  -> completed

any non-terminal phase -> timed_out when simulated_time > timeout_s
```

Transitions use explicit position, heading, stopped, dwell, and dock predicates. The terminal phases are immutable. The timeout check occurs before advancing beyond a simulation step; equality remains admissible, matching the specification's general boundary convention that exceeding a limit is failure.

## Motion, inspection, dock, timeout, and replay contracts

- **Motion:** deterministic differential-drive kinematics at a fixed simulation step. A geometric controller turns toward the current goal and then advances within configured speed caps. Acceleration/braking dynamics, obstacle inflation, range sensing, swept collision detection, and physical failure explanations are issue #3.
- **Inspection:** the rover must be within inspection position tolerance, face the target within heading tolerance, command zero linear and angular velocity, remain stopped for the full dwell, and then emit exactly one observation-capture event.
- **Dock:** after capture, the rover returns to the declared dock pose, enters dock position and heading tolerances, stops, and only then completes.
- **Timeout:** timeout is a mission outcome, not an exception. The trace retains all progress and ends with one terminal event. The verdict compares the recorded outcome with the frozen declared expectation.
- **Replay:** replay is derived solely from the returned trace. It supports play, pause, restart, and a scrubber over simulated time; phase labels and the terminal outcome remain visible. Playback speed changes presentation only and never changes evidence.

## Proposed values requiring approval

All values below are proposed implementation fixtures, not measured limits, validated safety settings, or confirmed product-wide defaults.

| Decision | Recommendation for issue #2 | Reason |
| --- | --- | --- |
| Open map bounds | 8 m × 6 m | Readable browser geometry with a nontrivial round trip |
| Rover start / dock pose | `(1.0 m, 3.0 m, 0 rad)` | Makes the dock and initial condition identical and obvious |
| Preset target footprint | 0.6 m × 1.0 m rectangle centered at `(6.5 m, 3.0 m)` | Provides a recognizable fixed target without perception |
| Inspection pose | `(5.5 m, 3.0 m, 0 rad)`, 0.7 m from the target boundary | Exceeds the specification's proposed minimum 0.5 m standoff |
| Simulation step | 50 ms | Matches the proposed planning period and keeps the trace compact; issue #3 may introduce a separate 5 ms physics step |
| Maximum speeds | 0.60 m/s linear, 0.80 rad/s angular | Reuses specification proposals without claiming validation |
| Inspection tolerances | 0.15 m position, 15° heading | Reuses proposed waypoint/inspection values |
| Stopped predicate | commanded and recorded linear/angular velocity both exactly zero in this ideal-kinematic slice | Avoids pretending issue #2 implements physical braking; issue #3 adopts physical thresholds |
| Inspection dwell | 1.0 simulated second | Reuses the specification proposal |
| Dock tolerances | 0.15 m position, 15° heading | Fills the specification's explicitly unresolved dock tolerance with a symmetric fixture |
| Success timeout | 120 simulated seconds | Reuses the specification proposal |
| Timeout fixture | 2 simulated seconds, expected outcome `timed_out` | Reliably exercises expected failure before target arrival |
| Seed | `20261027` | Stable explicit seed, even though this first controller uses no randomness |

Approval of this brief freezes these values for issue #2 fixtures only. Later validation may create a new configuration or scenario version rather than rewriting recorded evidence.

## Acceptance tests and runnable demonstration

The already-approved testing boundaries apply as follows:

- **Primary:** experiment runner inputs and observable outcomes, verdicts, traces, and saved run data.
- **Browser:** a small interaction/replay suite proving that a user can start a run and inspect the recorded phases and terminal result.
- **Not applicable yet:** focused numerical-runtime tests and provider contract checks, because issue #2 contains neither native inference nor integrations.

TDD behavior sequence:

1. A valid preset request completes inspection and return, emits the required ordered phases and one observation, and produces `mission_outcome=completed`, `test_verdict=passed`.
2. Repeating the identical request produces an identical canonical trace, observation, outcome, and verdict.
3. A short-timeout request ends once with `mission_outcome=timed_out`; an expected timeout passes and an expectation of completion fails.
4. The browser starts a run through the HTTP adapter and renders approach, alignment, stopped dwell, capture, return, dock, and terminal state from the recorded trace.
5. Browser replay controls pause, resume, restart, and scrub without mutating the run evidence.

Runnable demonstration:

```text
make setup
make dev
make check
```

The demonstration starts the successful run, replays it, then starts the expected-timeout run and shows its passing verdict despite the unsuccessful mission outcome. Tested package versions are pinned in `uv.lock` and `pnpm-lock.yaml`.

## Explicit boundaries from later issues

Issue #2 does **not** implement:

- obstacles, A*, range sensing, acceleration/braking physics, continuous collision checks, unreachable-target handling, or collision explanations (#3);
- SAM, masks, target phrases, ambiguity/missing-target behavior, or provider calls (#4);
- scene editing, scenario authoring/version creation, or photo-assisted scenes (#5–#6);
- multi-target missions (#7);
- learned collision-risk control, datasets, training, model artifacts, or risk thresholds (#8);
- C++ inference, native kernels, Apple Accelerate, worker settings, or performance measurements (#9–#12);
- asynchronous inference, observation age, modeled delays, queues, freshness, congestion, or memory admission (#13–#16);
- comparisons, configurable experiment editors, mission engineer behavior, exports, hosting, final evaluation, or demo packaging (#17–#23).

The code should leave clean seams for later extension, but issue #2 will not prefactor or add placeholder abstractions for those capabilities.

## Material questions for approval

1. **Freeze the proposed fixture geometry and values above for issue #2?** Recommendation: yes. They are deliberately simple, deterministic, and explicitly versioned rather than asserted as validated product defaults.
2. **Use ideal kinematic stopping in issue #2 and defer acceleration/braking physics to issue #3?** Recommendation: yes. This matches the ticket boundary while still making stopping and dwell observable.
3. **Return the complete recorded trace in the initial `POST /api/runs` response instead of adding artifact persistence now?** Recommendation: yes. It satisfies replay and determinism without pulling issue #20 storage/export scope forward.
4. **Treat a new `run_id` as metadata excluded from deterministic replay equality?** Recommendation: yes. The evidence should be identical while each execution remains a distinct run.

No material source contradiction was found. The only tension is intentional: `project.md` describes full-product perception and physical-control contracts, while issue #2 explicitly establishes the pre-perception, open-scene reference slice. The boundaries above preserve both sources.
