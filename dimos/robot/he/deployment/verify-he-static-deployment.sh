#!/usr/bin/env bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
cd "$repo_root"

export VIRTUAL_ENV="$repo_root/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
export PYTHONNOUSERSITE=1

test -x .venv/bin/python
test -x .venv/bin/dimos

printf '%s\n' '=== preflight read-only gate ==='
bash dimos/robot/he/deployment/verify-he-readonly.sh

printf '%s\n' '=== deployment integrity ==='
bash dimos/robot/he/deployment/verify-he-deployment-integrity.sh

printf '%s\n' '=== HE blueprint discovery ==='
blueprints=$(.venv/bin/dimos list)
grep -qx 'he-sense-headless' <<<"$blueprints"
grep -qx 'he-teleop-headless' <<<"$blueprints"

printf '%s\n' '=== HEConnection standard-library tests ==='
.venv/bin/python -m unittest -v dimos.robot.he.test_connection

printf '%s\n' '=== isolated ROS control dry-run ==='
.venv/bin/python dimos/robot/he/deployment/verify-he-control-dry-run.py

printf '%s\n' '=== live sensor quality gate ==='
.venv/bin/python dimos/robot/he/deployment/verify-he-sensors.py --scan-samples 30 --timeout 12

printf '%s\n' '=== DDS test-endpoint cleanup ==='
has_test_endpoints() {
  local topics nodes
  topics=$(ros2 topic list)
  nodes=$(ros2 node list)
  [[ "$topics" =~ /he_safety_test/|/he_test/ ]] \
    || [[ "$nodes" =~ he_(safety_test|sensor_quality|rf2o) ]]
}

for _ in $(seq 1 20); do
  if ! has_test_endpoints; then
    break
  fi
  sleep 0.5
done
if has_test_endpoints; then
  echo 'isolated test endpoint did not leave the ROS graph within 10 seconds' >&2
  exit 1
fi

printf '%s\n' '=== final read-only gate ==='
bash dimos/robot/he/deployment/verify-he-readonly.sh

printf '%s\n' 'HE static deployment closeout: PASS'
printf '%s\n' 'Real motion: DISABLED'
printf '%s\n' 'Visual SLAM/navigation/exploration: DEFERRED'
