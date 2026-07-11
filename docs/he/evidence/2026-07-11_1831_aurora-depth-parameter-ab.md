# Aurora930 Depth Parameter A/B

## Safety And Method

Date: 2026-07-11. The vehicle remained stationary. `HEConnection.enabled=False`,
`/he/nav_cmd_vel` had zero publishers, and no SLAM or navigation process ran.

Each isolated experiment used `run-he-aurora-depth-ab.sh`: pass the read-only
gate, stop the canonical camera service, launch one temporary Aurora930 parameter
override, collect at least 30 point-cloud samples, clean the process group,
restore systemd, wait for DDS expiry, then pass the live sensor and read-only
gates. No persistent launch or systemd value changed.

The canonical baseline and isolated runs were captured at different times and
the camera scene was not externally locked. Direct parameter attribution is
therefore limited to paired isolated controls. Publicly visible aggregate
differences are evidence of current variability, not a calibrated optical test.

## Results

| Case | Global valid | Center 40% | 90%-stable | Never valid | Largest stable component | Point cloud | Depth |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Canonical baseline | 24.26% | 18.57% | 20.84% | 69.88% | 5.27% | 12.50Hz | 14.29Hz |
| `threshold_size=30` | 21.84% | 15.66% | 18.89% | 72.37% | 6.07% | 8.40Hz | 14.93Hz |
| Isolated auto laser control (`1`) | 26.49% | 18.90% | 23.94% | 67.57% | 7.69% | 7.69Hz | 13.89Hz |
| Indoor laser (`2`) | 26.66% | 18.95% | 24.02% | 67.43% | 7.74% | 8.13Hz | 13.89Hz |
| Alignment disabled | 25.65% | 19.90% | 23.23% | 69.02% | 7.54% | 13.51Hz | 14.71Hz |
| Depth correction disabled | 26.46% | 18.86% | 23.79% | 67.53% | 7.66% | 8.06Hz | 14.60Hz |

All frames encoded invalid depth as zero. No run observed a non-zero value below
150mm, a value above 4000mm, or `65535`. Point-cloud zero XYZ matched the latest
depth zero ratio, while all XYZ values were finite.

## Decisions

- Keep `threshold_size=110`. Lowering it to 30 reduced global, center and stable
  coverage and did not recover the lower image.
- Keep `laser_power=1` (automatic). The paired indoor/automatic isolated runs
  differed by only 0.17 percentage points globally, 0.05 points in the center
  and 0.07 points in stable coverage. This is not a demonstrated improvement.
- Keep `align_mode=true`. Disabling alignment did not recover the lower image
  and would remove the required RGB-depth geometric relationship.
- Keep `depth_correction=true`. Disabling correction left coverage effectively
  unchanged and shifted p50/p95 depth from 1339/2887mm to 1392/3059mm without
  ground truth proving that shift is more accurate.
- Keep `rgbd_enable=false` based on the earlier paired test: no coverage or
  synchronization improvement and worse point-cloud timing.

No tested parameter resolves the spatial defect. The lower-third tiles remained
roughly 3-12% valid, and the largest 90%-stable connected region remained below
8% of the image. RGB-D navigation admission therefore remains failed.

## Operational Findings

- ROS 2 setup scripts are not nounset-safe; the runner scopes `set +u` only to
  environment loading.
- A stopped temporary publisher can remain in DDS discovery briefly. The runner
  waits five seconds after canonical service restoration and retains the strict
  one-publisher gate.
- SSH output can omit the runner's final lines after rclpy/DDS teardown. JSON,
  systemd state and independently repeated gates are the authoritative evidence.

Final state was explicitly verified: threshold 110, automatic laser, alignment
and depth correction enabled, RGB-D disabled, range 150-4000mm, resolution mode
2, both services active with zero restarts, live sensor gate PASS, read-only gate
PASS, and zero navigation publishers.

## Evidence Files

- `2026-07-11_1651_aurora-depth-baseline.json`
- `2026-07-11_1831_aurora-threshold-30.json`
- `2026-07-11_1831_aurora-laser-auto-control.json`
- `2026-07-11_1831_aurora-laser-indoor.json`
- `2026-07-11_1831_aurora-align-off.json`
- `2026-07-11_1831_aurora-depth-correction-off.json`
