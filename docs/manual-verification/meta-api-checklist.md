# Deferred Meta SAM verification checklist

Use this checklist when a Meta Model API key is available. Issue #4 must remain open until the live
checks pass and the resulting sanitized evidence is committed. Do not paste keys into chat, source,
tests, logs, screenshots, issue comments, or saved response fixtures.

## Credential setup

- [x] Export `MODEL_API_KEY` only in the local shell or approved secret store.
- [x] Confirm `.env` files and credential material remain ignored and untracked.
- [ ] Run the credentialed smoke command from a clean checkout.
- [x] Confirm authentication headers and the key value are absent from stdout, tracebacks, and saved
      artifacts.

## Account and model access

- [x] Call `POST https://api.meta.ai/v1/responses` with model `sam-3.1`.
- [x] Confirm the account can access the exact model identifier; a `404 model_not_found` is an access
      failure, not evidence that the model is unsupported globally.
- [x] Record the tested model, client, parser, and package versions.
- [x] Record provider request/response identifiers and duration when returned, without credentials.

## Live category feasibility

- [x] Test the proposed `red toolbox` phrase against its fresh rendered scene image.
- [x] Test the proposed `blue barrel` phrase against its fresh rendered scene image.
- [x] Verify each claimed category returns exactly one usable box and binary mask.
- [x] If a category is unreliable, revise the fixed illustrated asset or choose another concrete noun
      phrase, rerun the live test, and report only categories that actually passed.
- [x] Do not replace or repair a failed mask with hidden scenario target geometry.

## Required perception cases

- [x] Position variation: move each validated category and confirm the mask and derived standoff move
      with the rendered object.
- [x] Missing target: request a category absent from the image and confirm a normal zero-match
      `target_not_found` result with no rover motion.
- [x] Ambiguity: render two instances of one category and confirm `target_ambiguous` with no automatic
      selection by confidence, position, or hidden ID.
- [x] Provider failure: verify missing/invalid access produces labeled `provider_unavailable` evidence
      and never silently switches to recorded mode.
- [x] Mask validation: confirm decoded raster dimensions match the source image and contain only
      binary pixels.

## Grounding-to-mission behavior

- [x] Display the actual returned mask over the exact rendered source image.
- [x] Verify the recorded image SHA-256 matches the bytes sent to Meta.
- [x] Convert the mask boundary through the recorded orthographic camera transform.
- [x] Confirm the inspection pose is outside the mask footprint and at least 0.50 m from its boundary.
- [x] Confirm the pose is collision-free, faces the grounded target, and has a deterministic feasible
      route.
- [x] Complete approach, stopped inspection dwell, observation capture, and return to dock.
- [x] Repeat with target-position variation.

## Provenance and recorded fallback

- [x] Save sanitized raw output, parsed boxes/masks, parser diagnostics, hashes, versions, and timing.
- [x] Check saved artifacts for authorization headers, keys, signed URLs, and unrelated private data.
- [x] Capture immutable successful, missing, and ambiguous responses as explicitly recorded fixtures.
- [x] Run the same successful mission in recorded mode and verify deterministic mask, standoff, route,
      trace, outcome, and verdict.
- [x] Confirm the browser labels live and recorded grounding distinctly.
- [x] Confirm a live failure offers recorded mode but does not activate it automatically.

## Completion gate

- [x] Run the full deterministic suite and the separate credentialed SAM smoke suite.
- [x] Complete separate Standards and Spec reviews against the issue #4 baseline.
- [x] Update the issue #4 implementation brief with the categories and versions actually validated.
- [ ] Commit only sanitized evidence and close issue #4 through its implementation PR.
