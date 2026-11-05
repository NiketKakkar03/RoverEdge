# Issue #21 implementation brief — portable hosting and artifact persistence

## Observable behavior

The provider-independent FastAPI path can execute a portable run, atomically persist its complete
`RunResult` beneath `ROVEREDGE_ARTIFACT_DIR`, list saved identities, and load the same configuration,
run identity, trace, outcome, and verdict from a later application client. Existing saved runs can
be imported as an explicit `recorded_local` or `modeled` fallback. Virtual-device evidence cannot be
relabeled as live or recorded, and portable hosted execution rejects native backends rather than
advertising Apple Accelerate as available on a non-Apple host.

The status endpoint declares three labels: `live_hosted`, `recorded_local`, and `modeled`. It also
declares the deployment gate `not_run`; this local slice does not claim a Modal deployment or
persistent Modal Volume acceptance check.

## Credential boundary

Credentials remain process-only server configuration. The browser and artifact documents never
accept or persist credential values. The only recognized names are `MODEL_API_KEY` and
`Baseten_API_KEY`. No provider request is part of the local hosting path.

## Verification

- Execute and persist a portable run, then retrieve it through a fresh API client.
- Import a recorded-local fallback without changing its run identity.
- Require modeled runs to retain the modeled label.
- Reject native/Apple execution in the portable endpoint and expose its unavailability explicitly.
- Run the repository checks; report the Xcode-license blocker if a fresh native build cannot start.

## Deployment gate (not executed)

1. Provision a persistent volume and mount it at a server-only path.
2. Set `ROVEREDGE_ARTIFACT_DIR` to that mount and inject required provider credentials through the
   hosting platform's secret store, never through browser requests or committed configuration.
3. Build the pinned project dependencies and start
   `uv run uvicorn roveredge.api:app --host 0.0.0.0 --port 8000`.
4. From a clean deployment, run one portable request, restart the application, reload its run ID,
   load one recorded-local fallback, and verify `/api/hosting/status` labels Apple execution
   unavailable.
5. Only after those checks pass may the deployment and persistence gates be marked complete.

The exact Modal SDK wrapper and deploy command remain intentionally unfrozen until current official
documentation can be checked and the user directly authorizes deployment. No deployment was made
while preparing this path.

## Local restart acceptance — October 30, 2026

The portable endpoint created run `6f45fb51-7edd-4790-bcaa-5d341aa92859` with execution label
`live_hosted`, mission outcome `completed`, and test verdict `passed`. After stopping and restarting
the FastAPI application, retrieving that identity returned the same label, outcome, and verdict.
The sanitized record is in `artifacts/issue-21/local-persistence-acceptance.json`.

This closes only the local restart/persistence check. The remote deployment and persistent-volume
gate remains `not_run` because no Modal token variables were available to the process.

## Partial Modal acceptance — November 2, 2026

The deployed public endpoint returned `200` for the hosting status, preset scenario, hosted-run
creation, and hosted-run retrieval endpoints. The status continued to declare Apple Accelerate
unavailable in portable hosting. The operator-observed creation and retrieval durations were 782 ms
and 49 ms, respectively. The sanitized record is in
`artifacts/issue-21/modal-hosting-partial-acceptance-2026-11-02.json`.

This is deliberately **not** a passed deployment gate: the retained record has no run identity for
a byte-equivalence comparison, and the application has not been operator-authorized to restart or
redeploy. The recorded-local and modeled fallback imports also remain unverified.

## Modal persistence acceptance — November 2, 2026

After the partial check, the deployment was rolled over with Modal's rolling strategy. One
`live_hosted` run and imported `recorded_local` and `modeled` fallbacks were each retrieved by the
same identity after the rollover. Each retrieved JSON artifact was byte-equivalent to its
pre-rollover response. The hosted status endpoint returned `200`, continued to report Apple
Accelerate as unavailable in portable hosting, and exposed all three execution labels. The
sanitized acceptance evidence is in
`artifacts/issue-21/modal-hosting-acceptance-2026-11-02.json`.

This closes the narrow Modal deployment and persistent-artifact acceptance gate only. It does not
claim hosted Apple-native execution or provider-model execution.

The Modal image also includes the built browser distribution at `/root/dist`. After that deployment,
`GET /` returned `200` with the RoverEdge HTML page and its production JavaScript asset returned
`200`; these checks are included in the same sanitized acceptance record.
