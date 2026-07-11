#!/usr/bin/env bash
set -Eeuo pipefail

[[ $# -eq 1 && $1 = /*.json ]] || {
  echo "Usage: $0 /absolute/output.json" >&2
  exit 2
}

output=$1
repo=/home/ubuntu/he/dimos_wd_m20
sdk=/home/ubuntu/third_party/aurora_ws/src/deptrum-ros-driver-aurora930-0.2.11/ext/deptrum-stream-aurora900-linux-aarch64-v1.1.22-18.04
binary=/tmp/he-aurora-sdk-probe
sdk_stdout=/tmp/he-aurora-sdk-probe.$$.stdout
sdk_stderr=/tmp/he-aurora-sdk-probe.$$.stderr
restored=false

set +u
source /opt/ros/humble/setup.bash
source /home/ubuntu/third_party/aurora_ws/install/setup.bash
set -u

verify_readonly_converged() {
  local gate_log=
  for _ in {1..6}; do
    if gate_log=$(bash dimos/robot/he/deployment/verify-he-readonly.sh 2>&1); then
      printf '%s\n' "$gate_log"
      return 0
    fi
    sleep 3
  done
  printf '%s\n' "$gate_log" >&2
  return 1
}

restore_service() {
  [[ $restored == true ]] && return
  sudo systemctl start aurora930.service
  for _ in {1..40}; do
    systemctl is-active --quiet aurora930.service && break
    sleep 0.25
  done
  systemctl is-active --quiet aurora930.service
  sleep 10
  restored=true
}

on_exit() {
  status=$?
  trap - EXIT INT TERM
  restore_service || status=$?
  cd "$repo"
  .venv/bin/python dimos/robot/he/deployment/verify-he-sensors.py \
    --image-samples 5 --pointcloud-samples 2 --timeout 15 || status=$?
  verify_readonly_converged || status=$?
  rm -f "$binary" "$sdk_stdout" "$sdk_stderr"
  exit "$status"
}
trap on_exit EXIT INT TERM

cd "$repo"
[[ -d $sdk/include && -f $sdk/lib/libdeptrum_stream_aurora900.so ]]
mkdir -p "$(dirname "$output")"

g++ -std=c++17 -O2 -Wall -Wextra -Werror \
  -I"$sdk/include" \
  dimos/robot/he/deployment/probe-he-aurora-sdk.cc \
  -L"$sdk/lib" -Wl,-rpath,"$sdk/lib" \
  -ldeptrum_stream_aurora900 -o "$binary"

bash dimos/robot/he/deployment/verify-he-readonly.sh
sudo systemctl stop aurora930.service
sleep 1
if pgrep -f '/aurora930_node|ros2 launch.*aurora930_launch.py' >/dev/null; then
  echo "Aurora process remained after stopping the canonical service" >&2
  exit 1
fi

timeout 20 "$binary" "$output" >"$sdk_stdout" 2>"$sdk_stderr"
python3 -m json.tool "$output" >/dev/null
python3 - "$output" "$(git rev-parse HEAD)" <<'PY'
import json
from pathlib import Path
import sys
import time

path = Path(sys.argv[1])
report = json.loads(path.read_text())
report["captured_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
report["git_head"] = sys.argv[2]
path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
PY

restore_service
.venv/bin/python dimos/robot/he/deployment/verify-he-sensors.py \
  --image-samples 5 --pointcloud-samples 2 --timeout 15
verify_readonly_converged

trap - EXIT INT TERM
rm -f "$binary" "$sdk_stdout" "$sdk_stderr"
printf 'Aurora SDK read-only probe complete: %s\n' "$output"
