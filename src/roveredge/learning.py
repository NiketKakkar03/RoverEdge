import hashlib
import json
import math
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import torch

from .geometry import first_swept_collision, ray_distance
from .models import Pose, RunConfiguration
from .scenarios import Obstacle, Scenario


@dataclass(frozen=True)
class MotionCandidate:
    linear_velocity_mps: float
    angular_velocity_radps: float


CANDIDATE_COMMANDS = (
    MotionCandidate(0.0, 0.0),
    MotionCandidate(0.2, 0.0),
    MotionCandidate(0.4, 0.0),
    MotionCandidate(0.6, 0.0),
    MotionCandidate(0.3, 0.8),
    MotionCandidate(0.3, -0.8),
    MotionCandidate(0.0, 0.8),
    MotionCandidate(0.0, -0.8),
)


@dataclass(frozen=True)
class LearningState:
    range_readings_m: tuple[float, ...]
    linear_velocity_mps: float
    angular_velocity_radps: float
    waypoint_x_rover_m: float
    waypoint_y_rover_m: float
    previous_linear_command_mps: float
    previous_angular_command_radps: float

    def __post_init__(self) -> None:
        if len(self.range_readings_m) != 16:
            raise ValueError("learned controller requires exactly 16 range readings")


@dataclass(frozen=True)
class CandidateSelection:
    candidate_index: int
    command: MotionCandidate
    risk: float
    progress_score: float
    reason: str


@dataclass(frozen=True)
class Normalization:
    mean: tuple[float, ...]
    standard_deviation: tuple[float, ...]

    @classmethod
    def fit(cls, features: tuple[tuple[float, ...], ...]) -> "Normalization":
        if not features:
            raise ValueError("normalization requires training features")
        width = len(features[0])
        if any(len(row) != width for row in features):
            raise ValueError("training feature rows must have equal width")
        means = tuple(sum(row[index] for row in features) / len(features) for index in range(width))
        deviations = tuple(
            math.sqrt(sum((row[index] - means[index]) ** 2 for row in features) / len(features))
            for index in range(width)
        )
        return cls(means, tuple(value if value > 1e-12 else 1.0 for value in deviations))

    def transform(self, features: tuple[float, ...]) -> tuple[float, ...]:
        if len(features) != len(self.mean):
            raise ValueError("feature width does not match normalization")
        return tuple(
            (value - mean) / deviation
            for value, mean, deviation in zip(
                features, self.mean, self.standard_deviation, strict=True
            )
        )


@dataclass(frozen=True)
class DatasetSplit:
    split: Literal["train", "validation"]
    family_ids: tuple[str, ...]
    features: tuple[tuple[float, ...], ...]
    labels: tuple[int, ...]


@dataclass(frozen=True)
class RiskModelArtifact:
    artifact_version: str
    dataset_version: str
    layer_sizes: tuple[int, int, int, int]
    dtype: Literal["float32"]
    feature_order: tuple[str, ...]
    normalization: Normalization
    hidden_activation: Literal["relu"]
    output_activation: Literal["sigmoid"]
    weights: tuple[tuple[tuple[float, ...], ...], ...]
    biases: tuple[tuple[float, ...], ...]
    risk_cutoff: float
    training_seed: int
    modal_execution: Literal["not_used"]
    sha256: str


@dataclass(frozen=True)
class ValidationEvidence:
    examples: int
    false_negatives: int
    unnecessary_stops: int
    mean_safe_progress_score: float
    final_test_status: Literal["untouched"]


@dataclass(frozen=True)
class TrainingResult:
    artifact: RiskModelArtifact
    validation_evidence: ValidationEvidence


PathLike = str | Path


FEATURE_ORDER = tuple(
    [f"range_{index:02d}_m" for index in range(16)]
    + [
        "linear_velocity_mps",
        "angular_velocity_radps",
        "waypoint_x_rover_m",
        "waypoint_y_rover_m",
        "candidate_linear_velocity_mps",
        "candidate_angular_velocity_radps",
        "previous_linear_command_mps",
        "previous_angular_command_radps",
    ]
)


@dataclass(frozen=True)
class DatasetManifest:
    version: str
    train_families: tuple[str, ...]
    validation_families: tuple[str, ...]
    final_test_families: tuple[str, ...]
    samples_per_family: int
    candidates_per_state: int
    final_test_status: Literal["untouched"]

    def __post_init__(self) -> None:
        if self.samples_per_family <= 0 or self.candidates_per_state <= 0:
            raise ValueError("dataset sample counts must be positive")
        groups = (
            set(self.train_families),
            set(self.validation_families),
            set(self.final_test_families),
        )
        if groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2]:
            raise ValueError("family leakage across dataset splits")


