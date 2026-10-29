from dataclasses import replace
from pathlib import Path

import pytest

from roveredge.experiment import run_experiment
from roveredge.grounding import (
    GroundingAdapter,
    MetaSamGroundingAdapter,
    RecordedGroundingAdapter,
    _box_local_raster_to_counts,
)
from roveredge.models import (
    GroundingEvidence,
    GroundingMask,
    GroundingMatch,
    MissionOutcome,
    VisualTarget,
)
from roveredge.scenarios import physical_run_request


class LiteralGroundingAdapter(GroundingAdapter):
    def __init__(self, evidence: GroundingEvidence) -> None:
        self.evidence = evidence

    def ground(self, render, phrase: str) -> GroundingEvidence:
        assert phrase == self.evidence.target_phrase
        return self.evidence


def test_recorded_mask_grounds_target_and_completes_physical_mission() -> None:
    request = replace(
        physical_run_request("preset-perception-v1"),
        target=VisualTarget(
            kind="visual_target",
            phrase="red toolbox",
            grounding_source="recorded",
        ),
    )
    from roveredge.scene_rendering import render_scene

    render = render_scene("preset-perception-v1")
    evidence = GroundingEvidence(
        source="recorded",
        status="matched",
        provider="meta",
        model="sam-3.1",
        parser_version="contract-fixture-v1",
        target_phrase="red toolbox",
        render_sha256=render.sha256,
        render_width_px=800,
        render_height_px=600,
        duration_s=0.0,
        raw_output_sha256="fixture-output-sha256",
        matches=(
            GroundingMatch(
                ordinal=0,
                box_px=(620, 250, 680, 350),
                mask=GroundingMask(
                    width_px=800,
                    height_px=600,
                    counts=_rectangle_rle(800, 600, 620, 250, 680, 350),
                ),
                confidence=0.98,
            ),
        ),
        selected_match_ordinal=0,
    )

    result = run_experiment(request, LiteralGroundingAdapter(evidence))

    assert result.mission_outcome == "completed"
    assert result.test_verdict == "passed"
    assert result.grounding_evidence is not None
    assert result.grounding_evidence.source == "recorded"
    assert result.grounding_evidence.derived_inspection_pose is not None
    assert result.grounding_evidence.derived_inspection_pose.x_m == pytest.approx(5.45)
    assert result.grounding_evidence.derived_inspection_pose.y_m == pytest.approx(3.0)
    assert result.grounding_evidence.derived_inspection_pose.heading_rad == pytest.approx(0.0)
    assert result.observations[0].target_id.startswith("grounded:")
    assert result.request == request


@pytest.mark.parametrize(
    ("status", "match_count"),
    [("target_not_found", 0), ("target_ambiguous", 2), ("provider_unavailable", 0)],
)
def test_grounding_setup_outcomes_stop_before_rover_motion(status: str, match_count: int) -> None:
    request = replace(
        physical_run_request("preset-perception-v1"),
        target=VisualTarget(
            kind="visual_target", phrase="red toolbox", grounding_source="recorded"
        ),
        expected_mission_outcome=status,
    )
    from roveredge.scene_rendering import render_scene

    render = render_scene("preset-perception-v1")
    match = GroundingMatch(
        ordinal=0,
        box_px=(620, 250, 680, 350),
        mask=GroundingMask(
            width_px=800,
            height_px=600,
            counts=_rectangle_rle(800, 600, 620, 250, 680, 350),
        ),
    )
    evidence = GroundingEvidence(
        source="recorded",
        status=status,
        provider="meta",
        model="sam-3.1",
        parser_version="contract-fixture-v1",
        target_phrase="red toolbox",
        render_sha256=render.sha256,
        render_width_px=800,
        render_height_px=600,
        duration_s=0.0,
        raw_output_sha256="fixture-output-sha256",
        matches=tuple(replace(match, ordinal=index) for index in range(match_count)),
    )

    result = run_experiment(request, LiteralGroundingAdapter(evidence))

    assert result.mission_outcome == status
    assert result.test_verdict == "passed"
    assert result.observations == ()
    assert len(result.trace) == 1
    assert result.trace[0].phase == "setup_failed"
    assert result.trace[0].pose.x_m == 1.0


