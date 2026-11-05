The explicitly approved v7 held-out evaluation completed its full frozen schedule. Issue #22 remains open because the frozen quality criteria failed.

- Approval: `artifacts/issue-22/frozen-held-out-protocol-v7.json`, tied to proposal SHA-256 `7a0f790db19dd621ad1593adc0f3f153877b5c927acc715c79527bf02193bf2b` and untouched family manifest SHA-256 `27b03f38f2f3c31c23d47f7e7209fb52267d8d95d535ff067e8d55eaf17fdffc`.
- The four-backend non-final isolated preflight passed: 2,400 ticks/backend, zero pacing overruns and command disagreements, accepted time policy, GC disabled during measurement, and four distinct worker PIDs.
- The final schedule completed 120 modeled virtual runs, 60 measured native runs, and 12,000 saved-input replay batches. Native pacing recorded zero overruns (maximum 0.0 s); backend command disagreements were zero. Saved replay numerical tolerance passed on all four backends.
- Frozen quality gate failed: 2 false negatives versus maximum 0; 91 unnecessary stops among 768 states (11.848958%) versus maximum 10%. Mean safe progress was 0.304114 versus minimum 0.3. Across all runs, 34 missions completed and 146 timed out. These failures remain in the report; thresholds, model, cutoff, policy, and safety envelope were not changed.
- Authoritative report: `artifacts/issue-22/execution-v7/report.json`; complete run bundles and export hashes: `artifacts/issue-22/execution-v7/runs/` and `artifacts/issue-22/execution-v7/manifest.json` (184 hashed files). Browser-readable endpoint: `GET /api/evaluations/held-out`.
- Verification after execution: focused final evaluation, scenario, and API tests 28 passed; Ruff, strict mypy, and `git diff --check` passed.

The v7 final families are consumed. A fresh independent quality claim would require a new candidate and untouched families with a separately reviewed freeze. Do not reinterpret this completed failed result as a pass or rerun v7 to chase one.
