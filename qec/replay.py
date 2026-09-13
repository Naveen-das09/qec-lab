"""Run from an extracted QEC Lab export: python replay.py."""

import json
from pathlib import Path

import numpy as np
import pymatching
import stim


def main():
    root = Path(__file__).resolve().parent
    run = json.loads((root / "run.json").read_text())
    for point in run["points"]:
        circuit = stim.Circuit((root / f'circuits/{point["id"]}.stim').read_text())
        decoder = pymatching.Matching.from_detector_error_model(
            stim.DetectorErrorModel((root / f'circuits/{point["id"]}.dem').read_text())
        )
        errors = shots = 0
        for batch in point["batches"]:
            d, obs = circuit.compile_detector_sampler(seed=batch["seed"]).sample(
                batch["shots"], separate_observables=True
            )
            errors += int(np.any(decoder.decode_batch(d) != obs, axis=1).sum())
            shots += batch["shots"]
        print(
            f'{point["id"]}: {errors}/{shots}; saved {point["errors"]}/{point["shots"]}'
        )
        if errors != point["errors"]:
            raise SystemExit(
                "Samples differ: check Stim version and CPU SIMD architecture."
            )


if __name__ == "__main__":
    main()
