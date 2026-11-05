"""Compare safety policies on validation families without accessing final families."""

import json
import statistics
from pathlib import Path

from roveredge.learning import (
    CANDIDATE_COMMANDS,
    LearningState,
    build_default_manifest,
    candidate_progress_score,
    generate_dataset,
    load_risk_model,
    predict_risk,
    select_safe_candidate,
)
from roveredge.safety import DEFAULT_SAFETY_ENVELOPE, MOMENTUM_AWARE_SAFETY_ENVELOPE


def main() -> None:
    dataset = generate_dataset(build_default_manifest(), "validation")
    model = load_risk_model("artifacts/issue-8/risk-model-v1.json")
    results = {}
    for safety, cutoff in (
        (DEFAULT_SAFETY_ENVELOPE, model.risk_cutoff),
        *(
            (MOMENTUM_AWARE_SAFETY_ENVELOPE, value)
            for value in (0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.005, 0.01)
        ),
    ):
        false_negatives = unnecessary_stops = 0
        progress: list[float] = []
        turn_errors: list[int] = []
        for state_index, start in enumerate(range(0, len(dataset.labels), 8)):
            rows = dataset.features[start : start + 8]
            labels = dataset.labels[start : start + 8]
            risks = tuple(predict_risk(model, row) for row in rows)
            scores = tuple(
                candidate_progress_score(row[18], row[19], candidate)
                for row, candidate in zip(rows, CANDIDATE_COMMANDS, strict=True)
            )
            first = rows[0]
            state = LearningState(
                tuple(first[:16]), first[16], first[17], first[18], first[19], first[22], first[23]
            )
            selected = select_safe_candidate(risks, scores, cutoff, state, safety)
            unsafe = selected.candidate_index != 0 and labels[selected.candidate_index] == 1
            false_negatives += int(unsafe)
            if unsafe and selected.candidate_index in (6, 7):
                turn_errors.append(state_index)
            unnecessary_stops += int(
                selected.candidate_index == 0
                and any(
                    label == 0 and candidate.linear_velocity_mps > 0
                    for label, candidate in zip(labels, CANDIDATE_COMMANDS, strict=True)
                )
            )
            if labels[selected.candidate_index] == 0:
                progress.append(scores[selected.candidate_index])
        results[f"{safety.version}@{cutoff:g}"] = {
            "states": len(dataset.labels) // 8,
            "false_negatives": false_negatives,
            "unsafe_turn_state_indices": turn_errors,
            "unnecessary_stops": unnecessary_stops,
            "unnecessary_stop_rate": unnecessary_stops / (len(dataset.labels) // 8),
            "mean_safe_progress_score": statistics.fmean(progress),
        }
    output = Path("artifacts/issue-22/validation-safety-v2-probe.json")
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
