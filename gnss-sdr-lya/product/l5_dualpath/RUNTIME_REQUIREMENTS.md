# Runtime Requirements

This v1 bundle is a dynamically linked NUC/x86_64 build. It is not a portable or static Linux binary.

The target host must provide the GNU Radio, UHD, Boost, VOLK, logging, navigation, and system libraries listed in `ldd-report.txt`. The exact build host, compiler, GNU Radio version, UHD version, Git commit, and build time are recorded in `build-info.txt`.

Before running a receiver configuration, execute:

```bash
bash scripts/verify_release.sh ../l5-dualpath-v1.0.0-x86_64.tar.gz
```

For B210 operation, `uhd_find_devices` must discover the intended device and the configured serial number must match it. The release verifier checks binary and dependency integrity but does not claim RF hardware validation.
