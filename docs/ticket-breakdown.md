# RoverEdge ticket breakdown — published

Source: https://github.com/NiketKakkar03/RoverEdge/issues/1 (full body read; no comments at drafting).

Numbers below are planning identifiers, not GitHub issue numbers. All 22 tickets are published as unassigned ready-for-agent sub-issues of issue #1 with native blocking relationships. This publication does not start implementation. The parent title, body, and state were preserved.

Each slice includes the smallest complete user-visible path, persisted inputs/results where applicable, and tests at the agreed public boundaries. Extend the initial runner and browser rather than splitting infrastructure, API, UI, and tests into separate horizontal tickets. Use the project glossary and existing ADRs throughout. No prefactoring is needed because there is no implementation yet.

## 1. Run and replay a deterministic inspection mission

**Blocked by:** None.

**What to build:** Select one built-in open scene and a preset target, execute a geometric inspection-and-return mission, and inspect its recorded browser replay. This is explicitly the pre-perception reference controller.

- [ ] The browser starts a run through the experiment runner and displays approach, heading, stopping/dwell, observation capture, return, and terminal outcome.
- [ ] Saved inputs include scenario version, seeds, configuration, and declared expectations; output includes run identity, trace, mission outcome, and test verdict.
- [ ] Repeat execution reproduces the deterministic trace; timeout and expected failure verdicts are exercised. Establish minimal runnable setup and automated checks as part of this path.

## 2. Navigate obstacles and explain physical mission failures

**Blocked by:** 1.

**What to build:** Run open, narrow, and cluttered presets with range sensing, route planning, acceleration/braking, and visible failure explanations.

- [ ] Known-map route planning and ideal range sensing support the declared rover dynamics; physical and planning defaults are documented and frozen for these tests.
- [ ] Public-run tests cover ray geometry, braking distance, collisions between samples, unreachable targets, and terminal-state handling.
- [ ] Browser replay identifies collision, timeout, and unreachable outcomes; a correct expected failure can pass its test.

## 3. Ground an inspection request with actual SAM perception

**Blocked by:** 2.

**What to build:** Enter a target phrase, see an actual SAM mask from the rendered scene, and run the resulting inspection mission.

- [ ] Verify actual provider access and at least two initial target categories; save request/response provenance without credentials.
- [ ] Convert mask boundaries through known camera geometry into valid standoffs; hidden object IDs do not substitute for recognition.
- [ ] Demonstrate position variation, missing and ambiguous targets, and complete inspection/return; label recorded responses and offer an honest replay fallback.

## 4. Edit and version scenes before running missions

**Blocked by:** 3.

**What to build:** Create or edit a scene in the browser, confirm its geometry, save a version, and run perception and navigation against that version.

- [ ] Edit scale, obstacle footprints, dock, and targets, including starting from an empty scene or a preset.
- [ ] Edits create versions and never mutate an active run; target grounding uses the new rendered image.
- [ ] Reloading a saved scene reproduces the confirmed geometry and a corresponding mission; invalid geometry receives actionable validation.

## 5. Turn a photograph into a confirmed runnable scene

**Blocked by:** 4.

**What to build:** Upload a photograph, inspect a rough generated scene draft, correct uncertain geometry, and execute a mission in the confirmed scene.

- [ ] Test and implement a feasible drafting method; do not claim automatic metric reconstruction or present manual entry as automatic generation.
- [ ] Highlight uncertainty and require scale/geometry confirmation; incomplete drafts can be corrected before execution.
- [ ] Preserve the photo as a reference while perception uses the current rendered scene; a representative photo-to-mission browser test passes.

## 6. Inspect multiple targets and exercise mission variants

**Blocked by:** 3.

**What to build:** Select a sequence of required targets, inspect each, and return, with per-target observations and explicit incomplete outcomes.

- [ ] Record target identity, pose, dwell/inspection completion, and evidence for every required visit.
- [ ] Demonstrate multi-target missions over varied built-in routes and missing, ambiguous, or unreachable target cases.
- [ ] Test completion, timeout, and partial-progress reporting without calling a partial mission fully successful.

## 7. Run a learned collision-risk controller with validation evidence

**Blocked by:** 2.

**What to build:** Generate a separated dataset, train a small risk model, and compare learned versus geometric reference missions in the existing runner and viewer.

- [ ] Split scene/episode families before sampling, use training-only normalization, and preserve label-rollout and feature-order contracts; retain an untouched final test manifest.
- [ ] Export a versioned model and evaluate candidate commands with deterministic progress/risk/tie behavior, including braking when none qualifies.
- [ ] Show validation missed hazards, unnecessary stops, and mission progress; propose quality requirements for later review without consuming final test scenarios. Preserve artifact and training provenance, including actual Modal execution where used.

