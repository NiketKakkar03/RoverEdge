# RoverEdge: reproducible rover experiments under computation delays

## Problem Statement

Robotics engineers need to understand when delayed inference changes robot behavior and which part of the runtime causes the delay. A fast matrix benchmark alone does not explain whether a rover completes a mission, acts on stale observations, or spends its time waiting in a queue. Engineers need reproducible software experiments that connect numerical correctness, execution performance, and mission outcomes without requiring physical hardware or conflating hypothetical devices with measured computers.

## Solution

Provide a browser-accessible software environment for creating simulated inspection scenarios, requesting missions, comparing four inference backends, and investigating computation delays. Engineers can use presets, edit scenes directly, or turn photographs into rough scene drafts whose geometry they confirm. A rover locates targets using actual visual segmentation, navigates through a known map using geometric planning and learned local collision-risk scoring, captures inspection observations, and returns to its dock.

Runs preserve their scenario version, model, configuration, evidence, and timing provenance. Controlled comparisons vary one factor; exploratory comparisons show multiple configuration differences. A bounded mission engineer investigates completed runs and demonstrates whether an allowed change helped through before/after mission playback and recorded metrics. Negative findings and unresolved causes are valid results.

## User Stories

1. As a robotics engineer, I want to run experiments entirely in software, so that I can investigate behavior without supplying a physical robot.
2. As a robotics engineer, I want built-in scenarios, so that I can begin with repeatable examples.
3. As a robotics engineer, I want to create a scene directly, so that I can represent a layout relevant to my experiment.
4. As a robotics engineer, I want to upload a photograph for a rough scene draft, so that I can start from a recognizable environment.
5. As a robotics engineer, I want uncertain photo-derived geometry highlighted, so that I can correct assumptions before running calculations.
6. As a robotics engineer, I want to confirm scale, obstacles, dock, and targets, so that the simulated geometry is explicit.
7. As a robotics engineer, I want to edit object positions and save scenario versions, so that experiments can refer to exact arrangements.
8. As a robotics engineer, I want each run to use a fixed scene, so that scene edits cannot invalidate an ongoing comparison.
9. As a robotics engineer, I want to request inspection of a named target, so that I can express a meaningful mission.
10. As a robotics engineer, I want actual segmentation of the current rendered scene to locate the target, so that perception contributes to mission preparation.
11. As a robotics engineer, I want target recognition refreshed after edits, so that recognition matches the simulated environment.
12. As a robotics engineer, I want missing or ambiguous targets reported, so that the system does not silently select an unintended object.
13. As a robotics engineer, I want single-target and multi-target missions, so that I can exercise different task demands.
14. As a robotics engineer, I want open, narrow, and cluttered routes, so that my tests cover varied navigation conditions.
15. As a robotics engineer, I want unreachable-target cases, so that I can verify expected failure handling.
16. As a robotics engineer, I want the rover to approach, face the target, stop, and capture an observation, so that inspection completion has observable conditions.
17. As a robotics engineer, I want observations associated with target identity and rover pose, so that I can inspect the evidence of a completed visit.
18. As a robotics engineer, I want the rover to return to its dock, so that a mission represents a complete task.
19. As a robotics engineer, I want mission outcome distinguished from test verdict, so that an expected mission failure can pass its test.
20. As a robotics engineer, I want configurable rover dimensions, motion limits, sensor range, and planning frequency, so that I can explore relevant operating conditions.
21. As a robotics engineer, I want configurations outside the model's training conditions identified, so that I do not confuse configurability with validated model quality.
22. As a robotics engineer, I want naive, blocked, parallel blocked, and Apple Accelerate backends, so that I can compare numerical implementations of the same model.
23. As a robotics engineer, I want output agreement and command disagreements reported, so that speed comparisons do not hide correctness differences.
24. As a robotics engineer, I want identical saved-input workloads across backends, so that execution measurements are comparable.
25. As a robotics engineer, I want runtime distributions and worker settings, so that I can assess whether parallelism helps the workload.
26. As a robotics engineer, I want actual M1 measurements separated from hosted measurements, so that machine differences are visible.
27. As a robotics engineer, I want modeled device profiles, so that I can explore declared resource constraints without claiming measurements on an unavailable board.
28. As a robotics engineer, I want to reproduce portable benchmarks on compatible computers, so that I can collect results for my own machine.
29. As a robotics engineer, I want FIFO and latest-pending-observation policies, so that I can compare queue behavior.
30. As a robotics engineer, I want configurable freshness limits and modeled device costs, so that I can study delayed decisions.
31. As a robotics engineer, I want uncongested, steady-congestion, and burst-congestion conditions, so that I can inspect different load patterns.
32. As a robotics engineer, I want observation age and a stage-level timing timeline, so that I can distinguish computation time from waiting and delivery delays.
33. As a robotics engineer, I want queue drops, expired results, and memory rejections recorded, so that missing decisions remain visible.
34. As a robotics engineer, I want a controlled comparison that varies one factor, so that I can investigate a specific explanation.
35. As a robotics engineer, I want an exploratory comparison with all configuration differences listed, so that I can compare broader changes without overstating causality.
36. As a robotics engineer, I want test criteria fixed before a batch begins, so that outcomes cannot redefine what passing means.
37. As a robotics engineer, I want an optional autonomous investigation after a degraded run, so that I can explore evidence without manually inspecting every trace event.
38. As a robotics engineer, I want the mission engineer limited to validated tools and three follow-up runs, so that investigations stay bounded.
39. As a robotics engineer, I want the mission engineer to explain what happened and cite supporting evidence, so that I can verify its reasoning.
40. As a robotics engineer, I want a tested change demonstrated through comparable before/after playback, so that I can see whether it helped.
41. As a robotics engineer, I want unchanged or worse outcomes and uncertain causes reported honestly, so that explanations do not invent improvements.
42. As a robotics engineer, I want training, validation, and untouched final testing separated, so that quality claims reflect unseen scenarios.
43. As a robotics engineer, I want quality requirements to consider both missed hazards and mission progress, so that a rover that never moves does not appear successful.
44. As a robotics engineer, I want numerical and simulation correctness gates before performance claims, so that comparisons describe valid implementations.
45. As a robotics engineer, I want reports, configurations, metrics, and event traces exported, so that I can reproduce or independently examine findings.
46. As a demo viewer, I want a hosted browser experience, so that I can inspect missions and results without accessing the builder's laptop.
47. As a demo viewer, I want live, recorded, and modeled results clearly labeled, so that I understand what the demonstration establishes.
48. As a demo viewer, I want a saved replay when a cloud call fails, so that I can still inspect a clearly labeled completed experiment.
49. As a project maintainer, I want reproducibility instructions and contribution provenance, so that others can inspect the event-built work and its dependencies.

