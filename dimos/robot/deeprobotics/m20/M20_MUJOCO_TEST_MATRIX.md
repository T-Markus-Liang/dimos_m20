# M20 MuJoCo Test Matrix And Roadmap

This document records the verification completed while importing the official
DeepRobotics M20 into DimOS and MuJoCo. It distinguishes passing integration
checks from behavior that remains unsuitable for navigation acceptance.

## Scope

- DimOS branch: `codex/m20-official-mujoco-model`
- Official source: `DeepRoboticsLab/sdk_deploy` commit
  `80e3d40084c4ed151ba6f88b0d55cf1d480aa45e`
- Official policy SHA-256:
  `0ac99f3093d4a984d7587b88d57300cbf7ec2f788401dfa1570d1e4800568f6b`

## Completed Tests

| Area | Test | Result | Evidence / limitation |
| --- | --- | --- | --- |
| Source identity | Official repository, commit, BSD-3-Clause license, 17 meshes, MJCF, and ONNX audited | Pass | Asset attribution is in `assets/SOURCE.md`; public source calls the robot M20, not M20 Pro |
| Policy identity | Vendored ONNX hash and interface | Pass | Byte-identical to upstream; `obs [1,57] -> actions [1,16]` |
| MJCF contract | Dimensions, 16 actuators, names, joint order, home keyframe, four DimOS cameras | Pass | `nq=23`, `nv=22`, `nu=16`; covered by `test_m20_policy.py` |
| Physical asset preservation | CRLF-normalized diff against official `M20.xml` | Pass | Kinematics, inertia, ranges, torque limits, collision shapes, and friction retained; only scene composition/sensor additions changed |
| Controller contract | Joint permutation, observation/action scales, PD gains, leg-position and wheel-velocity mode | Pass | Matched against official `M20PolicyRunner`; 1 ms physics and 20 ms policy cadence |
| Basic stability | Zero command for 2-5 s | Pass | Upright and finite; base height settles near 0.562-0.564 m |
| Forward motion | `[0.2, 0, 0]` for 3 s | Pass | `+0.4884 m` forward, `-0.0018 m` lateral drift, upright |
| RGB render | Head and third-person EGL render | Pass | Nonblank third-person M20 render; RGB stream works in full blueprint |
| Synthetic depth | Robot-only depth and visible groups `(0, 1)` | Pass | Robot collision/visual groups excluded, preventing self-scan map obstacles |
| Sensor streams | Full M20 simple-nav startup | Pass | RGB about 9.5 Hz for 10 Hz config; point cloud about 2 Hz for 2 Hz config |
| Blueprint composition | `m20-simple-nav-sim` and `m20-dan-nav-sim` bounded starts | Pass | Both resolve `robot_model=deeprobotics_m20`, start MuJoCo and native dependencies, then shut down cleanly |
| Navigation wiring | Simple-nav and DAN blueprint tests | Pass | Robot model, remappings, sensor profile, and planning envelope covered by focused tests |
| Moving obstacle | Person motion, visibility, proximity reaction, static disable path | Pass | Focused moving-obstacle suite: 15 tests plus explicit MuJoCo check |
| Focused regression suite | M20 policy/process/blueprint tests | Pass | 36 focused tests passed during integration; subsequent `test_m20_policy.py`: 2 passed |
| Packaging | Wheel build and M20 package data | Pass | Wheel contains 21 M20 asset entries; ONNX deliberately remains normal Git data |
| Tooling | Ruff, pre-commit, LFS, large-file, YAML/TOML, doclinks | Pass | Passed for integration and documentation commits |

## Exposed Behavior Issues

| Behavior | Observed VM result | Status | Impact |
| --- | --- | --- | --- |
| Low lateral command | `[0, 0.2, 0]` for 3 s: `+0.0270 m` lateral and `-0.1375 m` forward | Open | Lateral velocity tracking has a low-response/dead-zone region |
| Maximum lateral command | `[0, 0.5, 0]` for 3 s: `+1.5548 m` lateral and `-0.2337 m` forward | Open | Lateral motion is possible but materially coupled to backward motion |
| Positive yaw | `[0, 0, +0.7]` for 3 s: `+0.2200 rad` | Open | Weak positive yaw response |
| Negative yaw | `[0, 0, -0.7]` for 3 s: `-0.7311 rad` | Open | Strongly asymmetric relative to positive yaw |
| Policy wheel targets | Signed yaw commands produce non-mirrored wheel targets | Root cause localized | Official ONNX gait response, not a dropped DimOS command or wheel-index error |
| Manual inverse wheels | Opposite wheel targets produce near-mirrored yaw (`-0.1394`, `+0.1458 rad`) | Diagnostic pass | Excludes gross static MuJoCo wheel-order/sign/contact asymmetry; manual controller is not a stance controller |
| Physical robot file | VM cannot reach documented `10.21.31.103` | Unverified | Published policy matches; the exact currently installed robot file still needs a read-only SHA-256 check |

## Acceptance Status

Forward motion, model loading, sensors, mapping inputs, navigation wiring, and
process lifecycle are validated. Lateral and yaw tracking are **not validated**
and must not be used for autonomous-navigation performance, safety clearance,
or Sim-to-Real acceptance.

## Optimization Roadmap

1. Reproduce the signed command matrix in the official upstream M20 runner
   with the same policy, initial pose, terrain, and timing. Store trajectories
   and wheel targets as the baseline.
2. On an authorized physical M20, record the same commands with joint state,
   IMU, odometry, video, and the policy SHA-256. This confirms deployed-policy
   identity and establishes the real command convention.
3. If upstream reproduces the issue, request a corrected policy or retrain with
   balanced signed-yaw/lateral tracking objectives and left/right symmetry
   augmentation. Preserve the existing 57-input/16-output contract.
4. If upstream does not reproduce it, compare scene friction, wheel contact,
   initial stance, and timing before changing DimOS. Do not flip joint signs or
   tune gains without this evidence.
5. Until a policy-level repair is accepted, constrain M20 simulation evaluation
   to forward-dominant trajectories and mark lateral/yaw metrics as diagnostic.
