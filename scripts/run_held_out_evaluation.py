import json

from roveredge.held_out_execution import execute

if __name__ == "__main__":
    print(json.dumps(execute(), indent=2, sort_keys=True))