def build_default_manifest() -> DatasetManifest:
    return DatasetManifest(
        version="risk-dataset-v1",
        train_families=tuple(f"train-family-{index:02d}" for index in range(8)),
        validation_families=tuple(f"validation-family-{index:02d}" for index in range(3)),
        final_test_families=tuple(f"final-family-{index:02d}" for index in range(3)),
        samples_per_family=64,
        candidates_per_state=8,
        final_test_status="untouched",
    )


def build_feature_vector(
    state: LearningState, candidate: MotionCandidate
) -> tuple[float, ...]:
    return (
        *state.range_readings_m,
        state.linear_velocity_mps,
        state.angular_velocity_radps,
        state.waypoint_x_rover_m,
        state.waypoint_y_rover_m,
        candidate.linear_velocity_mps,
        candidate.angular_velocity_radps,
        state.previous_linear_command_mps,
        state.previous_angular_command_radps,
    )


def collision_label(
    pose: Pose,
    linear_velocity_mps: float,
    angular_velocity_radps: float,
    candidate: MotionCandidate,
    scenario: Scenario,
    configuration: RunConfiguration,
) -> int:
    """Return ground truth for an immediate one-second candidate rollout."""
    elapsed_s = 0.0
    while elapsed_s < 1.0 - 1e-12:
        step_s = min(configuration.physics_step_s, 1.0 - elapsed_s)
        linear_velocity_mps = _approach(
            linear_velocity_mps,
            candidate.linear_velocity_mps,
            (
                configuration.max_braking_deceleration_mps2
                if candidate.linear_velocity_mps < linear_velocity_mps
                else configuration.max_linear_acceleration_mps2
            )
            * step_s,
        )
        angular_velocity_radps = _approach(
            angular_velocity_radps,
            candidate.angular_velocity_radps,
            configuration.max_angular_acceleration_radps2 * step_s,
        )
        heading = _normalize_angle(pose.heading_rad + angular_velocity_radps * step_s)
        next_pose = Pose(
            pose.x_m + linear_velocity_mps * math.cos(heading) * step_s,
            pose.y_m + linear_velocity_mps * math.sin(heading) * step_s,
            heading,
        )
        if (
            first_swept_collision(pose, next_pose, scenario, configuration.rover_radius_m)
            is not None
        ):
            return 1
        pose = next_pose
        elapsed_s += step_s
    return 0


def select_candidate(
    risks: tuple[float, ...], progress_scores: tuple[float, ...], cutoff: float
) -> CandidateSelection:
    if len(risks) != len(CANDIDATE_COMMANDS) or len(progress_scores) != len(
        CANDIDATE_COMMANDS
    ):
        raise ValueError("one risk and progress value is required for every candidate")
    acceptable = [index for index, risk in enumerate(risks) if risk <= cutoff]
    if not acceptable:
        return CandidateSelection(
            candidate_index=0,
            command=CANDIDATE_COMMANDS[0],
            risk=risks[0],
            progress_score=progress_scores[0],
            reason="no candidate below the risk cutoff; braking",
        )
    selected = min(
        acceptable, key=lambda index: (-progress_scores[index], risks[index], index)
    )
    return CandidateSelection(
        candidate_index=selected,
        command=CANDIDATE_COMMANDS[selected],
        risk=risks[selected],
        progress_score=progress_scores[selected],
        reason="acceptable candidate with maximum kinematic progress",
    )


def candidate_progress_score(
    waypoint_x_m: float,
    waypoint_y_m: float,
    candidate: MotionCandidate,
) -> float:
    start_distance = math.hypot(waypoint_x_m, waypoint_y_m)
    start_bearing = math.atan2(waypoint_y_m, waypoint_x_m)
    end_x = candidate.linear_velocity_mps * math.cos(candidate.angular_velocity_radps)
    end_y = candidate.linear_velocity_mps * math.sin(candidate.angular_velocity_radps)
    distance_progress = start_distance - math.hypot(
        waypoint_x_m - end_x, waypoint_y_m - end_y
    )
    alignment_progress = abs(start_bearing) - abs(
        _normalize_angle(start_bearing - candidate.angular_velocity_radps)
    )
    return distance_progress + 0.1 * alignment_progress


