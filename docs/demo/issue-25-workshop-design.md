# RoverEdge workshop design direction

Status: technical and cinematic workshop implemented locally with a perspective presentation view over the deterministic simulator. Queue freshness is the first experiment after the mission. The always-visible evidence fields are mission outcome, test verdict, and prediction age. This document is the design and implementation record, not an evaluation result.

## First screen

The rover mission is the signature. A large warehouse viewport shows the rover, route, inspection target, and dock. Its replay comes only from a scenario and recorded poses. A compact mission brief names the task, target, phase, and provenance. One primary action runs the selected mission. A transport sits directly beneath the viewport.

The evidence row shows mission outcome and test verdict as separate fields. Prediction age is the immediate experiment hook beside the rover: “How old is the decision the rover is using?” It appears when inference evidence exists; otherwise it says “Not available.” No metric or conclusion is filled from a mockup. Source labels appear beside the data they describe: live hosted run, recorded local run, modeled device timing, or measured saved-input replay.

## Workshop flow

1. **Mission:** choose a scenario and target, run or replay it, inspect the target grounding and route.
2. **Experiment:** state a question, change one declared factor, and show the conditions held fixed. Put advanced rover, backend, queue, and device settings behind an explicit setup disclosure.
3. **Comparison:** synchronize before and after replay. Show mission outcome, test verdict, prediction age, queue behavior, and only the metrics relevant to the selected factor. Controlled validity is visible before any isolated-cause language; exploratory comparisons list every changed setting.
4. **Conclusion:** summarize the observed change, unchanged result, worse result, or inconclusive result in plain language. Link to the full trace, configuration, timing provenance, hashes, and export bundle.

## Visual rules

- Technical and cinematic, with warehouse geometry and a recognizable rover carrying the domain identity.
- Restrained amber for the primary action, route selection, and current replay point; neutral surfaces for controls and evidence.
- No decorative status dots, invented figures, repeated card grids, all-cap micro labels, or fake browser frame.
- One primary action per screen. Inactive controls have clear empty and disabled states.
- Keep the technical top-down map and SAM orthographic render inspectable if a presentation-only 3D scene is chosen.
- The presentation renderer never changes pose, collision, timing, outcome, or trace evidence.

## Demo sequence to support

Open on a recognizable inspection mission and the age of the decision currently used by the rover. Introduce declared modeled congestion, then compare FIFO and latest-pending observation policies on a controlled pair. Show the actual recorded outcome: both current demo runs time out, so the comparison is unchanged mission behavior, not an improvement. Demonstrate the mission engineer's bounded investigation using its correct provider/fixture label. Show M1 saved-input backend measurements as a separate measured replay. End at an exportable evidence bundle and the simulation limits.

## Implemented boundary

The browser draws a fixed-camera perspective of the recorded scenario, route, target, dock, and rover pose. The existing top-down canvas remains available in a synchronized disclosure; the SAM orthographic render and mask remain in the experiment setup. This is a deliberately simple presentation renderer, not photorealistic 3D or a second physics engine. The mission API, trace, collision, timing, and verdict computation are unchanged.

The queue comparison runs two real virtual-device episodes with 80 ms modeled compute and a pending capacity of four. Only the queue policy changes. The resulting table is populated from the returned traces and summaries; the conclusion says explicitly when the mission outcome is unchanged. Other configuration controls and the full evidence list remain available through disclosures.
