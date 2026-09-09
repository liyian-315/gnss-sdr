# Known Limitations

1. v1 only handles two acquisition peaks that are already clearly separated. It does not claim 0.5-chip, sub-chip, or merged-peak super-resolution.
2. The current static product configurations use a 1.25-chip minimum acquisition separation. This is a product guardrail, not a measured universal resolution limit.
3. 10 Msps truncates GPS L5 bandwidth and reduces delay resolution. Use 20 Msps for characterization.
4. The second path is diagnostic only and is excluded from PVT.
5. More than two sources, antenna arrays, receiver-motion trajectory estimation, and research MEDLL/delay-Doppler Python fitters are outside v1.
6. Peak-quality and state thresholds are provisional until the complete negative/positive file-replay matrix and B210 tests are run.
7. `RELIABLE` means the configured online quality gates passed. It does not prove which physical transmitter is LOS or that the reported delay is unbiased.
8. Independent simulators can have relative clock/Doppler drift. The provisional 1000 Hz pair gate admits the approximately 800 Hz offset reported by the current hardware test, but still requires B210 positive- and negative-control validation before release.
9. A target PRN must carry usable L5 and remain trackable. Phone CN0 is not interchangeable with B210/GNSS-SDR CN0.
10. No minimum separable distance, detection probability, or false-alarm rate is claimed until independent validation supports it.
