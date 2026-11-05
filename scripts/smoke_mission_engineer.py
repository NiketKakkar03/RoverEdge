"""Manually exercise the explicitly-confirmed hosted Baseten mission-engineer path."""

import argparse
import json
from dataclasses import asdict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from roveredge import physical_run_request, run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one guarded hosted Baseten mission-engineer smoke test."
    )
    parser.add_argument("--endpoint", required=True, help="Hosted RoverEdge base URL")
    parser.add_argument("--confirm-live-provider-call", action="store_true")
    arguments = parser.parse_args()
    if not arguments.confirm_live_provider_call:
        parser.error("pass --confirm-live-provider-call to authorize two Baseten requests")

    baseline = run_experiment(physical_run_request("preset-open-v2"))
    payload = json.dumps(
        {
            "baseline": asdict(baseline),
            "instruction": (
                "Inspect the baseline trace, test one permitted runtime change, and report "
                "only a bounded controlled conclusion with real evidence citations."
            ),
            "confirm_live_provider_call": True,
        }
    ).encode()
    request = Request(
        arguments.endpoint.rstrip("/") + "/api/investigations/live",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:  # noqa: S310 - explicit user endpoint.
            if response.status != 200:
                raise RuntimeError(f"hosted investigation returned HTTP {response.status}")
            document = json.loads(response.read())
    except HTTPError as error:
        try:
            detail = json.loads(error.read()).get("detail", str(error))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = str(error)
        raise SystemExit(f"hosted investigation failed: {detail}") from error
    except (URLError, TimeoutError) as error:
        raise SystemExit(f"hosted investigation failed: {error}") from error

    investigation = document["investigation"]
    sanitized = {
        "source_label": document["source_label"],
        "provider": document["provider"],
        "model": document["model"],
        "provider_calls_used": document["provider_calls_used"],
        "baseline_run_id": investigation["baseline_run_id"],
        "follow_up_run_ids": [run["run_id"] for run in investigation["follow_up_runs"]],
        "comparison_valid": [
            comparison["valid"] for comparison in investigation["comparisons"]
        ],
        "finding": investigation["explanation"]["finding"],
    }
    print(json.dumps(sanitized, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
