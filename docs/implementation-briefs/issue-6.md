# Issue #6 implementation brief — photo-assisted scene drafts

**Issue:** [#6 — Turn a photograph into a confirmed runnable scene](https://github.com/NiketKakkar03/RoverEdge/issues/6)

## Feasibility method and claim boundary

The implemented `rough_color_region_proposals_v1` method finds sufficiently large red, blue, and
dark pixel regions and maps their image-space boxes into an 8 m × 6 m editable draft. This is a
deterministic rough-proposal heuristic for the representative synthetic warehouse reference; it is
not monocular depth, hidden-geometry recovery, or automatic metric reconstruction.

Every generated draft explicitly marks the default scale and dock as unmeasured, labels proposed
footprints uncertain, and remains incomplete when no supported region is found. The existing scene
confirmation gate requires the user to correct scale, dock, obstacles, targets, overlaps, and
reachability before saving or execution.

## Evidence boundary

The original PNG/JPEG is stored by SHA-256 in ignored local application storage and remains visible
as a reference. The hash follows the saved scenario version. Mission perception never uses the
photo: it uses the confirmed version's fresh deterministic scene render through the existing
manual-live / immutable-recorded grounding adapters.

## Verification

- API tests upload a representative photograph, verify rough proposals and uncertainty, retrieve
  the byte-identical reference, correct and save the draft, render the confirmed version, and run
  its mission.
- Invalid uploads and photos with no supported proposals remain explicit and correctable.
- A browser test exercises upload → rough uncertain draft → correction → confirmed version →
  mission execution while retaining the photo reference.
- `make check` covers the full Python/browser suites, native build, type checks, lint, and web build.
