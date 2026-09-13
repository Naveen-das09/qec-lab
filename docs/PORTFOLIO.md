# Portfolio case study

## Project

QEC Lab is a local first research workspace for quantum error correction. It gives a researcher one place to design an experiment, run a real Stim and PyMatching surface code simulation, inspect logical failures, compare runs, and export the evidence needed to reproduce the result.

The product also includes an optional Gemini powered research assistant. The assistant can read the selected evidence, validate a proposed experiment, and explain the measured result. Experiment execution stays behind an explicit user action so an AI suggestion never silently becomes a scientific claim.

## The problem

Quantum error correction experiments often spread across notebooks, scripts, simulator logs, decoder configuration, and hand written notes. That makes it difficult to answer simple questions:

- Which noise model produced this curve?
- Did the decoder use the same measurement noise as the circuit?
- Which detector events caused a logical failure?
- Can another researcher replay the exact batches and seeds?

QEC Lab turns those questions into a traceable investigation workflow.

## What to show in a portfolio demo

1. Open the workspace and select **Configure experiment**.
2. Run the **Baseline sweep** preset.
3. Select a measured chart point and open **Explore a failing shot**.
4. Show the detector coordinates, syndrome time slice, and actual versus predicted logical parity.
5. Run **Measurement stress**, then use **Compare a run** to show the overlay and uncertainty.
6. Open **Reports** and export the investigation bundle.
7. Explain that the bundle contains the specification, report, CSV measurements, exact circuits, decoder model, seeds, dependency versions, and replay script.

This sequence demonstrates product design, scientific computing, data provenance, and the AI boundary in under five minutes.

## Engineering highlights

- **Scientific core:** Stim circuit generation, circuit level Pauli noise, PyMatching MWPM decoding, deterministic batch seeds, and Wilson intervals.
- **Product layer:** responsive browser workspace, editable experiment plans, chart selection, failure explorer, comparison view, history, reports, and settings.
- **Agent layer:** bounded Gemini GenerateContent tool loop with typed evidence and staging tools. The assistant can propose; the user decides when to run.
- **Reproducibility:** SQLite persistence, provenance records, CSV and Markdown exports, exact circuit and decoder artifacts, and independent replay verification.
- **Operations:** local job queue, cooperative cancellation, time budgets, restart recovery, Docker packaging, API documentation, and CI tests.

## Scope and future work

This release is a single trusted local workspace. It deliberately does not claim to be a hosted multi tenant SaaS or a production hardware control plane. The next product milestones are authenticated team workspaces, durable distributed workers, richer agent evaluations, adaptive sampling with statistical guarantees, additional code families, and validated hardware adapters.

## Suggested portfolio description

> Built QEC Lab, an open source quantum error correction research workspace that combines real Stim and PyMatching simulations with reproducible experiment artifacts, failure level inspection, and an evidence grounded Gemini research assistant. Designed the end to end product experience from experiment planning and execution through comparison, provenance, export, and replay.

