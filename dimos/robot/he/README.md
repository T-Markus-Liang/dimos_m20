# HE Ackermann Platform

This package contains the DimOS adapters and deployment artifacts for the HE
Jetson Orin NX Ackermann platform.

## Safety State

- `HEConnection` is disabled by default.
- The persistent navigation topic has zero publishers until a later navigation
  phase explicitly passes its safety gates.
- Manual commands have priority over navigation through `twist_mux`.
- The final ROS controller applies 0.10m/s linear and 0.30rad/s angular limits,
  rejects non-finite commands, and stops/centers after a 100ms command timeout.
- No HE module publishes motor or steering PWM topics directly.

## Blueprints

- `he-sense-headless`: ROS sensor bridge plus bounded headless Rerun output.
- `he-teleop-headless`: sensor and movement wiring with real motion disabled.
- `he-nav-headless`: intentionally absent until trusted localization and the
  vehicle-down navigation gates pass.

## Verification

Run the static closeout from the Orin repository root:

```bash
bash dimos/robot/he/deployment/verify-he-static-deployment.sh
```

The lifted real-command scripts require an explicit `--confirm-lifted` flag and
must not be run with the vehicle on the ground or without a physical stop path.

See [Chassis characterization](docs/chassis-characterization-2026-07-11.md) for
the measured command-chain limits, latency, precision, and feedback gaps.