def generate_dataset(
    manifest: DatasetManifest, split: Literal["train", "validation"]
) -> DatasetSplit:
    family_ids = manifest.train_families if split == "train" else manifest.validation_families
    features: list[tuple[float, ...]] = []
    labels: list[int] = []
    configuration = RunConfiguration()
    for family_id in family_ids:
        seed = int.from_bytes(hashlib.sha256(family_id.encode()).digest()[:8], "big")
        generator = random.Random(seed)
        lateral_bias = generator.uniform(-0.25, 0.25)
        for _ in range(manifest.samples_per_family):
            pose = Pose(
                generator.uniform(1.0, 7.0),
                generator.uniform(1.0, 5.0),
                generator.uniform(-math.pi, math.pi),
            )
            obstacle_distance = generator.uniform(0.25, 1.25)
            obstacle_half_height = generator.uniform(0.12, 0.45)
            obstacle_center_x = (
                pose.x_m
                + obstacle_distance * math.cos(pose.heading_rad)
                - lateral_bias * math.sin(pose.heading_rad)
            )
            obstacle_center_y = (
                pose.y_m
                + obstacle_distance * math.sin(pose.heading_rad)
                + lateral_bias * math.cos(pose.heading_rad)
            )
            obstacle_half_width = generator.uniform(0.12, 0.3)
            obstacle = Obstacle(
                f"{family_id}-obstacle",
                obstacle_center_x - obstacle_half_width,
                obstacle_center_y - obstacle_half_height,
                obstacle_center_x + obstacle_half_width,
                obstacle_center_y + obstacle_half_height,
            )
            obstacles = () if generator.random() < 0.35 else (obstacle,)
            scenario = Scenario(
                scenario_version=family_id,
                name=family_id,
                width_m=8.0,
                height_m=6.0,
                initial_pose=pose,
                initial_linear_velocity_mps=0.0,
                dock_pose=Pose(1.0, 3.0, 0.0),
                inspection_pose=Pose(5.5, 3.0, 0.0),
                obstacles=obstacles,
            )
            linear_velocity = generator.uniform(0.0, 0.6)
            angular_velocity = generator.uniform(-0.3, 0.3)
            ranges = tuple(
                round(
                    ray_distance(
                        pose,
                        pose.heading_rad + index * 2 * math.pi / 16,
                        scenario,
                        configuration.range_max_m,
                    ),
                    9,
                )
                for index in range(16)
            )
            waypoint_x = generator.uniform(-4.5, 4.5)
            waypoint_y = generator.uniform(-4.5, 4.5)
            if math.hypot(waypoint_x, waypoint_y) < 0.5:
                waypoint_x += math.copysign(0.5, waypoint_x or 1.0)
            state = LearningState(
                range_readings_m=ranges,
                linear_velocity_mps=linear_velocity,
                angular_velocity_radps=angular_velocity,
                waypoint_x_rover_m=waypoint_x,
                waypoint_y_rover_m=waypoint_y,
                previous_linear_command_mps=generator.choice(CANDIDATE_COMMANDS).linear_velocity_mps,
                previous_angular_command_radps=generator.choice(
                    CANDIDATE_COMMANDS
                ).angular_velocity_radps,
            )
            for candidate in CANDIDATE_COMMANDS:
                features.append(build_feature_vector(state, candidate))
                labels.append(
                    collision_label(
                        pose,
                        linear_velocity,
                        angular_velocity,
                        candidate,
                        scenario,
                        configuration,
                    )
                )
    return DatasetSplit(split, family_ids, tuple(features), tuple(labels))


