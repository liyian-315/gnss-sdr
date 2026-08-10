# Product Validation Protocol

The repository contains code and test orchestration, not raw IQ. Raw captures stay outside Git and are referenced through a local copy of `replay_manifest.example.csv`.

## Layer 1: C++ tests

Required cases are implemented for path1 no-fallback, second-peak gates, key/time pairing, equal pseudoranges, weak CN0, Doppler mismatch, stable median/MAD, sudden delay jump, path1 loss/recovery, state transitions, and exact output formatting.

The release-blocking fix round must configure the target NUC with `-DENABLE_UNIT_TESTING=ON`, build the registered `run_tests` target, and execute the DualPath, Acquisition, and Observables regression suites. Directly compiling individual test files is not accepted as release evidence.

## Layer 2: file replay

Copy `replay_manifest.example.csv` to an external data directory, replace every path, and record one row per run. Required categories:

- single-source negative control;
- 1000 m dual source;
- approximately 200-220 m stable dual source;
- 350 m or another verified long-distance condition;
- known near-distance failure;
- noise or target-PRN-absent control.

For every row report primary/second lock rate, RELIABLE fraction, false reliable fraction, delta median/MAD, successful reacquisition count, expected delay/error, and PASS/MARGINAL/UNRESOLVED. No threshold is final until both positive and negative controls pass.

## Layer 3: realtime B210

Run single source for 30 minutes, dual source for 30 minutes, stop/restart source B, vary path power ratio, restart GNSS-SDR, and restart the simulator. Record overflow, CPU, RSS, log growth, state fractions, and reacquisitions. A single-source run must not contain sustained RELIABLE path1.

## Layer 4: distance ladder

Test 1000, 700, 350, approximately 220, 200, 100, and 50 m, at least three independent runs each. Record PASS/MARGINAL/UNRESOLVED. The smallest product-supported distance is the smallest independently passing condition, not the configured 1.25-chip guardrail or a theoretical estimate.

Until layers 2 and 3 pass, the only permitted label is `CODE COMPLETE`.
