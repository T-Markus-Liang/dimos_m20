#!/usr/bin/env bash
set -eo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
config="$repo_root/dimos/robot/he/deployment/he-rtabmap-shadow.yaml"
watchdog_binary="$repo_root/dimos/robot/he/deployment/he-rtabmap-db-watchdog.sh"
database_dir=/var/tmp/he-rtabmap
mode=${HE_RTABMAP_MODE:-mapping}
database=${HE_RTABMAP_DB:-}

validate_mode() {
  case "$mode" in
    mapping)
      if [[ -n "$database" && -e "$database" ]]; then
        echo "Refusing incremental mapping with an existing HE_RTABMAP_DB" >&2
        return 2
      fi
      ;;
    localization)
      if [[ -z "$database" ]]; then
        echo "HE_RTABMAP_DB is required in localization mode" >&2
        return 2
      fi
      if [[ ! -f "$database" || ! -s "$database" || ! -r "$database" ]]; then
        echo "Localization database must be an existing, non-empty readable file" >&2
        return 2
      fi
      ;;
    *)
      echo "HE_RTABMAP_MODE must be mapping or localization" >&2
      return 2
      ;;
  esac
}

validate_mode

if [[ "$mode" == localization ]]; then
  rtabmap_mode_args=(
    -p 'Mem/IncrementalMemory:=false'
    -p 'Mem/InitWMWithAllNodes:=true'
    -p 'Mem/LocalizationReadOnly:=true'
    -p 'Mem/LocalizationDataSaved:=false'
  )
else
  rtabmap_mode_args=(
    -p 'Mem/IncrementalMemory:=true'
    -p 'Mem/InitWMWithAllNodes:=false'
    -p 'Mem/LocalizationReadOnly:=false'
    -p 'Mem/LocalizationDataSaved:=false'
  )
fi

if [[ "${1:-}" == --check-mode ]]; then
  echo "HE RTAB-Map mode: $mode"
  echo "HE RTAB-Map database: ${database:-<auto-new>}"
  echo "HE RTAB-Map parameter overrides: ${rtabmap_mode_args[*]}"
  exit 0
fi

source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
source /home/ubuntu/third_party/aurora_ws/install/setup.bash

odom_binary=/opt/ros/humble/lib/rtabmap_odom/rgbd_odometry
slam_binary=/opt/ros/humble/lib/rtabmap_slam/rtabmap
[[ -x "$odom_binary" && -x "$slam_binary" ]] || {
  echo "RTAB-Map 0.23.7 odometry/SLAM packages are required" >&2
  exit 1
}
[[ -x "$watchdog_binary" ]] || {
  echo "HE RTAB-Map database watchdog is required" >&2
  exit 1
}

"$watchdog_binary" --check

nav_info=$(ros2 topic info /he/nav_cmd_vel -v 2>/dev/null || true)
nav_publishers=$(awk '/Publisher count:/ {print $3; exit}' <<<"$nav_info")
if [[ -n "${nav_publishers:-}" && "$nav_publishers" != 0 ]]; then
  echo "Refusing shadow SLAM while /he/nav_cmd_vel has publishers" >&2
  exit 1
fi

if [[ "${1:-}" == --check ]]; then
  echo "HE RTAB-Map shadow configuration: PASS"
  echo "Mode: $mode"
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

if [[ -z "$database" ]]; then
  database="$database_dir/rtabmap-$(date +%Y%m%d-%H%M%S).db"
  mapfile -t expired_databases < <(
    find "$database_dir" -maxdepth 1 -type f -name 'rtabmap-*.db' \
      -printf '%T@ %p\n' | sort -nr | tail -n +5 | cut -d' ' -f2-
  )
  if ((${#expired_databases[@]})); then
    rm -f -- "${expired_databases[@]}"
  fi
fi
validate_mode
if [[ "$mode" == mapping ]]; then
  mkdir -p "$(dirname "$database")"
fi
ulimit -c 0
echo "HE RTAB-Map mode: $mode"
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
  "${rtabmap_mode_args[@]}" \
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

"$watchdog_binary" "$database" &
watchdog_pid=$!

cleanup() {
  trap - EXIT INT TERM
  kill -INT "$watchdog_pid" "$slam_pid" "$odom_pid" 2>/dev/null || true
  sleep 1.5
  kill -TERM "$watchdog_pid" "$slam_pid" "$odom_pid" 2>/dev/null || true
  sleep 0.5
  kill -KILL "$watchdog_pid" "$slam_pid" "$odom_pid" 2>/dev/null || true
  wait "$watchdog_pid" "$slam_pid" "$odom_pid" 2>/dev/null || true
}

shutdown() {
  cleanup
  exit 0
}

trap cleanup EXIT
trap shutdown INT TERM

set +e
wait -n "$odom_pid" "$slam_pid" "$watchdog_pid"
child_status=$?
set -e
if ((child_status == 42)); then
  echo "HE RTAB-Map shadow stopped by the database size watchdog" >&2
elif ((child_status == 0)); then
  echo "HE RTAB-Map shadow child exited unexpectedly" >&2
  child_status=1
fi
exit "$child_status"
