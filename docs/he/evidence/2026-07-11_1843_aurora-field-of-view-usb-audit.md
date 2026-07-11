# Aurora930 Field-Of-View And USB Audit

## Safety And Privacy

Date: 2026-07-11. The vehicle remained stationary, navigation publishers stayed
at zero and the read-only gate passed before and after capture.

The RGB snapshot contains a private indoor scene and is intentionally not stored
in Git. Raw files remain only in `/tmp/he-aurora-field-of-view` on Orin and the
local temporary evidence directory. This report stores derived metrics and
SHA-256 hashes so the inspected files can be identified without publishing the
scene.

## Snapshot Evidence

The opt-in diagnostic captured nearest RGB, IR and depth frames with zero
reported timestamp offset. The latest frame was 28.10% valid; the 30-frame
median was 28.04%, center 40% was 20.51%, and the largest 90%-stable connected
region covered 8.58% of the image.

| Region | Valid depth | Mean IR | Mean RGB grayscale |
| --- | ---: | ---: | ---: |
| Upper half | 48.69% | 53.24 | 88.39 |
| Lower half | 7.51% | 60.76 | 65.34 |
| Top third | 49.38% | 53.26 | 94.21 |
| Middle third | 28.35% | 53.51 | 78.40 |
| Bottom third | 6.73% | 64.19 | 58.12 |

Visual inspection found:

- RGB and IR cover the full 640x400 field; there is no opaque vehicle body,
  bracket or image crop covering the lower half.
- The camera is mounted very low and nearly level with a smooth dark wood floor.
- Depth is continuous on vertical cabinets, doors, window structure, table legs
  and other upright objects.
- The large zero region follows the floor and open lower scene, where ToF light
  reaches the surface at a shallow grazing angle.
- Lower-image IR mean is higher, not lower, than the upper half. The failure is
  not explained by an entirely dark or missing IR image.

The evidence is most consistent with scene/material reflectivity, grazing-angle
geometry and low camera mounting. It contradicts a simple fixed software crop
or physical bracket occlusion. A controlled target-board and camera-pitch test
is still required before assigning a hardware defect.

Snapshot hashes:

| File | SHA-256 |
| --- | --- |
| `depth-mm.png` | `37cc6c8c11662152e916c06f17f1ccb678fcb431f5f01e6b16529f9a2613bd80` |
| `depth-visual.png` | `ae38e3e031b26b03d40f1fa5cbced4b26be937456d1ad28af3378e98fea80656` |
| `ir.png` | `d76e82f644ea21c0b578150909feab7c9497fd8a207bb2122f2161a4820ee9a1` |
| `rgb.png` | `7d3b03725eb4e2df723f7c8e9fdf7927e370568d02c36f405f8bf089f0e44` |
| `valid-mask.png` | `9dacc53a43bb6e204a0b8095d61feefb0883f8f9a45f6a8d647bf31532688e9d` |

## USB Topology

Aurora is USB device `3251:1930` at sysfs path `1-2.4`, negotiated at 480Mbps:

```text
USB 2 root (480M)
`-- port 2: Terminus 4-port hub (480M)
    |-- serial/controller devices (12M)
    |-- Aurora930 at port 4 (480M)
    `-- another 4-port hub with audio and serial devices

USB 3 root (10000M)
`-- no child device
```

The Aurora shares USB 2 bandwidth with several peripherals. This can contribute
to point-cloud rate variation and is not an acceptable final embedded topology
without qualification. However:

- kernel logs show no USB reset, stall, overflow or bandwidth error;
- Aurora runtime power status is active;
- RGB, IR and depth frames are complete 640x400 images;
- the zero-depth pattern follows scene geometry and remains stable over time.

USB 2 therefore remains a throughput risk but is not sufficient evidence for
the fixed spatial mask. Moving Aurora to the available 10Gbps root port requires
physical cable access and should be tested as a paired topology experiment, not
performed silently during remote static work.

## Next Qualification

1. Place a matte, high-reflectivity planar target at measured distances and
   pitches across upper, center and lower image regions.
2. Temporarily pitch the camera downward/upward or raise it, without moving the
   vehicle, and repeat the same target test.
3. With physical approval, connect Aurora directly to the USB 3 root and repeat
   the exact diagnostic while holding scene and mounting fixed.
4. If floor/target coverage remains abnormal, provide firmware 2.0.8, SDK
   1.1.22, driver 0.2.11, raw depth hashes and spatial metrics to Deptrum.

Until those tests pass, do not use Aurora depth as the sole navigation obstacle
or floor representation. RGB-D SLAM may remain shadow-only and must report the
coverage defect through localization/map health.
