#!/usr/bin/env bash
set -eo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
config="$repo_root/dimos/robot/he/deployment/he-rtabmap-shadow.yaml"
database_dir=/var/tmp/he-rtabmap

source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
source /home/ubuntu/third_party/aurora_ws/install/setup.bash

odom_binary=/opt/ros/humble/lib/rtabmap_odom/rgbd_odometry
slam_binary=/opt/ros/humble/lib/rtabmap_slam/rtabmap
[[ -x "$odom_binary" && -x "$slam_binary" ]] || {
  echo "RTAB-Map 0.23.7 odometry/SLAM packages are required" >&2
  exit 1
}

nav_info=$(ros2 topic info /he/nav_cmd_vel -v 2>/dev/null || true)
nav_publishers=$(awk '/Publisher count:/ {print $3; exit}' <<<"$nav_info")
if [[ -n "${nav_publishers:-}" && "$nav_publishers" != 0 ]]; then
  echo "Refusing shadow SLAM while /he/nav_cmd_vel has publishers" >&2
  exit 1
fi

if [[ "${1:-}" == --check ]]; then
  echo "HE RTAB-Map shadow configuration: PASS"
  echo "Motion output: disabled"
  exit 0
fi

mkdir -p "$database_dir"
exec 9>"$database_dir/shadow.lock"
flock -n 9 || {
  echo "Refusing to start a second HE RTAB-Map shadow instance" >&2
  exit 1
}

if pgrep -f "$odom_binary.*he-rtabmap-shadow.yaml|$slam_binary.*he-rtabmap-shadow.yaml" \
  >/dev/null; then
  echo "Refusing to start while an HE RTAB-Map process already exists" >&2
  exit 1
fi

if [[ -n "${HE_RTABMAP_DB:-}" ]]; then
  database=$HE_RTABMAP_DB
else
  database="$database_dir/rtabmap-$(date +%Y%m%d-%H%M%S).db"
  mapfile -t expired_databases < <(
    find "$database_dir" -maxdepth 1 -type f -name 'rtabmap-*.db' \
      -printf '%T@ %p\n' | sort -nr | tail -n +5 | cut -d' ' -f2-
  )
  if ((${#expired_databases[@]})); then
    rm -f -- "${expired_databases[@]}"
  fi
fi
mkdir -p "$(dirname "$database")"
ulimit -c 0
echo "HE RTAB-Map database: $database"

"$odom_binary" --ros-args \
  --params-file "$config" \
  -r rgb/image:=/aurora/rgb/image_raw \
  -r depth/image:=/aurora/depth/image_raw \
  -r rgb/camera_info:=/aurora/rgb/camera_info \
  -r odom:=/he/visual_odom \
  -r odom_info:=/he/visual_odom_info &
odom_pid=$!

"$slam_binary" --ros-args \
  --params-file "$config" \
  -p database_path:="$database" \
  -r rgb/image:=/aurora/rgb/image_raw \
  -r depth/image:=/aurora/depth/image_raw \
  -r rgb/camera_info:=/aurora/rgb/camera_info \
  -r odom:=/he/visual_odom \
  -r odom_info:=/he/visual_odom_info \
  -r map:=/he/visual_occupancy \
  -r mapPath:=/he/visual_path \
  -r mapData:=/he/visual_map_data \
  -r info:=/he/visual_slam_info \
  -r cloud_map:=/he/visual_cloud_map &
slam_pid=$!

stop_process() {
  local pid=$1
  for _ in $(seq 1 10); do
    kill -0 "$pid" 2>/dev/null || return
    sleep 0.2
  done
  kill -TERM "$pid" 2>/dev/null || true
  sleep 0.5
  kill -KILL "$pid" 2>/dev/null || true
}

cleanup() {
  trap - EXIT INT TERM
  kill -INT "$slam_pid" "$odom_pid" 2>/dev/null || true
  stop_process "$slam_pid"
  stop_process "$odom_pid"
}
trap cleanup EXIT INT TERM

wait -n "$odom_pid" "$slam_pid" || true
exit 1
