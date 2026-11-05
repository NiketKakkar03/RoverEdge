"""Execute only the separately reviewed v8 held-out schedule."""

import json

from roveredge.held_out_execution import OUTPUT_V8, execute

if __name__ == "__main__":
    print(json.dumps(execute(output=OUTPUT_V8, variant="v8"), indent=2, sort_keys=True))
