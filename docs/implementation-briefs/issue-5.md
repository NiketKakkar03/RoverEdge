# Issue #5 implementation brief — editable versioned scenes

**Issue:** [#5 — Edit and version scenes before running missions](https://github.com/NiketKakkar03/RoverEdge/issues/5)

## Observable completion criteria

1. The browser can load a preset or an empty draft and edit scale, obstacle footprints, dock
   position, and supported visual target footprints.
2. Confirmation validates the complete geometry and creates a content-addressed immutable scenario
   version. Editing the draft again creates a different version and cannot alter an earlier one.
3. Reloading a version through the API reproduces its geometry, deterministic rendered image, and
   default mission request. The saved request completes against that exact version.
4. Invalid scale, bounds, rectangles, target labels, missing targets, duplicate identifiers, and
   dock/obstacle overlap return actionable validation messages.
5. Rendering always reads the selected saved version. A later visual-grounding request therefore
   receives the new version's exact rendered bytes and hash; no live provider call is automated.

## Design boundary

Saved versions are written atomically to the ignored local `.roveredge/scenarios/` store and loaded
again when the application starts. Drafts may start empty, but confirmation requires at least one
supported target and a reachable inspection standoff so the saved version has a runnable mission.
Existing static presets and recorded SAM evidence remain unchanged. Live perception remains a
manual-only provider action: the editor prints the exact one-call command for the saved version,
whose sanitized evidence can then be replayed from `.roveredge/grounding/`.

## Verification

- API tests cover version creation, immutable reload, render stability, corresponding mission
  completion, and invalid empty/out-of-bounds geometry.
- Browser tests cover loading a preset, editing scale and footprint geometry, saving a version, and
  selecting that new version.
- `make check` covers the complete Python/browser suites, native build, type checks, lint, and web
  production build.