## 8. Execute a mission with fresh naive C++ inference

**Blocked by:** 7.

**What to build:** Select native naive inference, execute the same learned controller, and see numerical agreement and runtime provenance alongside the mission.

- [ ] Implement fresh FP32 multiplication and batched model evaluation with resident weights and owned reusable buffers; prevent overlapping-buffer misuse.
- [ ] Public numerical tests cover rectangular products, exported layer/logit/score agreement, malformed artifacts, and nonfinite inputs.
- [ ] Compare selected commands with the reference and record any disagreements; establish portable native build/reproduction commands.

## 9. Compare blocked inference with the naive backend

**Blocked by:** 8.

**What to build:** Choose a cache-blocked backend for missions and compare correct output and warmed saved-input latency with naive inference.

- [ ] Fresh blocked multiplication handles rectangular inputs and block tails at the agreed tolerance.
- [ ] Identical saved inputs produce a provenance-bearing comparison visible in the browser; performance results are withheld on correctness failure.
- [ ] Mission selection uses the same model/controller contracts and records command disagreement and backend configuration.

## 10. Compare parallel inference and worker settings

**Blocked by:** 9.

**What to build:** Run parallel blocked inference with explicit worker counts and inspect whether threading helps the real model workload.

- [ ] Correctness holds across supported worker counts and tail cases; concurrency does not corrupt buffers.
- [ ] Backend and worker selection flow through mission configuration and recorded results.
- [ ] Saved-input comparisons show measured distributions and overhead honestly, including slower-than-serial results; persistent thread pools remain deferred.

## 11. Add Apple Accelerate to the same-machine comparison

**Blocked by:** 8.

**What to build:** Run Apple Accelerate inference on the M1 Pro and compare it with available custom backends on identical inputs.

- [ ] Verify parity and command decisions using the same model contracts and correctness gate.
- [ ] Record measured Apple hardware/compiler settings and warmed workload results in the existing comparison output.
- [ ] Unsupported hosts clearly identify the backend as unavailable; recorded M1 results remain viewable without pretending they ran locally.

## 12. Observe actual inference completion in a paced mission

**Blocked by:** 8.

**What to build:** Run native inference asynchronously while the simulated rover continues on a wall-clock pace, then inspect observation age and pacing validity.

- [ ] Actual completion affects command availability rather than pausing simulation; identify request, observation, candidate set, model, and accepted decision.
- [ ] Enforce freshness and newer-result precedence; braking respects dynamics when usable output expires.
- [ ] Show measured latency/age and pacing overruns; freeze validity limits and test expiry/boundaries without claiming deterministic wall-clock timings.

## 13. Run a deterministic delayed-inference experiment

**Blocked by:** 7.

**What to build:** Execute the learned mission on a modeled single-lane FIFO device and inspect its queue, stage timing, stale decisions, and outcome.

- [ ] Model dispatch, transfer, compute, and completion with resident weights and bounded pending capacity; record overflow and expiry.
- [ ] Freeze simultaneous-event order, deadline/age boundary semantics, and result identity; host elapsed computation never advances modeled time.
- [ ] Replaying a baseline or delayed condition reproduces its trace and visible prediction-age timeline, with measured/modeled provenance.

## 14. Compare queue freshness under steady and burst congestion

**Blocked by:** 13.

**What to build:** Select latest-pending replacement or FIFO and run uncongested, steady-congestion, and burst-congestion cases with visible queue and mission effects.

- [ ] Latest-pending replaces waiting work for the rover without canceling executing work; FIFO behavior remains unchanged.
- [ ] Record all scheduled opportunities, admitted/completed/dropped counts, queue waits, deadlines, and age at consumption.
- [ ] Paired fixtures exercise replacement, overflow, expiry, and simultaneous events; actual unchanged or worse outcomes remain visible.

## 15. Expose modeled memory admission and recovery

**Blocked by:** 13.

**What to build:** Change a modeled allocation budget, run a mission, and see admission failures, releases, and resulting rover behavior.

- [ ] Account for resident weights, workspace, pending payloads, and in-flight payloads with explicit trace events.
- [ ] Test exact admission boundaries and release after completion or drop, without leaks or unbounded workspace.
- [ ] Display modeled memory and rejections distinctly from process RSS or cache behavior, with reproducible budget comparisons.

## 16. Demonstrate controlled and exploratory before/after comparisons

**Blocked by:** 12, 14.

**What to build:** Launch a controlled one-factor comparison or exploratory multi-change comparison and inspect aligned playback, metrics, and configuration differences.

