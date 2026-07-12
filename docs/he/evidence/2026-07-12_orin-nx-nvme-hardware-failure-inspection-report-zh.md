# Orin NX NVMe SSD 硬件故障检查报告

报告编号：HE-NVME-20260712-01
报告日期：2026-07-12
检查对象：HE 机器人平台 NVIDIA Jetson Orin NX 计算单元
检查结论：已确认 NVMe SSD 存在设备级介质/读取完整性硬件故障
判定置信度：高
处置等级：停止使用并更换 SSD

## 1. 报告目的

本报告用于固定 Orin NX 根 NVMe 的检查方法、原始证据、排除过程和最终结论，避免将
已经确认的存储硬件问题误判为 DimOS、Aurora、ROS、Python 或 EXT4 的单纯软件问题。

本报告可以用于：

- 内部故障复盘和责任边界确认；
- SSD 更换或售后沟通；
- 新 SSD 到货后的验收对照；
- HE 平台后续恢复部署的准入依据。

## 2. 检查对象

| 项目 | 信息 |
| --- | --- |
| 计算平台 | NVIDIA Jetson Orin NX Engineering Reference Developer Kit Super |
| CPU 架构 | ARM64 / aarch64 |
| 系统 | Ubuntu 22.04.5 LTS |
| Jetson Linux | L4T R36.4.7 |
| 内核 | 5.15.148-tegra |
| 根存储设备 | `/dev/nvme0n1` |
| 根分区 | `/dev/nvme0n1p1`，EXT4 |
| SSD 标称信息 | 128GB 级，系统识别约 119.2GiB |
| SSD 序列号 | 未写入 Git；如用于售后，请现场从 SSD 标签或 `nvme id-ctrl` 补录 |
| DimOS 分支 | `codex/he-orin` |
| 故障时 Orin 代码版本 | `329c9c689422138be37b4257e33509db67a5d818` |

## 3. 故障背景

Orin 在无运动输出的视觉 SLAM shadow 测试期间出现网络失联，现场断电重启。重启后：

- Aurora 服务无法稳定启动并进入重启循环；
- ROS/Python 读取用户 site-package metadata 时出现 I/O error；
- Linux 内核持续报告 NVMe critical medium error；
- EXT4 持续报告目录读取错误；
- 部分文件通过 `stat`、`head`、`sha256sum` 无法读取；
- 备份过程中发现额外不可读文件。

后续检查将“应用依赖问题”和“SSD 设备问题”分开验证。

## 4. 判定标准

本报告采用以下六项联合判定标准。六项全部满足时，判定为设备级存储硬件故障：

1. NVMe 自身记录非零且跨重启持续的 media/data-integrity error。
2. Linux 块设备层直接报告 NVMe medium/I/O error。
3. 绕过文件系统和应用后，固定裸设备扇区仍然读取失败。
4. 重启后错误计数和不可读位置仍然存在。
5. 邻近对照扇区可读取，排除测试命令本身全面失效。
6. 修复软件环境后，应用可以运行，但 NVMe SMART 和裸扇区故障不消失。

本设备六项条件全部满足。

## 5. 检查过程与结果

### 5.1 NVMe SMART 检查

执行：

```bash
sudo nvme smart-log /dev/nvme0
```

关键结果：

```text
critical_warning       : 0
available_spare        : 99%
available_spare_threshold : 32%
percentage_used        : 0%
unsafe_shutdowns       : 32
media_errors           : 472
power_on_hours         : 174
```

判定：

- `media_errors=472` 是 SSD 自身记录的数据完整性/介质错误；
- 该数值在再次重启后仍保持为 472；
- `unsafe_shutdowns=32` 是事件背景，但不能单独用于判定；
- `critical_warning=0`、99% spare、0% wear 不能抵消已经存在的 media errors。

结论：NVMe 设备自身已经记录持久介质错误。

### 5.2 Linux 块设备层检查

执行：

```bash
sudo dmesg -T | grep -E \
  'critical medium error|EXT4-fs error|I/O error|blk_update_request'
```

关键内核输出：

```text
blk_update_request: critical medium error, dev nvme0n1,
sector 87084872 op 0x0:(READ)

EXT4-fs error (device nvme0n1p1): __ext4_find_entry:
comm python3: reading directory lblock 0
```

判定：

