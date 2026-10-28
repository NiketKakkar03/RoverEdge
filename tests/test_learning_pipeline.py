import hashlib
import json
from pathlib import Path

import pytest

from roveredge.learning import (
    CANDIDATE_COMMANDS,
    DatasetManifest,
    LearningState,
    Normalization,
    build_default_manifest,
    build_feature_vector,
    collision_label,
    generate_dataset,
    load_risk_model,
    predict_risk,
    save_risk_model,
    select_candidate,
    train_risk_model,
)
from roveredge.models import Pose, RunConfiguration
from roveredge.scenarios import Obstacle, Scenario


def test_dataset_manifest_separates_families_before_sampling() -> None:
    manifest = build_default_manifest()

    assert len(manifest.train_families) == 8
    assert len(manifest.validation_families) == 3
    assert len(manifest.final_test_families) == 3
    assert manifest.samples_per_family == 64
    assert manifest.candidates_per_state == 8
    assert manifest.final_test_status == "untouched"
    assert not (
        set(manifest.train_families)
        & set(manifest.validation_families)
        | set(manifest.train_families)
        & set(manifest.final_test_families)
        | set(manifest.validation_families)
        & set(manifest.final_test_families)
    )


def test_dataset_manifest_rejects_family_leakage() -> None:
    with pytest.raises(ValueError, match="family leakage"):
        DatasetManifest(
            version="risk-dataset-v1",
            train_families=("family-a",),
            validation_families=("family-a",),
            final_test_families=("family-c",),
            samples_per_family=64,
            candidates_per_state=8,
            final_test_status="untouched",
        )


def test_feature_vector_has_the_declared_literal_order() -> None:
    state = LearningState(
        range_readings_m=tuple(float(index) for index in range(16)),
        linear_velocity_mps=0.25,
        angular_velocity_radps=-0.5,
        waypoint_x_rover_m=2.0,
        waypoint_y_rover_m=-1.0,
        previous_linear_command_mps=0.4,
        previous_angular_command_radps=0.8,
    )

    features = build_feature_vector(state, CANDIDATE_COMMANDS[5])

    assert features == (
        *tuple(float(index) for index in range(16)),
        0.25,
        -0.5,
        2.0,
        -1.0,
        0.3,
        -0.8,
        0.4,
        0.8,
    )


def test_collision_label_uses_one_second_rollout_and_hidden_geometry() -> None:
    scenario = Scenario(
        scenario_version="label-fixture-v1",
        name="Label fixture",
        width_m=8.0,
        height_m=6.0,
        initial_pose=Pose(1.0, 3.0, 0.0),
        initial_linear_velocity_mps=0.0,
        dock_pose=Pose(1.0, 3.0, 0.0),
        inspection_pose=Pose(5.5, 3.0, 0.0),
        obstacles=(Obstacle("near", 1.35, 2.5, 1.65, 3.5),),
    )
    configuration = RunConfiguration()

    assert collision_label(
        Pose(1.0, 3.0, 0.0), 0.0, 0.0, CANDIDATE_COMMANDS[2], scenario, configuration
    ) == 1
    assert collision_label(
        Pose(1.0, 3.0, 0.0), 0.0, 0.0, CANDIDATE_COMMANDS[0], scenario, configuration
    ) == 0


def test_candidate_selection_prioritizes_progress_then_risk_then_index() -> None:
    risks = (0.1, 0.2, 0.3, 0.2, 0.1, 0.1, 0.1, 0.1)
    progress = (0.0, 0.2, 0.4, 0.4, 0.3, 0.3, 0.0, 0.0)

    selection = select_candidate(risks, progress, cutoff=0.35)

    assert selection.candidate_index == 3
    assert selection.command == CANDIDATE_COMMANDS[3]
    assert selection.reason == "acceptable candidate with maximum kinematic progress"


