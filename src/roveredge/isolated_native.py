"""Process-isolated adapter for measured native-paced experiments."""

import gc
import multiprocessing
import os
import traceback
from dataclasses import dataclass
from multiprocessing.connection import Connection

from .models import RunRequest, RunResult
from .physical import run_physical_experiment
from .scenarios import Scenario


@dataclass(frozen=True)
class IsolatedNativeResult:
    result: RunResult
    worker_pid: int
    gc_disabled_during_run: bool


class IsolatedNativeError(RuntimeError):
    """Raised when the isolated measured worker fails or exceeds its wall timeout."""


def run_isolated_native_experiment(
    request: RunRequest,
    *,
    scenario_override: Scenario | None = None,
    observation_target_id: str | None = None,
    wall_timeout_s: float | None = None,
) -> IsolatedNativeResult:
    """Run one native-paced mission in a fresh spawned process.

    The caller remains the evidence owner. The child performs no artifact writes and
    disables cyclic garbage collection only while the measured experiment executes.
    """
    if request.configuration.execution_mode != "native_paced":
        raise ValueError("isolated native execution requires native_paced mode")
    timeout_s = wall_timeout_s or request.configuration.timeout_s + 30.0
    if timeout_s <= 0:
        raise ValueError("isolated native wall timeout must be positive")

    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker_main,
        args=(child, request, scenario_override, observation_target_id),
        name="roveredge-native-run",
    )
    process.start()
    child.close()
    try:
        if not parent.poll(timeout_s):
            process.terminate()
            process.join(timeout=5.0)
            if process.is_alive():
                process.kill()
                process.join()
            raise IsolatedNativeError(
                f"isolated native worker exceeded {timeout_s:.3f}s wall timeout"
            )
        status, payload, worker_pid, gc_disabled = parent.recv()
        process.join(timeout=10.0)
        if process.is_alive():
            process.terminate()
            process.join()
            raise IsolatedNativeError("isolated native worker did not shut down cleanly")
        if status == "error":
            raise IsolatedNativeError(f"isolated native worker failed:\n{payload}")
        if process.exitcode != 0:
            raise IsolatedNativeError(
                f"isolated native worker exited with status {process.exitcode}"
            )
        if not isinstance(payload, RunResult):
            raise IsolatedNativeError("isolated native worker returned an invalid result")
        return IsolatedNativeResult(payload, worker_pid, gc_disabled)
    finally:
        parent.close()
        if process.is_alive():
            process.terminate()
            process.join()


def _worker_main(
    connection: Connection,
    request: RunRequest,
    scenario_override: Scenario | None,
    observation_target_id: str | None,
) -> None:
    gc_was_enabled = gc.isenabled()
    try:
        gc.disable()
        result = run_physical_experiment(
            request,
            scenario_override=scenario_override,
            observation_target_id=observation_target_id,
        )
        gc_disabled = not gc.isenabled()
        if gc_was_enabled:
            gc.enable()
        connection.send(("ok", result, os.getpid(), gc_disabled))
    except BaseException:
        if gc_was_enabled:
            gc.enable()
        connection.send(("error", traceback.format_exc(), os.getpid(), not gc.isenabled()))
    finally:
        connection.close()
