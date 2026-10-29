from collections.abc import Callable
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass
from time import perf_counter

from .device import InferenceRequest

FeatureBatch = tuple[tuple[float, ...], ...]


@dataclass(frozen=True)
class TimedScores:
    scores: tuple[float, ...]
    started_at_wall_s: float
    completed_at_wall_s: float

    @property
    def execution_s(self) -> float:
        return self.completed_at_wall_s - self.started_at_wall_s


@dataclass(frozen=True)
class NativeCompletion[Payload]:
    request: InferenceRequest[Payload]
    scores: tuple[float, ...]
    execution_s: float


@dataclass(frozen=True)
class NativePacedEvent:
    kind: str
    request_id: int
    observation_id: int
    queue_depth: int
    detail: str
    execution_s: float | None = None


class NativePacedExecutor[Payload]:
    """Single-flight native evaluation with newest-only pending work."""

    def __init__(
        self,
        evaluate: Callable[[Payload], tuple[float, ...]],
        *,
        executor: Executor | None = None,
    ) -> None:
        self._evaluate = evaluate
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="roveredge-native"
        )
        self._owns_executor = executor is None
        self._executing: tuple[InferenceRequest[Payload], Future[TimedScores]] | None = None
        self._pending: InferenceRequest[Payload] | None = None
        self._newest_accepted_observation = -1

    def submit(
        self, request: InferenceRequest[Payload], simulated_time_s: float
    ) -> tuple[NativePacedEvent, ...]:
        del simulated_time_s
        if self._executing is None:
            return (self._dispatch(request),)
        events: list[NativePacedEvent] = []
        if self._pending is not None:
            events.append(
                self._event(
                    "replaced",
                    self._pending,
                    0,
                    f"replaced by request {request.request_id}",
                )
            )
        self._pending = request
        events.append(self._event("admitted", request, 1, "newest observation retained"))
        return tuple(events)

    def poll(
        self, simulated_time_s: float
    ) -> tuple[NativeCompletion[Payload] | None, tuple[NativePacedEvent, ...]]:
        del simulated_time_s
        if self._executing is None or not self._executing[1].done():
            return None, ()
        request, future = self._executing
        timed = future.result()
        completion = NativeCompletion(request, timed.scores, timed.execution_s)
        events = [
            self._event(
                "completed",
                request,
                1 if self._pending is not None else 0,
                f"native execution {timed.execution_s:.9f}s",
                timed.execution_s,
            )
        ]
        self._executing = None
        if self._pending is not None:
            pending = self._pending
            self._pending = None
            events.append(self._dispatch(pending))
        return completion, tuple(events)

    def accept(
        self,
        completion: NativeCompletion[Payload],
        simulated_time_s: float,
        *,
        maximum_age_s: float,
    ) -> NativeCompletion[Payload] | None:
        age_s = simulated_time_s - completion.request.observed_at_s
        if age_s > maximum_age_s:
            return None
        if completion.request.observation_id < self._newest_accepted_observation:
            return None
        self.note_accepted_observation(completion.request.observation_id)
        return completion

    def note_accepted_observation(self, observation_id: int) -> None:
        self._newest_accepted_observation = max(
            self._newest_accepted_observation, observation_id
        )

    def close(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=True)

    def _dispatch(self, request: InferenceRequest[Payload]) -> NativePacedEvent:
        future = self._executor.submit(self._timed_evaluate, request.payload)
        self._executing = (request, future)
        return self._event("dispatched", request, 0, "native inference dispatched")

    def _timed_evaluate(self, payload: Payload) -> TimedScores:
        started = perf_counter()
        scores = self._evaluate(payload)
        completed = perf_counter()
        return TimedScores(scores, started, completed)

    @staticmethod
    def _event(
        kind: str,
        request: InferenceRequest[Payload],
        queue_depth: int,
        detail: str,
        execution_s: float | None = None,
    ) -> NativePacedEvent:
        return NativePacedEvent(
            kind=kind,
            request_id=request.request_id,
            observation_id=request.observation_id,
            queue_depth=queue_depth,
            detail=detail,
            execution_s=execution_s,
        )
