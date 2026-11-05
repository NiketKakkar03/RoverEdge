# Contribution and license register

This register separates RoverEdge-authored work from third-party dependencies and records the
remaining provenance checks. It is a handoff artifact, not legal advice or a submission.

## RoverEdge-authored implementation

| Area | Repository evidence | Claim boundary |
| --- | --- | --- |
| Deterministic mission simulator, geometry, planning, traces, outcomes, and verdicts | `src/roveredge/experiment.py`, `geometry.py`, `physical.py`, `scenarios.py` | Event project integration; no physical-robot or safety-certification claim. |
| Fresh FP32 kernels and native inference integration | `native/`, `src/roveredge/native.py`, Issues #9–#12 artifacts | Naive, blocked, and parallel blocked kernels are project code; Apple Accelerate is a system-library comparison, not project-authored code. |
| Virtual queue, freshness, memory, and comparison evidence | `src/roveredge/device.py`, `comparison.py`, Issue #14–#17 tests and artifacts | Modeled timing is not measured hardware timing. |
| Scene, photo-draft, recorded grounding, and browser replay workflow | `src/roveredge/scene_rendering.py`, `photo_drafting.py`, `grounding.py`, `web/src/` | Recorded grounding is not a live-provider acceptance result. |
| Evidence export, bounded recorded investigation, and portable artifact storage | `src/roveredge/evidence.py`, `mission_engineer.py`, `hosting.py` | Recorded fixture and local persistence do not satisfy live-provider or deployment gates. |

The repository root `LICENSE` applies the MIT License to RoverEdge-authored source. Before public
submission, preserve dated Git history identifying these contributions; the current Xcode-license
state prevents a fresh local Git/native toolchain audit in this handoff.

## Third-party software and services

| Dependency/source | How it is used | Provenance action |
| --- | --- | --- |
| Python packages in `pyproject.toml` / `uv.lock` | API, arrays, model training, image handling, testing, and tooling | Exact versions are locked. Generate or review a complete third-party notices file before distributing vendored binaries; a lockfile alone is not a license notice. |
| Browser packages in `package.json` / `pnpm-lock.yaml` | TypeScript build, Vite, Vitest, DOM testing | Development dependencies are locked. Review their installed license texts before bundling anything beyond generated application code. |
| `meta-sam-parser==0.1.0` and Meta SAM | Parses provider image-segmentation output | Installed metadata declares the SAM License. If SAM Materials are redistributed, include that agreement and required acknowledgements; no model weights are intentionally committed here. Live use remains manual-only. |
| Apple Accelerate | System-library backend on supported Apple computers | Attribute as an Apple system-library comparison; do not claim authorship or portable availability. |
| PyTorch, NumPy, FastAPI, Pillow, OpenAI SDK, Uvicorn, pybind11, CMake, and test/build tools | Declared runtime and development dependencies | Do not claim authorship. Preserve dependency names and versions in reproduction evidence. |

## Visual and data assets

| Asset | SHA-256 | Status |
| --- | --- | --- |
| `web/public/assets/perception/red-toolbox.png` | `5152cfd47c70a15102f55efbdc534230df983aa01fd3f79702ff10da6675dd03` | Source/creation record must be confirmed before public submission. Do not infer rights from repository presence. |
| `web/public/assets/perception/blue-barrel.png` | `e48112c48b7a712034f642247a0e0ad183a090e4edf3def8a4329eac34810bfe` | Source/creation record must be confirmed before public submission. Do not infer rights from repository presence. |
| Synthetic scenarios, generated traces, learned-model training rows, and modeled demo evidence | Versioned manifests and repository generators | Project-generated; keep generator/version/hash provenance with exported evidence. |
| User-uploaded photo references | Local `.roveredge` storage only | The user must have rights to the input. Do not include private uploads in a public artifact without explicit authorization. |

## Public-handoff blockers

- Confirm the creation/source and distribution rights for both perception PNGs.
- Produce a dated contribution summary from Git after the Xcode license permits the local toolchain
  to inspect repository history.
- Review complete third-party notices for the exact locked dependency set if binaries or dependency
  source are distributed.
- Recheck the authenticated participant guide and any partner-model eligibility conditions while
  signed in; public search does not expose the full guide.
