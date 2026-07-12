#!/usr/bin/env bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
set -euo pipefail
trap 'printf "HE shadow read-only gate failed at line %s: %s\n" "$LINENO" "$BASH_COMMAND" >&2' ERR

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)

required_services=(
  odom-publisher.service
  joystick-control.service
  he-twist-mux.service
  he-camera-tf.service
  he-pointcloud-throttle.service
  aurora930.service
)
test "$(systemctl is-active he-storage-health.service)" = active
test "$(systemctl is-enabled he-storage-health.service || true)" = static
test "$(systemctl show he-storage-health.service -p Result --value)" = success

for service in "${required_services[@]}"; do
  test "$(systemctl is-active "$service")" = active
  test "$(systemctl is-enabled "$service")" = enabled
  test "$(systemctl show "$service" -p NRestarts --value)" = 0
done

test "$(systemctl is-active he-dimos-shadow.service)" = active
test "$(systemctl is-enabled he-dimos-shadow.service || true)" = static
test "$(systemctl show he-dimos-shadow.service -p NRestarts --value)" = 0
test "$(systemctl is-active he-dimos-sense.service || true)" = inactive
test "$(systemctl is-enabled he-dimos-sense.service)" = enabled
test "$(systemctl is-active he-ld19.service || true)" != active
test "$(systemctl is-active ros-robot-controller.service || true)" = inactive

test "$(fuser /dev/rrc 2>/dev/null | wc -w)" -eq 1

nav_info=$(ros2 topic info /he/nav_cmd_vel -v)
grep -q '^Publisher count: 0$' <<<"$nav_info"
grep -q '^Subscription count: 1$' <<<"$nav_info"
grep -q '^Node name: twist_mux$' <<<"$nav_info"

final_info=$(ros2 topic info /he/final_cmd_vel -v)
grep -q '^Publisher count: 1$' <<<"$final_info"
grep -q '^Subscription count: 1$' <<<"$final_info"
grep -q '^Node name: twist_mux$' <<<"$final_info"
grep -q '^Node name: odom_publisher$' <<<"$final_info"

aurora_topics=(
  /aurora/rgb/image_raw
  /aurora/depth/image_raw
  /aurora/ir/image_raw
  /aurora/rgb/camera_info
  /aurora/ir/camera_info
)
for topic in "${aurora_topics[@]}"; do
  topic_info=$(ros2 topic info "$topic" -v)
  grep -q '^Publisher count: 1$' <<<"$topic_info"
  grep -q '^Node name: aurora$' <<<"$topic_info"
  grep -q '^Node name: dimos_he_sensors$' <<<"$topic_info"
done

raw_pointcloud_info=$(ros2 topic info /aurora/points2 -v)
grep -q '^Publisher count: 1$' <<<"$raw_pointcloud_info"
grep -q '^Subscription count: 1$' <<<"$raw_pointcloud_info"
grep -q '^Node name: aurora$' <<<"$raw_pointcloud_info"
grep -q '^Node name: he_pointcloud_throttle$' <<<"$raw_pointcloud_info"

sampled_pointcloud_info=$(ros2 topic info /he/aurora/points2_sampled -v)
grep -q '^Publisher count: 1$' <<<"$sampled_pointcloud_info"
grep -q '^Subscription count: 1$' <<<"$sampled_pointcloud_info"
grep -q '^Node name: he_pointcloud_throttle$' <<<"$sampled_pointcloud_info"
grep -q '^Node name: dimos_he_sensors$' <<<"$sampled_pointcloud_info"

if ros2 topic list | grep -qx /scan; then
  echo 'retired LD19 /scan topic is still present' >&2
  exit 1
fi
if ros2 topic list | grep -qE '^/cmd_vel$|^/he_safety_test/|^/he_test/'; then
  echo 'legacy or isolated test command topic is still present' >&2
  exit 1
fi
if pgrep -f '[h]e-nav-headless|[m]ovement_manager|[b]asic_path_follower' >/dev/null; then
  echo 'navigation or motion process is running' >&2
  exit 1
fi
pgrep -f '/rtabmap_odom/rgbd_odometry.*he-rtabmap-shadow.yaml' >/dev/null
pgrep -f '/rtabmap_slam/rtabmap.*he-rtabmap-shadow.yaml' >/dev/null

if pgrep -f '[d]imos-viewer|[r]viz2|[m]ujoco' >/dev/null; then
  echo 'GUI or simulation process is running' >&2
  exit 1
fi
ss -ltn | grep -qE '0\.0\.0\.0:9877\b'
if ss -ltn | grep -qE ':(7779|9878|9990)\b'; then
  echo 'unexpected HE web or MCP port is listening' >&2
  exit 1
fi

memory_current=$(systemctl show he-dimos-shadow.service -p MemoryCurrent --value)
test "$memory_current" -lt $((2560 * 1024 * 1024))
test "$(systemctl show he-dimos-shadow.service -p MemoryHigh --value)" = 2147483648
test "$(systemctl show he-dimos-shadow.service -p MemoryMax --value)" = 2684354560

timeout 10 ros2 topic echo /he/visual_odom --once >/dev/null
health_file=$(mktemp)
trap 'rm -f "$health_file"' EXIT
"$repo_root/.venv/bin/python" \
  "$repo_root/dimos/robot/he/deployment/benchmark-he-localization-health.py" \
  --duration 3 --output "$health_file" >/dev/null
"$repo_root/.venv/bin/python" - "$health_file" <<'PY'
import json
import sys

from dimos.robot.he.visual_slam import validate_shadow_health_report

with open(sys.argv[1], encoding="utf-8") as stream:
    report = json.load(stream)
try:
    validate_shadow_health_report(report)
except ValueError as exc:
    raise SystemExit(str(exc)) from None
PY

printf 'HE integrated shadow read-only gate: PASS\n'
printf 'Motion gate: CLOSED (/he/nav_cmd_vel publishers=0)\n'
printf 'Shadow cgroup memory: %.1f MiB\n' "$((memory_current / 1024 / 1024))"
free -h