def train_risk_model(
    training: DatasetSplit,
    validation: DatasetSplit,
    manifest: DatasetManifest,
    *,
    epochs: int = 300,
    seed: int = 20261028,
) -> TrainingResult:
    if training.split != "train" or validation.split != "validation":
        raise ValueError("training requires train and validation splits")
    normalization = Normalization.fit(training.features)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    model = torch.nn.Sequential(
        torch.nn.Linear(24, 64),
        torch.nn.ReLU(),
        torch.nn.Linear(64, 32),
        torch.nn.ReLU(),
        torch.nn.Linear(32, 1),
    )
    train_x = torch.tensor(
        [normalization.transform(row) for row in training.features], dtype=torch.float32
    )
    train_y = torch.tensor(training.labels, dtype=torch.float32).reshape(-1, 1)
    positives = max(1, sum(training.labels))
    negative_count = len(training.labels) - sum(training.labels)
    loss_function = torch.nn.BCEWithLogitsLoss(
        pos_weight=torch.tensor([negative_count / positives], dtype=torch.float32)
    )
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    model.train()
    for _ in range(epochs):
        optimizer.zero_grad()
        loss = loss_function(model(train_x), train_y)
        loss.backward()
        optimizer.step()

    model.eval()
    validation_x = torch.tensor(
        [normalization.transform(row) for row in validation.features], dtype=torch.float32
    )
    with torch.no_grad():
        risks = tuple(float(value) for value in torch.sigmoid(model(validation_x)).flatten())
    cutoff, evidence = _select_cutoff(risks, validation.labels, validation.features)
    linear_layers = [layer for layer in model if isinstance(layer, torch.nn.Linear)]
    weights = tuple(
        tuple(tuple(float(value) for value in row) for row in layer.weight.detach().tolist())
        for layer in linear_layers
    )
    biases = tuple(
        tuple(float(value) for value in layer.bias.detach().tolist()) for layer in linear_layers
    )
    payload = {
        "artifact_version": "risk-model-v1",
        "dataset_version": manifest.version,
        "layer_sizes": [24, 64, 32, 1],
        "dtype": "float32",
        "feature_order": list(FEATURE_ORDER),
        "normalization": {
            "mean": normalization.mean,
            "standard_deviation": normalization.standard_deviation,
        },
        "hidden_activation": "relu",
        "output_activation": "sigmoid",
        "weights": weights,
        "biases": biases,
        "risk_cutoff": cutoff,
        "training_seed": seed,
        "modal_execution": "not_used",
    }
    artifact_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    artifact = RiskModelArtifact(
        artifact_version="risk-model-v1",
        dataset_version=manifest.version,
        layer_sizes=(24, 64, 32, 1),
        dtype="float32",
        feature_order=FEATURE_ORDER,
        normalization=normalization,
        hidden_activation="relu",
        output_activation="sigmoid",
        weights=weights,
        biases=biases,
        risk_cutoff=cutoff,
        training_seed=seed,
        modal_execution="not_used",
        sha256=artifact_hash,
    )
    return TrainingResult(artifact, evidence)


def save_risk_model(artifact: RiskModelArtifact, path: PathLike) -> None:
    Path(path).write_text(json.dumps(asdict(artifact), indent=2, sort_keys=True) + "\n")


def load_risk_model(path: PathLike) -> RiskModelArtifact:
    document = json.loads(Path(path).read_text())
    normalization = Normalization(
        mean=tuple(document["normalization"]["mean"]),
        standard_deviation=tuple(document["normalization"]["standard_deviation"]),
    )
    artifact = RiskModelArtifact(
        artifact_version=document["artifact_version"],
        dataset_version=document["dataset_version"],
        layer_sizes=tuple(document["layer_sizes"]),
        dtype=document["dtype"],
        feature_order=tuple(document["feature_order"]),
        normalization=normalization,
        hidden_activation=document["hidden_activation"],
        output_activation=document["output_activation"],
        weights=tuple(
            tuple(tuple(row) for row in layer) for layer in document["weights"]
        ),
        biases=tuple(tuple(layer) for layer in document["biases"]),
        risk_cutoff=float(document["risk_cutoff"]),
        training_seed=int(document["training_seed"]),
        modal_execution=document["modal_execution"],
        sha256=document["sha256"],
    )
    _validate_artifact(artifact)
    expected_hash = _artifact_hash(artifact)
    if artifact.sha256 != expected_hash:
        raise ValueError("risk model artifact hash does not match its contents")
    return artifact


