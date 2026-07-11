# Aurora900 SDK Guide Audit

## Source

- Document: `Aurora 900 SDK Developer guide`
- Version/date printed by vendor: V1.7, 2025-03-04
- Pages: 41
- SHA-256: `115a56c9612b3e528264c4cfcb903271254ed0841ae96c642de55160a3fbf0ad`
- Local vendor bundle: Deptrum stream SDK 1.1.22

The copyrighted PDF is not copied into the DimOS Git repository. Relevant pages
20, 26, 27 and 29 were text-extracted and visually rendered to verify the table
layout and API wording.

## Confirmed Semantics

- Page 20: `SwitchAlignedMode(true)` enables RGB-D/IR alignment after setting
  stream mode.
- Page 20: `SetRemoveFilterSize(110)` is a noise-removal threshold. The guide
  warns that a value too low can remove important detail and a value too high
  can retain noise. This is consistent with the HE `30` A/B losing coverage.
- Page 26: `SetLaserDriver()` values are 1 auto, 2 indoor and 3 outdoor. The
  guide describes exposure/gain adaptation, not a guaranteed depth-power or
  coverage increase.
- Page 26: `FilterOutRangeDepthMap(150, 4000)` removes values outside the chosen
  range. It is a configurable filter window, not a published hardware rating.
- Page 27: `DepthCorrection(true)` enables vendor depth-data calibration.
- Page 29: `SetFilterOutBorderDepth()` supports an edge trim setting from 0 to
  15; `SetDepthRange()` sets a measurement window.

## Missing Qualification Data

The API guide does not provide Aurora930-specific numeric specifications for:

- horizontal or vertical field of view;
- minimum/maximum rated range by reflectivity;
- accuracy, precision or repeatability versus distance;
- floor, grazing-angle or dark-material performance;
- ambient-light rejection;
- USB bandwidth requirement;
- required mounting height or pitch;
- expected valid-pixel coverage.

It therefore cannot prove that the observed floor mask is within specification,
nor can it support a navigation admission threshold.

## Unexposed Device Information

The SDK declares `GetSupportInfo(SupportedInfo&)`; its `depth_range` field can
contain device-reported range information. It also exposes edge trim, depth
range, temperature and laser-current APIs. The current Aurora ROS 2 driver does
not call these APIs or publish their results, and its common ROS parameter list
is not an equivalent substitute.

Do not add speculative ROS parameters. The next vendor-facing step is either:

1. ask Deptrum for Aurora930 optical/range/reflectivity specifications and a
   documented way to read `SupportedInfo.depth_range`; or
2. add a small, separately reviewed read-only SDK diagnostic only after checking
   ABI ownership, process exclusivity and license constraints.

No firmware rollback, laser-current change, undocumented edge trim or direct SDK
device access is approved from this audit.