def test_grounding_rejects_evidence_for_a_different_render() -> None:
    request = replace(
        physical_run_request("preset-perception-v1"),
        target=VisualTarget(
            kind="visual_target", phrase="red toolbox", grounding_source="recorded"
        ),
    )
    evidence = GroundingEvidence(
        source="recorded",
        status="target_not_found",
        provider="meta",
        model="sam-3.1",
        parser_version="contract-fixture-v1",
        target_phrase="red toolbox",
        render_sha256="different-render",
        render_width_px=800,
        render_height_px=600,
        duration_s=0.0,
        raw_output_sha256="fixture-output-sha256",
        matches=(),
    )

    with pytest.raises(ValueError, match="render hash"):
        run_experiment(request, LiteralGroundingAdapter(evidence))


def test_live_adapter_without_process_key_records_unavailability_without_a_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    from roveredge.scene_rendering import render_scene

    evidence = MetaSamGroundingAdapter().ground(
        render_scene("preset-perception-v1"), "red toolbox"
    )

    assert evidence.status == "provider_unavailable"
    assert evidence.matches == ()
    assert evidence.diagnostics == ("MODEL_API_KEY is not set in the process",)


def test_box_local_provider_mask_is_placed_on_the_full_render() -> None:
    counts = _box_local_raster_to_counts(
        bytes((1, 0, 0, 1)),
        mask_width_px=2,
        mask_height_px=2,
        render_width_px=4,
        render_height_px=3,
        left_px=1,
        top_px=1,
    )

    assert sum(counts) == 12
    assert counts == (5, 1, 4, 1, 1)


@pytest.mark.parametrize(
    ("scenario_version", "phrase", "expected_outcome", "expected_matches"),
    [
        ("preset-perception-v1", "red toolbox", "completed", 1),
        ("preset-perception-v1", "blue barrel", "completed", 1),
        ("fixture-perception-shifted-v1", "red toolbox", "completed", 1),
        ("fixture-perception-shifted-v1", "blue barrel", "completed", 1),
        (
            "fixture-perception-absent-v1",
            "red toolbox",
            "target_not_found",
            0,
        ),
        (
            "fixture-perception-ambiguous-v1",
            "red toolbox",
            "target_ambiguous",
            2,
        ),
    ],
)
def test_sanitized_live_capture_replays_offline(
    scenario_version: str,
    phrase: str,
    expected_outcome: MissionOutcome,
    expected_matches: int,
) -> None:
    artifact_name = f"{scenario_version}--{phrase.replace(' ', '-')}.json"
    adapter = RecordedGroundingAdapter.from_file(
        Path(__file__).parents[1] / "artifacts" / "issue-4" / "recorded" / artifact_name
    )
    request = replace(
        physical_run_request(scenario_version),
        target=VisualTarget(
            kind="visual_target", phrase=phrase, grounding_source="recorded"
        ),
        expected_mission_outcome=expected_outcome,
    )

    result = run_experiment(request, adapter)

    assert result.mission_outcome == expected_outcome
    assert result.test_verdict == "passed"
    assert result.grounding_evidence is not None
    assert len(result.grounding_evidence.matches) == expected_matches


def _rectangle_rle(
    width: int, height: int, left: int, top: int, right: int, bottom: int
) -> tuple[int, ...]:
    values = [
        1 if left <= x < right and top <= y < bottom else 0
        for y in range(height)
        for x in range(width)
    ]
    counts: list[int] = []
    current = 0
    run = 0
    for value in values:
        if value == current:
            run += 1
        else:
            counts.append(run)
            current = value
            run = 1
    counts.append(run)
    return tuple(counts)
