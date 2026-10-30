import argparse
from pathlib import Path

from roveredge.evidence import load_evidence_bundle, reproduce_evidence_bundle


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate and reproduce a RoverEdge evidence bundle."
    )
    parser.add_argument("bundle", type=Path, help="Path to a downloaded evidence ZIP")
    arguments = parser.parse_args()

    result = reproduce_evidence_bundle(load_evidence_bundle(arguments.bundle.read_bytes()))
    print(f"verified {len(result.run_ids)} run(s): {', '.join(result.run_ids)}")


if __name__ == "__main__":
    main()
