#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  echo "Usage: $0 PARAMETER VALUE OUTPUT.json [SAMPLES]" >&2
  exit 2
}

[[ $# -ge 3 && $# -le 4 ]] || usage

parameter=$1
value=$2
output=$3
samples=${4:-30}
repo=/home/ubuntu/he/dimos_wd_m20
launch_pid=
restored=false

case "$parameter" in
  threshold_size|laser_power|align_mode|depth_correction|minimum_filter_depth_value|maximum_filter_depth_value|resolution_mode_index|rgbd_enable) ;;
  *)
    echo "Unsupported Aurora930 parameter: $parameter" >&2
    exit 2
    ;;
esac

[[ $output = /*.json ]] || {
  echo "OUTPUT must be an absolute .json path" >&2
  exit 2
}
[[ $samples =~ ^[0-9]+$ && $samples -ge 2 ]] || {
  echo "SAMPLES must be an integer of at least 2" >&2
  exit 2
}

set +u
source /opt/ros/humble/setup.bash
source /home/ubuntu/third_party/aurora_ws/install/setup.bash
set -u
cd "$repo"

stop_isolated_driver() {
  if [[ -n $launch_pid ]] && kill -0 "$launch_pid" 2>/dev/null; then
    kill -TERM -- "-$launch_pid" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "$launch_pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL -- "-$launch_pid" 2>/dev/null || true
    wait "$launch_pid" 2>/dev/null || true
  fi
  launch_pid=
}

restore_service() {
  $restored && return
  set +e
  stop_isolated_driver
  sudo systemctl start aurora930.service
  for _ in {1..40}; do
    systemctl is-active --quiet aurora930.service && break
    sleep 0.25
  done
  sleep 2
  restored=true
}

on_exit() {
  status=$?
  trap - EXIT INT TERM
  restore_service
  .venv/bin/python dimos/robot/he/deployment/verify-he-sensors.py \
    --image-samples 5 --pointcloud-samples 2 --timeout 15 || status=$?
  bash dimos/robot/he/deployment/verify-he-readonly.sh || status=$?
  exit "$status"
}
trap on_exit EXIT INT TERM

bash dimos/robot/he/deployment/verify-he-readonly.sh
mkdir -p "$(dirname "$output")"
{
  printf 'captured_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'git_head=%s\n' "$(git rev-parse HEAD)"
  printf 'parameter=%s\n' "$parameter"
  printf 'test_value=%s\n' "$value"
  printf 'canonical_value='
  timeout 5 ros2 param get /aurora/aurora "$parameter" || true
} >"${output%.json}.experiment"

sudo systemctl stop aurora930.service
sleep 1
if pgrep -f '/aurora930_node|ros2 launch.*aurora930_launch.py' >/dev/null; then
  echo "Aurora process remained after stopping the canonical service" >&2
  exit 1
fi

log=${output%.json}.driver.log
setsid ros2 launch deptrum-ros-driver-aurora930 aurora930_launch.py \
  "$parameter:=$value" >"$log" 2>&1 &
launch_pid=$!

ready=false
for _ in {1..40}; do
  if timeout 2 ros2 node list 2>/dev/null | grep -qx '/aurora/aurora'; then
    ready=true
    break
  fi
  kill -0 "$launch_pid" 2>/dev/null || {
    echo "Isolated Aurora launch exited before becoming ready" >&2
    exit 1
  }
  sleep 0.5
done
$ready || {
  echo "Isolated Aurora node did not become ready" >&2
  exit 1
}

.venv/bin/python dimos/robot/he/deployment/diagnose-he-aurora.py \
  --samples "$samples" --timeout 25 --output "$output" >"${output%.json}.stdout"

stop_isolated_driver
restore_service
.venv/bin/python dimos/robot/he/deployment/verify-he-sensors.py \
  --image-samples 5 --pointcloud-samples 2 --timeout 15
bash dimos/robot/he/deployment/verify-he-readonly.sh

trap - EXIT INT TERM
printf 'Aurora A/B complete: %s=%s -> %s\n' "$parameter" "$value" "$output"
