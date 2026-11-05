import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_modal_wrapper_declares_explicit_durable_hosting_contract() -> None:
    source = Path("modal_app.py").read_text()

    assert 'ARTIFACT_VOLUME_NAME = "roveredge-artifacts-v1"' in source
    assert 'ARTIFACT_MOUNT_PATH = "/roveredge-artifacts"' in source
    assert "modal.Volume.from_name(ARTIFACT_VOLUME_NAME, create_if_missing=False)" in source
    assert '"ROVEREDGE_ARTIFACT_DIR": ARTIFACT_MOUNT_PATH' in source
    assert '"ROVEREDGE_DEPLOYMENT_GATE": "modal_deployed"' in source
    assert "volumes={ARTIFACT_MOUNT_PATH: artifact_volume}" in source
    assert "secrets=[provider_secret]" in source
    assert "artifact_volume.commit()" in source
    assert 'request.url.path in _ARTIFACT_WRITING_PATHS' in source
    assert "modal deploy" not in source
    assert source.index(".env(") < source.index('.add_local_dir("src", "/root/src")')
    assert '.add_local_dir("dist", "/root/dist")' in source


def test_portable_source_imports_without_the_native_extension(tmp_path) -> None:
    shutil.copytree(
        Path("src/roveredge"),
        tmp_path / "roveredge",
        ignore=shutil.ignore_patterns("*.so"),
    )
    environment = os.environ | {"PYTHONPATH": str(tmp_path)}

    imported = subprocess.run(
        [sys.executable, "-c", "import roveredge.api; print('portable import succeeded')"],
        check=False,
        capture_output=True,
        env=environment,
        text=True,
    )

    assert imported.returncode == 0, imported.stderr
    assert imported.stdout == "portable import succeeded\n"
