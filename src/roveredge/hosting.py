import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, ValidationError

from .models import RunRequest, RunResult

ExecutionLabel = Literal["live_hosted", "recorded_local", "modeled"]
_RUN_ADAPTER = TypeAdapter(RunResult)
_ARTIFACT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class HostedRunArtifact:
    schema: Literal["roveredge.hosted-run.v1"]
    execution_label: ExecutionLabel
    run: RunResult


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_environment(cls) -> "ArtifactStore":
        configured = os.environ.get("ROVEREDGE_ARTIFACT_DIR", ".roveredge/hosted-artifacts")
        return cls(Path(configured))

    def save(self, run: RunResult, execution_label: ExecutionLabel) -> HostedRunArtifact:
        _validate_execution_label(run, execution_label)
        artifact = HostedRunArtifact(
            schema="roveredge.hosted-run.v1",
            execution_label=execution_label,
            run=run,
        )
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self._path(run.run_id)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{run.run_id}.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w") as handle:
                document = json.dumps(asdict(artifact), sort_keys=True, separators=(",", ":"))
                handle.write(document + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return artifact

    def load(self, run_id: str) -> HostedRunArtifact:
        path = self._path(run_id)
        if not path.is_file():
            raise ValueError(f"stored run is unavailable: {run_id}")
        try:
            document = json.loads(path.read_text())
            if document.get("schema") != "roveredge.hosted-run.v1":
                raise ValueError("stored run has an unsupported schema")
            label = document["execution_label"]
            if label not in ("live_hosted", "recorded_local", "modeled"):
                raise ValueError("stored run has an unsupported execution label")
            run = _RUN_ADAPTER.validate_python(document["run"])
            _validate_execution_label(run, label)
            return HostedRunArtifact(
                schema="roveredge.hosted-run.v1", execution_label=label, run=run
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as error:
            raise ValueError(f"stored run is malformed: {run_id}") from error

    def list_run_ids(self) -> tuple[str, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(sorted(path.stem for path in self.root.glob("*.json")))

    def _path(self, run_id: str) -> Path:
        if not _ARTIFACT_ID.fullmatch(run_id):
            raise ValueError("run ID contains unsupported characters")
        return self.root / f"{run_id}.json"


def validate_portable_hosted_request(request: RunRequest) -> None:
    configuration = request.configuration
    if configuration.inference_backend.startswith("native-"):
        raise ValueError(
            "portable hosted runs require python-reference inference; "
            "native and Apple results must be loaded as recorded-local evidence"
        )
    if configuration.execution_mode == "native_paced":
        raise ValueError("native-paced execution is unavailable in portable hosting")


def validate_portable_hosted_run(result: RunResult) -> None:
    validate_portable_hosted_request(result.request)


def _validate_execution_label(run: RunResult, label: str) -> None:
    modeled = run.request.configuration.execution_mode == "virtual_fifo"
    if label == "modeled" and not modeled:
        raise ValueError("modeled label requires virtual modeled execution")
    if label != "modeled" and modeled:
        raise ValueError("virtual modeled execution must retain the modeled label")
