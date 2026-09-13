"""The scientific core. No web or LLM dependencies."""

import math
import platform
import time
from importlib.metadata import version
from typing import Literal

import numpy as np
import pymatching
import stim
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Experiment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(
        default="Surface-code noise investigation", min_length=1, max_length=120
    )
    question: str = Field(
        default="How does code distance affect logical memory performance?",
        max_length=2000,
    )
    distances: list[int] = Field(default=[3, 5, 7], min_length=1, max_length=4)
    probabilities: list[float] = Field(
        default=[0.001, 0.003, 0.005, 0.007, 0.01], min_length=1, max_length=6
    )
    rounds: int = Field(default=5, ge=1, le=25)
    shots: int = Field(default=10000, ge=100, le=100000)
    measurement_multiplier: float = Field(default=1, ge=0, le=10)
    decoder: Literal["matched", "mismatched"] = "matched"
    seed: int = Field(default=42, ge=0, le=2147483647)
    budget_seconds: int = Field(default=120, ge=1, le=600)

    @field_validator("distances")
    @classmethod
    def valid_distances(cls, values):
        if any(d not in (3, 5, 7, 9) for d in values) or len(set(values)) != len(
            values
        ):
            raise ValueError("Choose unique odd distances from 3, 5, 7, 9.")
        return sorted(values)

    @field_validator("probabilities")
    @classmethod
    def valid_probabilities(cls, values):
        if any(not math.isfinite(p) or not 0 <= p <= 0.05 for p in values) or len(
            set(values)
        ) != len(values):
            raise ValueError("Choose unique probabilities between 0 and 0.05.")
        return sorted(values)

    @model_validator(mode="after")
    def bounded_work(self):
        if len(self.distances) * len(self.probabilities) * self.shots > 2400000:
            raise ValueError("An investigation is limited to 2.4 million shots.")
        return self


def circuit_for(spec: Experiment, distance: int, p: float, *, decoder=False):
    multiplier = (
        1 if decoder and spec.decoder == "mismatched" else spec.measurement_multiplier
    )
    return stim.Circuit.generated(
        "surface_code:rotated_memory_z",
        distance=distance,
        rounds=spec.rounds,
        after_clifford_depolarization=p,
        before_round_data_depolarization=p,
        before_measure_flip_probability=p * multiplier,
        after_reset_flip_probability=p,
    )


def wilson(errors: int, shots: int):
    """Two-sided nominal 95% Wilson interval for a binomial proportion."""
    if shots == 0:
        return [0.0, 1.0]
    z = 1.959963984540054
    rate = errors / shots
    denominator = 1 + z * z / shots
    center = (rate + z * z / (2 * shots)) / denominator
    radius = (
        z
        * math.sqrt(rate * (1 - rate) / shots + z * z / (4 * shots * shots))
        / denominator
    )
    return [max(0, center - radius), min(1, center + radius)]


def environment():
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "stim": version("stim"),
        "pymatching": version("pymatching"),
        "numpy": version("numpy"),
        "batch_size": 2048,
        "schema_version": 1,
    }


