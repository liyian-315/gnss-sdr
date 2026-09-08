# GPS L5 Dual-Path Receiver v1

Status: **CODE COMPLETE; formal file-replay and realtime B210 product validation are pending.**

This product runs two independent tracking chains for the same GPS L5 PRN when acquisition already contains two clearly separated peaks. C++ emits both pseudoranges, CN0 values, Dopplers, their delta, and a quality state. Python is not a runtime dependency.

Edit the B210 serial, gain, and matching PRNs in the configuration, then run:

```bash
./bin/gnss-sdr --config_file=conf/l5_dualpath_b210_20msps.conf 2>&1 | tee l5_dualpath_run.log
```

Validate a package and optionally run it for 60 seconds:

```bash
bash scripts/check_runtime.sh ./bin/gnss-sdr conf/l5_dualpath_b210_20msps.conf --run-seconds 60
```

`L5_SIGNAL_STATUS` reports each channel's staged tracking, L5Q secondary-code, CNAV TOW, valid-word, interpolation, and pseudorange state. Its `waiting_for` field identifies the first unmet stage, while unavailable CN0 and pseudorange values are printed as `N/A`.

`DUALPATH_OBS` and `DUALPATH_PAIR` remain compatibility outputs. `DUALPATH_STATUS version=1` is the stable product interface. Missing path-1 values are printed as `N/A`. Optional low-rate CSV is written directly by C++.

The B210 configurations enable a path-1 watchdog. If three consecutive valid observations collapse inside the configured main-peak exclusion distance, `DUALPATH_REACQUIRE` is printed and only path 1 is reset. Failed second-peak acquisitions repeat, so moving the antenna back inside the detectable range can recover without restarting the receiver.

20 Msps is recommended. The 10 Msps configuration reduces realtime load but is bandwidth-limited. All research dumps and raw-IQ recording are disabled. PVT continues to consume path 0 only.

Build from the source root with:

```bash
bash product/l5_dualpath/scripts/build_release.sh
```

The bundle targets the NUC/x86_64 host and its current dynamic runtime; it is not a static portable build. Verify both checksum layers after packaging:

```bash
sha256sum -c dist/l5-dualpath-v1.0.0-x86_64.tar.gz.sha256
bash product/l5_dualpath/scripts/verify_release.sh dist/l5-dualpath-v1.0.0-x86_64.tar.gz
```

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), [RUNTIME_REQUIREMENTS.md](RUNTIME_REQUIREMENTS.md), and the source-tree `tests/README.md` before interpreting results.
