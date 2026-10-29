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

    assert [event.kind for event in device.submit(request(1), 0.0)] == [
        "memory_allocated",
        "dispatched",
    ]
    assert device.advance(0.049) == ()
    assert [event.kind for event in device.advance(0.05)] == [
        "completed",
        "memory_released",
    ]
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
    assert [event.kind for event in device.submit(request(2, 0.01), 0.01)] == [
        "memory_allocated",
        "admitted",
    ]
    assert [event.kind for event in device.submit(request(3, 0.02), 0.02)] == (
        ["overflow"]
        if policy == "fifo"
        else ["memory_released", "memory_allocated", "replaced"]
    )
    assert [event.kind for event in device.advance(0.21)] == [
        "completed",
        "memory_released",
        "deadline_missed",
    ]
    assert [event.kind for event in device.submit(request(4, 0.21), 0.21)] == [
        "memory_allocated",
        "expired",
        "memory_released",
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

    assert [event.kind for event in device.advance(0.05)] == [
        "completed",
        "memory_released",
    ]
    _, consumed = device.consume_latest(0.05)
    dispatched = device.submit(request(3, 0.05), 0.05)

    assert [event.kind for event in consumed] == ["consumed"]
    assert [event.kind for event in dispatched] == ["memory_allocated", "dispatched"]
    assert dispatched[1].request_id == 2


def test_fifo_device_marks_only_completion_beyond_deadline() -> None:
    device = FifoDevice[str](
        ModeledDeviceProfile(compute_s=0.020001, deadline_s=0.025)
    )
    device.submit(request(1), 0.0)

    assert [event.kind for event in device.advance(0.025002)] == [
        "completed",
        "memory_released",
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

    assert [event.kind for event in replacement] == [
        "memory_released",
        "memory_allocated",
        "replaced",
    ]
    assert replacement[-1].request_id == 2
    assert [event.request_id for event in device.advance(0.206)] == [1, 1, 1]
    assert [event.request_id for event in device.submit(request(4, 0.206), 0.206)] == [
        4,
        3,
    ]


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
    assert fifo.memory_summary["pending_payload_bytes"] == 1_024
    assert fifo.memory_summary["in_flight_payload_bytes"] == 1_024
    assert [event.kind for event in latest.submit(request(3), 0.0)] == [
        "memory_released",
        "memory_allocated",
        "replaced",
    ]


def test_modeled_memory_accepts_exact_boundary_and_rejects_one_byte_less() -> None:
    exact = FifoDevice[str](
        ModeledDeviceProfile(
            resident_weights_bytes=100,
            workspace_bytes=20,
            request_payload_bytes=10,
            memory_budget_bytes=130,
        )
    )
    constrained = FifoDevice[str](
        ModeledDeviceProfile(
            resident_weights_bytes=100,
            workspace_bytes=20,
            request_payload_bytes=10,
            memory_budget_bytes=129,
        )
    )

    exact_events = exact.submit(request(1), 0.0)
    constrained_events = constrained.submit(request(1), 0.0)

    assert [event.kind for event in exact_events] == ["memory_allocated", "dispatched"]
    assert exact_events[0].modeled_memory_bytes == 130
    assert exact_events[0].memory_budget_bytes == 130
    assert [event.kind for event in constrained_events] == ["memory_rejected"]
    assert constrained_events[0].modeled_memory_bytes == 120
    assert constrained_events[0].memory_budget_bytes == 129


@pytest.mark.parametrize(
    "changes",
    [
        {"pending_capacity": 1.5},
        {"requests_per_tick": 1.5},
        {"memory_budget_bytes": 32_768.5},
    ],
)
def test_modeled_device_rejects_noninteger_capacity_and_memory(changes: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="integers"):
        ModeledDeviceProfile(**changes)


def test_modeled_device_rejects_deadline_beyond_maximum_age() -> None:
    with pytest.raises(ValueError, match="deadline cannot exceed"):
        ModeledDeviceProfile(deadline_s=0.2, maximum_age_s=0.1)


def test_modeled_memory_releases_payloads_after_completion_replacement_and_expiry() -> None:
    profile = ModeledDeviceProfile(
        compute_s=0.2,
        pending_capacity=2,
        maximum_age_s=0.1,
        queue_policy="latest_pending",
        resident_weights_bytes=100,
        workspace_bytes=20,
        request_payload_bytes=10,
        memory_budget_bytes=140,
    )
    device = FifoDevice[str](profile)

    device.submit(request(1), 0.0)
    device.submit(request(2, 0.01), 0.01)
    replacement = device.submit(request(3, 0.02), 0.02)
    completion = device.advance(0.21)
    dispatch_after_expiry = device.submit(request(4, 0.21), 0.21)

    assert [event.kind for event in replacement] == [
        "memory_released",
        "memory_allocated",
        "replaced",
    ]
    assert [event.kind for event in completion] == [
        "completed",
        "memory_released",
        "deadline_missed",
    ]
    assert [event.kind for event in dispatch_after_expiry] == [
        "memory_allocated",
        "expired",
        "memory_released",
        "dispatched",
    ]
    assert device.memory_summary == {
        "resident_weights_bytes": 100,
        "workspace_bytes": 20,
        "pending_payload_bytes": 0,
        "in_flight_payload_bytes": 10,
        "current_modeled_memory_bytes": 130,
        "peak_modeled_memory_bytes": 140,
        "memory_budget_bytes": 140,
        "memory_rejections": 0,
    }

    terminal_release = device.release_all(0.22)

    assert [event.kind for event in terminal_release] == [
        "dropped",
        "memory_released",
    ]
    assert device.memory_summary["current_modeled_memory_bytes"] == 120
    assert device.memory_summary["in_flight_payload_bytes"] == 0
