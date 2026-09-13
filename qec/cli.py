"""Run the same scientific engine without the web interface."""

import argparse
import json
from pathlib import Path

from .engine import Experiment, environment, simulate


def main():
    parser = argparse.ArgumentParser(
        description="Run a QEC Lab JSON experiment specification"
    )
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    spec = Experiment.model_validate_json(args.spec.read_text())
    points, status = simulate(spec)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "spec": spec.model_dump(),
                "points": points,
                "status": status,
                "environment": environment(),
            },
            indent=2,
        )
    )
    print(f"{status}: {len(points)} points saved to {args.output}")


if __name__ == "__main__":
    main()
