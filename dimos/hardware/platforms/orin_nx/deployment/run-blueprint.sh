#!/usr/bin/env bash
set -euo pipefail

mode=${1:-}
case "$mode" in
  sense) blueprint=${DIMOS_SENSE_BLUEPRINT:-} ;;
  shadow) blueprint=${DIMOS_SHADOW_BLUEPRINT:-} ;;
  *) printf 'usage: %s {sense|shadow}\n' "$0" >&2; exit 2 ;;
esac

if [[ -z "$blueprint" ]]; then
  printf 'no DimOS blueprint configured for mode %s\n' "$mode" >&2
  exit 2
fi
if [[ ! -f "${DIMOS_ROS_SETUP}" ]]; then
  printf 'ROS setup not found: %s\n' "${DIMOS_ROS_SETUP}" >&2
  exit 1
fi

source "${DIMOS_ROS_SETUP}"
IFS=: read -r -a overlays <<<"${DIMOS_ROS_OVERLAYS:-}"
for overlay in "${overlays[@]}"; do
  [[ -z "$overlay" ]] && continue
  if [[ ! -f "$overlay" ]]; then
    printf 'ROS overlay not found: %s\n' "$overlay" >&2
    exit 1
  fi
  source "$overlay"
done

cd "${DIMOS_REPO}"
exec "${DIMOS_CLI}" run "$blueprint"
