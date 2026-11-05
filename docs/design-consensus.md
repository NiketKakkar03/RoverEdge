# RoverEdge design discussion

Status: design confirmed by the user in Q48, October 27, 2026. This records the interview; project.md incorporates the agreed scope. Documentation is not implementation approval.

## Settled direction

- Build software for robotics engineers. The builder supplies no physical robot; integration with users' hardware is future work.
- Primary objective: establish when computation delays affect rover behavior and investigate their causes. Compare numerical implementations as supporting evidence; do not assume backend speed explains every delay or mission outcome. Negative findings are valid results.
- Provide single-target, multi-target, open/narrow/cluttered routes, missing/ambiguous/unreachable targets, and varied runtime conditions. Prioritize engineering test coverage and numerical calculations.
- Inspection produces an observation, target identity, pose, and completion status; automated defect judgments are not part of this agreed contract.
- Users can edit object positions, choose targets and runtime conditions, and save reproducible scenarios.
- Support photo-assisted rough scene construction with an editable preview and user-confirmed geometry, plus built-in scenarios and direct scene editing. The automatic drafting mechanism requires a feasibility test.
- Scene edits create scenario versions; each run uses a fixed scene.
- Photo drafts highlight uncertain geometry for correction before execution. After scene edits, recognition uses a fresh rendered scene image; the original photograph remains a reference.
- Retain naive, blocked, parallel, and Apple Accelerate inference backends and report results for all four.
- Compare numerical agreement, runtime performance, and mission behavior. Default backend comparisons hold model, inputs, scenario, and controller settings constant. Users can configure different tests; every comparison must preserve configuration provenance and identify changes.
- Offer controlled comparisons that vary one factor and exploratory comparisons that allow several changes. Use controlled comparisons for causal investigation.
- Hardware variation means benchmarking on compatible computers or editing modeled device profiles. Actual robot integration remains future work; Apple Accelerate is only measured where supported.
- Expose validated rover dimensions/motion limits, sensor range, planning frequency, backend/worker settings, queue policy, freshness limits, and modeled device costs. Initially fix rover type and model feature structure; identify configurations outside training conditions.
- Report observation age and a stage timeline for queue wait, dispatch, transfer, inference, and result consumption. Label durations as measured or modeled.
- Evaluate uncongested baseline, steady congestion, and brief congestion bursts across selected backends and queue policies.
- Use an agent to investigate completed runs with bounded, validated tools and autonomously explain outcomes and pass/fail criteria. Deterministic evaluation supplies the actual outcomes.
- When investigation is enabled, the agent may perform up to three allowed follow-up runs. It must report when a cause is not established.
- Investigations explain what happened, what evidence supports a cause, what change was tested, and whether it helped. Demonstrate the final answer through a visible before/after run comparison as well as metrics.
- Distinguish mission outcome from test verdict: correctly handling an impossible mission can pass its test. Freeze criteria before each test batch; the agent cannot relax them during evaluation.
- Automated coverage includes numerical kernels, model export, navigation/dynamics, perception failure cases, queues/freshness/memory, reproducibility, controlled comparisons, and bounded evidence-backed agent behavior.
- Require numerical agreement, deterministic simulation, scheduling semantics, and expected failure handling before presenting performance claims.
- Use a separate validation stage to propose collision-risk and mission-quality thresholds, then explicitly review and freeze the thresholds before untouched final test scenarios. Do not adjust criteria to match final results.
- Export a readable report plus configurations, metrics, and event traces. Preserve model identity, scenario version, hardware, backend settings, and timing provenance.
- Provide hosted portable simulation and recorded M1 comparisons, with local benchmark reproduction instructions. Optimize backend presentation for usefulness to engineers.
- First implementation gate: an actual SAM response selects a target and geometric navigation completes an inspection-and-return mission.
- Solo builder on an M1 Pro. Reserve November 3 for testing and demo preparation, with November 4 as the submission buffer under the existing proposal. User declines an hours estimate and requests completion of the full scope; schedule feasibility is not established by that commitment.
- Preserve the proposed MVP scope; do not silently remove features. Fine-tuning remains post-MVP and contingent on suitable access/credits and an identified need.
- Prioritize a complete, understandable submission over exhaustive optimization.

## Remaining verification and confirmation

- Photo drafting feasibility and exact geometry confirmation interaction.
- Concrete workload and numerical settings remain proposals in project.md; empirical thresholds require the agreed validation stage and review.
- Feasibility of the full scope before the protected testing/demo day, without an hours estimate.
- Final shared understanding is confirmed in Q48. Implementation has not been approved.

## Model-quality review in plain language

1. Split scene/episode families into training, validation, and final test sets before generating samples. Nearby snapshots from one family must not leak across these groups.
2. Training teaches the model from example actions and their collision labels.
3. Validation is practice evaluation: inspect missed hazards and unnecessary stops, choose a risk-score cutoff, and assess mission behavior. A low collision count alone is insufficient if the rover never completes tasks.
4. Propose and review minimum acceptable quality and freeze the model, cutoff, evaluation criteria, and test protocol before final testing. Report weak validation performance rather than weakening expectations merely to pass.
5. Final test scenarios provide the independent report. A failed final test stays in the report; subsequent tuning requires a new model version and a new untouched final test set for a fresh independent claim.

The risk-score cutoff controls which candidate actions the rover considers. Evaluation acceptance thresholds judge model/mission quality; these are different thresholds.

## Discussion process

Present multiple batches of independent questions together. Record resolved terminology as it settles; avoid treating recommendations or unresolved questions as approvals.

## Architecture decision records

The specification above and project.md contain the full agreed requirements. ADRs preserve the rationale for selected consequential boundaries, rather than duplicating every requirement:

- [0001: Measured versus modeled time](adr/0001-distinguish-measured-and-modeled-time.md)
- [0002: Confirmed scene geometry and visual target grounding](adr/0002-confirm-scene-geometry.md)
- [0003: Agent authority outside the driving loop](adr/0003-bound-agent-authority.md)
- [0004: Reproducible runs and frozen evaluation](adr/0004-preserve-experiment-evidence.md)
- [0005: Model-assisted risk-data governance](adr/0005-model-assisted-risk-data-governance.md)
- [0006: Learned risk with deterministic command admission](adr/0006-compose-learned-risk-with-deterministic-command-admission.md)
