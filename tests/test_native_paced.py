from concurrent.futures import Executor, Future

from roveredge.device import InferenceRequest
from roveredge.native_paced import NativePacedExecutor, TimedScores


class ManualExecutor(Executor):
    def __init__(self) -> None:
        self.calls: list[
            tuple[Future[TimedScores], tuple[tuple[float, ...], ...]]
        ] = []

    def submit(self, function, batch):  # type: ignore[no-untyped-def]
        future: Future[TimedScores] = Future()
        self.calls.append((future, batch))
        return future

    def shutdown(self, wait: bool = True) -> None:
        return None


def request(identifier: int) -> InferenceRequest[tuple[tuple[float, ...], ...]]:
    return InferenceRequest(
        episode_id="episode-test",
        observation_id=identifier,
        request_id=identifier,
        candidate_set_id="candidate-set-v1",
        model_sha256="model-sha",
        observed_at_s=identifier * 0.05,
        payload=((float(identifier),),),
    )


def test_native_paced_executor_keeps_only_newest_pending_observation() -> None:
    pool = ManualExecutor()
    executor: NativePacedExecutor[tuple[tuple[float, ...], ...]] = NativePacedExecutor(
        lambda batch: (batch[0][0],), executor=pool
    )

    assert [event.kind for event in executor.submit(request(0), 0.0)] == ["dispatched"]
    assert [event.kind for event in executor.submit(request(1), 0.05)] == ["admitted"]
    replacement = executor.submit(request(2), 0.1)
    assert [event.kind for event in replacement] == ["replaced", "admitted"]
    assert replacement[0].request_id == 1

    pool.calls[0][0].set_result(TimedScores((0.0,), 10.0, 10.001))
    completed, events = executor.poll(0.1)

    assert completed is not None
    assert completed.request.request_id == 0
    assert [event.kind for event in events] == ["completed", "dispatched"]
    assert len(pool.calls) == 2
    assert pool.calls[1][1] == request(2).payload


def test_native_paced_executor_reports_strict_expiry_boundary_and_newer_precedence() -> None:
    pool = ManualExecutor()
    executor: NativePacedExecutor[tuple[tuple[float, ...], ...]] = NativePacedExecutor(
        lambda batch: (batch[0][0],), executor=pool
    )
    executor.submit(request(0), 0.0)
    pool.calls[0][0].set_result(TimedScores((0.0,), 10.0, 10.001))

    completion, _ = executor.poll(0.1)
    assert completion is not None
    assert executor.accept(completion, 0.1, maximum_age_s=0.1) is not None
    assert executor.accept(completion, 0.100001, maximum_age_s=0.1) is None

    executor.note_accepted_observation(3)
    assert executor.accept(completion, 0.05, maximum_age_s=1.0) is None