- [ ] Freeze mission/scenario/model/criteria and other declared controls for controlled experiments; disclose every difference for exploratory ones.
- [ ] Display numerical agreement, runtime behavior, mission outcome, and test verdict together using recorded results and shared replay time controls.
- [ ] Preserve negative results and prohibit isolated-cause claims from multi-change comparisons; accept backend registrations and memory metrics as they become available without requiring those branches to start this ticket.

## 17. Configure rover and device experiments with validity checks

**Blocked by:** 7, 14, 15.

**What to build:** Edit supported rover, sensor, planning, backend, queue, freshness, and device settings through the browser and run a saved reproducible configuration.

- [ ] Validate dimensions/motion limits, sensor range, planning frequency, worker settings, queue/age limits, transfer/compute costs, and modeled memory budgets.
- [ ] Keep rover type and model feature structure fixed; show training-domain warnings when settings exceed declared model conditions.
- [ ] Configurations round-trip into the runner and reports; invalid inputs cannot silently alter active runs or fixed test expectations.

## 18. Let the mission engineer investigate and demonstrate a tested change

**Blocked by:** 3, 16.

**What to build:** Enable the real provider-backed mission engineer to prepare a mission, investigate a completed run, and show evidence-linked before/after results.

- [ ] Smoke-test the intended Baseten endpoint and tool use; accurately label any tested fallback and saved response. Ground mission targets through the existing perception contract.
- [ ] Validate tools and enforce three follow-up runs plus execution/API budgets; allow only backend/queue changes and preserve objectives, model, controller, and criteria.
- [ ] Explain what happened, supporting evidence, the tested change, and whether it helped; display actual comparisons and admit an unestablished cause. Test invalid calls, exhausted budgets, and unsupported claims through the tool boundary.

## 19. Export a reproducible experiment report and evidence bundle

**Blocked by:** 16.

**What to build:** Download a readable report and machine-readable configurations, metrics, traces, and manifests for a run or comparison, then reproduce it from the bundle.

- [ ] Include scenario/model identity, expectations, seeds, hardware, compiler/runtime settings, samples, changed factors, and measured/modeled provenance.
- [ ] Preserve failed outcomes and distinguish mission outcome from test verdict; export existing model, queue, and available memory metrics without inventing unavailable measurements.
- [ ] Round-trip a representative experiment through export/reproduction and verify report/replay agreement; reject incomplete or inconsistent reproduction inputs clearly.

## 20. Host portable missions and labeled local-result replay

**Blocked by:** 3, 16.

**What to build:** Open the application through a hosted URL, run a portable mission, and inspect stored local measurements without an inbound laptop connection.

- [ ] Verify Modal deployment and persistent artifact access, keep credentials server-side, and preserve configuration/run identity across hosted requests.
- [ ] Clearly label live hosted, recorded local, and modeled execution; provide usable labeled saved-run fallback on provider failure.
- [ ] Confirm unavailable Apple execution is not advertised as live; deployment commands and clean-start checks make the narrow hosted path reproducible. Later feature slices reuse this hosted path.

## 21. Freeze and execute the full held-out evaluation

**Blocked by:** 5, 6, 10, 11, 15, 17, 18, 19, 20.

**What to build:** Review and freeze the protocol, execute the completed feature set on untouched scenarios, and publish a browser-readable report backed by exportable evidence.

- [ ] Obtain the promised quality-threshold review; freeze model/risk cutoff, expectations, manifests, numerical tolerance, pacing validity, sample counts, and stopping rules before final evaluation.
- [ ] Pass numerical, simulation, scheduler, failure-handling, photo/editor, configuration, and provider/agent correctness gates. Evaluate all four M1 backends, actual native behavior, virtual queue/load/memory conditions, mission variants, and the agent versus a fixed-policy rule.
- [ ] Report paired outcomes and uncertainty with valid timing provenance, include all failures, and preserve the final test set's independence. Existing features and harnesses must already work; this ticket integrates evaluation rather than hiding unfinished implementation.

## 22. Package the verified demo and reproduction handoff

**Blocked by:** 21.

**What to build:** Deliver the three-minute evidence-based demonstration and a clean-start reproduction handoff for the completed project.

- [ ] Demonstrate a recognizable mission, declared congestion, investigation, actual before/after outcome, backend measurements, and limitations using real saved evidence.
- [ ] Verify hosted access and local reproduction from a clean setup; label recording, accelerated playback, and fallbacks.
- [ ] Include contribution/license provenance and recheck event requirements; prepare submission materials without submitting or changing repository visibility automatically. Reserve the agreed testing/demo day and report schedule failures rather than dropping scope.

