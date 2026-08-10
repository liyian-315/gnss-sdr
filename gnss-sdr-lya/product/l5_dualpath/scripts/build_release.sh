#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
product_dir=$(cd -- "$script_dir/.." && pwd)
root=$(cd -- "$product_dir/../.." && pwd)
version=$(tr -d '[:space:]' < "$product_dir/VERSION")
build_dir=${BUILD_DIR:-"$root/build-product-l5-dualpath"}
dist_dir=${DIST_DIR:-"$root/dist"}
jobs=${JOBS:-$(nproc)}
arch=$(uname -m)
name="l5-dualpath-v${version}-${arch}"
stage="$dist_dir/$name"
archive="$dist_dir/$name.tar.gz"

mkdir -p "$dist_dir"
[[ ! -e $stage ]] || { echo "ERROR: staging path already exists: $stage" >&2; exit 1; }
[[ $arch == "x86_64" ]] || { echo "ERROR: v1 NUC package requires x86_64, got $arch" >&2; exit 1; }
if grep -qi microsoft /proc/version 2>/dev/null; then
    echo "ERROR: build the v1 release package on the target NUC, not WSL" >&2
    exit 1
fi
command -v uhd_config_info >/dev/null || { echo "ERROR: uhd_config_info is required" >&2; exit 1; }
pkg-config --exists gnuradio-runtime || { echo "ERROR: gnuradio-runtime development metadata is required" >&2; exit 1; }

cmake -S "$root" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=ON
cmake --build "$build_dir" --target gnss-sdr -- -j"$jobs"

binary="$build_dir/src/main/gnss-sdr"
[[ -x $binary ]] || { echo "ERROR: expected binary missing: $binary" >&2; exit 1; }
"$binary" --version
for config in "$product_dir"/conf/*.conf; do [[ -f $config ]] || { echo "ERROR: product config missing" >&2; exit 1; }; done
bash "$script_dir/check_runtime.sh" "$binary" "$product_dir/conf/l5_dualpath_b210_20msps.conf"

mkdir -p "$stage/bin" "$stage/conf" "$stage/scripts" "$stage/tests" "$stage/LICENSES"
cp "$binary" "$stage/bin/gnss-sdr"
cp "$product_dir"/conf/*.conf "$stage/conf/"
cp "$product_dir"/README_CN.md "$product_dir"/README_EN.md "$product_dir"/CHANGELOG.md "$product_dir"/KNOWN_LIMITATIONS.md "$product_dir"/RUNTIME_REQUIREMENTS.md "$product_dir"/VERSION "$stage/"
cp "$script_dir/check_runtime.sh" "$script_dir/check_status_log.sh" "$script_dir/run_file_replay_validation.sh" "$script_dir/verify_release.sh" "$stage/scripts/"
cp "$product_dir/tests/README.md" "$product_dir/tests/replay_manifest.example.csv" "$stage/tests/"
cp -a "$root/LICENSES/." "$stage/LICENSES/"
git -C "$root" rev-parse HEAD > "$stage/git-commit.txt"
ldd "$binary" > "$stage/ldd-report.txt"
{
    echo "version=$version"
    echo "git_sha=$(git -C "$root" rev-parse HEAD)"
    echo "build_time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "target=NUC"
    echo "hostname=$(hostname)"
    echo "arch=$arch"
    echo "os=$(grep '^PRETTY_NAME=' /etc/os-release | cut -d= -f2- | tr -d '\"')"
    echo "kernel=$(uname -sr)"
    echo "cmake=$(cmake --version | head -1)"
    echo "compiler=$(${CXX:-c++} --version | head -1)"
    echo "uhd=$(uhd_config_info --version 2>/dev/null || echo unavailable)"
    echo "gnuradio=$(pkg-config --modversion gnuradio-runtime 2>/dev/null || echo unavailable)"
    echo "validation=CODE COMPLETE; realtime B210 validation pending"
} > "$stage/build-info.txt"
(cd "$stage" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C "$dist_dir" -czf "$archive" "$name"
(cd "$dist_dir" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256")
echo "Created $archive"
echo "Created $archive.sha256"
