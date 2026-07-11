# Aurora930 Depth Coverage And Synchronization Support Request

Date prepared: 2026-07-12

## Request Summary

We are qualifying an Aurora930 RGB-D camera for visual SLAM on an NVIDIA Jetson
Orin NX 8GB. The camera publishes complete 640x400 RGB, IR and depth frames, but
depth validity is strongly non-uniform: vertical objects are reconstructed while
a smooth floor viewed at a shallow angle is mostly zero. We need the vendor to
clarify whether this is expected for the product, a firmware limitation, an
optical/mounting constraint, or a configuration defect.

We are not requesting an unsafe laser-current change or undocumented firmware
modification. The device serial is intentionally omitted from this package and
can be supplied through a private support channel.

## System

| Item | Value |
| --- | --- |
| Camera | Deptrum Aurora930, USB ID `3251:1930` |
| Device firmware | 2.0.8 |
| Stream SDK | Aurora900-series 1.1.22 |
| ROS 2 driver | `deptrum-ros-driver-aurora930` 0.2.11 |
| Driver source base | `c2bff34c634adf5c1998a00bb6914ca936b3b81b` |
| Host | Jetson Orin NX 8GB, Ubuntu 22.04, ROS 2 Humble, aarch64 |
| Current USB link | 480Mbps USB 2 hub; a direct USB 3 A/B is pending |
| Resolution | RGB/IR/depth 640x400; point cloud 256,000 points |

Canonical settings are alignment enabled, depth correction enabled, RGB-D mode
disabled, automatic laser mode, remove-filter threshold 110 and software depth
filter 150-4000mm. The ROS driver reads these settings only at device creation.

## Reproducible Observations

1. A 39-frame static baseline measured 24.26% globally valid depth. 69.88% of
   pixels were never valid, 18.97% were always valid and 11.15% were
   intermittent. A 90%-stable valid mask covered 20.84%, but its largest
   connected component covered only 5.27% of the image.
2. A later matched RGB/IR/depth snapshot measured 28.04% median global validity
   and 20.51% in the center 40%. Upper-half validity was 48.69%, lower-half
   validity 7.51%, and bottom-third validity 6.73%.
3. RGB and IR cover the full image. No bracket, vehicle body or software crop
   covers the lower region. Lower-half IR mean was 60.76 versus 53.24 in the
   upper half, so the failed area is not a missing IR frame.
4. Valid depth follows upright cabinets, doors and table legs. The stable zero
   region follows a smooth dark floor viewed from a low, nearly level camera.
5. In the canonical baseline, below-filter, above-filter and `65535` depth
   classes were all zero. Point-cloud usable/zero XYZ ratios matched depth and
   all XYZ values were finite.
6. Live valid-depth p50/p95 were about 1240/2522mm, while
   `GetSupportInfo().depth_range` returned printable bytes `0.3~1m`.
7. The same support query returned `synced_two_images=0`. Software timestamps
   often match exactly, but over 120 seconds RGB-nearest depth alignment P95 was
   69ms. We therefore do not claim hardware synchronization.
8. The current USB2 path has no kernel reset, stall, overflow or bandwidth
   errors. Raw point cloud still shows intermittent whole-frame gaps. A direct
   USB3 root-port comparison is pending and USB2 is not presented as proof of
   the stable spatial mask.

## Controlled Configuration Results

| Test | Result | Decision |
| --- | --- | --- |
| `threshold_size=30` vs 110 | global/center validity fell to 21.84/15.66% | retain 110 |
| laser indoor mode 2 vs auto 1 | only +0.17pp global, +0.05pp center | retain auto |
| alignment disabled | 25.65% global, lower defect remained | retain alignment |
| depth correction disabled | no meaningful isolated benefit; depth distribution shifted | retain correction |
| `rgbd_enable=true` | no pairing/coverage gain; point-cloud rate regressed | retain false |

No tested public ROS parameter resolves the spatial defect. Parameters declared
for other Deptrum products but unused by the Aurora930 configure path were not
treated as valid controls.

## Questions Requiring Vendor Answers

1. What are the certified minimum/maximum range, accuracy, precision, horizontal
   and vertical FOV, reflectivity requirement and incidence-angle limits for
   Aurora930 firmware 2.0.8?
2. What exactly does `SupportedInfo.depth_range = "0.3~1m"` mean? Is it an
   accuracy band, operating mode, product profile or another constraint?
3. What does a zero value in the 16-bit depth frame mean after filtering and
   depth correction? Are there separate invalid/saturated/confidence states?
4. Is the observed floor loss expected at shallow grazing angles or on dark,
   smooth materials? Is there an approved mounting pitch/height envelope or
   target reflectivity specification?
5. Does Aurora930 provide hardware-synchronized RGB/depth/IR timestamps? How
   should `synced_two_images=0` be interpreted, and which device clock should a
   ROS driver expose?
6. Is USB 3 required for simultaneous 640x400 RGB, depth, IR and 256,000-point
   output at the advertised rates? What minimum sustained bandwidth is required?
7. Is firmware 2.0.8 current for this hardware revision? Are there known depth
   mask, floor, synchronization or USB issues, and what is the supported update
   and rollback procedure?
8. What is the documented `Open`/`SetMode` sequence required for
   `GetDeviceInfo` and `GetCameraParameters`? Please provide the supported method
   to retrieve RGB/IR intrinsics and RGB-to-IR/depth extrinsics without changing
   persistent device state.
9. Is there a confidence/amplitude output or an SDK-supported diagnostic that
   distinguishes low reflectivity, multipath, saturation and out-of-range data?

## Requested Reproduction From Vendor

Please test the same firmware/SDK combination with a matte planar target at
measured distances of 0.3, 0.5, 1.0, 2.0 and 3.0m, including center and lower
image regions and multiple incidence angles. Report valid-pixel coverage,
depth error, confidence/amplitude if available, stream rates and synchronization
semantics. A comparison over direct USB3 would help separate transport effects.

## Attachment And Privacy Boundary

The generated support package contains only derived JSON metrics and text
audits. It excludes RGB/IR/depth images, point-cloud payloads, rosbags, device
serials, private indoor imagery, SDK stdout/stderr and credentials. Snapshot
SHA-256 hashes are retained so private source frames can be matched locally if a
secure vendor channel is established.

Build and verify the package from the repository root:

```bash
bash dimos/robot/he/deployment/build-he-aurora-vendor-package.sh \
  /tmp/he-aurora930-vendor-support.tar.gz
```

