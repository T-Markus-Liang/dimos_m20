#!/usr/bin/env bash
set -euo pipefail

max_mib=${HE_RTABMAP_MAX_DB_MIB:-256}
poll_seconds=${HE_RTABMAP_DB_POLL_SECONDS:-2}

if [[ ! "$max_mib" =~ ^[1-9][0-9]*$ ]] || ((max_mib > 4096)); then
  echo "HE_RTABMAP_MAX_DB_MIB must be an integer from 1 to 4096" >&2
  exit 2
fi
if [[ ! "$poll_seconds" =~ ^[1-9][0-9]*$ ]] || ((poll_seconds > 60)); then
  echo "HE_RTABMAP_DB_POLL_SECONDS must be an integer from 1 to 60" >&2
  exit 2
fi

max_bytes=$((max_mib * 1024 * 1024))
if [[ "${1:-}" == --check ]]; then
  echo "HE RTAB-Map database limit: ${max_mib} MiB (poll ${poll_seconds}s)"
  exit 0
fi

database=${1:?database path is required}
while true; do
  database_bytes=$(stat -c %s "$database" 2>/dev/null || printf 0)
  if ((database_bytes >= max_bytes)); then
    echo "HE RTAB-Map database reached ${database_bytes} bytes; limit is ${max_bytes}" >&2
    exit 42
  fi
  sleep "$poll_seconds"
done
