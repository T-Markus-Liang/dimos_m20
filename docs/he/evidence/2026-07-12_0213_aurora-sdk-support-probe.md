# HE Aurora930 SDK Support Probe

- Date: 2026-07-12 02:10 CST
- Orin commit: `a4af65e6b9f5b29a81ee77de1b760b0a72b6974b`
- SDK: vendor Aurora900-series 1.1.22
- Operation: getter-only device open/close; no stream or device setter
- Vehicle: lifted and stationary; motion publishers zero

## Results

The successful SDK getters returned:

| Field | Value |
| --- | --- |
| support depth-range length | 6 bytes |
| support depth-range hex | `30 2e 33 7e 31 6d` |
| support depth-range text | `0.3~1m` |
| 7x24 operation support | 1 |
| synchronized two-image support | 0 |
| face/code scan support | 1 / 1 |
| secure-encryption support | 0 |
| camera/VCSEL/CPU temperature raw | 65 / 63 / 72 |
| laser current | 1450mA |

The SDK guide describes `SupportedInfo.depth_range` as device minimum/maximum
depth information and documents laser-current units as mA. It does not document
the depth-range buffer encoding; the returned bytes are printable ASCII.

The `0.3~1m` field is not yet a safe algorithm cutoff or accuracy guarantee.
The existing canonical live baseline reported valid-depth p50 1240mm and p95
2522mm while the software filter allowed 150-4000mm. Vendor clarification is
required to explain whether this support field denotes a certified accuracy
band, a product profile, a face-scan mode or another constraint.

`synced_two_images=0` independently supports the current decision not to claim
hardware RGB-depth synchronization. It does not prove that every frame pair is
invalid; measured timestamp pairing remains the runtime evidence.

## Deliberate Missing Fields

`GetDeviceInfo` and `GetCameraParameters` returned `-1`. SDK diagnostics state
that both require successful `Open + SetMode`. The probe intentionally does not
call `SetMode`, so device-info, RGB/IR intrinsics and RGB-to-IR extrinsics are
serialized as `null`. Existing ROS CameraInfo and driver logs remain separate
evidence; this probe does not overwrite or validate them.

The structured output omits the device serial. SDK stdout/stderr can contain the
serial, so the runner stores them only in process-scoped `/tmp` files and deletes
them on every exit. Final inspection found no probe binary or SDK log residue.

## Lifecycle And Safety

The first two development runs exposed DDS endpoint convergence timing: fixed
five- and ten-second waits could briefly observe an expired Aurora publisher,
although the independent EXIT-trap gate passed. The final runner retries the
complete read-only gate at three-second intervals for at most 18 seconds and
fails if the graph does not converge.

The final main path passed the pre-stop read-only gate, post-restore live sensor
gate and final read-only gate. Aurora RGB/depth/IR were about 13.79Hz, depth
validity was 26.1%, point cloud contained 256,000 points, both services were
active with zero restarts, `he-dimos-sense` was about 1000MiB and available
memory was about 3.3GiB. `/he/nav_cmd_vel` publishers remained zero.

Raw JSON: `2026-07-12_0213_he-aurora-sdk-probe.json` (SHA-256
`b07b8fd2828cc6a9820b637f29c91eda2c8aba6252276ea41c9a9c6af1fe9349`).
