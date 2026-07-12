# HE Orin NVMe Hardware Failure Determination

Date: 2026-07-12 CST
Classification: confirmed device-level storage hardware failure
Confidence: high
Required action: replace the NVMe; do not return it to HE runtime service

## Formal Conclusion

The Orin root NVMe has a persistent device-level media/read-integrity failure.
This is confirmed by mutually independent evidence at the NVMe health,
Linux block-device, raw-sector and filesystem layers. The failure persists
across reboot and is independent of the separately identified Python user-site
dependency defect.

The evidence is sufficient to reject the SSD for continued development,
qualification or deployment. Filesystem repair, package reinstall,
`PYTHONNOUSERSITE=1`, service restart or reformatting cannot restore confidence
in the physical device. Replacement storage and a clean system deployment are
required.

The evidence does not identify which internal component failed. Without vendor
factory diagnostics or destructive teardown, do not narrow the claim to one
specific NAND die, SSD controller, solder joint or root cause. The defensible
scope is: persistent NVMe device/media hardware failure causing deterministic
unrecoverable reads.

## Decision Standard

A hardware-failure conclusion is accepted when all of the following are true:

1. The storage device itself reports nonzero persistent media/data-integrity
   errors.
2. The kernel reports block-layer medium/I/O errors against the NVMe device,
   not only application exceptions.
3. Direct reads of fixed device sectors fail independently of the filesystem
   and application stack.
4. The same failure persists after reboot.
5. A nearby control sector remains readable, showing a localized deterministic
   read failure rather than a universally broken test command.
6. Software isolation can repair the application symptom but cannot clear the
   raw-device failure or NVMe error counter.

All six conditions were satisfied on this Orin.

## Evidence Chain

### 1. NVMe SMART/media counter

Command used:

```bash
sudo nvme smart-log /dev/nvme0
```

Observed values:

```text
critical_warning       : 0
available_spare        : 99%
percentage_used        : 0%
unsafe_shutdowns       : 32
media_errors           : 472
```

`media_errors=472` is the decisive device-reported data-integrity counter. It
remained 472 after another boot. `unsafe_shutdowns=32` is relevant incident
history but is not, by itself, proof of hardware failure.

`critical_warning=0` does not mean the device is healthy. That field is a
summary bitmask for specific threshold conditions. It does not override a
nonzero media-error counter, kernel medium errors or direct unreadable sectors.
Likewise, 99% spare and 0% wear do not prove that all existing media is readable.

### 2. Kernel block-layer medium errors

The kernel repeatedly reported:

```text
blk_update_request: critical medium error, dev nvme0n1,
sector 87084872 op 0x0:(READ)
```

This message is below EXT4, Python, ROS, Aurora and DimOS. It means a read
submitted to the NVMe block device completed as an unrecoverable medium error.

EXT4 then reported the secondary consequence:

```text
EXT4-fs error (device nvme0n1p1): __ext4_find_entry:
comm python3: reading directory lblock 0
```

The process name only identifies who triggered the read. It does not make
Python the cause of the block-device medium error.

During the later bounded environment audit, the same boot accumulated at least
935 matching `critical medium error`/EXT4 error lines before containment.

### 3. Raw-sector A/B

A controlled, read-only block-level A/B was performed on sectors identified by
kernel evidence. The equivalent diagnostic form is:

```bash
sudo dd if=/dev/nvme0n1 of=/dev/null \
  bs=512 skip=<sector> count=1 iflag=direct status=none
```

Observed results:

| Block-layer sector | Result |
| --- | --- |
| 87084872 | read failed with I/O error |
| 87057648 | read failed with I/O error |
| 87084800 | read succeeded |

This bypasses EXT4 path lookup and Python packages. Two failing locations plus a
nearby readable control location establish deterministic, location-dependent
raw-device failure.

Do not repeatedly rerun these reads on the failed production disk. The original
evidence is preserved. Any further recovery work should be done with the old
device unmounted and preferably after a block-level recovery image.

### 4. Filesystem-visible EIO

Affected files/directories returned `EIO` through ordinary tools such as
`stat`, `head` and `sha256sum`. Recovery copy also encountered unreadable files
in a generated legacy speech grammar directory.

These errors prove user-visible data loss but are not used alone to classify the
hardware. They are consistent downstream consequences of the raw-sector and
kernel evidence above.

### 5. Persistence across reboot