- `critical medium error` 来源于 Linux block layer，层级低于 EXT4、Python、
  ROS、Aurora 和 DimOS；
- `op 0x0:(READ)` 表示对 NVMe 的读取请求返回不可恢复的介质错误；
- EXT4 错误是底层读取失败向上的表现；
- 日志中的 `comm python3` 只表示触发读取的进程，不表示 Python 造成硬件错误。

在后续受控环境检查中，单次启动累计至少出现 935 条匹配的 medium/EXT4 错误。

结论：错误发生在 NVMe 块设备层，不是单纯应用异常。

### 5.3 裸设备扇区 A/B 检查

首先确认逻辑扇区大小：

```bash
sudo blockdev --getss /dev/nvme0n1
```

设备返回 512 字节。

使用 direct I/O 直接读取内核指出的扇区，绕过 EXT4 和 page cache：

```bash
sudo dd if=/dev/nvme0n1 of=/dev/null \
  bs=512 skip=<sector> count=1 iflag=direct status=none
```

结果：

| 测试扇区 | 结果 | 返回状态 |
| --- | --- | --- |
| 87084872 | Input/output error | 失败 |
| 87057648 | Input/output error | 失败 |
| 87084800 | 正常读取 | 成功 |

判定：

- 两个不同位置的裸设备读取失败；
- 邻近扇区 87084800 可正常读取；
- 该测试不经过文件路径、EXT4、Python、ROS、Aurora 或 DimOS；
- 结果具有固定位置相关性，不是测试命令整体失效。

结论：已直接证明 NVMe 上存在确定性不可读区域。

### 5.4 文件系统可见错误

受影响文件或目录通过以下工具读取时返回 `EIO`：

- `stat`
- `head`
- `sha256sum`
- recovery copy/rsync

备份过程中，旧语音 grammar 生成目录中的部分文件无法读取并被明确排除。

判定：已经发生用户可见的数据不可读。该证据与裸扇区及 block-layer 错误一致，但本报告
不依靠文件系统错误单独判断硬件。

### 5.5 重启持久性检查

受控重启后：

- SMART 仍为 `media_errors=472`；
- sector 87084872 和 87057648 仍然读取失败；
- 邻近 sector 87084800 仍然可读；
- Linux 继续报告 critical medium error。

结论：排除一次性缓存、临时进程状态或单次挂载异常。

### 5.6 软件环境隔离 A/B

发现 Aurora systemd 会加载损坏/不可读的
`/home/ubuntu/.local/lib/python3.10/site-packages`。

对照结果：

| 条件 | 结果 |
| --- | --- |
| 默认 Python user-site | ROS/Python metadata 读取失败 |
| 设置 `PYTHONNOUSERSITE=1` | ROS 2 CLI 恢复 |
| 隔离 user-site 启动 Aurora | 相机打开，RGB/depth 约 14.72Hz |
| 隔离后 SMART | 仍为 472 media errors |
| 隔离后裸扇区 | 两个故障 sector 仍不可读 |

判定：

- Python user-site 污染是一个独立、可修复的软件问题；
- 软件隔离可以恢复 ROS/Aurora；
- 软件隔离不能修改 NVMe media error 或恢复裸扇区读取。

结论：Python 依赖问题不是 NVMe 硬件故障的根因，也不能作为继续使用该 SSD 的理由。

## 6. 替代解释排除

| 可能解释 | 排除依据 |
| --- | --- |
| DimOS 或 Aurora bug | 应用代码无法产生跨重启 NVMe SMART media error，也无法使固定裸扇区返回 medium error。 |
| Python 包损坏 | `PYTHONNOUSERSITE=1` 恢复 ROS/Aurora，但 SMART 和裸扇区错误不变。 |
| 仅 EXT4 损坏 | 裸读 `/dev/nvme0n1` 绕过 EXT4 后仍失败。 |
| 单个文件损坏 | 两个独立 sector 失败，且恢复复制发现额外不可读数据。 |
| 缓存或瞬时故障 | 重启后错误计数和不可读位置继续存在。 |
| SSD 正常磨损 | 0% wear 不代表没有介质故障；实际 media error 和不可读扇区具有更高证据优先级。 |
| 断电次数导致的普通脏盘 | 断电可能触发或暴露故障，但不能使持续不可读的设备重新符合运行要求。 |
| `critical_warning=0` 表示健康 | 该字段是特定阈值的汇总位，不能覆盖非零 media error 和直接读取失败。 |

