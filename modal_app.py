"""Manual-only Modal entry point for RoverEdge portable hosting.

Deploy this module only after the operator has provisioned the named Volume and
server-side Secret described in ``docs/manual-verification/modal-deployment.md``.
"""

import os

import modal

ARTIFACT_VOLUME_NAME = "roveredge-artifacts-v1"
ARTIFACT_MOUNT_PATH = "/roveredge-artifacts"
PROVIDER_SECRET_NAME = "roveredge-provider-credentials"
_ARTIFACT_WRITING_PATHS = frozenset({"/api/hosted/runs", "/api/hosted/saved-runs"})

image = (
    modal.Image.debian_slim(python_version="3.12")
    .uv_sync()
    .env(
        {
            "PYTHONPATH": "/root/src",
            "ROVEREDGE_ARTIFACT_DIR": ARTIFACT_MOUNT_PATH,
            "ROVEREDGE_DEPLOYMENT_GATE": "modal_deployed",
        }
    )
    .add_local_dir("src", "/root/src")
    .add_local_dir("dist", "/root/dist")
)
app = modal.App("roveredge-portable-hosting")
artifact_volume = modal.Volume.from_name(ARTIFACT_VOLUME_NAME, create_if_missing=False)
provider_secret = modal.Secret.from_name(PROVIDER_SECRET_NAME)


@app.function(
    image=image,
    volumes={ARTIFACT_MOUNT_PATH: artifact_volume},
    secrets=[provider_secret],
)
@modal.asgi_app()
def roveredge_asgi_app():
    """Return the existing FastAPI application with durable Volume writes."""
    os.environ["ROVEREDGE_ARTIFACT_DIR"] = ARTIFACT_MOUNT_PATH
    from roveredge.api import app as api

    @api.middleware("http")
    async def commit_artifacts_after_request(request, call_next):
        response = await call_next(request)
        if request.method == "POST" and request.url.path in _ARTIFACT_WRITING_PATHS:
            artifact_volume.commit()
        return response

    return api