## Implementation Decisions

- **Current state:** the repository contains design documents and no implementation or existing test harness. Build ordinary modules with explicit responsibilities rather than a generalized robotics platform. No completed capability or benchmark result is claimed.
- **Scene preparation:** support presets, direct editing, photo-assisted drafts, uncertainty highlighting, and user-confirmed geometry. Save a new scenario version when the scene changes. Automatic drafting requires a feasibility gate and does not promise metric reconstruction from one photograph.
- **Perception boundary:** provide the fresh rendered image and a concrete target phrase to Meta SAM; use its returned mask to select the target. The confirmed map provides traversability. Known camera geometry converts mask boundaries to collision-free inspection standoffs; hidden object identifiers must not replace recognition. Initial categories require actual segmentation tests.
- **Simulation and control:** use a deterministic flat static world, one differential-drive rover, known pose, and simulated range sensing. A geometric route planner supplies waypoints; a small learned model scores candidate commands for local collision risk. Prefer progress among acceptable candidates with deterministic tie handling. Brake when no candidate qualifies or no fresh decision is available, respecting physical deceleration and collision checks between samples.
- **Mission contract:** support single/multiple required targets, inspection heading and stopping conditions, a dwell, observation capture, return-to-dock, collision failure, and timeout. Expected missing, ambiguous, or unreachable-target handling can produce a passing test verdict despite an unsuccessful mission outcome. Inspection does not diagnose defects.
- **Model pipeline:** generate collision labels using declared immediate-action rollouts, separate scene/episode families before sampling, and fit preprocessing only on training data. Keep feature order, normalization, activations, shapes, dtype, model version, and hash in the model artifact. Initial architecture and dynamics values remain proposed numerical defaults until validated and frozen.
- **Model-assisted data curation:** Meta models may propose bounded scenario templates, trace clusters, and data-quality summaries from recorded training or validation evidence. Deterministic validation assigns split identity and simulator rollouts produce every collision label. Providers never supply labels, driving commands, frozen criteria, or final verdicts; retain prompt/response hashes and reviewer decisions for every accepted or rejected proposal.
- **Numerical runtime:** implement fresh naive, blocked, and parallel blocked FP32 matrix kernels, with Apple Accelerate as the fourth backend. Use resident model weights and reusable buffers, batch candidate evaluation, and prevent overlapping calls from sharing writable workspaces. Verify reference agreement and command decisions before benchmarking.
- **Execution modes:** retain saved-input native replay benchmarks, actual asynchronous native closed-loop execution, and deterministic virtual closed-loop execution. Native closed-loop simulation is wall-clock paced and records overruns. Virtual completion follows declared modeled durations without adding host computation time.
- **Modeled device:** initially one execution lane with serial dispatch, input transfer, compute, and output transfer; resident weights; bounded pending capacity; explicit modeled memory admission and release. FIFO rejects new work when full; latest-pending replaces waiting work for the rover without canceling executing work.
- **Freshness and identity:** distinguish reporting deadlines from hard observation-age limits. Check expiry before dispatch and at command consumption; older results cannot replace newer accepted results. Record episode, observation, request, candidate-set, and model identity. Freeze simultaneous-event ordering and boundary semantics before evaluation.
- **User configuration:** validate rover dimensions/motion limits, sensor range, planning frequency, backend/worker settings, queue policy, freshness limits, and modeled device costs. Keep the initial rover type and feature structure fixed. Mark settings outside training conditions. Hardware changes mean compatible-computer benchmarks or modeled profiles, not physical robot integration.
- **Experiment runner:** accept a fixed scenario version, mission, model, runtime configuration, seeds, execution mode, and predeclared expectations. Produce a run identifier, mission outcome, test verdict, metrics, trace, and reproducibility metadata. This is the proposed principal testing interface; exact transport and schema are implementation work.
- **Comparisons:** controlled comparisons hold other declared conditions fixed while varying one selected factor. Exploratory comparisons display every configuration difference and do not isolate causality. Compare all four backends on the same M1 Pro; show other computers separately. Report numerical command differences so behavioral changes are not automatically attributed to timing.
- **Investigation authority:** the mission engineer acts before or between runs through target location, episode execution, trace inspection, latency breakdown, allowed runtime configuration, and comparison tools. When enabled, it can perform at most three follow-up runs changing permitted backend or queue settings. It cannot drive the rover, alter frozen criteria, change the mission objective, or claim unsupported outcomes.
- **Investigation output:** explain what happened, the evidence supporting a cause, the tested change, and whether it helped. Link explanations to actual runs and trace events. Demonstrate the last answer with comparable before/after playback and metrics, including unchanged or worse outcomes. Report when a cause is not established.
- **Evaluation governance:** distinguish the risk cutoff used to select actions from minimum quality requirements used to judge the model and missions. Use validation to propose settings and quality requirements, explicitly review them, then freeze model and protocol before untouched final tests. Preserve failures; tuning after final evaluation requires a new independent test set for a fresh independent claim.
- **Reporting:** expose numerical agreement, runtime performance, and mission behavior together. Include observation age, queue wait, dispatch, transfers, inference, and result consumption with measured/modeled provenance. Do not invent unavailable native stage measurements. Record mission completion, collisions, timeouts, inspection completion, distance, stops, model-quality metrics, deadline misses, drops, and memory rejections.
- **Artifact contracts:** export readable reports and machine-readable configuration, metrics, traces, and manifests carrying scenario version, model identity, hardware, compiler/runtime settings, seeds, sample counts, and timing boundaries. Preserve criteria and original failed results.
- **Hosting:** provide portable hosted simulation and replay of labeled local M1 measurements; no inbound laptop connection is required. Apple Accelerate is used only where supported. Recorded API responses, recorded runs, modeled execution, and accelerated playback are labeled.
- **Planned stack:** Python/NumPy simulation and experiments; PyTorch training; C++20/CMake with Python bindings for native inference; TypeScript/Canvas browser interface; FastAPI and Modal for hosting/batch work; versioned artifacts and storage as needed. Verify package versions and provider access during setup rather than treating the proposal as tested compatibility.
- **Providers:** Meta SAM supplies target grounding; the planned Baseten Meta model supplies mission/investigation tool use. Validate the event-specific endpoint with the actual account. A tested Meta-hosted reasoning fallback must be labeled accurately. Fireworks is optional and fine-tuning is post-MVP.