The same SMART media-error count and deterministic unreadable locations remained
after a controlled reboot. A transient process, cache or one-time mount-state
problem would not explain this combination.

### 6. Hardware/software separation A/B

A separate software defect existed: Aurora systemd inherited
`/home/ubuntu/.local`, where Python metadata was unreadable/corrupt.

Observed A/B:

- default ROS 2/Python user site failed;
- `PYTHONNOUSERSITE=1` made ROS 2 CLI work;
- isolated Aurora opened the camera and produced RGB/depth at about 14.72Hz;
- SMART still reported 472 media errors;
- direct reads of the two failing sectors still failed.

Therefore the Python issue explains one service-start symptom and is fixed in
the canonical service configuration. It does not explain or repair the NVMe
device failure.

## Alternative Explanations And Why They Fail

| Proposed explanation | Why it is insufficient |
| --- | --- |
| DimOS/Aurora bug | Application code cannot create a persistent NVMe SMART media-error count or make fixed raw sectors return medium errors. |
| Python dependency corruption | User-site isolation restored ROS/Aurora operation while raw-sector failures and SMART errors remained. |
| EXT4-only corruption | Direct reads against `/dev/nvme0n1` bypass EXT4 and still failed. |
| One bad file | Two distinct block-layer sectors failed, kernel callbacks were repeatedly suppressed, and recovery encountered additional unreadable data. |
| Cache/transient boot issue | The SMART count and bad locations persisted after reboot. |
| Normal SSD wear | `percentage_used=0` is not proof of health, but it makes ordinary endurance exhaustion unlikely; the observed media failure is still real. |
| Unsafe shutdown only | Unsafe shutdown may have triggered or exposed the failure, but it does not make a device with persistent unreadable sectors acceptable. |
| PCIe/cable/power issue | No evidence here proves the exact internal cause. However deterministic LBA failures, a readable nearby control and the device media-error counter support device/media failure rather than an application problem. Replacement remains required either way. |

## Evidence Preservation

Canonical compact report:

`docs/he/evidence/2026-07-12_0824_nvme-media-failure.md`

Verified recovery directory:

`/Users/markus/Downloads/he-orin-recovery-2026-07-12`

Raw diagnostic hashes:

| Artifact | SHA-256 |
| --- | --- |
| `diagnostics/nvme-smart-log.txt` | `56c74bcfb1e25d384ebc3aaeefa8648c71c50b435c52fab788256cf5e75a0442` |
| `diagnostics/dmesg.txt` | `e76f9a3db3fdeec2b498cfe621527565f5fd4364f0a8db0ad284b95381997255` |
| `diagnostics/runtime-state.txt` | `04e5ac946816bc06cb140fcd39f18171e88a707a8d1e9b90b2561d844196d1dc` |

The recovery-wide manifest and both HE rosbag manifests were also verified.
These hashes make later alteration of the preserved evidence detectable.

## Replacement-SSD Acceptance Method

A replacement SSD is not accepted merely because it boots. Before enabling
Aurora, DimOS or control services:

1. Flash a clean compatible Jetson system.
2. Capture baseline `nvme smart-log` and require `media_errors=0`.
3. Inspect current-boot kernel logs and require no NVMe medium/I/O, block update
   or EXT4 errors.
4. Run the repository `he-storage-health.service` and require
   `/run/he-storage-health.json` to report `healthy=true`.
5. Pass deployment integrity and read-only gates before starting sensors.
6. Keep motion disabled through sensor and shadow qualification.
7. Preserve the new baseline report in Git evidence.

Do not use destructive `badblocks -w`, full-device writes or mounted-root
`fsck` as an acceptance test.

## Approved External Wording

Use this wording in reports, supplier communication and internal decisions:

> The Orin root NVMe is confirmed to have a persistent device-level
> media/read-integrity hardware failure. NVMe SMART reports 472 media errors
> across reboot; Linux reports repeated critical medium errors; direct reads of
> sectors 87084872 and 87057648 fail while nearby sector 87084800 succeeds.
> These results bypass the filesystem and application stack. A separate Python
> dependency issue was isolated and repaired, but it did not change the raw
> NVMe failures. The SSD is rejected for continued use and must be replaced.

Avoid saying only "Python package corruption", "filesystem problem" or "service
configuration problem". Also avoid claiming a specific NAND die or controller
failed unless a vendor hardware analysis provides that evidence.
