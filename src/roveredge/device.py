import math
from dataclasses import dataclass
from typing import Literal, TypeVar

Payload = TypeVar("Payload")
QueuePolicy = Literal["fifo", "latest_pending"]


@dataclass(frozen=True)
class ModeledDeviceProfile:
    dispatch_s: float = 0.001
    input_transfer_s: float = 0.002
    compute_s: float = 0.005
    output_transfer_s: float = 0.002
    pending_capacity: int = 2
    deadline_s: float = 0.02
    maximum_age_s: float = 0.1
    queue_policy: QueuePolicy = "fifo"
    requests_per_tick: int = 1
    resident_weights_bytes: int = 14_852
    workspace_bytes: int = 4_096
    request_payload_bytes: int = 1_024
    memory_budget_bytes: int = 32_768

    def __post_init__(self) -> None:
        durations = (
            self.dispatch_s,
            self.input_transfer_s,
            self.compute_s,
            self.output_transfer_s,
        )
        if any(not math.isfinite(duration) or duration < 0 for duration in durations):
            raise ValueError("modeled stage durations must be finite and nonnegative")
        if self.pending_capacity < 0:
            raise ValueError("pending capacity cannot be negative")
        if self.requests_per_tick <= 0:
            raise ValueError("requests per tick must be positive")
        memory_values = (
            self.resident_weights_bytes,
            self.workspace_bytes,
            self.request_payload_bytes,
            self.memory_budget_bytes,
        )
        if any(value < 0 for value in memory_values):
            raise ValueError("modeled memory values cannot be negative")
        if self.memory_budget_bytes < self.resident_weights_bytes + self.workspace_bytes:
            raise ValueError("modeled memory budget cannot fit resident weights and workspace")
        if self.queue_policy not in ("fifo", "latest_pending"):
            raise ValueError("unsupported queue policy")
        if (
            not math.isfinite(self.deadline_s)
            or not math.isfinite(self.maximum_age_s)
            or self.deadline_s < 0
            or self.maximum_age_s < 0
        ):
            raise ValueError("modeled timing limits must be finite and nonnegative")

    @property
    def service_s(self) -> float:
        return self.dispatch_s + self.input_transfer_s + self.compute_s + self.output_transfer_s


@dataclass(frozen=True)
class InferenceRequest[Payload]:
    episode_id: str
    observation_id: int
    request_id: int
    candidate_set_id: str
    model_sha256: str
    observed_at_s: float
    payload: Payload


@dataclass(frozen=True)
class CompletedInference[Payload]:
    request: InferenceRequest[Payload]
    dispatched_at_s: float
    completed_at_s: float

    @property
    def age_at_completion_s(self) -> float:
        return self.completed_at_s - self.request.observed_at_s


@dataclass(frozen=True)
class DeviceEvent:
    kind: str
    modeled_time_s: float
    request_id: int
    queue_depth: int
    detail: str
    episode_id: str
    observation_id: int
    candidate_set_id: str
    model_sha256: str
    queue_wait_s: float | None = None
    modeled_memory_bytes: int | None = None
    memory_budget_bytes: int | None = None
    resident_weights_bytes: int | None = None
    workspace_bytes: int | None = None
    pending_payload_bytes: int | None = None
    in_flight_payload_bytes: int | None = None
    peak_modeled_memory_bytes: int | None = None


