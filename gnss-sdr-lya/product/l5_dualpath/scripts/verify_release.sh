#!/usr/bin/env bash
set -euo pipefail

[[ $# -eq 1 ]] || { echo "Usage: $0 <l5-dualpath-archive.tar.gz>" >&2; exit 2; }
archive=$(realpath "$1")
archive_sum="${archive}.sha256"
[[ -f $archive ]] || { echo "ERROR: archive not found: $archive" >&2; exit 1; }
[[ -f $archive_sum ]] || { echo "ERROR: archive checksum not found: $archive_sum" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cp "$archive" "$archive_sum" "$work/"
archive_name=$(basename "$archive")

(cd "$work" && sha256sum -c "${archive_name}.sha256")
tar -C "$work" -xzf "$work/$archive_name"
mapfile -t package_dirs < <(find "$work" -mindepth 1 -maxdepth 1 -type d)
[[ ${#package_dirs[@]} -eq 1 ]] || { echo "ERROR: archive must contain exactly one package directory" >&2; exit 1; }
package=${package_dirs[0]}

cd "$package"
sha256sum -c SHA256SUMS
[[ -x bin/gnss-sdr ]] || { echo "ERROR: bin/gnss-sdr is missing or not executable" >&2; exit 1; }
[[ -s KNOWN_LIMITATIONS.md ]] || { echo "ERROR: KNOWN_LIMITATIONS.md is missing" >&2; exit 1; }
[[ -s RUNTIME_REQUIREMENTS.md ]] || { echo "ERROR: RUNTIME_REQUIREMENTS.md is missing" >&2; exit 1; }
grep -Eq '^[0-9a-f]{40}$' git-commit.txt || { echo "ERROR: invalid git-commit.txt" >&2; exit 1; }

bin/gnss-sdr --version
for config in conf/*.conf; do
    bash scripts/check_runtime.sh bin/gnss-sdr "$config"
done
ldd bin/gnss-sdr > "$work/ldd-report.txt"
if grep -q 'not found' "$work/ldd-report.txt"; then
    grep 'not found' "$work/ldd-report.txt" >&2
    echo "ERROR: missing dynamic libraries" >&2
    exit 1
fi

echo "Release verification: PASS"
