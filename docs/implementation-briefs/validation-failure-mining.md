# Validation-failure-mining proposal governance

## Observable acceptance criteria

A local or recorded proposal source can submit a bounded `scenario-template-v1` object and receive
a deterministic `scenario-proposal-record-v1` audit record. Valid train or validation templates
are accepted only after strict schema, numeric-bound, geometry, waypoint-relationship,
reachability, seed, family-identity, and split checks. Every rejection has a stable actionable
reason. Replaying the same input and provenance produces the same response hash and record ID.

The record preserves source kind and model identifier, optional prompt hash, derived response hash,
reviewer decision, simulator version, and generated-family identity. It deliberately contains no
timestamp, collision label, run verdict, wheel command, or provider call.

## Bounded schemas

`scenario-template-v1` allows only:

- a generated family identity, `train` or `validation` split, and unsigned 32-bit seed;
- a 2–20 m rectangular map and at most 16 bounded rectangular obstacles;
- one bounded start pose and one waypoint with an explicit relative relationship;
- initial linear speed from 0–0.6 m/s and angular speed from -0.8–0.8 rad/s; and
- one of the declared validation failure modes: unsafe command selected, unnecessary stop, or
  insufficient recovery progress.

Unknown fields are rejected. Geometry uses the declared 0.20 m rover clearance, and reachability
uses the existing deterministic route planner at 0.10 m resolution. The proposal remains a family
template: this stage does not sample states or invoke the simulator's collision-label rollout.

`scenario-proposal-record-v1` contains the deterministic record ID, accepted/rejected decision,
reason list, bounded provenance, and the parsed template only when accepted. A rejected response is
identified by its response hash without copying an arbitrary untrusted payload into the audit
record.

## Split and provider boundary

The parser recognizes only `train` and `validation`; a `final` split explicitly fails. Family IDs
containing `final`, IDs already present in train/validation, and duplicate IDs in one proposal batch
also fail. The validator is not given held-out family identities and has no operation for reading,
creating, generating, or inspecting held-out material.

`LocalProposalFixture` and the `ProposalSource` protocol are the only source integration in this
slice. There are no Baseten, Meta, SAM, Modal, HTTP, or socket clients. A future recorded provider
response can enter through the same untrusted envelope, but provider execution remains outside this
module and this acceptance boundary.

## Manual acceptance

Run the deterministic focused checks:

```bash
uv run pytest tests/test_failure_mining.py -q
uv run ruff check src/roveredge/failure_mining.py tests/test_failure_mining.py
uv run mypy src/roveredge/failure_mining.py
```

These checks do not generate dataset rows, simulator labels, or final-family material.
