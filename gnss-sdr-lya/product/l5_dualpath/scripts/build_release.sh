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
cmake -S "$root" -B "$build_dir" -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF
cmake --build "$build_dir" --target gnss-sdr -- -j"$jobs"

binary="$build_dir/src/main/gnss-sdr"
[[ -x $binary ]] || { echo "ERROR: expected binary missing: $binary" >&2; exit 1; }
"$binary" --version
for config in "$product_dir"/conf/*.conf; do [[ -f $config ]] || { echo "ERROR: product config missing" >&2; exit 1; }; done
bash "$script_dir/check_runtime.sh" "$binary" "$product_dir/conf/l5_dualpath_b210_20msps.conf"

mkdir -p "$stage/bin" "$stage/conf" "$stage/scripts" "$stage/LICENSES"
cp "$binary" "$stage/bin/gnss-sdr"
cp "$product_dir"/conf/*.conf "$stage/conf/"
cp "$product_dir"/README_CN.md "$product_dir"/README_EN.md "$product_dir"/CHANGELOG.md "$product_dir"/KNOWN_LIMITATIONS.md "$product_dir"/VERSION "$stage/"
cp "$script_dir/check_runtime.sh" "$script_dir/check_status_log.sh" "$stage/scripts/"
cp -a "$root/LICENSES/." "$stage/LICENSES/"
git -C "$root" rev-parse HEAD > "$stage/git-commit.txt"
ldd "$binary" > "$stage/ldd-report.txt"
{
    echo "version=$version"
    echo "git_sha=$(git -C "$root" rev-parse HEAD)"
    echo "build_time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "host=$(uname -a)"
    echo "cmake=$(cmake --version | head -1)"
    echo "compiler=$(${CXX:-c++} --version | head -1)"
    echo "uhd=$(uhd_config_info --version 2>/dev/null || echo unavailable)"
    echo "gnuradio=$(pkg-config --modversion gnuradio-runtime 2>/dev/null || echo unavailable)"
    echo "validation=CODE COMPLETE; realtime B210 validation pending"
} > "$stage/build-info.txt"
(cd "$stage" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C "$dist_dir" -czf "$archive" "$name"
sha256sum "$archive" > "$archive.sha256"
echo "Created $archive"
echo "Created $archive.sha256"
