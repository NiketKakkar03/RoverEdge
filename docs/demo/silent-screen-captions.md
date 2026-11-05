# RoverEdge silent screen recording

| Time | Screen | Caption |
| --- | --- | --- |
| 0–7 s | Open lane, rover moving | RoverEdge tests how computing delays affect a simulated inspection rover. |
| 7–15 s | Mission brief and target | The rover has to inspect the target and return to its dock. |
| 15–24 s | Play the recorded mission, open the top-down map | The 3D replay and the engineering map follow the same recorded position and heading. |
| 24–36 s | Open lane, select 20 ms and run the queue comparison | At 20 ms of simulated compute, both queue policies finish the mission. |
| 36–49 s | Change to 80 ms and run again | At 80 ms, both time out. Each run accepts just one driving decision before the mission ends. |
| 49–60 s | Show accepted decisions, replacements and inspections | Latest pending replaces older waiting observations. In this run it replaced 1,199. Neither rover captured an inspection. |
| 60–70 s | Recorded grounding overlay for red toolbox | Meta SAM identifies the requested object in an orthographic scene image. This overlay replays saved grounding evidence. |
| 70–80 s | Mission engineer and saved investigation record | Baseten serves the Meta model. In a verified investigation, one request proposed a bounded test and a second explained its result. |
| 80–91 s | Evidence export and hosting acceptance record | Python and FastAPI run the simulation. TypeScript and WebGL replay the trace. The Modal hosting test verified that saved run evidence survives a restart. |
| 91–98 s | Return to the completed and stalled open-lane runs | The same inspection mission completed at the lower delay. The trace shows where decisions expired at the higher delay. |

Use results visible in the captured take for every number. Label the local demo, recorded grounding, and previously verified provider and hosting checks in their respective shots.