def test_candidate_selection_brakes_when_no_risk_is_acceptable() -> None:
    selection = select_candidate((0.9,) * 8, (1.0,) * 8, cutoff=0.5)

    assert selection.candidate_index == 0
    assert selection.command == CANDIDATE_COMMANDS[0]
    assert selection.reason == "no candidate below the risk cutoff; braking"


def test_normalization_is_fit_only_from_training_features() -> None:
    training = ((1.0, 10.0), (3.0, 14.0))
    normalization = Normalization.fit(training)

    assert normalization.mean == (2.0, 12.0)
    assert normalization.standard_deviation == (1.0, 2.0)
    assert normalization.transform((5.0, 8.0)) == (3.0, -2.0)


def test_training_exports_declared_model_and_leaves_final_split_untouched() -> None:
    manifest = DatasetManifest(
        version="risk-dataset-v1",
        train_families=("train-a", "train-b"),
        validation_families=("validation-a",),
        final_test_families=("final-a",),
        samples_per_family=4,
        candidates_per_state=8,
        final_test_status="untouched",
    )
    training = generate_dataset(manifest, "train")
    validation = generate_dataset(manifest, "validation")

    result = train_risk_model(training, validation, manifest, epochs=2)

    assert training.family_ids == manifest.train_families
    assert validation.family_ids == manifest.validation_families
    assert result.artifact.layer_sizes == (24, 64, 32, 1)
    assert result.artifact.dtype == "float32"
    assert result.artifact.hidden_activation == "relu"
    assert result.artifact.output_activation == "sigmoid"
    assert 0.05 <= result.artifact.risk_cutoff <= 0.95
    assert len(result.artifact.normalization.mean) == 24
    assert result.validation_evidence.final_test_status == "untouched"
    assert result.validation_evidence.examples == len(validation.labels)
    assert len(result.artifact.sha256) == 64


def test_saved_artifact_round_trips_and_runs_reference_inference(tmp_path) -> None:
    manifest = DatasetManifest(
        version="risk-dataset-v1",
        train_families=("train-a",),
        validation_families=("validation-a",),
        final_test_families=("final-a",),
        samples_per_family=2,
        candidates_per_state=8,
        final_test_status="untouched",
    )
    result = train_risk_model(
        generate_dataset(manifest, "train"),
        generate_dataset(manifest, "validation"),
        manifest,
        epochs=1,
    )
    path = tmp_path / "risk-model.json"

    save_risk_model(result.artifact, path)
    loaded = load_risk_model(path)
    risk = predict_risk(loaded, generate_dataset(manifest, "validation").features[0])

    assert loaded == result.artifact
    assert 0.0 <= risk <= 1.0

    with pytest.raises(ValueError, match="finite"):
        predict_risk(loaded, (float("nan"),) + validation_features(manifest)[1:])


def validation_features(manifest: DatasetManifest) -> tuple[float, ...]:
    return generate_dataset(manifest, "validation").features[0]


@pytest.mark.parametrize(
    ("corruption", "message"),
    [
        ("dtype", "dtype"),
        ("version", "version"),
        ("modal", "provenance"),
        ("cutoff", "finite"),
        ("normalization", "finite"),
        ("weight_shape", "dimensions"),
    ],
)
def test_loader_rejects_self_consistent_malformed_artifact(
    tmp_path, corruption: str, message: str
) -> None:
    source = json.loads(Path("artifacts/issue-8/risk-model-v1.json").read_text())
    if corruption == "dtype":
        source["dtype"] = "float64"
    elif corruption == "version":
        source["artifact_version"] = "risk-model-v2"
    elif corruption == "modal":
        source["modal_execution"] = "claimed_without_evidence"
    elif corruption == "cutoff":
        source["risk_cutoff"] = float("nan")
    elif corruption == "normalization":
        source["normalization"]["mean"][0] = float("inf")
    else:
        source["weights"][0][0].pop()
    payload = dict(source)
    del payload["sha256"]
    source["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    path = tmp_path / "unsupported.json"
    path.write_text(json.dumps(source))

    with pytest.raises(ValueError, match=message):
        load_risk_model(path)
