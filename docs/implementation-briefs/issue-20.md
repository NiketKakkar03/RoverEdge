# Issue #20 implementation brief — reproducible evidence bundles

**Issue:** [#20 — Export a reproducible experiment report and evidence bundle](https://github.com/NiketKakkar03/RoverEdge/issues/20)

## Observable behavior

After a run, the browser downloads a ZIP containing a generated Markdown report, the complete
machine-readable run evidence, and a manifest with schema identity, export environment, and SHA-256
for every evidence file. After a second run it can export the same material for a comparison,
including the declared factor, every changed request path, comparison validity, and the bounded
causal interpretation.

The run documents preserve scenario and model identity, expectations, seeds, full configuration,
trace samples, mission outcome, test verdict, grounding evidence, runtime provenance, queue metrics,
and available modeled-memory metrics. Missing measurements are labeled `not_recorded`; the exporter
does not synthesize them.

`uv run python scripts/reproduce_evidence.py <bundle.zip>` validates the archive, declared files,
hashes, schemas, report agreement, run identities, and comparison agreement before rerunning the
requests. Recorded visual grounding reuses only the immutable evidence embedded in the bundle.
Live provider runs are never invoked automatically. Native-paced reproduction ignores only
inherently variable measured execution and pacing values while requiring the remaining evidence to
agree.

## Verification

- A representative deterministic run exports, imports, reruns, and agrees with the saved evidence.
- A comparison retains negative mission outcomes separately from passing test verdicts and
  preserves every changed factor and interpretation limit.
- Missing files, undeclared files, hash mismatches, malformed typed evidence, inconsistent
  comparisons, and reports that disagree with machine evidence are rejected.
- API tests cover ZIP download and server-side reproduction; browser tests cover run and comparison
  downloads.
- `make check` covers the full Python/browser suites, native build, type checks, lint, and web build.

## Acceptance — November 2, 2026

The checked-in modeled queue-policy comparison bundle reproduced two runs with
`scripts/reproduce_evidence.py`. Focused evidence/demo tests and browser download tests passed,
followed by a successful `make check`: 159 Python tests, mypy, Ruff, 22 browser tests, and the
production web build all passed. The sanitized acceptance record is in
`artifacts/issue-20/acceptance-2026-11-02.json`.
