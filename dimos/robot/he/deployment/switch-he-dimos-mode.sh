#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
deployment="$repo_root/dimos/robot/he/deployment"
mode=${1:-status}

if [[ $mode != status && $mode != check && $EUID -ne 0 ]]; then
  echo "Run mode changes with sudo: sudo $0 {shadow|sense}" >&2
  exit 2
fi

wait_active() {
  local service=$1
  local attempts=${2:-30}
  for _ in $(seq 1 "$attempts"); do
    if systemctl is-active --quiet "$service"; then
      return 0
    fi
    sleep 1
  done
  echo "$service did not become active" >&2
  return 1
}

wait_gate() {
  local gate=$1
  local gate_log
  gate_log=$(mktemp)
  for _ in $(seq 1 6); do
    if bash "$gate" >"$gate_log" 2>&1; then
      cat "$gate_log"
      rm -f "$gate_log"
      return 0
    fi
    sleep 5
  done
  cat "$gate_log" >&2
  rm -f "$gate_log"
  return 1
}

restore_sense() {
  set +e
  systemctl stop he-dimos-shadow.service
  systemctl start he-dimos-sense.service
  wait_active he-dimos-sense.service 30
  wait_gate "$deployment/verify-he-readonly.sh"
}

restore_sense_on_error() {
  local status=$?
  restore_sense
  exit "$status"
}

case "$mode" in
  check)
    bash -n "$deployment/switch-he-dimos-mode.sh"
    bash -n "$deployment/verify-he-shadow-readonly.sh"
    systemd-analyze verify \
      "$deployment/he-dimos-sense.service" \
      "$deployment/he-dimos-shadow.service"
    printf 'HE DimOS service-mode artifacts: PASS\n'
    ;;
  shadow)
    bash "$deployment/verify-he-readonly.sh"
    trap restore_sense_on_error ERR
    systemctl start he-dimos-shadow.service
    wait_active he-dimos-shadow.service 30
    wait_gate "$deployment/verify-he-shadow-readonly.sh"
    trap - ERR
    ;;
  sense)
    systemctl stop he-dimos-shadow.service
    systemctl start he-dimos-sense.service
    wait_active he-dimos-sense.service 30
    wait_gate "$deployment/verify-he-readonly.sh"
    ;;
  status)
    systemctl show he-dimos-sense.service \
      -p ActiveState -p SubState -p MainPID -p MemoryCurrent
    systemctl show he-dimos-shadow.service \
      -p ActiveState -p SubState -p MainPID -p MemoryCurrent
    ;;
  *)
    echo "Usage: $0 {shadow|sense|status|check}" >&2
    exit 2
    ;;
esac
