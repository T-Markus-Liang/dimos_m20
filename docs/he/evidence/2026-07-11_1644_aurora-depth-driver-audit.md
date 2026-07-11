# Aurora930 Depth Driver Audit

## Scope

This is a source and live-parameter audit of the HE Aurora930 depth path. The
vehicle remained stationary, no SLAM process ran, and no command publisher was
enabled.

## Version And Runtime

- ROS driver release: `deptrum-ros-driver-aurora930` 0.2.11
- Driver source commit: `c2bff34c634adf5c1998a00bb6914ca936b3b81b`
- Bundled Deptrum stream SDK: 1.1.22
- Live node: `/aurora/aurora`
- Live settings: alignment and depth correction enabled, RGB-D mode disabled,
  range 150-4000mm, remove-filter threshold 110, resolution mode 2 and laser
  mode 1 (automatic).

The vendor source checkout on Orin is not a clean Git worktree, so the commit
identifies its base rather than proving every local byte matches upstream. The
installed launch and device code were inspected directly.

## Parameters That Affect Aurora930

`Aurora900Ros2Device::ConfigureDevice()` applies these settings to Aurora930:

| ROS parameter | SDK call | Meaning available from vendor source |
| --- | --- | --- |
| `threshold_size` | `SetRemoveFilterSize()` | Noise-removal threshold, accepted range 30-400 |
| `depth_correction` | `DepthCorrection()` | Enable device depth correction |
| `align_mode` | `SwitchAlignedMode()` | Align RGB-D and IR streams |
| `minimum_filter_depth_value`, `maximum_filter_depth_value` | `FilterOutRangeDepthMap()` | Filter depth outside the configured millimetre range |
| `laser_power` | `SetLaserDriver()` | 1 automatic, 2 indoor, 3 outdoor |
| `resolution_mode_index` | stream configuration | Select the advertised stream resolution mode |
| `rgbd_enable` | stream selection | Obtain RGB, depth, IR and point cloud from the combined RGB-D frame |

These values are read during node/device construction. A successful
`ros2 param set` does not prove the SDK was reconfigured because the driver has
no dynamic parameter callback. Controlled A/B tests must restart an isolated
driver instance and then restore the systemd service.

## Parameters That Do Not Affect Aurora930

The common `RosDevice` class declares parameters for several Deptrum products.
The Aurora930 device path does not call the corresponding SDK functions for:

- `slam_mode`
- `mtof_crop_up`, `mtof_crop_down`
- `mtof_filter_level`, `stof_filter_level`, `stof_minimum_range`
- `filter_type`
- `depth_frequency_fusion_threshold`
- `ratio_scatter_filter_threshold`
- `outlier_point_removal_flag`

The crop and mToF/sToF mode calls are in the Nebula implementation. The
frequency/scatter/filter-type calls are in the Stellar implementation. Their
presence in `ros2 param list` is not evidence that they change Aurora930 data.

## Invalid Depth Encoding Boundary

The driver publishes the SDK depth payload as `16UC1`. The open headers describe
range filtering but do not define the output sentinel used by the closed SDK.
Therefore the exact firmware meaning of every zero cannot be claimed from
source alone. The HE diagnostic now separates zero, non-zero below-minimum,
above-maximum and `65535` pixels so a controlled A/B can establish observed
behaviour without assuming that all zeros have one physical cause.

## Next Static Experiments

Run the enhanced baseline first. If the validity mask is temporally stable,
test only Aurora-effective parameters, one variable at a time:

1. `threshold_size=30` versus the current 110;
2. `laser_power=2` indoor versus automatic mode 1;
3. alignment disabled versus enabled, preserving the original output for
   calibration comparison;
4. depth correction disabled versus enabled while alignment remains enabled.

Do not persist a change unless it improves central/spatial coverage without
unacceptable noise, timing, point-cloud or resource regression. Always restore
`aurora930.service`, confirm zero restarts and rerun both sensor and read-only
gates.
