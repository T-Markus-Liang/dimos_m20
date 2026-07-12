#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
deployment="$repo_root/dimos/robot/he/deployment"
ros_root=/home/ubuntu/ros2_ws

compare() {
  local expected=$1 actual=$2
  if ! cmp -s "$expected" "$actual"; then
    echo "deployment drift: $actual differs from $expected" >&2
    exit 1
  fi
}

compare "$deployment/he-dimos-sense.service" /etc/systemd/system/he-dimos-sense.service
compare "$deployment/he-dimos-shadow.service" /etc/systemd/system/he-dimos-shadow.service
compare "$deployment/he-storage-health.service" /etc/systemd/system/he-storage-health.service
compare \
  "$deployment/aurora930-storage-health.conf" \
  /etc/systemd/system/aurora930.service.d/he-storage-health.conf
compare \
  "$deployment/he-pointcloud-throttle.service" \
  /etc/systemd/system/he-pointcloud-throttle.service
compare "$deployment/he-camera-tf.service" /etc/systemd/system/he-camera-tf.service
compare "$deployment/he-twist-mux.service" /etc/systemd/system/he-twist-mux.service
compare \
  "$deployment/odom-publisher-he.conf" \
  /etc/systemd/system/odom-publisher.service.d/he-command-mux.conf
test ! -e /etc/systemd/system/he-ld19.service
test "$(systemctl is-enabled he-dimos-shadow.service || true)" = static
test "$(systemctl is-enabled he-storage-health.service || true)" = static
test "$(systemctl is-enabled he-pointcloud-throttle.service)" = enabled
dpkg-query -W -f='${Status}\n' ros-humble-topic-tools | grep -qx 'install ok installed'

(
  cd "$ros_root/src/driver/controller"
  git apply --reverse --check "$deployment/he-controller-command-safety.patch"
  git apply --reverse --check "$deployment/he-controller-stop-center.patch"
)
(
  cd "$ros_root/src/peripherals"
  git apply --reverse --check "$deployment/he-joystick-mux.patch"
)

compare \
  "$ros_root/src/driver/controller/controller/ackermann.py" \
  "$ros_root/build/controller/controller/ackermann.py"
compare \
  "$ros_root/src/driver/controller/controller/odom_publisher_node.py" \
  "$ros_root/build/controller/controller/odom_publisher_node.py"
compare \
  "$ros_root/src/peripherals/peripherals/joystick_control.py" \
  "$ros_root/build/peripherals/peripherals/joystick_control.py"

launch_link="$ros_root/install/controller/share/controller/launch/odom_publisher.launch.py"
test "$(readlink -f "$launch_link")" = \
  "$ros_root/src/driver/controller/launch/odom_publisher.launch.py"

printf '%s\n' 'HE deployment integrity: PASS'
printf '%s\n' 'Live systemd files match repository artifacts'
printf '%s\n' 'LD19 service is retired and absent'
printf '%s\n' 'ROS safety patches are applied and build copies match source'
