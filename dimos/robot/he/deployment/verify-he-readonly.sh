#!/usr/bin/env bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
set -euo pipefail

required_services=(
  odom-publisher.service
  joystick-control.service
  he-twist-mux.service
  he-ld19.service
  he-camera-tf.service
  he-dimos-sense.service
  aurora930.service
)

for service in "${required_services[@]}"; do
  test "$(systemctl is-active "$service")" = "active"
  test "$(systemctl is-enabled "$service")" = "enabled"
  test "$(systemctl show "$service" -p NRestarts --value)" = "0"
done

test "$(systemctl is-active ros-robot-controller.service || true)" = "inactive"
test "$(systemctl is-enabled ros-robot-controller.service || true)" = "disabled"

rrc_holders=$(fuser /dev/rrc 2>/dev/null | wc -w)
lidar_holders=$(fuser /dev/lidar 2>/dev/null | wc -w)
test "$rrc_holders" -eq 1
test "$lidar_holders" -eq 1

nav_cmd_vel_info=$(ros2 topic info /he/nav_cmd_vel -v)
final_cmd_vel_info=$(ros2 topic info /he/final_cmd_vel -v)
manual_cmd_vel_info=$(ros2 topic info /controller/cmd_vel -v)
pwm_info=$(ros2 topic info /ros_robot_controller/pwm_servo/set_state -v)
scan_info=$(ros2 topic info /scan -v)
camera_info=$(ros2 topic info /aurora/points2 -v)

grep -q '^Publisher count: 0$' <<<"$nav_cmd_vel_info"
grep -q '^Subscription count: 1$' <<<"$nav_cmd_vel_info"
grep -q '^Node name: twist_mux$' <<<"$nav_cmd_vel_info"
grep -q '^Publisher count: 1$' <<<"$final_cmd_vel_info"
grep -q '^Subscription count: 1$' <<<"$final_cmd_vel_info"
grep -q '^Node name: twist_mux$' <<<"$final_cmd_vel_info"
grep -q '^Node name: odom_publisher$' <<<"$final_cmd_vel_info"
grep -q '^Publisher count: 1$' <<<"$manual_cmd_vel_info"
grep -q '^Subscription count: 1$' <<<"$manual_cmd_vel_info"
grep -q '^Node name: joystick_control$' <<<"$manual_cmd_vel_info"
grep -q '^Node name: twist_mux$' <<<"$manual_cmd_vel_info"
grep -q '^Publisher count: 1$' <<<"$pwm_info"
grep -q '^Subscription count: 1$' <<<"$pwm_info"
grep -q '^Node name: odom_publisher$' <<<"$pwm_info"
grep -q '^Node name: ros_robot_controller$' <<<"$pwm_info"
grep -q '^Publisher count: 1$' <<<"$scan_info"
grep -q '^Subscription count: 0$' <<<"$camera_info"

if ros2 topic list | grep -qE '^/cmd_vel$|^/he_safety_test/|^/he_test/'; then
  echo "legacy or isolated test command topic is still present" >&2
  exit 1
fi

if pgrep -f '[r]f2o_laser_odometry_node|[h]e_rf2o|[s]lam_toolbox|[r]tabmap|[h]e-nav-headless' >/dev/null; then
  echo "localization or navigation process is still running" >&2
  exit 1
fi

if pgrep -f '[d]imos-viewer|[r]viz2|[m]ujoco' >/dev/null; then
  echo "GUI or simulation process is still running" >&2
  exit 1
fi

ss -ltn | grep -qE '0\.0\.0\.0:9877\b'
if ss -ltn | grep -qE ':(7779|9878|9990)\b'; then
  echo "unexpected HE web or MCP port is listening" >&2
  exit 1
fi

memory_bytes=$(systemctl show he-dimos-sense.service -p MemoryCurrent --value)
memory_limit_bytes=$((1200 * 1024 * 1024))
test "$memory_bytes" -lt "$memory_limit_bytes"
test "$(systemctl show he-dimos-sense.service -p MemoryHigh --value)" = "1073741824"
test "$(systemctl show he-dimos-sense.service -p MemoryMax --value)" = "1342177280"

timeout 5 ros2 topic echo /scan --once >/dev/null
timeout 5 ros2 topic echo /ros_robot_controller/imu_raw --once >/dev/null
timeout 5 ros2 topic echo /odom_raw --once >/dev/null

printf 'HE read-only sensor gate: PASS\n'
printf 'Motion gate: CLOSED (/he/nav_cmd_vel publishers=0, HEConnection remains disabled)\n'
printf 'Command graph: joystick -> twist_mux -> odom_publisher (single owner)\n'
printf 'Localization/navigation: DEFERRED (no active process or test topic)\n'
printf 'he-dimos-sense memory: %.1f MiB\n' "$((memory_bytes / 1024 / 1024))"
df -h /
free -h
