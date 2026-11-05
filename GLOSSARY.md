# RoverEdge

RoverEdge is a software environment for robotics engineers to investigate how inference execution and timing affect simulated rover missions.

## Language

**Mission**:
A requested task for the rover with explicit completion conditions. A mission is distinct from a particular attempt to execute it.

**Run**:
One recorded execution of a mission under a particular scenario and runtime configuration.
_Avoid_: Mission when referring to a single execution

**Mission engineer**:
The AI assistant that prepares missions and investigates completed runs through bounded tools. Its explanations must be supported by recorded evidence.

**Inference backend**:
One of the alternative numerical implementations used to evaluate the same rover model. A backend comparison holds the model and input workload constant.
_Avoid_: Different AI models when referring to backend alternatives

**Inspection observation**:
Evidence captured at a mission target, associated with the target identity, rover pose, and completion status. It does not itself constitute a defect diagnosis.

**Scenario**:
A saved scene arrangement and initial conditions in which missions can be executed repeatedly.

**Mission outcome**:
The recorded result of an attempted rover task, including completion or the reason it did not complete. An unsuccessful mission can still satisfy a test that expects that failure.

**Test verdict**:
Whether recorded behavior meets the expectations fixed for a test. It is distinct from mission completion.

**Scenario version**:
A fixed revision of a scenario used to identify the exact scene and initial conditions for a run.

**Controlled comparison**:
A comparison of runs or workloads with one selected experimental factor varied and other declared conditions held fixed.

**Isolated native evaluation worker**:
A fresh child process that owns exactly one measured native-paced run and performs no evidence
writing. A supervisor owns protocol ordering, stop rules, and post-run artifact serialization.

**Exploratory comparison**:
A comparison that permits multiple configuration differences. Its results alone cannot isolate which change caused an outcome.

**Modeled device profile**:
A declared set of execution, transfer, queue, and memory assumptions for a simulated device. It is distinct from measurements on a physical computer.

**Observation age**:
The elapsed time since the sensor observation that produced a driving decision. It includes waiting and delivery delays as well as calculation time.

**Validation failure mining**:
A bounded workflow that clusters recorded validation failures and proposes new scenario templates
for deterministic review. It does not inspect or alter final families.

**Scenario template**:
A versioned, parameterized description of a family of simulator states. A template becomes training
or validation data only after deterministic validation and split assignment; it is not a collision
label or a run result.

**Safety envelope**:
A deterministic rule that rejects a candidate command when current sensor-derived clearance cannot
satisfy its declared braking or collision bound. It supplements, but does not train or replace, the
learned collision-risk scorer.
