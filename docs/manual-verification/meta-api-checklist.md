# Deferred Meta SAM verification checklist

Use this checklist when a Meta Model API key is available. Issue #4 must remain open until the live
checks pass and the resulting sanitized evidence is committed. Do not paste keys into chat, source,
tests, logs, screenshots, issue comments, or saved response fixtures.

## Credential setup

- [ ] Export `MODEL_API_KEY` only in the local shell or approved secret store.
- [ ] Confirm `.env` files and credential material remain ignored and untracked.
- [ ] Run the credentialed smoke command from a clean checkout.
- [ ] Confirm authentication headers and the key value are absent from stdout, tracebacks, and saved
      artifacts.

## Account and model access

- [ ] Call `POST https://api.meta.ai/v1/responses` with model `sam-3.1`.
- [ ] Confirm the account can access the exact model identifier; a `404 model_not_found` is an access
      failure, not evidence that the model is unsupported globally.
- [ ] Record the tested model, client, parser, and package versions.
- [ ] Record provider request/response identifiers and duration when returned, without credentials.

## Live category feasibility

- [ ] Test the proposed `red toolbox` phrase against its fresh rendered scene image.
- [ ] Test the proposed `blue barrel` phrase against its fresh rendered scene image.
- [ ] Verify each claimed category returns exactly one usable box and binary mask.
- [ ] If a category is unreliable, revise the fixed illustrated asset or choose another concrete noun
      phrase, rerun the live test, and report only categories that actually passed.
- [ ] Do not replace or repair a failed mask with hidden scenario target geometry.

## Required perception cases

- [ ] Position variation: move each validated category and confirm the mask and derived standoff move
      with the rendered object.
- [ ] Missing target: request a category absent from the image and confirm a normal zero-match
      `target_not_found` result with no rover motion.
- [ ] Ambiguity: render two instances of one category and confirm `target_ambiguous` with no automatic
      selection by confidence, position, or hidden ID.
- [ ] Provider failure: verify missing/invalid access produces labeled `provider_unavailable` evidence
      and never silently switches to recorded mode.
- [ ] Mask validation: confirm decoded raster dimensions match the source image and contain only
      binary pixels.

## Grounding-to-mission behavior

- [ ] Display the actual returned mask over the exact rendered source image.
- [ ] Verify the recorded image SHA-256 matches the bytes sent to Meta.
- [ ] Convert the mask boundary through the recorded orthographic camera transform.
- [ ] Confirm the inspection pose is outside the mask footprint and at least 0.50 m from its boundary.
- [ ] Confirm the pose is collision-free, faces the grounded target, and has a deterministic feasible
      route.
- [ ] Complete approach, stopped inspection dwell, observation capture, and return to dock.
- [ ] Repeat with target-position variation.

## Provenance and recorded fallback

- [ ] Save sanitized raw output, parsed boxes/masks, parser diagnostics, hashes, versions, and timing.
- [ ] Check saved artifacts for authorization headers, keys, signed URLs, and unrelated private data.
- [ ] Capture immutable successful, missing, and ambiguous responses as explicitly recorded fixtures.
- [ ] Run the same successful mission in recorded mode and verify deterministic mask, standoff, route,
      trace, outcome, and verdict.
- [ ] Confirm the browser labels live and recorded grounding distinctly.
- [ ] Confirm a live failure offers recorded mode but does not activate it automatically.

## Completion gate

- [ ] Run the full deterministic suite and the separate credentialed SAM smoke suite.
- [ ] Complete separate Standards and Spec reviews against the issue #4 baseline.
- [ ] Update the issue #4 implementation brief with the categories and versions actually validated.
- [ ] Commit only sanitized evidence and close issue #4 through its implementation PR.
