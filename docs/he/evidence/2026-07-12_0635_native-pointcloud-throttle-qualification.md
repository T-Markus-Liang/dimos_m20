# HE Native Point-cloud Throttle Qualification

Date: 2026-07-12

Commit under test: `eee19da2c926dabc3ef1807b45e4bf505eb7e461`

Safety state: vehicle motion disabled, `HEConnection.enabled=False`, and
`/he/nav_cmd_vel` had zero publishers throughout.

## Scope

Qualify the C++ serialized point-cloud pre-throttle used by HESensorBridge and
Rerun. Raw Aurora topics remain unchanged and RTAB-Map continues to consume
full-rate `/aurora/rgb/image_raw` and `/aurora/depth/image_raw` directly.

## Rate Selection

Adjacent 75-second tests used the same Sense runtime and `ros2 topic hz` typed
subscriber:

| Native limit | Effective rate | Minimum interval | Maximum interval |
| ---: | ---: | ---: | ---: |
| 1.0Hz | 0.863Hz | 1.004s | 3.057s |
| 1.2Hz | 0.993Hz | 0.835s | 2.652s |

The retained 1.2Hz service completed a separate 125-second run at 1.014Hz,
with 0.831s minimum and 2.648s maximum intervals over the final 123-sample
window. The HESensorBridge guard is 1.3Hz so it does not accidentally drop the
slightly jittered 1.2Hz upstream output. The intended Rerun rate remains about
1Hz.

## Raw Sensor Timing

A subsequent 120.015-second bounded diagnostic subscribed to the raw topics.
It retained timestamps only and peaked at 93.74MiB RSS.

| Stream | Span rate | Estimated missing | Median / P95 / max interval |
| --- | ---: | ---: | ---: |
| RGB | 14.524Hz | 1.30% | 67 / 82 / 153ms |
| Depth | 12.097Hz | 17.78% | 69 / 148 / 400ms |
| IR | 13.381Hz | 9.06% | 68 / 135 / 337ms |
| Raw point cloud | 13.240Hz | 10.02% | 68 / 136 / 220ms |
| IMU | 46.669Hz | 0.00% | 21.26 / 22.23 / 30.05ms |

Raw point-cloud continuity is materially better than the earlier extra Python
typed-consumer result of 11.672Hz and 20.7% estimated missing. Depth still has
large minute-to-minute gaps on the shared USB2 path, so visual-input admission
remains open. This optimization does not claim hardware synchronization.

Raw timing JSON:
`2026-07-12_0631_native-throttle-raw-timing.json`.

## Resources And Lifecycle

Across the 249-second sampled-plus-raw run:

- throttle cgroup memory was 20.8MiB before and 20.9MiB after;
- Sense cgroup memory was 929.8MiB before and 929.8MiB after;
- system available memory increased from 3.49GB to 3.50GB;
- swap stayed exactly 574,881,792 bytes;
- tegrastats RAM was 4178-4214MiB, GR3D peaked at 9%, and Tj peaked at 62.656C;
- both services retained `NRestarts=0`;
- the only throttle process was the systemd-owned 1.2Hz native binary.

The complete shadow stack then exposed one best-effort `/he/visual_odom`
publisher and two expected subscribers, produced odometry at about 8.6Hz, and
passed the independent shadow read-only gate at 1389MiB cgroup memory. Native
RTAB-Map arguments confirmed raw RGB/depth inputs. Returning to Sense removed
all RTAB-Map processes and passed the ordinary read-only gate.

The first mode-switch attempt encountered an intermittent CLI readiness timeout
for `/he/visual_odom` even though RTAB-Map was computing. Recovery succeeded,
but the switch script returned success and allowed the caller to continue. The
wrapper was corrected to preserve the original non-zero admission status after
restoring Sense. A controlled same-shadow A/B then isolated the readiness
failure: an `ubuntu` no-daemon echo returned 0 while root timed out after 12
seconds with status 124. Mode switching still runs as root, but readiness gates
now run as the `ubuntu` runtime user through `runuser`. No gate, QoS, or timeout
was weakened.

## Result

Accept native serialized pre-throttling at 1.2Hz for the sampled visualization
branch. Keep the 1.3Hz bridge guard, 128MiB Rerun window, raw RTAB-Map RGB-D
inputs, and all existing motion gates. This closes the Python-before-
deserialization optimization item, but not USB3, physical calibration, moving
ATE/RPE, loop closure, relocalization, map quality, or navigation admission.
