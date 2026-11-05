"""Record v2 candidate behavior on existing nonfinal mission presets."""

import json
from dataclasses import replace
from pathlib import Path

from roveredge.physical import run_physical_experiment
from roveredge.scenarios import physical_run_request


def main() -> None:
    results = {}
    for scenario in ("preset-open-v2", "preset-narrow-v1", "preset-cluttered-v1"):
        base = physical_run_request(scenario)
        request = replace(
            base,
            configuration=replace(
                base.configuration,
                controller_kind="learned_collision_risk",
                model_artifact_version="risk-model-v2",
                safety_envelope_version="sensor-stopping-v2",
            ),
        )
        result = run_physical_experiment(request)
        results[scenario] = {
            "mission_outcome": result.mission_outcome,
            "test_verdict": result.test_verdict,
            "model_sha256": result.request.configuration.model_sha256,
            "risk_cutoff": result.request.configuration.risk_cutoff,
            "safety_envelope_version": result.request.configuration.safety_envelope_version,
            "timing_provenance": result.inference_summary["timing_provenance"]
            if result.inference_summary
            else None,
        }
    output = Path("artifacts/issue-22/validation-candidate-v2-missions.json")
    output.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(output.read_text())


if __name__ == "__main__":
    main()
