# Gemini live validation

## Scope

A live smoke test exercised QEC Lab's HTTP assistant endpoint with `gemini-3.8-flash`, the actual provider, and locally measured Stim/PyMatching results. Credentials and local conversation files are excluded from the repository.

## Planning

The assistant called `propose_experiment` and staged a validated specification: distance 3, physical noise parameter 0.005, five syndrome rounds, 1,000 shots, matched decoder, measurement multiplier 1, seed 42, and a 30-second budget. It explicitly instructed the user to review and run the plan. The number of investigations remained two before and after planning.

The validation driver then explicitly submitted the plan to the run endpoint. The assistant itself did not execute it. This check covers the API workflow; it is not a browser click-through test.

## Evidence analysis

The completed run `53dda75f-aa7b-4e1a-a967-cc73f676f96f` produced:

| Measurement | Recorded value |
| --- | --- |
| Point ID | `d3-p0.005` |
| Logical failures / shots | 23 / 1,000 |
| Logical error probability per memory experiment | 0.023 |
| 95% Wilson interval | [0.0153742769, 0.0342764507] |

The live assistant returned HTTP 200 with the trace `Read measured evidence`. Its point ID, counts, rate, and rounded interval agreed with the saved results. It explained that this single point does not establish a threshold. Its proposal was null and the number of investigations did not change.

## Service failures and limits

Earlier analysis attempts received HTTP 503. The integration now retries HTTP 502, 503, and 504 up to three attempts per provider request, waiting one and two seconds between attempts and checking the assistant time budget before each attempt. Completed local tool calls are not replayed by these HTTP retries. Persistent service failures produce an availability message rather than implying that the key is invalid.

The analysis succeeded on a later request after this change; the live record does not establish that retries caused recovery. Automated tests separately cover recovery, persistent failures, and non-retryable authentication errors. The full suite passes 30 tests.

This smoke test does not establish general factual accuracy, availability, or reliability across models and research questions. Broader evaluation should cover zero-failure points, incomplete runs, misleading questions, and multi-run comparisons.
