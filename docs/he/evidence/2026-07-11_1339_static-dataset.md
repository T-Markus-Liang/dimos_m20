# HE Static Visual Dataset Evidence

- Capture time: 2026-07-11 13:39 CST
- Orin path: `/home/ubuntu/he/data/visual-navigation/20260711_133901_static-qualification`
- Source commit: `1c8d41189cc3376e57d00b05144570c4edf3ce27`
- Vehicle state: lifted/static; motion output disabled
- Storage: SQLite3 rosbag, 280.0MiB
- Actual bag duration: 3.541247970s
- Messages: 669

## Topic Counts

| Topic | Count |
| --- | ---: |
| `/aurora/rgb/image_raw` | 52 |
| `/aurora/depth/image_raw` | 52 |
| `/aurora/ir/image_raw` | 52 |
| `/aurora/points2` | 52 |
| `/aurora/rgb/camera_info` | 52 |
| `/aurora/ir/camera_info` | 52 |
| `/ros_robot_controller/imu_raw` | 171 |
| `/odom_raw` | 175 |
| `/diagnostics` | 8 |
| `/tf_static` | 3 |
| `/controller/cmd_vel` | 0 |
| `/he/final_cmd_vel` | 0 |
| `/tf` | 0 |

`/he/nav_cmd_vel` was absent because it had zero publishers. The recorder did
not create or publish any control topic. Read-only safety gates passed before
and after capture.

## Integrity

The first generated checksum list incorrectly included `SHA256SUMS` itself.
The data files were not corrupt; the list was regenerated excluding itself and
then passed `sha256sum -c`:

| File | SHA-256 |
| --- | --- |
| bag database | `099fcdea92bc07f9a3f97d4bf33e6fcfb80aff70bc3b2fe07d7c610bb5e3d568` |
| manifest | `f603d8f34af29386c22cbfb0ca9d3471d70407d43052c96711e64b3f300f4d14` |
| metadata | `62599b63bf5dd276f4269df7ad50d351902838a488b80cdcce770278b64ea2b5` |

The corresponding corrected live diagnostic is
`docs/he/evidence/2026-07-11_1338_aurora-diagnostic.json`.

## Limitations

- The requested process duration was 5s, but rosbag discovery/startup consumed
  about 1.46s, leaving 3.54s of recorded data. Future manifests record both
  requested and actual durations.
- This static bag can test startup, timestamps, depth coverage and stationary
  drift. It cannot prove trajectory accuracy, scale, loop closure or
  relocalization.
- Motion datasets still require a new vehicle-down safety confirmation.