class FifoDevice[Payload]:
    def __init__(self, profile: ModeledDeviceProfile) -> None:
        self.profile = profile
        self._executing: tuple[InferenceRequest[Payload], float, float] | None = None
        self._pending: list[InferenceRequest[Payload]] = []
        self._completed: list[CompletedInference[Payload]] = []
        self._pending_payload_bytes = 0
        self._in_flight_payload_bytes = 0
        self._peak_modeled_memory_bytes = self._modeled_memory_bytes
        self._memory_rejections = 0

    @property
    def _modeled_memory_bytes(self) -> int:
        return (
            self.profile.resident_weights_bytes
            + self.profile.workspace_bytes
            + self._pending_payload_bytes
            + self._in_flight_payload_bytes
        )

    @property
    def memory_summary(self) -> dict[str, int]:
        return {
            "resident_weights_bytes": self.profile.resident_weights_bytes,
            "workspace_bytes": self.profile.workspace_bytes,
            "pending_payload_bytes": self._pending_payload_bytes,
            "in_flight_payload_bytes": self._in_flight_payload_bytes,
            "current_modeled_memory_bytes": self._modeled_memory_bytes,
            "peak_modeled_memory_bytes": self._peak_modeled_memory_bytes,
            "memory_budget_bytes": self.profile.memory_budget_bytes,
            "memory_rejections": self._memory_rejections,
        }

    def advance(self, modeled_time_s: float) -> tuple[DeviceEvent, ...]:
        events: list[DeviceEvent] = []
        while self._executing is not None and self._executing[2] <= modeled_time_s:
            request, dispatched_at_s, completed_at_s = self._executing
            self._completed.append(
                CompletedInference(request, dispatched_at_s, completed_at_s)
            )
            self._executing = None
            self._in_flight_payload_bytes -= self.profile.request_payload_bytes
            events.append(
                self._event(
                    "completed",
                    completed_at_s,
                    request,
                    len(self._pending),
                    (
                        f"dispatch={self.profile.dispatch_s:.6f}s "
                        f"input={self.profile.input_transfer_s:.6f}s "
                        f"compute={self.profile.compute_s:.6f}s "
                        f"output={self.profile.output_transfer_s:.6f}s"
                    ),
                )
            )
            events.append(
                self._event(
                    "memory_released",
                    completed_at_s,
                    request,
                    len(self._pending),
                    "modeled in-flight payload released after completion",
                )
            )
            if completed_at_s - request.observed_at_s > self.profile.deadline_s:
                events.append(
                    self._event(
                        "deadline_missed",
                        completed_at_s,
                        request,
                        len(self._pending),
                        "completion exceeded the reporting deadline",
                    )
                )
        return tuple(events)

    def submit(
        self, request: InferenceRequest[Payload], modeled_time_s: float
    ) -> tuple[DeviceEvent, ...]:
        if self._executing is not None and self.profile.queue_policy == "latest_pending":
            for index in range(len(self._pending) - 1, -1, -1):
                if self._pending[index].episode_id == request.episode_id:
                    replaced = self._pending[index]
                    self._pending_payload_bytes -= self.profile.request_payload_bytes
                    released = self._event(
                        "memory_released",
                        modeled_time_s,
                        replaced,
                        len(self._pending),
                        "modeled pending payload released for replacement",
                    )
                    allocated = self._allocate(request, modeled_time_s)
                    self._pending[index] = request
                    return (
                        released,
                        allocated,
                        self._event(
                            "replaced",
                            modeled_time_s,
                            replaced,
                            len(self._pending),
                            f"replaced by request {request.request_id}",
                        ),
                    )
        if self._executing is not None and len(self._pending) >= self.profile.pending_capacity:
            return (
                self._event(
                    "overflow",
                    modeled_time_s,
                    request,
                    len(self._pending),
                    "FIFO pending capacity reached",
                ),
            )
        if (
            self._modeled_memory_bytes + self.profile.request_payload_bytes
            > self.profile.memory_budget_bytes
        ):
            self._memory_rejections += 1
            return (
                self._event(
                    "memory_rejected",
                    modeled_time_s,
                    request,
                    len(self._pending),
                    "modeled allocation budget cannot admit request payload",
                    modeled_memory_bytes=self._modeled_memory_bytes,
                    memory_budget_bytes=self.profile.memory_budget_bytes,
                ),
            )
        allocated = self._allocate(request, modeled_time_s)
        if self._executing is None:
            self._pending.append(request)
            return (allocated, *self._dispatch_next(modeled_time_s))
        self._pending.append(request)
        return (
            allocated,
            self._event(
                "admitted",
                modeled_time_s,
                request,
                len(self._pending),
                "request admitted to FIFO pending queue",
            ),
        )

    def consume_latest(
        self, modeled_time_s: float
    ) -> tuple[CompletedInference[Payload] | None, tuple[DeviceEvent, ...]]:
        if not self._completed:
            return None, ()
        latest = max(self._completed, key=lambda item: item.request.observation_id)
        self._completed.clear()
        age_s = modeled_time_s - latest.request.observed_at_s
        if age_s > self.profile.maximum_age_s:
            return None, (
                self._event(
                    "expired",
                    modeled_time_s,
                    latest.request,
                    len(self._pending),
                    f"result age {age_s:.6f}s exceeds maximum {self.profile.maximum_age_s:.6f}s",
                ),
            )
        return latest, (
            self._event(
                "consumed",
                modeled_time_s,
                latest.request,
                len(self._pending),
                f"observation age {age_s:.6f}s",
            ),
        )

    def release_all(self, modeled_time_s: float) -> tuple[DeviceEvent, ...]:
        events: list[DeviceEvent] = []
        if self._executing is not None:
            request, _, _ = self._executing
            self._executing = None
            self._in_flight_payload_bytes -= self.profile.request_payload_bytes
            events.extend(
                (
                    self._event(
                        "dropped",
                        modeled_time_s,
                        request,
                        len(self._pending),
                        "in-flight request dropped when the mission ended",
                    ),
                    self._event(
                        "memory_released",
                        modeled_time_s,
                        request,
                        len(self._pending),
                        "modeled in-flight payload released after drop",
                    ),
                )
            )
        while self._pending:
            request = self._pending.pop(0)
            self._pending_payload_bytes -= self.profile.request_payload_bytes
            events.extend(
                (
                    self._event(
                        "dropped",
                        modeled_time_s,
                        request,
                        len(self._pending),
                        "pending request dropped when the mission ended",
                    ),
                    self._event(
                        "memory_released",
                        modeled_time_s,
                        request,
                        len(self._pending),
                        "modeled pending payload released after drop",
                    ),
                )
            )
        return tuple(events)

    def _dispatch_next(self, modeled_time_s: float) -> list[DeviceEvent]:
        if self._executing is not None or not self._pending:
            return []
        request = self._pending.pop(0)
        if modeled_time_s - request.observed_at_s > self.profile.maximum_age_s:
            self._pending_payload_bytes -= self.profile.request_payload_bytes
            return [
                self._event(
                    "expired",
                    modeled_time_s,
                    request,
                    len(self._pending),
                    "request expired before dispatch",
                ),
                self._event(
                    "memory_released",
                    modeled_time_s,
                    request,
                    len(self._pending),
                    "modeled pending payload released after expiry",
                ),
                *self._dispatch_next(modeled_time_s),
            ]
        completed_at_s = modeled_time_s + self.profile.service_s
        self._pending_payload_bytes -= self.profile.request_payload_bytes
        self._in_flight_payload_bytes += self.profile.request_payload_bytes
        self._executing = (request, modeled_time_s, completed_at_s)
        return [
            self._event(
                "dispatched",
                modeled_time_s,
                request,
                len(self._pending),
                (
                    f"queue wait {modeled_time_s - request.observed_at_s:.6f}s; "
                    f"modeled completion at {completed_at_s:.6f}s"
                ),
                modeled_time_s - request.observed_at_s,
            )
        ]

    def _event(
        self,
        kind: str,
        modeled_time_s: float,
        request: InferenceRequest[Payload],
        queue_depth: int,
        detail: str,
        queue_wait_s: float | None = None,
        modeled_memory_bytes: int | None = None,
        memory_budget_bytes: int | None = None,
    ) -> DeviceEvent:
        return DeviceEvent(
            kind=kind,
            modeled_time_s=modeled_time_s,
            request_id=request.request_id,
            queue_depth=queue_depth,
            detail=detail,
            episode_id=request.episode_id,
            observation_id=request.observation_id,
            candidate_set_id=request.candidate_set_id,
            model_sha256=request.model_sha256,
            queue_wait_s=queue_wait_s,
            modeled_memory_bytes=(
                self._modeled_memory_bytes
                if modeled_memory_bytes is None
                else modeled_memory_bytes
            ),
            memory_budget_bytes=(
                self.profile.memory_budget_bytes
                if memory_budget_bytes is None
                else memory_budget_bytes
            ),
            resident_weights_bytes=self.profile.resident_weights_bytes,
            workspace_bytes=self.profile.workspace_bytes,
            pending_payload_bytes=self._pending_payload_bytes,
            in_flight_payload_bytes=self._in_flight_payload_bytes,
            peak_modeled_memory_bytes=self._peak_modeled_memory_bytes,
        )

    def _allocate(
        self, request: InferenceRequest[Payload], modeled_time_s: float
    ) -> DeviceEvent:
        self._pending_payload_bytes += self.profile.request_payload_bytes
        self._peak_modeled_memory_bytes = max(
            self._peak_modeled_memory_bytes, self._modeled_memory_bytes
        )
        return self._event(
            "memory_allocated",
            modeled_time_s,
            request,
            len(self._pending),
            "modeled request payload allocated as pending",
        )