def simulate(spec: Experiment, update=lambda *_: None, cancelled=lambda: False):
    """Fixed-shot design, bounded by wall time; publishes partial points per batch.

    Seeds and batch sizes are recorded. Stim reproducibility also depends on
    version, SIMD architecture, and the sequence of sampling calls.
    """
    started = time.monotonic()
    points = []
    total = len(spec.distances) * len(spec.probabilities)
    for d in spec.distances:
        for p in spec.probabilities:
            if cancelled() or time.monotonic() - started >= spec.budget_seconds:
                return points, "cancelled" if cancelled() else "budget_reached"
            circuit = circuit_for(spec, d, p)
            matching = pymatching.Matching.from_detector_error_model(
                circuit_for(spec, d, p, decoder=True).detector_error_model(
                    decompose_errors=True
                )
            )
            point = {
                "id": f"d{d}-p{p!r}",
                "distance": d,
                "p": p,
                "shots": 0,
                "errors": 0,
                "rate": 0,
                "interval": [0, 1],
                "decode_seconds": 0,
                "complete": False,
                "batches": [],
                "failure": None,
                "qubits": len(circuit.get_final_qubit_coordinates()),
                "detectors": circuit.num_detectors,
            }
            points.append(point)
            while point["shots"] < spec.shots:
                if cancelled() or time.monotonic() - started >= spec.budget_seconds:
                    update(points, (len(points) - 1) / total)
                    return points, "cancelled" if cancelled() else "budget_reached"
                n = min(2048, spec.shots - point["shots"])
                seed = spec.seed + (len(points) - 1) * 100000 + len(point["batches"])
                sampler = circuit.compile_detector_sampler(seed=seed)
                detectors, actual = sampler.sample(n, separate_observables=True)
                before = time.perf_counter()
                predicted = matching.decode_batch(detectors)
                point["decode_seconds"] += time.perf_counter() - before
                failed = np.any(predicted != actual, axis=1)
                if point["failure"] is None and failed.any():
                    idx = int(np.flatnonzero(failed)[0])
                    coords = circuit.get_detector_coordinates()
                    point["failure"] = {
                        "batch_seed": seed,
                        "batch_shots": n,
                        "shot_index": idx,
                        "events": np.flatnonzero(detectors[idx]).tolist(),
                        "coordinates": {str(k): v for k, v in coords.items()},
                        "actual": actual[idx].astype(int).tolist(),
                        "predicted": predicted[idx].astype(int).tolist(),
                    }
                point["shots"] += n
                point["errors"] += int(failed.sum())
                point["rate"] = point["errors"] / point["shots"]
                point["interval"] = wilson(point["errors"], point["shots"])
                point["batches"].append({"seed": seed, "shots": n})
                point["complete"] = point["shots"] == spec.shots
                update(
                    points, ((len(points) - 1) + point["shots"] / spec.shots) / total
                )
    return points, "completed"


def report(run):
    s = run["spec"]
    lines = [
        f'# {s["title"]}',
        "",
        s["question"],
        "",
        f'Run: {run["id"]} · Status: {run["status"]}',
        "",
        "## Method",
        "",
        f'Rotated surface-code Z memory; {s["rounds"]} syndrome rounds. PyMatching MWPM, {s["decoder"]} noise weights.',
        f'Clifford and round-data depolarization = p; reset flips = p; measurement flips = {s["measurement_multiplier"]} × p.',
        "The x-axis p is a channel parameter, not an aggregate device error probability.",
        "",
        "## Observations",
        "",
        "| Distance | p | Failures / shots | Logical error / memory experiment | 95% Wilson interval |",
        "|---|---|---|---|---|",
    ]
    for v in run["points"]:
        if v["shots"]:
            lines.append(
                f'| {v["distance"]} | {v["p"]:g} | {v["errors"]} / {v["shots"]} | {v["rate"]:.6g} | [{v["interval"][0]:.6g}, {v["interval"][1]:.6g}] |'
            )
    lines += [
        "",
        "## Interpretation limits",
        "",
        "Intervals are nominal, pointwise binomial intervals for the fixed-shot design. Live or budget-truncated results are provisional; no sequential coverage or simultaneous coverage is claimed.",
        "Zero observed failures do not establish zero failure probability. These finite-distance sweeps do not establish an asymptotic threshold.",
        "Failure views show detection events and logical observable predictions, not an inferred exact physical error history.",
        "Decoder timing measures batched decoding only, excludes graph construction and sampling, and is not real-time hardware latency.",
        "",
        "## Reproduction",
        "",
        "The export contains circuits, all sampling batch seeds and sizes, dependency versions, and replay.py. Exact sample reproduction requires compatible Stim version and SIMD architecture.",
        "",
        f'Environment: {run["environment"]}',
        "",
    ]
    return "\n".join(lines)
