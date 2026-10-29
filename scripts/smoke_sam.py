import argparse
import json
from dataclasses import asdict
from pathlib import Path

from roveredge.grounding import MetaSamGroundingAdapter
from roveredge.scene_rendering import render_scene


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Make exactly one explicitly confirmed live SAM 3.1 request."
    )
    parser.add_argument("--phrase", required=True)
    parser.add_argument("--scenario", default="preset-perception-v1")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--confirm-live-provider-call", action="store_true")
    arguments = parser.parse_args()
    if not arguments.confirm_live_provider_call:
        parser.error("pass --confirm-live-provider-call to authorize exactly one Meta API request")

    render = render_scene(arguments.scenario)
    adapter = MetaSamGroundingAdapter()
    evidence = adapter.ground(render, arguments.phrase)
    request_shape = {
        "endpoint": "https://api.meta.ai/v1/responses",
        "model": "sam-3.1",
        "input": [{"role": "user", "content_types": ["input_text", "input_image"]}],
        "target_phrase": arguments.phrase,
        "render_sha256": render.sha256,
        "metadata": {"mask_encoding": "one_bit", "include_confidence": "true"},
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(
            {
                "request": request_shape,
                "evidence": asdict(evidence),
                "sanitized_raw_output": adapter.last_raw_output,
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "status": evidence.status,
                "matches": len(evidence.matches),
                "render_sha256": evidence.render_sha256,
                "output": str(arguments.output),
            }
        )
    )


if __name__ == "__main__":
    main()