def _validate_artifact(artifact: RiskModelArtifact) -> None:
    if (
        artifact.artifact_version != "risk-model-v1"
        or artifact.dataset_version != "risk-dataset-v1"
    ):
        raise ValueError("unsupported risk model artifact or dataset version")
    if artifact.modal_execution != "not_used":
        raise ValueError("unsupported risk model execution provenance")
    if artifact.layer_sizes != (24, 64, 32, 1) or artifact.feature_order != FEATURE_ORDER:
        raise ValueError("unsupported risk model shape or feature order")
    if (
        artifact.dtype != "float32"
        or artifact.hidden_activation != "relu"
        or artifact.output_activation != "sigmoid"
    ):
        raise ValueError("unsupported risk model dtype or activation")
    if not 0.0 < artifact.risk_cutoff < 1.0 or not math.isfinite(artifact.risk_cutoff):
        raise ValueError("risk model cutoff must be finite and between zero and one")
    if (
        len(artifact.normalization.mean) != 24
        or len(artifact.normalization.standard_deviation) != 24
    ):
        raise ValueError("risk model normalization must contain 24 values")
    if not all(math.isfinite(value) for value in artifact.normalization.mean):
        raise ValueError("risk model normalization must be finite")
    if not all(
        math.isfinite(value) and value > 0
        for value in artifact.normalization.standard_deviation
    ):
        raise ValueError("risk model normalization scales must be finite and positive")
    expected_shapes = ((64, 24), (32, 64), (1, 32))
    if len(artifact.weights) != 3 or len(artifact.biases) != 3:
        raise ValueError("risk model must contain exactly three affine layers")
    for weights, biases, (rows, columns) in zip(
        artifact.weights, artifact.biases, expected_shapes, strict=True
    ):
        if len(weights) != rows or any(len(row) != columns for row in weights):
            raise ValueError("risk model weight dimensions do not match the declared shape")
        if len(biases) != rows:
            raise ValueError("risk model bias dimensions do not match the declared shape")
        if not all(math.isfinite(value) for row in weights for value in row) or not all(
            math.isfinite(value) for value in biases
        ):
            raise ValueError("risk model parameters must be finite")


def predict_risk(artifact: RiskModelArtifact, features: tuple[float, ...]) -> float:
    if not all(math.isfinite(value) for value in features):
        raise ValueError("risk model features must be finite")
    values = artifact.normalization.transform(features)
    for layer_index, (weights, biases) in enumerate(
        zip(artifact.weights, artifact.biases, strict=True)
    ):
        values = tuple(
            sum(weight * value for weight, value in zip(row, values, strict=True)) + bias
            for row, bias in zip(weights, biases, strict=True)
        )
        if layer_index < len(artifact.weights) - 1:
            values = tuple(max(0.0, value) for value in values)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("risk model output must be finite")
    if values[0] >= 0:
        return 1.0 / (1.0 + math.exp(-values[0]))
    exponential = math.exp(values[0])
    return exponential / (1.0 + exponential)


def _artifact_hash(artifact: RiskModelArtifact) -> str:
    payload = asdict(artifact)
    del payload["sha256"]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _select_cutoff(
    risks: tuple[float, ...],
    labels: tuple[int, ...],
    features: tuple[tuple[float, ...], ...],
) -> tuple[float, ValidationEvidence]:
    ranked: list[tuple[tuple[int, int, float, float], float, ValidationEvidence]] = []
    for step in range(1, 20):
        cutoff = step * 0.05
        false_negatives = 0
        unnecessary_stops = 0
        selected_progress: list[float] = []
        for start in range(0, len(labels), len(CANDIDATE_COMMANDS)):
            state_risks = risks[start : start + len(CANDIDATE_COMMANDS)]
            state_labels = labels[start : start + len(CANDIDATE_COMMANDS)]
            state_features = features[start : start + len(CANDIDATE_COMMANDS)]
            progress = tuple(
                candidate_progress_score(row[18], row[19], candidate)
                for row, candidate in zip(state_features, CANDIDATE_COMMANDS, strict=True)
            )
            selection = select_candidate(state_risks, progress, cutoff)
            false_negatives += (
                selection.reason == "acceptable candidate with maximum kinematic progress"
                and state_labels[selection.candidate_index] == 1
            )
            unnecessary_stops += selection.candidate_index == 0 and any(
                label == 0 and candidate.linear_velocity_mps > 0
                for label, candidate in zip(state_labels, CANDIDATE_COMMANDS, strict=True)
            )
            if state_labels[selection.candidate_index] == 0:
                selected_progress.append(progress[selection.candidate_index])
        mean_progress = (
            sum(selected_progress) / len(selected_progress) if selected_progress else 0.0
        )
        evidence = ValidationEvidence(
            examples=len(labels),
            false_negatives=false_negatives,
            unnecessary_stops=unnecessary_stops,
            mean_safe_progress_score=mean_progress,
            final_test_status="untouched",
        )
        ranked.append(
            ((false_negatives, unnecessary_stops, -mean_progress, cutoff), cutoff, evidence)
        )
    _, cutoff, evidence = min(ranked, key=lambda item: item[0])
    return cutoff, evidence


def _approach(current: float, desired: float, maximum_change: float) -> float:
    if current < desired:
        return min(desired, current + maximum_change)
    return max(desired, current - maximum_change)


def _normalize_angle(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi
