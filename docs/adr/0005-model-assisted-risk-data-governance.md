# Keep model assistance outside collision labels, control, and verdicts

Meta vision and reasoning models may assist the local collision-risk pipeline by proposing
scenario templates from recorded validation failures, identifying trace clusters, and producing
human-readable data-quality summaries. Every proposal is untrusted input: deterministic schema,
geometry, split-leakage, and simulator checks decide whether it is admissible. The deterministic
simulator remains the only source of collision labels, and the local risk model plus deterministic
safety logic remains the only source of driving decisions.

This provides useful model assistance across scenario design, data curation, error analysis, and
reporting without allowing a stochastic provider to invent safety labels, issue wheel commands,
alter frozen thresholds, or certify results. Each accepted template records the provider/model,
prompt and response hashes, reviewer decision, simulator version, and generated-family identity.
Provider-generated or human-authored templates are split into train, validation, or final families
before sampling; no template or derivative may cross those boundaries. A new final family is never
generated or inspected until its protocol is frozen.

The hosted Meta SAM API is a zero-shot grounding service, not the collision-risk trainer. Any
self-hosted fine-tuning investigation is separate from this protocol and requires reviewed license,
compute, data-provenance, and independent-evaluation plans.
