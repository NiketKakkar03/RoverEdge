# Issue #4 implementation brief — actual SAM target grounding

**Issue:** [#4 — Ground an inspection request with actual SAM perception](https://github.com/NiketKakkar03/RoverEdge/issues/4)

**Status:** Proposed for approval. No issue #4 application code or tests have started.

**Implementation boundary:** Extend the merged issue #3 runner so a concise target phrase and a
fresh deterministic rendering are sent to Meta SAM 3.1, the returned mask determines a safe
inspection standoff, and the existing geometric mission executes against that grounded pose.

## User-visible behavior

1. The browser shows a fixed perception preset containing at least two visually distinct target
   categories and accepts one concise target noun phrase.
2. Starting a live grounded run renders the selected scenario version, calls Meta SAM 3.1, and
   shows the returned mask before motion begins.
3. Exactly one returned match becomes a grounded target. Its mask boundary is converted through
   the declared orthographic camera transform into floor coordinates; the rover navigates to a
   collision-free standoff, inspects while stopped, and returns to dock.
4. Zero matches produce a recorded `target_not_found` setup outcome with no rover motion.
5. Multiple matches produce a recorded `target_ambiguous` setup outcome with no hidden-ID or
   confidence-based auto-selection.
6. Provider authentication, access, transport, parser, and incomplete-response failures produce a
   recorded `provider_unavailable` setup outcome. They do not silently substitute a fixture.
7. The browser offers a separately labeled recorded-response replay. It uses a response captured
   by an earlier successful live call and never claims to be live provider execution.
8. Every result identifies whether grounding was live or recorded and preserves sanitized request,
   response, model, parser, image, mask, and timing provenance without credentials.
9. Replaying the same recorded grounding evidence reproduces the selected mask, standoff, route,
   physical trace, mission outcome, and verdict. A live cloud call is not claimed deterministic.

## Source contracts

- `project.md` §5 **Technical stack and platform responsibilities**: Meta Model API and
  `sam-3.1`; pin tested dependencies and verify actual account access.
- `project.md` §6 **Robotics and perception contract**: fresh rendered image, orthographic
  image-to-floor transform, mask-derived target, collision-free standoff, and no hidden-ID
  substitution.
- `project.md` §11 **Testing and evaluation**: real response, position variation, absent target,
  ambiguity, and valid standoff conversion.
- `docs/roveredge-spec.md` **Implementation Decisions**, **Testing Decisions**, and **Further
  Notes**: live provider smoke tests plus labeled frozen responses for repeatable experiments.
- `docs/adr/0002-confirm-scene-geometry.md`: confirmed geometry supplies traversability while SAM
  supplies visual grounding.
- `docs/adr/0004-preserve-experiment-evidence.md`: fixed scenario versions, complete
  configuration, model identity, timing provenance, and recorded failures.
- `GLOSSARY.md`: mission outcome remains distinct from test verdict; a setup failure is still a
  recorded result of the attempted mission.

Current official Meta documentation confirms that SAM 3.1 uses `POST /v1/responses` at
`https://api.meta.ai/v1`, authenticates with the `MODEL_API_KEY` Bearer key, accepts one short noun
phrase plus an `input_image` URL or data URL, returns every match as a box and mask, and treats an
empty output as a valid zero-match result. The official `meta_sam_parser` Python package parses the
wire grammar and decodes masks. References:

- [SAM overview](https://dev.meta.ai/docs/sam/overview)
- [Segmenting with prompts](https://dev.meta.ai/docs/sam/segmenting)
- [SAM client libraries](https://dev.meta.ai/docs/sam/client-libraries)

The repository currently has no `MODEL_API_KEY` in its process environment and contains no `.env`
file. Actual provider access therefore remains unverified and is an acceptance blocker, not a
reason to claim fixture-only completion.

## Proposed domain language

- **Target grounding:** the recorded result of applying a target phrase to a rendered scene image;
  it may be matched, not found, ambiguous, or unavailable.
- **Live grounding evidence:** evidence produced by an actual provider call during the current run.
- **Recorded grounding evidence:** a sanitized, immutable response captured from an earlier live
  call and replayed without contacting the provider.
- **Grounded target:** the single mask selected only because the provider returned exactly one
  match for the phrase. It is not a hidden simulator target ID.

After approval, add these terms to `GLOSSARY.md`. No new ADR is proposed: the governing geometry,
grounding, and evidence decisions already exist in ADRs 0002 and 0004.

## Proposed public interface and module structure

Keep one public experiment-runner interface while making target selection explicit with a
discriminated target request:

```text
RunRequest
  scenario_version
  target
    known_target_fixture { target_id }       # issue #2/#3 geometric fixtures only
    visual_target { phrase, grounding_source }
  simulation_seed
  configuration
  expected_mission_outcome

run_experiment(request, grounding_adapter?) -> RunResult
```

`known_target_fixture` remains explicitly labeled and cannot satisfy perception acceptance tests.
`visual_target` requires either the live or recorded grounding adapter. This avoids ambiguous
optional `target_id`/`target_phrase` combinations and preserves a single public runner seam.

New result evidence:

```text
GroundingEvidence
  source: live | recorded
  status: matched | target_not_found | target_ambiguous | provider_unavailable
  provider / model / parser versions
  target phrase
  scenario-render SHA-256 and dimensions
  provider response/request IDs when supplied
  request start / completion duration
  sanitized raw-output SHA-256 and parser diagnostics
  returned boxes, confidence when supplied, and masks as versioned RLE
  selected match ordinal only when exactly one match exists
  camera transform and derived floor footprint / inspection pose
```

Minimal implementation modules:

- `scene_rendering`: deterministic server-owned PNG rendering and camera metadata from a fixed
  scenario version. The browser displays this same artifact instead of independently inventing
  grounding pixels.
- `grounding`: one deep interface, `ground(rendered_scene, phrase) -> GroundingEvidence`, with two
  adapters: live Meta and immutable recorded response.
- `standoff`: mask boundary to floor coordinates, collision-free candidate generation, deterministic
  route feasibility, and selected inspection heading.
- `experiment`: orchestrates render → ground → standoff → existing physical mission, preserving
  setup outcomes and evidence.
- `api` / browser: accept the phrase and explicit source, display masks/provenance/setup failures,
  and start replay only from recorded result evidence.

Use the official OpenAI-compatible Python client for transport and `meta_sam_parser` for parsing and
mask decoding. Pin the tested versions after the first successful smoke call. Do not hand-parse the
special-token mask grammar.

## Proposed perception preset and camera contract

Add one fixed `preset-perception-v1` scenario derived from the open map:

- Map: 8 m × 6 m; orthographic render: 800 × 600 pixels; 100 pixels/meter.
- Pixel origin `(0, 0)` maps to floor `(0 m, 0 m)` with the same axis directions used by the
  current browser canvas. The complete affine transform is recorded.
- Candidate categories: a **red toolbox** and a **blue barrel**, rendered as recognizable,
  high-contrast illustrated objects rather than plain unlabeled rectangles.
- Position-variation fixtures move one category while preserving its appearance and phrase.
- Absent fixture omits the requested category.
- Ambiguous fixture contains two instances of the same requested category.

These categories are proposed feasibility candidates, not validated SAM capabilities. They become
the reported initial categories only if actual live calls segment them successfully. If either
fails, simplify the rendered asset or choose a different concrete category and record that result;
never replace the mask with known geometry while claiming success.

## Mask-to-standoff and mission contracts

- Request `one_bit` mask encoding and confidence metadata. Confidence is recorded, not used as an
  unapproved acceptance threshold.
- Validate that box and mask dimensions match the rendered artifact and that decoded rasters contain
  only binary pixels.
- Derive the target floor footprint from the returned mask boundary. Hidden scenario identities may
  validate evaluation afterward but cannot select, repair, or replace a mask.
- Generate standoff candidates at least 0.50 m from the grounded mask boundary, outside obstacles and
  map margins. For issue #4, sample deterministic cardinal boundary normals, face the mask centroid,
  discard unreachable candidates, and choose the shortest deterministic route with stable tie order.
- Treat the grounded mask footprint as occupied target geometry. Never route to its centroid.
- Freeze the grounded inspection pose before physical simulation. Replay never calls SAM or
  recomputes grounding.
- `target_not_found`, `target_ambiguous`, and `provider_unavailable` are explicit mission setup
  outcomes and can produce passing test verdicts when expected.
- Provider setup time is recorded as user-visible wall duration but excluded from the 120 simulated
  second mission timeout, consistent with `project.md` §6.

## Provider and evidence contracts

- Read `MODEL_API_KEY` only from the process environment. Never accept it through the browser,
  request body, saved run, logs, fixtures, commits, or test snapshots.
- Send a base64 PNG data URL so the exact rendered bytes and hash are known; do not require public
  image hosting.
- Live calls use `sam-3.1`, `metadata.mask_encoding="one_bit"`, and
  `metadata.include_confidence="true"`.
- Persist a sanitized provider artifact containing request shape without authorization, exact raw
  output, parsed records, diagnostics, hashes, versions, and timing. Store large mask data once and
  reference it from results.
- Recorded mode accepts only repository fixtures whose source live-call provenance and image hash
  match the requested scenario render. A mismatch is an error, not an approximate fallback.
- A missing key, `model_not_found`, authentication failure, rate/transport failure, incomplete
  stream, parser diagnostic that invalidates a match, or invalid mask becomes recorded
  `provider_unavailable` evidence.
- The UI may suggest the recorded mode after a live failure, but it never switches automatically.

## Acceptance tests and runnable demonstration

The previously approved testing boundaries remain unchanged:

- **Primary:** experiment-runner requests and observable grounding, standoff, route, trace, outcome,
  verdict, and reproducibility evidence.
- **Provider:** genuine contract smoke tests for actual SAM integration, kept separate from the
  deterministic default suite and skipped with an explicit reason when credentials are absent.
- **Browser:** a small suite for phrase input, live/recorded labeling, mask overlay, setup failures,
  and recorded mission replay.
- **Not applicable yet:** numerical-runtime tests.

Planned TDD slices:

1. Recorded single-mask evidence grounds one target, derives a literal standoff, and completes the
   issue #3 physical mission.
2. Literal camera/mask fixtures verify pixel-to-floor conversion, 0.50 m boundary clearance,
   collision-free candidate rejection, deterministic shortest-route selection, and target-facing
   heading.
3. Zero and multiple recorded matches terminate before motion with passing expected-failure verdicts.
4. Provider errors and malformed/incomplete responses preserve sanitized failure evidence without
   exposing credentials.
5. Browser tests submit phrase/source, display the exact recorded mask and provenance label, and show
   matched, missing, ambiguous, and unavailable outcomes.
6. Live smoke tests verify actual account/model access, both candidate categories, target-position
   variation, absent and ambiguous images, and response provenance.
7. Capture the successful live responses as labeled immutable fixtures; repeat the default suite
   offline and prove replay determinism.

## Live validation results (2026-10-29)

The user manually authorized and ran each provider call. Automated tests and the browser never call
the provider. The validated stack is `sam-3.1`, `openai==3.41.0`, and
`meta-sam-parser==0.1.0` with one-bit masks.

| Scenario | Phrase | Result | Matches | Render SHA-256 |
| --- | --- | --- | ---: | --- |
| `preset-perception-v1` | `red toolbox` | `matched` | 1 | `d52abfeb4b2247bc4ad2529b705f99ef3f87f7500073c825226a941ffdb511c9` |
| `preset-perception-v1` | `blue barrel` | `matched` | 1 | `d52abfeb4b2247bc4ad2529b705f99ef3f87f7500073c825226a941ffdb511c9` |
| `fixture-perception-shifted-v1` | `red toolbox` | `matched` | 1 | `27ea0c352dd13823ba04c82228cd8dbf6751111b0622c57c8eee97597195fcbc` |
| `fixture-perception-shifted-v1` | `blue barrel` | `matched` | 1 | `27ea0c352dd13823ba04c82228cd8dbf6751111b0622c57c8eee97597195fcbc` |
| `fixture-perception-absent-v1` | `red toolbox` | `target_not_found` | 0 | `71c830cad0df5d504aab0dcdce043897665a97a20ad066d07a20952b756bcb81` |
| `fixture-perception-ambiguous-v1` | `red toolbox` | `target_ambiguous` | 2 | `31c2d25b607d20992f87c30a40904d30a1949b6c75c73358fb12f573194c1254` |

The successful base and shifted captures replayed offline through mask-to-floor conversion,
collision-free standoff selection, inspection, and return-to-dock. The shifted poses differed for
both validated categories. The absent and ambiguous captures terminated at `setup_failed` with no
motion or observations. The first schematic red-toolbox render returned zero matches; that sanitized
failure is retained under `artifacts/issue-4/live-failures/`. Replacing the schematic objects with
recognizable fixed assets produced the successful results above.

Demonstration:

```text
export MODEL_API_KEY=...        # set locally; never commit or paste it
make test-sam-live              # explicit credentialed smoke/fixture capture
make check                      # deterministic suite, typechecks, lint, build
make dev
```

In the browser, run one live grounded mission, an absent/ambiguous result, and the same successful
mission from the recorded response. The page must visibly distinguish live from recorded evidence.

## Explicit boundaries from later issues

Issue #4 does **not** implement:

- general scene editing/version creation or photo-assisted drafting (#5–#6);
- multiple required mission targets or user resolution of ambiguous matches (#7);
- learned collision-risk control (#8);
- native inference, asynchronous delay experiments, queues, memory, comparisons, agent behavior,
  exports, hosting, held-out evaluation, or demo packaging (#9–#23);
- broad website/world visual redesign (#25).

The issue may add fixed rendered assets required to validate SAM, but not a general asset editor.

## Material decisions for approval

1. **Evolve `RunRequest.target` into a discriminated known-fixture/visual-target request while
   retaining one public runner interface?** Recommendation: yes. It labels the old geometric fixture
   honestly and prevents hidden IDs from leaking into visual grounding.
2. **Use the official Python transport/parser stack and explicit live/recorded grounding adapters?**
   Recommendation: yes. This creates a real seam with two adapters and avoids hand-parsing Meta's
   mask grammar.
3. **Start feasibility with “red toolbox” and “blue barrel,” revising only if actual smoke evidence
   shows they are unreliable?** Recommendation: yes. They are concrete, visually separable noun
   phrases; validation, not the proposal, determines the categories ultimately claimed.
4. **Treat zero matches as `target_not_found` and every multi-match response as
   `target_ambiguous`, with no confidence or hidden-geometry auto-selection?** Recommendation: yes.
   User disambiguation belongs to #7; this is the honest issue #4 behavior.
5. **Freeze a 0.50 m minimum mask-boundary standoff and deterministic shortest feasible cardinal
   candidate selection?** Recommendation: yes. It adopts the project proposal while keeping the
   conversion inspectable and bounded.
6. **Require explicit recorded-mode selection and never silently fall back after a live provider
   failure?** Recommendation: yes. This preserves provenance and prevents a recorded demo from being
   presented as live.
7. **Provide `MODEL_API_KEY` through the local process environment before live acceptance?** Required:
   yes. The key is currently absent, so implementation can build and verify deterministic seams, but
   issue #4 cannot truthfully pass its actual-provider acceptance gate or be committed as complete
   until a credentialed live smoke test succeeds.

No material contradiction was found among issue #4, the specification, ADRs, and glossary. The
official current Meta documentation resolves the previously unverified endpoint/parser details;
account-level model access remains unverified.
