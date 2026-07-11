#!/usr/bin/env bash
set -euo pipefail

duration=10
label=static
output_root=/home/ubuntu/he/data/visual-navigation
dry_run=false

while (($#)); do
  case "$1" in
    --duration) duration="$2"; shift 2 ;;
    --label) label="$2"; shift 2 ;;
    --output-root) output_root="$2"; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; exit 2 ;;
  esac
done

[[ "$duration" =~ ^[1-9][0-9]*$ ]] || { echo '--duration must be a positive integer'; exit 2; }
[[ "$label" =~ ^[a-zA-Z0-9._-]+$ ]] || { echo '--label contains unsupported characters'; exit 2; }

topics=(
  /aurora/rgb/image_raw
  /aurora/depth/image_raw
  /aurora/ir/image_raw
  /aurora/points2
  /aurora/rgb/camera_info
  /aurora/ir/camera_info
  /ros_robot_controller/imu_raw
  /odom_raw
  /tf
  /tf_static
  /diagnostics
  /controller/cmd_vel
  /he/nav_cmd_vel
  /he/final_cmd_vel
)

timestamp=$(date +%Y%m%d_%H%M%S)
output="$output_root/${timestamp}_${label}"
printf 'Output: %s\nDuration: %ss\nTopics:\n' "$output" "$duration"
printf '  %s\n' "${topics[@]}"
$dry_run && exit 0

mkdir -p "$output_root"
available_kib=$(df -Pk "$output_root" 2>/dev/null | awk 'NR==2 {print $4}')
if [[ -n "${available_kib:-}" && "$available_kib" -lt 8388608 ]]; then
  echo 'Refusing to record with less than 8GiB free' >&2
  exit 1
fi

ros2 bag record --storage sqlite3 -o "$output" "${topics[@]}" &
recorder_pid=$!
cleanup() {
  if kill -0 "$recorder_pid" 2>/dev/null; then
    kill -INT "$recorder_pid"
    wait "$recorder_pid" || true
  fi
}
trap cleanup EXIT INT TERM
sleep "$duration"
cleanup
trap - EXIT INT TERM

{
  printf 'captured_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'duration_seconds=%s\n' "$duration"
  printf 'label=%s\n' "$label"
  printf 'git_commit=%s\n' "$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  printf 'vehicle_motion=disabled\n'
  printf 'topics=%s\n' "${topics[*]}"
} >"$output/he-manifest.txt"

find "$output" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum >"$output/SHA256SUMS"
printf 'Recording complete: %s\n' "$output"
