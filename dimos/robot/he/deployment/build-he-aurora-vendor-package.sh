#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
request=docs/he/aurora930-vendor-support-request.md
evidence=(
  docs/he/evidence/2026-07-11_1644_aurora-depth-driver-audit.md
  docs/he/evidence/2026-07-11_1651_aurora-depth-baseline.json
  docs/he/evidence/2026-07-11_1831_aurora-depth-parameter-ab.md
  docs/he/evidence/2026-07-11_1841_aurora-field-of-view.json
  docs/he/evidence/2026-07-11_1843_aurora-field-of-view-usb-audit.md
  docs/he/evidence/2026-07-11_1848_aurora-sdk-guide-audit.md
  docs/he/evidence/2026-07-12_0213_aurora-sdk-support-probe.md
  docs/he/evidence/2026-07-12_0213_he-aurora-sdk-probe.json
  docs/he/evidence/2026-07-12_0525_visual-timing-and-executor-ab.md
  docs/he/evidence/2026-07-12_0631_native-throttle-raw-timing.json
)

for file in "$request" "${evidence[@]}"; do
  test -f "$repo_root/$file"
done

if [[ ${1:-} == --check ]]; then
  printf 'HE Aurora vendor package inputs: PASS (%d evidence files)\n' "${#evidence[@]}"
  exit 0
fi

output=${1:-/tmp/he-aurora930-vendor-support.tar.gz}
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/evidence" "$(dirname "$output")"

cp "$repo_root/$request" "$staging/README.md"
for file in "${evidence[@]}"; do
  cp "$repo_root/$file" "$staging/evidence/"
done

forbidden=$(find "$staging" -type f \( \
  -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o \
  -iname '*.rrd' -o -iname '*.db3' -o -iname '*.mcap' \) -print -quit)
if [[ -n $forbidden ]]; then
  echo 'refusing to package image, recording or rosbag payload' >&2
  exit 1
fi

(
  cd "$staging"
  find . -type f ! -name SHA256SUMS -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 sha256sum >SHA256SUMS
  sha256sum -c SHA256SUMS >/dev/null
)
tar -czf "$output" -C "$staging" .
printf 'Created %s\n' "$output"
sha256sum "$output"
