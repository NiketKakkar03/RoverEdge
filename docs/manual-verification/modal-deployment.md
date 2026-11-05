# Deferred Modal deployment checklist

This is a manual, cost-bearing acceptance procedure. Do not run it until the
operator explicitly approves deployment. It neither authorizes live provider
calls nor changes the held-out evaluation gate.

## Prerequisites

- Modal authentication is available through the operator's local profile or
  `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET` process environment variables.
- The Xcode license gate is separate and remains required for local native
  compilation; it is not a Modal prerequisite.
- The server-only Modal Secret is named `roveredge-provider-credentials`. When
  provider credentials are available and approved for server use, create it in
  the authenticated Modal dashboard and enter only `MODEL_API_KEY` and
  `Baseten_API_KEY` there. Do not put values in a repository file or pass them
  as shell arguments, which can expose them through shell history or process
  inspection. Do not create the Secret with fabricated values. The portable
  acceptance path does not make provider requests.

## Provision the persistent store

Create the named Volume v2 before deployment:

```zsh
uvx --from modal modal volume create --version=2 roveredge-artifacts-v1
```

This creates billable persistent storage. The Volume is mounted at
`/roveredge-artifacts` and is the sole location used for
`ROVEREDGE_ARTIFACT_DIR` in the deployed container.

## Deploy only after explicit approval

Build the browser distribution before deploying; the Modal image serves this directory at `/`:

```zsh
pnpm build:web
```

The exact deployment command is:

```zsh
uv run modal deploy modal_app.py
```

Expected cost-bearing actions: Modal builds the image, creates or updates the
named web App, serves a public endpoint, and keeps the named Volume. The wrapper
does not create a Volume implicitly (`create_if_missing=False`).

Rollback: use the Modal dashboard or `modal app stop roveredge-portable-hosting`
to stop serving. Do not delete the Volume until its retained evidence is no
longer needed; deletion destroys that evidence and can remain billable for a
short retention period.

## Acceptance after deployment

1. From the deployed URL, request `/api/hosting/status`; confirm
   `apple_accelerate_live` is `unavailable_in_portable_hosting`.
2. Create one portable run through `POST /api/hosted/runs` and record its ID.
3. Redeploy or restart the App, then retrieve the same identity through
   `GET /api/hosted/runs/{run_id}`. Its configuration, trace, outcome, and
   verdict must match.
4. Import one `recorded_local` fallback and one `modeled` fallback, preserving
   their labels. Never relabel native/Apple execution as live hosted.
5. Save sanitized acceptance evidence only. Scan it for authorization headers,
   token values, signed URLs, and unrelated private data before committing.