## Dependency and scope review

- Initial frontier: 1. After 2, perception (3) and learned control (7) can proceed independently.
- After 3, scene editing/photo drafting (4–5) and multi-target missions (6) branch. After 7, native execution (8–12) and virtual timing (13–15) branch.
- Comparison (16) joins one valid native and virtual path; it does not wait for every backend. Configurability (17), investigation (18), exports (19), and hosting (20) join only their relevant prerequisites.
- Final evaluation (21) joins the feature branches. Transitive blockers are intentionally omitted.
- All 49 source stories are covered: 1–2/9–19 by 1–3 and 6; 3–8/11 by 4–5; 20–21 by 17; 22–28 by 8–13 and 20; 29–33 by 13–15; 34–36/40–41 by 16 and 18; 37–39 by 18; 42–44 by 7 and 21; 45 by 19; 46–48 by 20; 49 by 22.

The user authorized publication with explicit What to build, Acceptance criteria, and Blocked by sections. All published sections, labels, assignments, parent links, and native dependency edges were verified.

## Published issue index

| Planning ticket | GitHub issue | Blocked by GitHub issues |
| --- | --- | --- |
| 1 | [#2: Run and replay a deterministic inspection mission](https://github.com/NiketKakkar03/RoverEdge/issues/2) | None |
| 2 | [#3: Navigate obstacles and explain physical mission failures](https://github.com/NiketKakkar03/RoverEdge/issues/3) | #2 |
| 3 | [#4: Ground an inspection request with actual SAM perception](https://github.com/NiketKakkar03/RoverEdge/issues/4) | #3 |
| 4 | [#5: Edit and version scenes before running missions](https://github.com/NiketKakkar03/RoverEdge/issues/5) | #4 |
| 5 | [#6: Turn a photograph into a confirmed runnable scene](https://github.com/NiketKakkar03/RoverEdge/issues/6) | #5 |
| 6 | [#7: Inspect multiple targets and exercise mission variants](https://github.com/NiketKakkar03/RoverEdge/issues/7) | #4 |
| 7 | [#8: Run a learned collision-risk controller with validation evidence](https://github.com/NiketKakkar03/RoverEdge/issues/8) | #3 |
| 8 | [#9: Execute a mission with fresh naive C++ inference](https://github.com/NiketKakkar03/RoverEdge/issues/9) | #8 |
| 9 | [#10: Compare blocked inference with the naive backend](https://github.com/NiketKakkar03/RoverEdge/issues/10) | #9 |
| 10 | [#11: Compare parallel inference and worker settings](https://github.com/NiketKakkar03/RoverEdge/issues/11) | #10 |
| 11 | [#12: Add Apple Accelerate to the same-machine comparison](https://github.com/NiketKakkar03/RoverEdge/issues/12) | #9 |
| 12 | [#13: Observe actual inference completion in a paced mission](https://github.com/NiketKakkar03/RoverEdge/issues/13) | #9 |
| 13 | [#14: Run a deterministic delayed-inference experiment](https://github.com/NiketKakkar03/RoverEdge/issues/14) | #8 |
| 14 | [#15: Compare queue freshness under steady and burst congestion](https://github.com/NiketKakkar03/RoverEdge/issues/15) | #14 |
| 15 | [#16: Expose modeled memory admission and recovery](https://github.com/NiketKakkar03/RoverEdge/issues/16) | #14 |
| 16 | [#17: Demonstrate controlled and exploratory before/after comparisons](https://github.com/NiketKakkar03/RoverEdge/issues/17) | #13, #15 |
| 17 | [#18: Configure rover and device experiments with validity checks](https://github.com/NiketKakkar03/RoverEdge/issues/18) | #8, #15, #16 |
| 18 | [#19: Let the mission engineer investigate and demonstrate a tested change](https://github.com/NiketKakkar03/RoverEdge/issues/19) | #4, #17 |
| 19 | [#20: Export a reproducible experiment report and evidence bundle](https://github.com/NiketKakkar03/RoverEdge/issues/20) | #17 |
| 20 | [#21: Host portable missions and labeled local-result replay](https://github.com/NiketKakkar03/RoverEdge/issues/21) | #4, #17 |
| 21 | [#22: Freeze and execute the full held-out evaluation](https://github.com/NiketKakkar03/RoverEdge/issues/22) | #6, #7, #11, #12, #16, #18, #19, #20, #21 |
| 22 | [#23: Package the verified demo and reproduction handoff](https://github.com/NiketKakkar03/RoverEdge/issues/23) | #22 |