## Testing Decisions

- **Confirmed testing seams:** use the experiment runner as the primary public boundary: submit scenario, mission, and configuration; assert outcomes, verdicts, traces, comparisons, and export contents. Add focused public numerical-runtime tests for output correctness and malformed inputs, provider contract smoke tests for actual integrations, and a small browser suite for scene editing and playback. No existing implementation seams or test prior art exist to reuse.
- Test observable behavior and contract invariants, not private functions, internal call sequences, or incidental implementation structure. Prefer complete representative runs to tests that reproduce the implementation's logic.
- At the experiment boundary, verify deterministic replay, mission completion conditions, multi-target visits, braking and collisions, impossible missions, expected perception failures, fixed scenario versions, and mission-outcome/test-verdict separation.
- Exercise zero load, steady load, bursts, pending overflow, replacement, expiry, simultaneous timestamps, exact admission boundaries, memory release, stale command handling, and no host-time double counting. Include admitted, completed, and dropped work in deadline accounting.
- At the public numerical boundary, compare rectangular products, block tails, worker counts, layer outputs, logits, scores, and selected commands against a trusted reference. Reject malformed artifacts and nonfinite inputs. Numerical tolerance and timing validity limits are proposed until validated and frozen.
- Verify dataset separation, preprocessing provenance, feature ordering, and labeling semantics; assess missed hazards and unnecessary braking on validation scenes before the untouched final evaluation. Concrete quality thresholds require the agreed later review.
- For model-assisted scenario proposals, verify schema/geometry/reachability validation, family-split isolation, prompt and response provenance, rejected-proposal retention, and that no provider receives or infers final-family material.
- Use genuine provider smoke tests for image/mask behavior and tool use; freeze responses for repeatable offline experiments and label fixtures. Test absent/ambiguous targets and target-position variation. Offline fixtures alone do not demonstrate live provider functionality.
- Test the mission engineer through validated tools and produced artifacts: invalid arguments, unsupported settings, budget exhaustion, evidence references, unchanged criteria, and honest inconclusive findings. Compare bounded investigations with a simple fixed queue-policy rule on held-out scenarios.
- Browser checks cover photo-draft correction, geometry confirmation, direct scene editing, scenario versions, fresh rendered perception, readable provenance, replay fallback, exports, and before/after comparisons linked to the same recorded results.
- Require correctness gates before performance claims. Use identical warmed inputs for backend timing, paired scenarios for controlled comparisons, stated sample counts, and uncertainty across runs. Do not present small samples as reliable tail-latency estimates or simulation outcomes as physical-robot safety evidence.
- First integration acceptance gate: a real SAM mask identifies a target and geometric navigation completes inspection and return, with missing/ambiguous cases handled. Final acceptance includes the agreed mission catalog, scene workflow, all four backends, configurable experiments, bounded investigations, visible comparisons, exports, and reproducibility instructions.

