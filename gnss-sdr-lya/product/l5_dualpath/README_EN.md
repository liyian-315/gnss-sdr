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

`DUALPATH_OBS` and `DUALPATH_PAIR` remain compatibility outputs. `DUALPATH_STATUS version=1` is the stable product interface. Missing path-1 values are printed as `N/A`. Optional low-rate CSV is written directly by C++.

20 Msps is recommended. The 10 Msps configuration reduces realtime load but is bandwidth-limited. All research dumps and raw-IQ recording are disabled. PVT continues to consume path 0 only.

Build from the source root with:

```bash
bash product/l5_dualpath/scripts/build_release.sh
```

See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and [tests/README.md](tests/README.md) before interpreting results.
