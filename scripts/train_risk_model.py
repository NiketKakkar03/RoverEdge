import hashlib
import json
import platform
from dataclasses import asdict
from pathlib import Path

import numpy
import torch

from roveredge.learning import (
    FEATURE_ORDER,
    build_default_manifest,
    generate_dataset,
    save_risk_model,
    train_risk_model,
)


def main() -> None:
    output = Path("artifacts/issue-8")
    output.mkdir(parents=True, exist_ok=True)
    manifest = build_default_manifest()
    training = generate_dataset(manifest, "train")
    validation = generate_dataset(manifest, "validation")
    result = train_risk_model(training, validation, manifest)
    manifest_document = asdict(manifest)
    manifest_document.update(
        {
            "generator_version": "synthetic-risk-generator-v1",
            "family_seed_derivation": "first 8 bytes of SHA-256(family_id), big-endian",
            "feature_order": FEATURE_ORDER,
            "label_contract": "collision during immediate one-second rollout",
            "split_hashes": {
                split: hashlib.sha256("\n".join(families).encode()).hexdigest()
                for split, families in {
                    "train": manifest.train_families,
                    "validation": manifest.validation_families,
                    "final_test": manifest.final_test_families,
                }.items()
            },
            "generated_row_hashes": {
                split.split: hashlib.sha256(
                    json.dumps(
                        {"features": split.features, "labels": split.labels},
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                for split in (training, validation)
            },
        }
    )
    (output / "dataset-manifest.json").write_text(
        json.dumps(manifest_document, indent=2, sort_keys=True) + "\n"
    )
    save_risk_model(result.artifact, output / "risk-model-v1.json")
    state_count = result.validation_evidence.examples // manifest.candidates_per_state
    validation_document = {
        **asdict(result.validation_evidence),
        "states": state_count,
        "selected_risk_cutoff": result.artifact.risk_cutoff,
        "model_sha256": result.artifact.sha256,
        "metric_definitions": {
            "false_negatives": "selected accepted commands whose rollout label is collision",
            "unnecessary_stops": "brake selections where a moving collision-free candidate exists",
            "mean_safe_progress_score": (
                "mean dimensionless distance-and-alignment progress score "
                "for safe selected commands"
            ),
        },
        "proposed_quality_requirements": {
            "false_negatives": 0,
            "maximum_unnecessary_stop_rate": 0.1,
            "minimum_mean_safe_progress_score": 0.3,
        },
        "quality_gate_status": (
            "met"
            if result.validation_evidence.false_negatives == 0
            and result.validation_evidence.unnecessary_stops / state_count <= 0.1
            and result.validation_evidence.mean_safe_progress_score >= 0.3
            else "not_met"
        ),
        "training": {
            "epochs": 300,
            "seed": result.artifact.training_seed,
            "device": "cpu",
            "torch_version": torch.__version__,
            "numpy_version": numpy.__version__,
            "python_version": platform.python_version(),
            "modal_execution": "not_used",
            "optimizer": "Adam",
            "learning_rate": 0.01,
            "loss": "BCEWithLogitsLoss",
            "positive_weighting": "negative_count / positive_count from training split",
        },
    }
    (output / "validation-report.json").write_text(
        json.dumps(validation_document, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