## Out of Scope

- Physical robot deployment, hardware connections, ROS integration, SLAM, automatic metric reconstruction, and validated claims about particular embedded boards.
- Dynamic people/obstacles during a run, multiple rovers, photorealistic 3D or MuJoCo, and automated defect diagnosis.
- Multiple agents, direct language-model wheel commands, live controller rewriting, and agent changes to frozen objectives or evaluation criteria.
- GPU kernel development, persistent thread pools, temporal models, distributed training, ISA/RTL work, and exhaustive low-level optimization.
- Fine-tuning until after MVP, contingent on suitable access/credits, evidence of a deficiency, license review, and independent evaluation data. Hosted Meta SAM grounding remains zero-shot; Fireworks is not a dependency.
- Guaranteed custom-kernel speedups, guaranteed mission improvement, real-world safety certification, and unsupported causal claims from exploratory comparisons.

## Further Notes

- The user confirmed the design in Q48. This request authorizes specification preparation and the skill's issue publication workflow, not implementation, deployment, or hackathon submission.
- The solo builder uses an M1 Pro. Target implementation completion by November 2, reserve November 3 for testing/demo preparation, and retain November 4 as submission buffer. Preserve agreed scope; report gate failures rather than silently removing features. These are planning targets, not proven feasibility.
- The event deadline recorded in the design is November 4 at 9 PM Eastern; recheck participant rules before submission. Credits, endpoint access, photo drafting quality, and synthetic-target segmentation require actual verification.
- Exact physics defaults, model sizes, sample counts, numerical tolerances, pacing limits, and quality requirements must remain labeled proposals until the relevant validation gate; this specification does not convert recommendations into measurements.
- The user confirmed the testing seams and GitHub tracker setup for NiketKakkar03/RoverEdge. The specification uses the generic ready-for-agent triage label without an assignee or automation configuration; implementation authorization remains separate.
