import math

import pytest

from roveredge.device import FifoDevice, InferenceRequest, ModeledDeviceProfile, QueuePolicy


def request(identifier: int, observed_at_s: float = 0.0) -> InferenceRequest[str]:
    return InferenceRequest(
        episode_id="episode-1",
        observation_id=identifier,
        request_id=identifier,
        candidate_set_id="candidate-set-v1",
        model_sha256="model-sha",
        observed_at_s=observed_at_s,
        payload=f"result-{identifier}",
    )


def test_fifo_device_freezes_completion_consumption_and_boundary_semantics() -> None:
    device = FifoDevice[str](
        ModeledDeviceProfile(
            dispatch_s=0.01,
            input_transfer_s=0.01,
            compute_s=0.02,
            output_transfer_s=0.01,
            deadline_s=0.05,
            maximum_age_s=0.1,
        )
    )

    assert [event.kind for event in device.submit(request(1), 0.0)] == ["dispatched"]
    assert device.advance(0.049) == ()
    assert [event.kind for event in device.advance(0.05)] == ["completed"]
    completed, events = device.consume_latest(0.1)

    assert completed is not None
    assert completed.request.payload == "result-1"
    assert completed.age_at_completion_s == 0.05
    assert [event.kind for event in events] == ["consumed"]


@pytest.mark.parametrize("policy", ["fifo", "latest_pending"])
def test_fifo_device_records_overflow_and_expiry(policy: QueuePolicy) -> None:
    device = FifoDevice[str](
        ModeledDeviceProfile(
            compute_s=0.2,
            pending_capacity=1,
            maximum_age_s=0.1,
            queue_policy=policy,
        )
    )

    device.submit(request(1), 0.0)
    assert [event.kind for event in device.submit(request(2, 0.01), 0.01)] == ["admitted"]
    assert [event.kind for event in device.submit(request(3, 0.02), 0.02)] == [
        "overflow" if policy == "fifo" else "replaced"
    ]
    assert [event.kind for event in device.advance(0.21)] == ["completed", "deadline_missed"]
    assert [event.kind for event in device.submit(request(4, 0.21), 0.21)] == [
        "expired",
        "dispatched",
    ]


@pytest.mark.parametrize("policy", ["fifo", "latest_pending"])
def test_fifo_device_defers_dispatch_and_accepts_exact_deadline(policy: QueuePolicy) -> None:
    device = FifoDevice[str](
        ModeledDeviceProfile(
            dispatch_s=0.01,
            input_transfer_s=0.01,
            compute_s=0.02,
            output_transfer_s=0.01,
            deadline_s=0.05,
            queue_policy=policy,
        )
    )
    device.submit(request(1), 0.0)
    device.submit(request(2, 0.01), 0.01)

    assert [event.kind for event in device.advance(0.05)] == ["completed"]
    _, consumed = device.consume_latest(0.05)
    dispatched = device.submit(request(3, 0.05), 0.05)

    assert [event.kind for event in consumed] == ["consumed"]
    assert [event.kind for event in dispatched] == ["dispatched"]
    assert dispatched[0].request_id == 2


def test_fifo_device_marks_only_completion_beyond_deadline() -> None:
    device = FifoDevice[str](
        ModeledDeviceProfile(compute_s=0.020001, deadline_s=0.025)
    )
    device.submit(request(1), 0.0)

    assert [event.kind for event in device.advance(0.025002)] == [
        "completed",
        "deadline_missed",
    ]


@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_modeled_device_rejects_nonfinite_timing(value: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        ModeledDeviceProfile(compute_s=value)
    with pytest.raises(ValueError, match="finite"):
        ModeledDeviceProfile(maximum_age_s=value)


def test_latest_pending_replaces_waiting_work_without_canceling_execution() -> None:
    device = FifoDevice[str](
        ModeledDeviceProfile(
            compute_s=0.2,
            pending_capacity=2,
            maximum_age_s=1.0,
            queue_policy="latest_pending",
        )
    )
    device.submit(request(1), 0.0)
    device.submit(request(2, 0.01), 0.01)

    replacement = device.submit(request(3, 0.02), 0.02)

    assert [event.kind for event in replacement] == ["replaced"]
    assert replacement[0].request_id == 2
    assert [event.request_id for event in device.advance(0.206)] == [1, 1]
    assert [event.request_id for event in device.submit(request(4, 0.206), 0.206)] == [3]


def test_burst_fixture_exposes_fifo_overflow_and_latest_replacement() -> None:
    fifo = FifoDevice[str](ModeledDeviceProfile(compute_s=0.2, pending_capacity=1))
    latest = FifoDevice[str](
        ModeledDeviceProfile(
            compute_s=0.2, pending_capacity=1, queue_policy="latest_pending"
        )
    )
    for device in (fifo, latest):
        device.submit(request(1), 0.0)
        device.submit(request(2), 0.0)

    assert [event.kind for event in fifo.submit(request(3), 0.0)] == ["overflow"]
    assert [event.kind for event in latest.submit(request(3), 0.0)] == ["replaced"]