## 7. 最终结论

综合 SMART、Linux block layer、raw-sector A/B、文件 EIO、重启持久性和软件隔离对照，
结论如下：

> Orin 根 NVMe 已确认存在持续性的设备级介质/读取完整性硬件故障。NVMe SMART 跨重启
> 报告 472 个 media errors；Linux 持续报告 critical medium error；直接读取 sector
> 87084872 和 87057648 失败，而邻近 sector 87084800 成功。这些检查绕过了文件系统和
> 应用软件。Python 依赖问题已被独立隔离并修复，但不会改变 NVMe 裸设备故障。该 SSD
> 不允许继续使用，必须更换。

判定等级：已确认。
工程处置：SSD 退役并更换，不允许继续承担 HE 研发、验证或部署运行。

## 8. 结论边界

当前证据可以确定：

- NVMe 设备/介质层存在持续硬件故障；
- 存在确定性不可读区域；
- 继续使用存在数据丢失、系统服务异常和运行不确定性；
- 需要更换 SSD。

当前证据不能进一步确定：

- 具体是哪颗 NAND die 损坏；
- 是否为 SSD 主控内部故障；
- 是否存在焊接、供电或连接器内部问题；
- 32 次 unsafe shutdown 中哪一次触发或暴露了故障。

如需确定内部元件或起因，必须由 SSD 厂商执行工厂级诊断或拆解分析。但这不影响
“当前 SSD 已不符合继续使用条件”的工程结论。

## 9. 处置建议

1. 保持故障 Orin 关机，避免继续写入。
2. 拆下并标记故障 SSD，禁止重新投入 HE 平台。
3. 如需数据恢复，先在 SSD 未挂载状态制作块级镜像。
4. 不要在挂载的根文件系统上运行 `fsck`。
5. 不要使用 `badblocks -w` 或全盘写入方式证明磁盘“恢复”。
6. 更换 NVMe 后重新刷写兼容的 Jetson Linux 系统。
7. 只从 Git 和已验证的 macOS recovery package 恢复经过审查的内容。
8. 新 SSD 必须通过 storage-health、部署完整性和只读门后才能启动传感器。
9. 导航和运动控制继续保持禁用，直到后续独立验收。

## 10. 新 SSD 验收标准

新 SSD 不以“可以开机”作为通过标准，必须满足：

- `nvme smart-log` 中 `media_errors=0`；
- 本次启动的 dmesg 中没有 NVMe medium/I/O error；
- 没有 block update 或 EXT4 读取错误；
- `he-storage-health.service` 成功；
- `/run/he-storage-health.json` 报告 `healthy=true`；
- 部署完整性、静态 closeout、传感器和 read-only gate 依次通过；
- shadow admission 通过后，重新执行中断的两小时持久化 soak。

## 11. 原始证据与完整性

原始恢复目录：

`/Users/markus/Downloads/he-orin-recovery-2026-07-12`

| 原始文件 | SHA-256 |
| --- | --- |
| `diagnostics/nvme-smart-log.txt` | `56c74bcfb1e25d384ebc3aaeefa8648c71c50b435c52fab788256cf5e75a0442` |
| `diagnostics/dmesg.txt` | `e76f9a3db3fdeec2b498cfe621527565f5fd4364f0a8db0ad284b95381997255` |
| `diagnostics/runtime-state.txt` | `04e5ac946816bc06cb140fcd39f18171e88a707a8d1e9b90b2561d844196d1dc` |

相关技术记录：

- `docs/he/evidence/2026-07-12_0824_nvme-media-failure.md`
- `docs/he/evidence/2026-07-12_nvme-hardware-failure-determination.md`
- `docs/he/orin-nx-environment-inventory-2026-07-12.md`

上述哈希用于检测原始证据是否被修改。恢复包总清单及两份 HE rosbag 原始清单均已通过
校验。

## 12. 复核签署

检查结论：NVMe SSD 设备级介质/读取完整性硬件故障，必须更换。

检查执行：Codex 自动化检查与日志核对
人工复核：____________________
设备/SSD 标签序列号补录：____________________
复核日期：____________________
供应商处理意见：____________________
