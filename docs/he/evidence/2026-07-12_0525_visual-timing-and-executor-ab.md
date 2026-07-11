# HE Visual Timing And Executor A/B

Date: 2026-07-12 04:57-05:24 CST

Platform: HE Jetson Orin NX 8GB, stationary and lifted

Safety: `HEConnection.enabled=False`, `/he/nav_cmd_vel` publishers remained
zero, LD19 remained retired, and no shadow/navigation process ran.

## Method

`diagnose-he-visual-timing.py` subscribes to Aurora RGB, depth, IR, point cloud
and chassis IMU while retaining only source and callback receipt timestamps.
It does not retain image or point-cloud payloads. Collection is capped at
200,000 samples per stream and 3600 seconds.

The first run held Sense active for 600 seconds. After adding full-window rate
and missing-ratio output, two adjacent 120-second cases compared the same scene:

- `concurrent`: normal HESensorBridge plus the timing diagnostic;
- `isolated`: Sense stopped, leaving the timing diagnostic as the only consumer
  chain for these topics.

A third 120-second `two-thread` case tested a candidate HESensorBridge with a
two-thread ROS executor and point cloud in a separate callback group. No topic,
output rate, point-cloud stride or Rerun setting changed.

## Boundedness

The 600-second diagnostic process ended at 102.9MiB RSS. Minute samples grew
from about 85.5MiB to 91.4MiB before final summarization, rather than scaling
with camera payload volume. Sense stayed about 853-858MiB, system available
memory stayed about 3.44-3.47GiB, swap free did not change, service restarts
stayed zero and every navigation-publisher sample was zero.

## Ten-Minute Baseline

| Stream | Samples | Effective samples/s | Estimated missing | Source interval P95 | Callback age P95 |
| --- | ---: | ---: | ---: | ---: | ---: |
| RGB | 8213 | 13.69 | 7.0% | 132ms | 30.5ms |
| Depth | 7373 | 12.29 | 16.5% | 144ms | 32.3ms |
| IR | 8225 | 13.71 | 6.8% | 133ms | 32.9ms |
| Point cloud | 5731 | 9.55 | 34.7% | 214.5ms | 47.6ms |
| IMU | 27947 | 46.58 | approximately 0% | 22.6ms | 8.5ms |

No stream had a source timestamp regression or duplicate. RGB-nearest exact/
within-1ms pairing was 84.4% for depth, 93.0% for IR and 65.5% for point cloud;
their alignment P95 was 67/60/80ms. IMU alignment median/P95 was 5.39/10.13ms.
This is stable software pairing evidence, not hardware synchronization.

## Subscriber-Load A/B

| Stream | Concurrent span rate | Concurrent missing | Isolated span rate | Isolated missing |
| --- | ---: | ---: | ---: | ---: |
| RGB | 13.85Hz | 5.9% | 14.01Hz | 4.8% |
| Depth | 13.13Hz | 10.8% | 14.47Hz | 1.6% |
| IR | 13.98Hz | 5.0% | 14.36Hz | 2.4% |
| Point cloud | 9.65Hz | 34.0% | 12.35Hz | 16.1% |
| IMU | 46.58Hz | 0% | 46.92Hz | 0% |

Removing HESensorBridge materially improved depth and point-cloud continuity.
Therefore the normal Python bridge/DDS subscription path contributes load.
The isolated point cloud still missed about 16%, so bridge load does not explain
the complete problem and the shared USB2/driver path remains unqualified.

## Two-Thread Candidate

The candidate failed retention:

| Stream | Single-thread concurrent missing | Two-thread missing |
| --- | ---: | ---: |
| RGB | 5.9% | 6.0% |
| Depth | 10.8% | 14.6% |
| IR | 5.0% | 5.8% |
| Point cloud | 34.0% | 37.1% |
| IMU | 0% | 0% |

Depth span rate fell from 13.13 to 12.57Hz and point cloud from 9.65 to 9.22Hz.
Point-cloud RGB-alignment P95 worsened from 79 to 124ms. Memory and safety gates
remained bounded, but the functional regression takes precedence. The candidate
is rejected and the single-thread executor is restored.

## Decision

- Keep the bounded timing diagnostic and full-window metrics.
- Do not claim RGB/depth/point-cloud hardware synchronization.
- Do not retain the Python two-thread callback candidate.
- Keep RTAB-Map shadow-only; current software timing admission is not passed.
- Next physical A/B is direct Aurora USB3-root connection with mounting and
  scene fixed.
- A future software optimization must reduce full-rate Python point-cloud DDS
  delivery before deserialization (for example driver/native pre-throttling),
  not merely add Python executor threads. It must preserve the required default
  HESensorBridge point-cloud surface and prove output/resource equivalence.

## Raw Evidence

- `2026-07-12_visual-timing-10min.json`:
  `8b9a2abf77fd4c45dcfe7ce991b79a4b3489bd0cafd7ed8d96fbe409e5b3aa70`
- `2026-07-12_visual-timing-concurrent.json`:
  `478bca89ec854e425052bd0a8809e92daa9892e169355b9cbfe076e978a268a7`
- `2026-07-12_visual-timing-isolated.json`:
  `505a576c775fc1b334cf0483a4267414452b6b381b78a62b13d998317031db9c`
- `2026-07-12_visual-timing-two-thread.json`:
  `b2099b0dee8987637ad98c421a45afe5a6172221746506f8337fc6348e54f482`

The revert was deployed to Orin at commit `2e5255924064bc566c3fe983e94b7e399f12f3d0`.
The running bridge uses `SingleThreadedExecutor`; Sense is active with zero
restarts and shadow is inactive. Deployment integrity, read-only and live sensor
gates passed. The post-revert sensor sample measured RGB/depth/IR at
15.63/13.16/15.38Hz, depth validity 25.8%, a 256000-point cloud, both camera
calibrations and 44 IMU/odom samples. `/he/nav_cmd_vel` remained at zero
publishers and `/odom_raw` remained explicitly untrusted.
