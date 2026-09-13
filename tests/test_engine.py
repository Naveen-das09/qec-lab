import numpy as np
import pymatching
import pytest

from qec.engine import Experiment, circuit_for, simulate, wilson


def test_noiseless_memory_and_nonzero_upper_bound():
    points, status = simulate(Experiment(distances=[3], probabilities=[0], shots=1000))
    assert status == "completed"
    assert points[0]["errors"] == 0
    assert points[0]["qubits"] == 17
    assert points[0]["interval"][0] == pytest.approx(0)
    assert 0 < points[0]["interval"][1] < 0.004


def test_fixed_seed_and_failure_replay():
    spec = Experiment(distances=[3], probabilities=[0.01], shots=3000)
    points, status = simulate(spec)
    repeated, _ = simulate(spec)
    point = points[0]
    assert status == "completed" and point["complete"]
    assert point["shots"] == 3000
    assert point["errors"] == repeated[0]["errors"]
    assert point["failure"] == repeated[0]["failure"]
    f = point["failure"]
    assert f is not None
    circuit = circuit_for(spec, 3, 0.01)
    detectors, actual = circuit.compile_detector_sampler(seed=f["batch_seed"]).sample(
        f["batch_shots"], separate_observables=True
    )
    decoder = pymatching.Matching.from_detector_error_model(
        circuit.detector_error_model(decompose_errors=True)
    )
    predictions = decoder.decode_batch(detectors)
    index = f["shot_index"]
    assert actual[index].astype(int).tolist() == f["actual"]
    assert predictions[index].astype(int).tolist() == f["predicted"]
    assert np.flatnonzero(detectors[index]).tolist() == f["events"]
    assert f["actual"] != f["predicted"]


def test_mismatched_weights_preserve_sampling_circuit():
    matched = Experiment(distances=[3], measurement_multiplier=3)
    mismatch = matched.model_copy(update={"decoder": "mismatched"})
    assert circuit_for(matched, 3, 0.005) == circuit_for(mismatch, 3, 0.005)
    assert circuit_for(matched, 3, 0.005, decoder=True) != circuit_for(
        mismatch, 3, 0.005, decoder=True
    )


@pytest.mark.parametrize(
    "change",
    [
        {"distances": [2]},
        {"distances": [3, 3]},
        {"probabilities": [-0.1]},
        {"probabilities": [float("nan")]},
        {"probabilities": [0.1]},
        {"shots": 0},
        {"rounds": 26},
        {"decoder": "imaginary"},
        {"budget_seconds": 1000},
        {"extra": True},
    ],
)
def test_rejects_unsupported_or_unbounded_plans(change):
    with pytest.raises(ValueError):
        Experiment(**change)


def test_cancellation_preserves_partial_batches():
    seen = []
    points, status = simulate(
        Experiment(distances=[3], probabilities=[0.01], shots=10000),
        lambda points, progress: seen.append(progress),
        lambda: bool(seen),
    )
    assert status == "cancelled"
    assert points[0]["shots"] == 2048
    assert not points[0]["complete"]


def test_budget_stops_before_new_point(monkeypatch):
    times = iter([0, 2])
    monkeypatch.setattr("qec.engine.time.monotonic", lambda: next(times))
    points, status = simulate(Experiment(budget_seconds=1))
    assert points == [] and status == "budget_reached"


def test_wilson_reference_interval():
    low, high = wilson(50, 100)
    assert low == pytest.approx(0.4038315, abs=1e-6)
    assert high == pytest.approx(0.5961685, abs=1e-6)
