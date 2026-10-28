import math
from dataclasses import dataclass
from typing import TypeVar

Payload = TypeVar("Payload")


@dataclass(frozen=True)
class ModeledDeviceProfile:
    dispatch_s: float = 0.001
    input_transfer_s: float = 0.002
    compute_s: float = 0.005
    output_transfer_s: float = 0.002
    pending_capacity: int = 2
    deadline_s: float = 0.02
    maximum_age_s: float = 0.1

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


class FifoDevice[Payload]:
    def __init__(self, profile: ModeledDeviceProfile) -> None:
        self.profile = profile
        self._executing: tuple[InferenceRequest[Payload], float, float] | None = None
        self._pending: list[InferenceRequest[Payload]] = []
        self._completed: list[CompletedInference[Payload]] = []

    def advance(self, modeled_time_s: float) -> tuple[DeviceEvent, ...]:
        events: list[DeviceEvent] = []
        while self._executing is not None and self._executing[2] <= modeled_time_s:
            request, dispatched_at_s, completed_at_s = self._executing
            self._completed.append(
                CompletedInference(request, dispatched_at_s, completed_at_s)
            )
            self._executing = None
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
        if self._executing is None:
            self._pending.append(request)
            return tuple(self._dispatch_next(modeled_time_s))
        if len(self._pending) >= self.profile.pending_capacity:
            return (
                self._event(
                    "overflow",
                    modeled_time_s,
                    request,
                    len(self._pending),
                    "FIFO pending capacity reached",
                ),
            )
        self._pending.append(request)
        return (
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

    def _dispatch_next(self, modeled_time_s: float) -> list[DeviceEvent]:
        if self._executing is not None or not self._pending:
            return []
        request = self._pending.pop(0)
        if modeled_time_s - request.observed_at_s > self.profile.maximum_age_s:
            return [
                self._event(
                    "expired",
                    modeled_time_s,
                    request,
                    len(self._pending),
                    "request expired before dispatch",
                ),
                *self._dispatch_next(modeled_time_s),
            ]
        completed_at_s = modeled_time_s + self.profile.service_s
        self._executing = (request, modeled_time_s, completed_at_s)
        return [
            self._event(
                "dispatched",
                modeled_time_s,
                request,
                len(self._pending),
                f"modeled completion at {completed_at_s:.6f}s",
            )
        ]

    @staticmethod
    def _event(
        kind: str,
        modeled_time_s: float,
        request: InferenceRequest[Payload],
        queue_depth: int,
        detail: str,
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
        )
