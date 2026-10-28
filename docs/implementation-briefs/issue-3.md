# Issue #3 implementation brief — obstacle navigation and physical mission failures

**Issue:** [#3 — Navigate obstacles and explain physical mission failures](https://github.com/NiketKakkar03/RoverEdge/issues/3)

**Status:** Approved and implemented on 2026-10-27. Full verification and separate Standards
and Spec reviews passed; the scoped commit records the final implementation.

**Implementation boundary:** Extend the merged issue #2 experiment runner and recorded replay with deterministic static obstacles, differential-drive dynamics, ideal range sensing, known-map A* routing, braking, swept collision checks, and explicit collision/unreachable terminal outcomes.

## User-visible behavior

1. The browser offers open, narrow, and cluttered built-in scenario versions without adding a general scene editor.
2. Starting a run sends the selected fixed scenario version and complete dynamics/planning configuration through the existing experiment runner.
3. Successful runs visibly follow a planned route, approach and inspect the preset target, and return to the dock under acceleration, braking, and angular-acceleration limits.
4. Replay shows static obstacles, route waypoints, ideal range rays, rover pose and heading, current velocity, braking, collision contact when applicable, and the terminal explanation.
5. An unreachable fixture terminates before motion with `mission_outcome=unreachable`; a declared expectation of `unreachable` produces `test_verdict=passed`.
6. A deterministic insufficient-stopping-distance fixture records braking followed by swept collision contact and terminates with `mission_outcome=collision`; a declared expectation of `collision` produces `test_verdict=passed`.
7. Timeout remains supported. Collision, unreachable, and timeout remain mission outcomes rather than exceptions, and none is mislabeled as mission completion.
8. Repeating the same scenario version, seeds, configuration, and expectation reproduces the canonical route, sensor samples, motion trace, collision/unreachable evidence, outcome, and verdict.

This issue deliberately improves technical simulation readability only. The broader rover/world and website visual-design concerns remain deferred to issue #25.

## Source contracts

- `project.md` §4 **Architecture**: keep simulation, experiment runner, recorder, and browser responsibilities separate.
- `project.md` §6 **Robotics and perception contract**: deterministic flat static world; one differential-drive rover; known map and pose; ideal range sensing; collision-free standoff; physical braking; collision checks between physics samples.
- `project.md` §11 **Testing and evaluation**: public-run coverage for ray geometry, braking distance, collision between samples, terminal states, impossible missions, and deterministic replay.
- `docs/roveredge-spec.md` **Implementation Decisions** and **Testing Decisions**: geometric global routing, declared dynamics, visible failure handling, and mission-outcome/test-verdict separation.
- `docs/adr/0004-preserve-experiment-evidence.md`: fixed scenario versions and complete configuration; failed outcomes remain recorded evidence.
- `GLOSSARY.md`: preserve the distinctions among scenario, scenario version, mission, run, mission outcome, and test verdict.

ADR 0002 will govern later target grounding but does not require SAM in this issue. ADRs 0001 and 0003 remain inapplicable because there is no measured/modeled inference timing or mission engineer.

## Proposed public-interface changes

Extend the existing transport-independent runner types rather than adding a second simulation entry point.

```text
Scenario
  scenario_version
  map_bounds_m
  dock_pose
  rover_initial_state: pose + linear/angular velocity
  target + inspection_pose
  obstacles: axis-aligned rectangles with stable IDs

RunConfiguration
  physics_step_s
  planning_period_s
  rover_radius_m
  max_linear_speed_mps / max_angular_speed_radps
  max_linear_acceleration_mps2 / max_braking_deceleration_mps2
  max_angular_acceleration_radps2
  range_ray_count / range_max_m
  route_grid_resolution_m / planning_clearance_m
  existing inspection, dock, and timeout configuration

RunResult
  existing identity, request, observations, outcome, verdict, terminal reason
  planned_route: waypoint list
  trace events containing pose, velocities, commanded velocities, ranges, and event detail
  terminal_failure: optional structured code, message, pose, obstacle ID/contact point
```

Extend `MissionOutcome` with `collision` and `unreachable`. Extend trace kinds with route-planned, range-sampled, braking-started, collision, and terminal evidence only where those events actually occur. The HTTP API continues to return fixed server-owned scenario documents and accepts a complete saved run request.

Unsupported scenario versions, target identities, malformed geometry, or invalid numeric configuration remain validation errors rather than recorded mission outcomes. `unreachable` means a valid fixed scenario for which no route exists.

## Minimal implementation structure

- `scenarios`: one server-owned registry for scenario geometry, initial conditions, target/inspection pose, and default request. This resolves the issue #2 review note about duplicated preset geometry before multiple presets amplify it.
- `geometry`: ray/rectangle intersection, circle/rectangle overlap, segment intersection against rover-radius-inflated rectangles, angle/distance helpers.
- `planning`: deterministic occupancy-grid construction, obstacle inflation, A* route search, stable neighbor/tie ordering, and waypoint simplification only if proven by public behavior.
- `simulation`: fixed-step differential-drive state integration, acceleration/braking limits, command updates at the planning period, ideal range scans, swept collision detection, and terminal-state precedence.
- `experiment`: mission phase orchestration, route-to-target and route-to-dock requests, evidence recording, outcome/verdict evaluation.
- Existing FastAPI and TypeScript/Canvas adapters consume the extended public documents and trace; they do not implement physics or planning independently.

## Scenario geometry

All geometry below is proposed, versioned fixture data—not measured warehouse geometry or validated robot safety data.

Common geometry retains the issue #2 8 m × 6 m map, dock/start pose `(1.0, 3.0, 0 rad)`, target footprint centered at `(6.5, 3.0)`, and inspection pose `(5.5, 3.0, 0 rad)`.

| Scenario version | Proposed obstacles `(x_min, y_min)–(x_max, y_max)` | Intended behavior |
| --- | --- | --- |
| `preset-open-v2` | None | Straight successful inspection and return under physical dynamics |
| `preset-narrow-v1` | Upper block `(2.5, 3.4)–(5.0, 5.5)`; lower block `(2.5, 0.5)–(5.0, 2.6)` | Successful 0.8 m-wide corridor traversal |
| `preset-cluttered-v1` | A `(2.5, 2.2)–(3.2, 4.5)`; B `(4.0, 0.8)–(4.7, 2.2)`; C `(5.2, 3.6)–(5.8, 5.0)` | Successful deterministic multi-turn route |
| `fixture-unreachable-v1` | Full barrier `(3.5, 0.0)–(3.8, 6.0)` | Planner reports no route before rover motion |
| `fixture-collision-stop-v1` | Near obstacle `(1.3, 2.5)–(1.6, 3.5)`; rover starts at `(1.0, 3.0, 0 rad)` with `0.6 m/s` linear velocity | Immediate braking cannot prevent swept collision |

Before implementation, route feasibility will be checked against the approved inflation/grid rules. If a coordinate adjustment is required to produce the stated behavior, update this brief and fixture version rather than silently changing geometry.

## Planning, sensing, motion, and terminal contracts

- **Known-map planning:** A* runs over a fixed 2D grid whose occupied cells include map boundaries and obstacles inflated by rover radius plus planning clearance. Neighbor order and cost/tie ordering are fixed so routes reproduce exactly. Plan separately to the inspection pose and back to the dock.
- **Ideal range sensing:** rays originate at rover center, rotate with rover heading, cover 360° uniformly, and return the nearest map-boundary or obstacle distance capped at maximum range. Readings are noiseless and do not reveal target identity.
- **Controller:** a deterministic geometric waypoint follower produces desired linear/angular velocities. It may request forward motion only when heading error is within the route-following tolerance. Forward range and stopping distance trigger braking; no learned scoring is introduced.
- **Dynamics:** desired velocities are approached subject to linear/angular acceleration limits. Reducing positive forward speed uses the braking deceleration. Pose integration occurs at the physics step; planning/control and range evidence update at the planning period.
- **Braking:** stopping distance for a current forward speed `v` is `v²/(2a)` using the configured braking magnitude. Braking is not instantaneous and does not retroactively avoid contact.
- **Collision:** the circular rover is tested against map boundaries and obstacle rectangles throughout each integrated motion segment by inflating obstacles by rover radius and intersecting the rover-center sweep. The first contact time/point and obstacle ID are recorded. Collision takes terminal precedence over later phase transitions at the same interval.
- **Unreachable:** failure to find either required route terminates with a structured explanation before entering the corresponding motion phase. No fabricated straight-line fallback is allowed.
- **Terminal states:** completed, collision, unreachable, and timed-out states are immutable and emit exactly one terminal event. Verdict evaluation compares the outcome with the expectation frozen in the request.
- **Replay:** obstacle, route, range, braking, and failure visuals derive only from recorded scenario/result evidence. Playback speed and scrubbing never recompute physics.

## Approved declared values

The project specification labels these as proposals. The user approved all five material
decisions for issue #3 on 2026-10-27. These values are frozen for these scenario versions and
public tests; they are declared simulation parameters, not empirically validated safety limits.

| Decision | Recommendation | Rationale |
| --- | --- | --- |
| Physics / planning periods | 5 ms / 50 ms | Adopt the project proposals and separate integration from control updates |
| Rover footprint | Circle, 0.20 m radius | Adopt the project proposal and enable exact inflated-rectangle collision tests |
| Speed limits | 0.60 m/s linear, 0.80 rad/s angular | Retain issue #2/specification values |
| Linear acceleration / braking | 0.80 / 1.20 m/s² | Adopt the project proposals and make stopping-distance behavior explicit |
| Angular acceleration | 1.60 rad/s² | Adopt the project proposal |
| Range sensor | 16 uniform rays, 4 m maximum, no noise/dropout | Adopt the project proposal; include map boundaries as returns |
| Stopped condition | `|v| ≤ 0.02 m/s`, `|ω| ≤ 0.05 rad/s` | Adopt the project proposal instead of issue #2's ideal zero-command shortcut |
| Occupancy-grid resolution | 0.10 m | Bounded, readable A* workload for the 8 m × 6 m maps |
| Planning clearance | 0.05 m beyond the 0.20 m rover radius | Avoid boundary-grazing paths while preserving the proposed narrow corridor |
| A* connectivity | 8-connected; cardinal cost `1`, diagonal cost `√2`; Euclidean heuristic | Produces shorter geometric routes with deterministic fixed neighbor order |
| Route-following heading gate | 15° | Reuse the approved inspection-heading proposal for forward-motion admission |
| Terminal precedence | collision, then timeout, then mission-phase completion | Physical contact must not be hidden by a simultaneous success/timeout transition |

## Acceptance tests and runnable demonstration

The already-approved testing boundaries remain unchanged:

- **Primary:** complete runner requests and observable results, including route, sensor/motion trace, terminal outcome, verdict, and reproducibility evidence.
- **Browser:** a small suite for scenario selection and recorded replay of successful and expected physical failures.
- **Not applicable yet:** numerical-runtime and provider contract tests.

Planned TDD slices:

1. A public open-scenario run accelerates, brakes, satisfies stopped/dwell/dock predicates, and completes deterministically.
2. Known literal ray fixtures verify nearest rectangle/boundary hits, rotations, and maximum-range clipping.
3. Known literal motion fixtures verify acceleration and `v²/(2a)` stopping distance.
4. The narrow and cluttered saved scenarios produce deterministic collision-free routes and complete inspection/return.
5. Segment-sweep fixtures detect a collision that endpoint-only overlap would miss; a collision run records contact and a passing expected-failure verdict.
6. An unreachable saved scenario emits no motion samples, records the route failure, and passes when unreachable was expected.
7. Terminal precedence and immutability cover collision/timeout/phase boundaries without duplicate terminal events.
8. Browser/API tests select each preset, serialize the server-owned request, render obstacles/routes/ranges, and visibly distinguish completed, collision, unreachable, and timeout outcomes.

Demonstration remains:

```text
make setup
make dev
make check
```

The browser demonstration will run one successful obstacle scenario and the expected collision and unreachable fixtures. It will not attempt the broader visual redesign tracked in issue #25.

## Explicit boundaries from later issues

Issue #3 does **not** implement:

- SAM, target phrases/masks, missing/ambiguous perception, or provider calls (#4);
- scene editing, version creation, or photo-assisted scenes (#5–#6);
- multiple required targets (#7);
- learned collision-risk scoring, datasets, training, or quality thresholds (#8);
- native inference, Apple Accelerate, worker settings, or latency measurement (#9–#13);
- modeled delay, queues, freshness, congestion, or memory admission (#14–#16);
- comparisons, configurable experiment editors, mission engineer behavior, exports, hosting, or evaluation (#17–#23);
- the deferred rover/world and website visual redesign (#25).

The geometric controller, ideal sensing, static axis-aligned obstacles, and single rover remain deliberately narrow reference implementations for later comparisons.

## Approved material decisions

1. Freeze the proposed dynamics and sensor values from `project.md` for issue #3 fixtures.
2. Use a 0.10 m, 8-connected A* grid with 0.05 m clearance beyond the circular rover radius.
3. Use axis-aligned rectangle obstacles with swept circle-versus-inflated-rectangle collision checks.
4. Add the two explicit expected-failure fixtures alongside the three successful route presets.
5. Keep browser changes functional and evidence-oriented; defer broad visual polish to issue #25.

Route-feasibility verification did not require changing the approved scenario coordinates or
version identifiers.

No material source contradiction was found. The issue narrows the full-product contract to a geometric reference controller; learned local risk scoring remains explicitly assigned to issue #8.

## Completion evidence

- `make check`: 21 Python tests and 5 browser tests passed; strict mypy, Ruff, TypeScript,
  and the production web build passed.
- Demonstrated outcomes: open, narrow, and cluttered presets complete; unreachable and
  insufficient-stopping-distance fixtures produce passing expected failures.
- Standards review: all boundary collision, dock-tolerance, replay-evidence, and first-contact
  timing findings were resolved; no blockers remain.
- Spec review: all sensing/braking, swept collision, replay/contact, structured evidence, and
  terminal-precedence findings were resolved; no blockers remain.
