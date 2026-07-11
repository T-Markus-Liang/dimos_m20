# HE Orin NX 8GB DimOS 轻量化部署方案

更新日期：2026-07-11 12:40 CST

目标：将 `MeloLong/dimos` 的 `feat/wd/m20` 分支作为 DimOS 开发基线，部署到 HE 机器人平台的 Jetson Orin NX 8GB 上，复用现有前转后驱阿克曼底盘和 Aurora 930 RGB-D/IR 深度相机。LD19 单线激光雷达从 HE 默认架构中弃用。Orin 只承担实机闭环，开发、仿真、回放和重型可视化留在外部电脑。

本文中的机器人相关模块统一使用 `HE` 前缀，例如 `HEConnection`、`HESensorBridge`、`HEAckermannSafety`、`he-teleop`、`he-nav-headless`。

## 1. 结论与边界

方案可行，但当前系统尚不满足“直接接入导航闭环”的条件。本轮部署的交付边界是：
完成轻量运行环境、硬件接口收敛、静态传感器数据链、受限可视化和离地控制安全链，
并留下可复现的服务、验证器与问题记录。车辆当前被抬起，无法产生真实机体运动，
因此不在本轮宣称建图、定位、规划或自动探索可用。

建图定位作为下一独立阶段处理。LD19 已从 HE 默认架构弃用，不把纯二维激光
SLAM 作为路线；后续优先研究 Aurora RGB-D/视觉惯性 SLAM，并评估 DINOv3 等
学习特征在地点识别、回环检测和重定位中的价值。视觉定位通过实地移动验证后，
再接 DimOS 的地图、规划、自动探索和路径跟踪。

HE Orin 上应运行：

- ROS 2 硬件驱动与 HE 适配层。
- 当前阶段运行 DimOS 传感器桥、控制管理与安全看门狗；地图、规划和自动探索留待下一阶段。
- 无界面 Rerun 网桥和受限的 Web 命令入口。
- 最小必要的日志、资源监控和 systemd 服务。

HE Orin 上不应运行：

- MuJoCo、Unity、本机 `dimos-viewer`、桌面 RViz。
- 全量历史回放、长期无上限 Rerun 缓冲。
- VLM、YOLO、Ollama、TensorRT 模型导出或大模型推理。
- LFS 数据集、回放包、仿真资源、全量开发依赖。

## 2. 已确认的 HE 平台事实

### 2.1 计算单元

| 项目 | 实测状态 | 部署含义 |
| --- | --- | --- |
| 平台 | Jetson Orin NX，aarch64 | 依赖与原生模块必须在 Jetson/L4T 环境构建 |
| 系统 | Ubuntu 22.04.5，L4T 36.4.7，内核 `5.15.148-tegra` | ROS 2 Humble 已安装，可直接复用 |
| CPU | 6 核 Cortex-A78AE，最高约 1.984GHz | 导航应限制工作线程，避免点云和可视化占满 CPU |
| 内存 | 7.4GiB RAM，13GiB swap | 目标是常态保留至少 1GiB 可用内存，不能依赖 swap 维持实时性 |
| 存储 | 75GB NVMe，审计时仅约 4.4GB 可用，94% 已用 | 必须先备份并清理，部署前目标至少释放到 25GB 可用 |
| 网络 | Wi-Fi `192.168.1.106/24`；有线网卡当前未连接 | 运行时服务应绑定 `0.0.0.0`，但现场优先使用有线网络 |
| 电源模式 | `MAXN_SUPER` | 保持现状；发现 nvpmodel 配置引用不存在 CPU6/CPU7，后续单独修正，不在 DimOS 部署阶段修改 |

### 2.2 底盘与控制板

HE 是前转向、后驱动的阿克曼底盘，现有 ROS 2 配置使用 `MACHINE_TYPE=ROSOrin_Acker`。

| 层级 | 当前接口 |
| --- | --- |
| 控制板 | QinHeng USB CDC ACM，`1a86:55d4` |
| 稳定设备名 | `/dev/rrc -> /dev/ttyACM0` |
| 协议速率 | 1,000,000 baud |
| ROS 控制节点 | `ros_robot_controller` |
| 速度输入 | `/cmd_vel`，类型 `geometry_msgs/msg/Twist` |
| 现有执行节点 | `odom_publisher`，订阅 `/cmd_vel` 后发布电机与 PWM 转向命令 |
| 电机控制 topic | `/ros_robot_controller/set_motor` |
| 转向控制 topic | `/ros_robot_controller/pwm_servo/set_state` |
| IMU | `/ros_robot_controller/imu_raw`，约 47Hz，frame 为 `imu_link` |
| 电池 | `/ros_robot_controller/battery`，`UInt16`，当前读数 10623，按现有语义应作为约 10.623V 使用 |

现有阿克曼参数位于 ROS 工作区：轴距 `0.17706m`、轮距 `0.17165m`、轮径 `0.085m`、最大转向角约 34 度。当前统一最终执行层已将线速度限制为 `+/-0.10m/s`、角速度限制为 `+/-0.30rad/s`；旧路径中约 `+/-0.2m/s`、`+/-0.5rad/s` 的限制不再作为最终安全边界。

重要限制：当前 `/odom_raw` 不是轮编码器或视觉里程计。它根据下发的速度指令按 50Hz 积分得到，属于开环推算。它可用于遥控状态展示和初始软件联调，不能作为自主导航定位、闭环停车精度或地图对齐的可信反馈来源。

### 2.3 深度相机

| 项目 | 实测状态 |
| --- | --- |
| 设备 | Aurora 930，USB ID `3251:1930` |
| 驱动 | `deptrum-ros-driver-aurora930`，systemd 服务 `aurora930.service` |
| ROS 节点 | `/aurora/aurora` |
| RGB | `/aurora/rgb/image_raw`，640x400，约 14-15Hz，约 10.7MB/s |
| 深度 | `/aurora/depth/image_raw`，约 14-15Hz，约 7.5MB/s |
| 点云 | `/aurora/points2`，`PointCloud2`，约 13-14Hz，约 58MB/s |
| 点云 frame | `depth_camera_link` |
| 当前深度范围 | 驱动参数为 150mm 至 4000mm |
| USB 链路 | 当前连接在 USB 2.0 Hub，480Mbps |

当前相机驱动使用可靠传输 QoS，原始点云在本机订阅时已达到约 58MB/s。这个流不得原样通过 Wi-Fi 转发到远程查看器，也不应写入无界限的 Rerun 缓冲。DimOS 应在 Orin 本机接收并处理点云，只向远程端发布降采样局部地图、低频路径与状态；RGB 仅在明确调试时压缩后限频发布。

相机坐标系目前未接入底盘 TF 树：底盘 URDF 提供 `base_link -> camera_link0`，相机驱动提供 `depth_camera_link -> rgb_camera_link`，二者之间没有变换。部署前必须测量或标定 `camera_link0 -> depth_camera_link` 静态外参，否则点云不能可靠用于地图和规划。

### 2.4 LD19 单线激光雷达（已弃用）

| 项目 | 实测状态 |
| --- | --- |
| 型号 | LD19 |
| 物理接口 | CH340，USB ID `1a86:7523` |
| 稳定设备名 | `/dev/lidar -> /dev/ttyCH341USB0` |
| 驱动 | `ldlidar_stl_ros2` |
| 配置 | 波特率 230400，`LDLiDAR_LD19`，期望输出 `sensor_msgs/msg/LaserScan` |
| 底盘安装 frame | URDF 中为 `lidar_frame`，位于 `base_link` 前上方 |

LD19 后续曾恢复并完成 10Hz 数据验证，但单线二维扫描不满足 HE 的视觉建图定位目标。自 Aurora 全模态接入版本起，`he-ld19.service` 被删除并停止启用，`HESensorBridge` 不再订阅 `/scan`。驱动工作区可以保留作为硬件库存，不属于 HE 默认运行、资源验收或导航输入。

### 2.5 当前 ROS 服务问题

当前系统同时存在 `ros-robot-controller.service` 和 `odom-publisher.service`。后者又会拉起一个 `ros_robot_controller`，因此 ROS 图中存在两个同名控制节点，二者都占用 `/dev/rrc` 并重复发布 IMU、电池等 topic。Wi-Fi 按键程序也直接打开同一串口。

这不是 DimOS 可以绕过的问题。HE 部署前必须指定唯一的控制板所有者：保留一个 `ros_robot_controller` 实例，并让按键功能通过 ROS topic 或一个明确的串口仲裁方式访问控制板。没有完成这一步之前，不允许 DimOS 向真实底盘发送运动命令。

## 3. 目标架构

```text
Aurora 930  ── RGB / Depth / IR / PointCloud2 / CameraInfo ── HESensorBridge ─┐
控制板 IMU  ── ROS 2 Imu                   │                  │
开环 odom   ── ROS 2 Odometry              │                  ▼
                                           │     下一阶段: visual SLAM -> map/pose
                                           │                  -> explorer/planner/controller
DimOS cmd_vel ── HEConnection ── /he/nav_cmd_vel ──┐
手柄 cmd_vel  ── /controller/cmd_vel ───────────────┼─ twist_mux
                                                     └─ /he/final_cmd_vel
                                                                │
                                                                ▼
                                              odom final watchdog -> HE 阿克曼底盘
                                                        │
                                                        ▼
                                限频状态 / 局部地图 / 路径 -> Rerun Web -> 外部电脑
```

`HESensorBridge` 负责把 ROS 2 输入转成 DimOS 数据流：点云或二维扫描、IMU、里程计、时间戳和坐标系。`HEConnection` 负责 DimOS 导航出口：接收最终 `Twist`，执行速度限幅、命令过期检测和显式停止，再发布到 `/he/nav_cmd_vel`。`twist_mux` 将手柄置于导航之上；`odom_publisher` 只订阅 `/he/final_cmd_vel`，承担最终限幅、100ms 看门狗、电机归零和转向回中。

第一版不直接让 DimOS 发布 `/ros_robot_controller/set_motor` 或 PWM。继续复用现有的 ROS 阿克曼运动学层，所有导航和手柄命令先经过 mux，再由唯一的 `odom_publisher` 计算电机和转向，避免并行发布者绕过最终安全层。

## 4. HE 模块与蓝图命名

建议在 WD 基线中新增独立的 HE 机器人包，不修改或伪装为 M20：

| 类型 | 建议名称 | 职责 |
| --- | --- | --- |
| 传感器接入 | `HESensorBridge` | Aurora RGB、深度、IR、点云、标定信息，以及 ROS 2 IMU、里程计到 DimOS 流 |
| 控制接入 | `HEConnection` | DimOS 最终速度到 `/cmd_vel`，带限幅和看门狗 |
| 安全层 | `HEAckermannSafety` | 最大速度、最大角速度、命令超时、关闭停止、遥控覆盖 |
| 坐标系 | `HEFrameConfig` | `base_link`、`lidar_frame`、`depth_camera_link` 的外参和校验 |
| 仅传感器蓝图 | `he-sense-headless` | 验证 ROS 2 到 DimOS 数据与远程可视化 |
| 遥控蓝图 | `he-teleop-headless` | `tele_cmd_vel -> HEAckermannSafety -> HEConnection` |
| 导航蓝图（后续） | `he-nav-headless` | 可信视觉位姿、地图、自动探索、规划、跟踪、运动管理、HE 控制出口 |

所有 HE 蓝图必须默认无本机 GUI，所有实车控制功能默认禁用，直到通过对应的集成门。

## 5. Orin 侧轻量化原则

### 5.1 存储策略

部署前的目标是至少 25GB 可用空间，推荐 30GB。当前可优先迁移到 macOS 的大目录包括：

- `/home/ubuntu/models`，约 8.3GB，VLA/VLM 权重和 ONNX 导出。
- `/home/ubuntu/tensorrt_export`，约 2.8GB。
- `/home/ubuntu/.ollama`，约 1.8GB。
- `/home/ubuntu/openvla-edge`、`llama.cpp`、`large_models`、`vla_data` 和旧下载目录。
- 旧 Python AI 环境的包清单与源码。`~/.local` 约 6.7GB，其中 CUDA 12 pip 包约 3.5GB，但不可在未验证当前 ROS 服务依赖前直接删除。

必须备份的内容：`ros2_ws`、`third_party/aurora_ws`、`wifi_manager`、`/etc/systemd/system` 中相关服务、`/etc/udev/rules.d` 中 `/dev/rrc` 和 `/dev/lidar` 规则、ROS 环境脚本、已安装软件包清单，以及上述大模型目录的文件清单。完成校验后再清理可重建的模型、导出物、下载缓存和旧 AI 环境。

不要清理：Ubuntu、JetPack/L4T、ROS 2 Humble、Aurora 驱动、控制板 udev 规则和现有底盘工作区。LD19 驱动工作区不再是 HE 运行依赖，可在后续磁盘维护时单独归档。

### 5.2 Python 与原生依赖

WD 分支必须使用跳过 LFS 的克隆：

```bash
export GIT_LFS_SKIP_SMUDGE=1
git clone --branch feat/wd/m20 https://github.com/MeloLong/dimos.git /opt/he/dimos_wd_m20
```

实际路径可以是 `/home/ubuntu/he/dimos_wd_m20`，但不应与旧 ROS 工作区混放。部署环境需要独立虚拟环境，禁止安装全量 extras、仿真、回放和感知模型。任何需要 Rust、Nix 或 Cargo 构建的原生模块都先在 Jetson 上单独验证；不能假设 x86 VM 产物可直接复制到 aarch64 Orin。

安装顺序应为：最小 Python 运行时 -> ROS 2 桥 -> 点云/地图原生模块 -> Web/Rerun -> 规划与控制。每一步记录磁盘、内存和 CPU 增量。

### 5.3 Rerun 与远程查看

M20 的现有 Rerun 配置不能原样照搬到 HE。HE 运行时建议：

- Orin 不启动本机 `dimos-viewer`。
- Rerun 进程和桥接缓冲初始上限设为 256MB，稳定后最多 512MB。
- 只发布最新状态，避免将历史帧无限制保留给 Web 客户端。
- 原始 Aurora 点云不远程发布；改发 1Hz 左右的下采样局部地图或占据结果。
- Aurora RGB、深度、IR、点云和 CameraInfo 默认进入 `HESensorBridge`；RGB/深度/IR 初始各限 5Hz，点云限 1Hz 并按 stride 8 下采样，Rerun 仅保留最新状态。
- 路径、目标、机器人位姿、诊断状态可发布 2-10Hz。
- Web 服务监听 `0.0.0.0`，只允许受信任局域网访问。

此前 WD M20 专用配置中 `max_hz=0` 的语义是“不限频”而不是“禁用”。HE 配置不得使用 `0` 试图关闭高带宽相机流，必须显式不订阅或使用正值限频。

端口以运行时实际监听结果为准。已有开发环境通常使用 `7779`、`9877`、`9878`，部署后应由 systemd 服务和防火墙规则统一固定，并在外部电脑上验证访问。

### 5.4 资源预算

| 组件 | 初始预算 |
| --- | --- |
| 操作系统、ROS 2 驱动与后台服务 | 1.5-2.0GB RAM |
| DimOS Python/桥接 | 1.0-1.5GB RAM |
| 地图、规划与控制原生模块 | 1.0-1.5GB RAM |
| Rerun 网桥 | 256MB，最大 512MB |
| 可用安全余量 | 至少 1GB RAM |
| CPU 持续目标 | 低于 70%，保留一个核心的调度余量 |
| 网络 | 原始点云禁止跨 Wi-Fi；远程流量目标低于 10Mbps |

地图参数不在当前静态部署阶段固化。下一阶段应先用实采数据离线比较视觉 SLAM
候选，再根据定位精度和 Orin 资源实测确定分辨率、关键帧、回环和地图发布频率，
不能沿用 M20 或二维雷达栈的默认参数。

## 6. 实施阶段与集成门

### 阶段 0：备份、清理与基线固化

1. 备份硬件工作区、服务、udev、环境脚本、软件包清单和大目录清单到 macOS。
2. 验证备份可读、文件数和校验和正确。
3. 清理旧模型、TensorRT 导出、Ollama 数据、下载缓存和可重建的 AI 包，达到至少 25GB 可用空间。
4. 记录系统版本、JetPack/L4T、ROS 包、ROS topic 列表和当前服务状态。

通过标准：硬件服务仍可启动，磁盘可用空间达到目标，备份位置明确且可恢复。

### 阶段 1：ROS 硬件链路收敛

1. 让 `/dev/rrc` 只有一个 ROS 控制节点所有者。
2. 停用 LD19 服务并确认 `/scan` 不再属于 HE 默认运行图。
3. 完成相机到 `base_link` 的静态外参，验证相机、激光和底盘在同一 TF 树。
4. 标明 `/odom_raw` 为开环推算；在没有真实轮速或视觉/激光里程计前，禁止其作为自主导航定位依据。

通过标准：一个控制板节点、稳定 IMU/电池；Aurora RGB、深度、IR、点云和两路 CameraInfo 均稳定进入 `HESensorBridge`，相机数据能变换到 `base_link`。

### 集成门 A：HE 遥控安全闭环

1. 仅部署 `HEConnection` 和 `HEAckermannSafety`，不启动地图与规划。
2. 由 DimOS 以固定频率发布受限 `/cmd_vel`，命令超时建议 200ms；模块退出时连续发布零速度。
3. 在车轮离地或开阔低风险区域测试：零速度、短前进、短后退、短转向、遥控覆盖、客户端断连、服务停止。

通过标准：运动命令可预测，任何超时、断连、停止服务或程序退出都能让底盘停止。

### 集成门 B：HE 传感器到 DimOS

1. `HESensorBridge` 默认接入 Aurora RGB、深度、IR、点云、RGB CameraInfo、IR/depth CameraInfo，以及 IMU 和开环 odom。
2. 在 Orin 本机验证 DimOS 可收到带正确时间戳和 frame 的数据。
3. 仅将低频下采样局部地图、位姿、目标、路径和状态推送到远程浏览器。

通过标准：远程页面稳定，Rerun 缓冲受限，Orin 内存保留至少 1GB，网络不会因原始点云饱和。

### 当前阶段冻结点：静态部署验收

车辆保持抬起时，只完成阶段 0、阶段 1、集成门 A 的离地部分和集成门 B。验收后
保持 `HEConnection.enabled=False`、`/he/nav_cmd_vel` 零发布者，不新增
`he-nav-headless`，不启动 RF2O、SLAM Toolbox、RTAB-Map、视觉模型或自动探索。

### 下一阶段集成门 C：视觉 SLAM 影子模式

1. 车辆落地后先录制时间同步的 RGB、深度、IR、点云、IMU 和人工标记路线数据。
2. 在外部电脑离线比较 RGB-D SLAM、VIO/视觉惯性 SLAM及学习特征增强方案。
3. 选出的算法在 Orin 上只发布候选 `map -> odom -> base_footprint` 和地图，禁止连接规划控制。
4. 验证静止漂移、尺度、方向、重复路线闭环、遮挡/弱纹理恢复、CPU、内存和温度。

通过标准：实测路线误差和恢复能力达到预先定义的阈值，动态 TF 唯一且连续，
候选在 Orin 上不触发 OOM、持续 swap 或传感器丢帧。DINOv3 若使用，只能作为
特征、地点识别或回环辅助，不能单独作为六自由度几何定位器。

### 下一阶段集成门 D：DimOS 地图与自动探索空跑

1. 将可信视觉位姿和地图转换为 DimOS 地图/位姿接口。
2. 接入 DimOS 自动探索、目标生成和规划，但保持 `nav_cmd_vel` 与
   `HEConnection` 断开。
3. 用录制数据和现场影子模式验证 frontier、路径、取消、重定位和地图更新。

通过标准：目标和路径与真实可通行区域一致，定位重置或丢失时探索立即暂停，
没有任何真实底盘命令。

### 下一阶段集成门 E：低速自主探索

只有集成门 C、D 和落地后的控制安全复验通过后，才连接
`explorer -> path planner -> speed/control -> MovementManager -> HEConnection`。
初始线速度不高于 `0.10m/s`、角速度不高于 `0.30rad/s`，保留遥控最高优先级、
目标取消、定位健康门、命令看门狗和物理急停。

## 7. HE 控制安全约束

`HEConnection` 的最低要求：

- 只接受有限数值；拒绝 NaN、Inf 和超过限制的速度。
- 初始限幅：线速度 `+/-0.10m/s`，角速度 `+/-0.30rad/s`；通过集成门后才允许提高到现有 ROS 上限。
- 输入命令超过 200ms 未刷新时发布零速度。
- DimOS 停止、异常退出或 systemd 停止时连续发布零速度。
- 遥控优先级高于导航；遥控介入立即取消当前导航目标。
- 不将 `linear.y` 传给阿克曼底盘。
- 在接入真实底盘前，对所有控制 topic 做 dry-run 和 topic ownership 检查。

物理安全不由软件替代。每次实车测试都应有可触达的断电/急停方式、清空测试区域，并先从车轮离地或低速短指令开始。

## 8. 关键风险与处理顺序

| 优先级 | 风险 | 当前状态 | 处理方式 |
| --- | --- | --- | --- |
| P0 | 控制板串口被多个程序同时访问 | 已发现两个同名 ROS 控制节点和按键进程 | 完成单一所有权和串口仲裁后才允许运动 |
| P0 | 里程计为命令积分且无动态 `odom -> base_footprint` TF | 已确认 | `/odom_raw` 仅展示；下一阶段引入经实测的视觉/RGB-D/VIO 定位 |
| P0 | 相机 TF 与底盘 TF 断开 | 已确认 | 标定并发布 `camera_link0 -> depth_camera_link` |
| P0 | 可用磁盘仅约 4.4GB | 已确认 | 备份并清理到至少 25GB 可用后再安装 |
| P1 | 单线 LD19 不足以承担目标场景主建图定位 | 已确认并弃用 | 从 HE 服务、传感桥和验收中移除；需要近场障碍感知时使用 Aurora 或另行选型 |
| P1 | Aurora 深度当前有效像素分布异常 | 静态快照约 18.6% 非零且光心附近为空 | 下一阶段先检查安装遮挡、模式、标定和同步，再评估 RGB-D SLAM |
| P1 | 原始点云约 58MB/s | 已实测 | 本机处理，远程端只接收降采样地图和低频图像 |
| P1 | Rerun 可能累积历史帧 | 已在 M20 测试中出现 | HE 配置设硬上限、只看最新状态、禁用无界限流 |
| P2 | Wi-Fi 不稳定或 IP 改变 | 当前只使用 Wi-Fi | 优先有线；服务绑定所有接口，现场记录实际 IP |
| P2 | nvpmodel 配置与 6 核 SKU 不匹配 | 已观察到 CPU6/CPU7 警告 | 与实时部署分离，后续单独审计和修正 |

## 9. 验证清单

每次变更后至少记录：

- `df -h`、`free -h`、`tegrastats` 的启动前后数值。
- `ros2 node list`、`ros2 topic list -t`、关键 topic 的 `ros2 topic info -v` 和频率。
- `/dev/rrc`、`/dev/lidar` 的 udev 映射与占用进程。
- TF 中 `base_link`、`lidar_frame`、`depth_camera_link` 的连通性。
- HE 控制 topic 的发布者与订阅者数量。
- DimOS/Rerun 的端口、内存窗口、最新数据延迟和远程网络带宽。

## 10. 推荐执行顺序

1. 完成备份与磁盘释放。
2. 固化 HE ROS 硬件基线并修复重复控制节点。
3. 启动 Aurora 全模态桥，完成 RGB/depth/IR 内参、时间戳和相机外参检查。
4. 在 Orin 以最小依赖克隆并构建 WD DimOS。
5. 实现 `HEConnection` 和 `HEAckermannSafety`，通过遥控安全集成门。
6. 实现 `HESensorBridge`，通过本机数据和远程低带宽可视化集成门。
7. 完成本文档和静态回归后冻结当前部署；车辆落地再启动独立的视觉 SLAM/自动探索阶段。

当前阶段结束时 DimOS 仍只允许常驻读取 HE 数据，导航输出不得连接真实电机控制。

## 11. 2026-07-11 实际部署记录

### 11.1 当前安装状态

- 已完成备份和清理。备份根目录为 `/Users/markus/Backups/HE-OrinNX-2026-07-11`，状态文件为 `BACKUP-STATUS.md`；保留了 ROS 硬件工作区、Aurora 驱动、systemd 单元、udev 规则与软件包清单。
- 已从约 `4.4GB` 可用空间释放到当前约 `23GB`。这足以继续最小接入验证，但仍低于建议的 `25GB` 运行前余量；后续不要再安装仿真、模型或全量 extras。
- DimOS 工作区已安装在 `/home/ubuntu/he/dimos_wd_m20`，分支为 `feat/wd/m20`，独立环境为 `.venv`，当前约 `2.0GB`。
- 使用了核心 `pip install -e .`，未安装仿真、学习、感知模型等 extras。Rerun 启动所需的 `matplotlib` 已作为最小缺失依赖单独安装。
- 已实现并同步 HE 适配代码：`dimos/robot/he/connection.py`、`dimos/robot/he/sensors.py`、`dimos/robot/he/blueprints.py`；注册了 `he-sense-headless` 与 `he-teleop-headless`。
- LD19 已恢复在独立 `/home/ubuntu/he/ldlidar_ws` 中构建，源码为官方 `ldlidar_stl_ros2`，当前工作区约 `6.2MB`。
- 已启用 `he-ld19.service`、`he-camera-tf.service` 和 `he-dimos-sense.service`。三者均保留在 WD 基线的 `dimos/robot/he/deployment/` 中，便于重建。

当前只完成了“传感器读取和安全控制出口”的接入，不代表已具备可用的自主导航。`he-teleop-headless` 中的 `HEConnection` 固定为 `enabled=False`，因此不会创建 `/cmd_vel` 发布者。

### 11.2 已验证能力

1. `dimos list` 可发现 `he-sense-headless` 与 `he-teleop-headless`。
2. `he-sense-headless` 已作为 `he-dimos-sense.service` 持续运行。六秒 LCM 采样实际收到 `/imu` 95 条、`/odom` 97 条、`/lidar` 36 条；相应 ROS 基线约为 IMU 47Hz、odom 约 50Hz、LD19 10Hz。
3. Rerun gRPC 正在监听 `0.0.0.0:9877`；HE 传感器蓝图的 Rerun 内存限制设为 `256MB`，不启动本机 viewer。常驻服务运行两分钟以上无重启，DimOS cgroup 内存约 `560-610MB`。
4. `he-teleop-headless` 已作短时安全启动验证，`MovementManager`、`HEConnection`、`HESensorBridge`、Rerun bridge 和 websocket server 都能部署；运行期间 `/cmd_vel` 发布者数为 `0`。
5. Aurora 原始点云没有接入默认蓝图。`HESensorBridge.enable_camera_pointcloud` 默认为 `false`；显式启用后仍会限为 `1Hz`、每 8 点取 1 点，不能把原始 58MB/s 数据流直接转发到 Wi-Fi。
6. `/dev/rrc` 现在仅由 `odom-publisher.service` 内部的一个 `ros_robot_controller` 持有。独立重复的 `ros-robot-controller.service` 已禁用，Wi-Fi 按键服务已移除仅用于蜂鸣器的串口访问，保留 GPIO 按键与 Wi-Fi 复位功能。
7. `/scan` 由 `he-ld19.service` 唯一发布，frame 为 `lidar_frame`，量程 `0.02-25m`，驱动报告逆时针；`base_footprint -> lidar_frame` 与 `base_footprint -> depth_camera_link` 都已可查询。

### 11.3 Orin 上的正确启动方式

Orin 的登录 shell 是 `zsh`，不能直接 `source /opt/ros/humble/setup.bash`。该 ROS 脚本依赖 Bash 的 `BASH_SOURCE`；在 zsh 中会错误解析安装前缀，造成 `rclpy` 与 `ros2` 不可用。所有运行命令应使用 Bash：

```bash
ssh ubuntu@192.168.1.106
bash -lc 'source /opt/ros/humble/setup.bash
cd /home/ubuntu/he/dimos_wd_m20
.venv/bin/dimos run he-sense-headless'
```

仅当完成“集成门 A”的物理安全测试后，才允许把 `HEConnection.blueprint(enabled=False)` 改为显式启用。当前禁止把它改为 `true`。

### 11.4 本次遇到的问题与处理

| 问题 | 原因 | 已采取的处理 | 后续约束 |
| --- | --- | --- | --- |
| GitHub 克隆失败 | 旧 `http_proxy`/`https_proxy` 指向不可达的 `192.168.1.38:7890` | 在 VM 从 WD 分支制作 Git bundle，经 macOS 传入 Orin 后克隆 | 网络恢复前，Git 与 pip 命令均要清除代理环境变量 |
| 无法创建虚拟环境 | 系统缺少 `python3.10-venv` | 安装 `python3.10-venv` | 新机器部署先检查该包 |
| 新 venv 中没有 pip | 环境没有自动运行 ensurepip | 运行 `.venv/bin/python -m ensurepip --upgrade` | 写入自动化部署脚本 |
| pip 安装失败或卡住 | 继承了失效代理 | 使用 `env -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY` 执行 pip | 保留该前缀，直到代理被修复 |
| HE 蓝图导入失败 | 普通 Python tuple 被当作 Blueprint 调用 `.global_config()` | 使用 `autoconnect(...)` 构造 `he-sense-headless` | 新蓝图必须复用 DimOS 的组合 API |
| HE 模块部署失败 | WD 的 `Module` 构造器使用关键字配置，初版适配器沿用了旧的 dict 位置参数 | 两个适配器均改为 `__init__(self, **config_args)` 和 `super().__init__(**config_args)` | 接入新模块时先按 WD 现有 Module API 编写 |
| Rerun bridge 启动失败 | WD 的核心依赖没有包含运行时所需 `matplotlib` | 在 Orin venv 单独安装 `matplotlib` | 应将该依赖补入上游项目声明或部署 requirements |
| 后台测试不响应 SIGINT | DimOS 多进程 forkserver 在后台作业中未按预期退出 | 已用 SIGTERM 清理测试进程和端口 | systemd 服务应使用 `KillSignal=SIGTERM`、合理的 `TimeoutStopSec`，不要用后台 shell 管理 |
| 控制板串口竞争 | 独立控制服务、odom 启动链路和 Wi-Fi 按键服务都打开 `/dev/rrc` | 禁用独立 `ros-robot-controller.service`；按键服务移除 `Board()`/蜂鸣器调用；重启 odom 服务 | 仅 `odom-publisher.service` 允许拥有控制板串口 |
| LD19 包不可用 | 历史 `third_party_ws` 仅留下失效环境引用，驱动源码和二进制均已不存在 | 在独立 `~/he/ldlidar_ws` 恢复官方驱动并只构建该包；新增 `he-ld19.service` | 服务使用 `/dev/lidar`、230400、`lidar_frame`、`/scan`，不依赖旧工作区 |
| colcon 启动时读取错误 | 遗留 `~/.local` 中存在损坏的 setuptools 文件 | LD19 已构建成功；HE 新服务使用 `PYTHONNOUSERSITE=1` | 后续离线文件系统维护时再处理旧用户包，当前不要让其进入运行时 |
| IMU 初始无样本 | 串口争用结束后旧控制节点保持了无有效接收的状态 | 在唯一所有者条件下重启 `odom-publisher.service`，IMU 恢复约 47Hz | 控制服务变更后必须复验 IMU、电池和串口唯一性 |
| `.venv/bin/activate` 不存在 | 当前 venv 的激活脚本缺失，但解释器、包和 entry point 完整 | systemd 和验证命令直接调用 `.venv/bin/python`/`.venv/bin/dimos`，或显式设置 `VIRTUAL_ENV` 与 `PATH` | 不为补激活脚本重建正在工作的环境 |
| `odom -> base_footprint` TF 不存在 | 旧 `odom_publisher_node.py` 的 TransformBroadcaster 被注释，只发布 `/odom_raw` 消息 | 将 `/odom_raw` 明确标记为命令积分展示数据，未伪造静态 TF | 视觉 SLAM 通过实测前不得启动依赖动态 odom TF 的导航栈 |
| Aurora 深度无法支持当前 RGB-D 验证 | 静态帧仅约 18.6% 非零，光心附近 ROI 全零；原因可能是遮挡、双 ToF 模式、融合或标定 | 保留原始驱动，停止把深度数据用于方向/定位结论 | 下一阶段先检查相机安装、模式、标定和同步，再选 RGB-D SLAM |
| RF2O 诊断一直等待扫描 | 诊断命令未把 `init_pose_from_topic` 置空，节点等待不存在的 `/base_pose_ground_truth` | 清理全部测试进程/topic，并保留此前静止漂移结论 | RF2O 降级为历史参考，不再作为单线雷达主定位方案 |
| Orin 无法运行 `python -m pytest` | 轻量 venv 未安装开发测试框架 | 使用测试文件原生的 `python -m unittest -v dimos.robot.he.test_connection`，同样 6 项通过 | 不为静态验收安装 pytest 或全量开发 extras |
| 一键回归在最终门前看似停止 | 隔离测试进程退出后，DDS endpoint 注销存在短暂发现延迟；早期工具输出还只返回了长 SSH 命令的部分结果 | 编排脚本最多等待 10 秒并再次执行严格只读门；工具层持续轮询到真实退出码 | 不用固定长 sleep，也不放宽残留 topic 检查；必须看到 `STATIC_CLOSEOUT_RC=0` |
| 最终速度上限可被绕过 | `/he/final_cmd_vel` remap 到 `cmd_vel_callback`，而 0.10/0.30 限幅原先只在 `app_cmd_vel_callback` | 将限幅和 NaN/Inf 归零放入所有输入共用的最终回调；同步 ROS `src`/`build` 与仓库补丁 | 最终执行层必须独立于 HEConnection/手柄再次限幅，完整性门检查补丁已应用 |

### 11.5 常驻服务与复验

| 服务 | 职责 | 当前状态 |
| --- | --- | --- |
| `odom-publisher.service` | 唯一控制板所有者、现有阿克曼运动学、odom/IMU ROS topic | 已启用；不得同时启动独立控制服务 |
| `he-ld19.service` | LD19 到 `/scan`、`lidar_frame` | 已启用，单发布者约 10Hz |
| `he-camera-tf.service` | `camera_link0 -> depth_camera_link` 名义静态外参 | 已启用，TF 树已连通 |
| `he-dimos-sense.service` | `HESensorBridge`、受限 Rerun、LCM 数据输出 | 已启用，控制出口不在此服务中 |

常用检查：

```bash
systemctl status odom-publisher.service he-ld19.service he-camera-tf.service he-dimos-sense.service
ros2 topic hz /scan
ros2 topic hz /ros_robot_controller/imu_raw
ros2 topic info /cmd_vel -v
```

完整静态封板使用仓库内的一条命令：

```bash
cd /home/ubuntu/he/dimos_wd_m20
bash dimos/robot/he/deployment/verify-he-static-deployment.sh
```

该脚本不调用 `verify-he-lifted-control-gate.py`，不会发布真实底盘脉冲。它在前后
执行增强只读门，中间运行 `verify-he-deployment-integrity.sh`、蓝图发现、6 项
标准库单元测试、隔离 ROS 控制 dry-run 和实时传感质量门，并等待隔离 DDS
endpoint 清理。完整性门逐字节比较仓库与 live `/etc` 单元，反向检查三组 ROS
补丁处于已应用状态，并确认实际 `build/` Python 副本与 `src/` 一致。成功结束
必须同时输出
`HE static deployment closeout: PASS`、`Real motion: DISABLED` 和
`Visual SLAM/navigation/exploration: DEFERRED`。

### 11.6 尚未完成的集成门

- `camera_link0 -> depth_camera_link` 已按现有平台配置发布，但仍需要现场测量/标定复核，才能把 Aurora 点云用于建图。
- LD19 已验证协议、频率、frame 与软件方向；仍需要在车前放置已知障碍物，确认 `0` 度与车体正前方一致。
- `/odom_raw` 是命令积分且不发布动态 `odom -> base_footprint` TF，不能用于闭环
  定位、停车精度或 SLAM 里程计输入。
- 离地命令链、遥控覆盖、看门狗、mux 异常和服务停止已完成下游验证；现场人员
  仍需记录肉眼轮向、舵向、回中和断电/急停观察。`HEConnection.enabled` 继续
  保持 `false`。
- 车辆当前被抬起，无法验证真实平移、旋转、视觉尺度、轨迹误差或回环恢复。
- 尚未新增 `he-nav-headless`。视觉 SLAM、地图、自动探索、规划和低速闭环全部
  移到车辆落地后的下一阶段。

### 11.7 RF2O 激光里程计候选评估

为验证 LD19 是否能补齐可信定位缺口，已在独立工作区
`/home/ubuntu/he/rf2o_ws` 构建 `Adlink-ROS/rf2o_laser_odometry`，固定源码提交为
`313bb4c4123bcc0cc2e042f278312b19a3c46f31`。为适配当前 ROS 2 Humble 和
LD19，测试版本做了三项最小修改：补齐 `package.xml` format/运行依赖和
`nav_msgs`，将 LaserScan 订阅 QoS 改为与 LD19 的 reliable 发布兼容，并将
无初始位姿时的非法四元数 `w=0` 修正为 `w=1`。

补丁已保存为
`dimos/robot/he/deployment/rf2o-he-candidate.patch`。测试使用 `/scan` 输入、
`/odom_rf2o` 输出、`publish_tf=false`，计算频率约 10Hz，每帧约 32ms。静止测试
仍观察到厘米级位置漂移和航向噪声，因此它不是可信定位。后续复核还确认现有
`odom_publisher` 不发布动态 `odom -> base_footprint` TF；SLAM Toolbox 不能直接
建立所需 TF 链。一次 RF2O 诊断因没有把 `init_pose_from_topic` 设为空而一直等待
`/base_pose_ground_truth`，该次“零输出”不能用于评价算法精度。

RF2O 未注册 systemd 服务、未接入 DimOS 导航，测试进程和 `/odom_rf2o` 发布者
均已清理。结合单线雷达能力和用户确定的视觉主路线，本候选降级为历史参考，不再
作为当前 HE 建图定位主方案，也不在车辆抬起期间继续调参。

### 11.8 07:15 运行状态复验

- 必要服务 `odom-publisher`、`he-ld19`、`he-camera-tf`、`he-dimos-sense`、
  `aurora930` 均为 active，`NRestarts=0`；重复的
  `ros-robot-controller.service` 保持 disabled/inactive。
- `/dev/rrc` 仅由 PID 31573 的 `ros_robot_controller` 持有，`/dev/lidar`
  仅由 PID 28813 的 `he_ld19` 持有。
- `/cmd_vel` 为 0 个发布者、1 个订阅者；没有 DimOS 控制输出。
- LD19 `/scan` 单发布者约 10Hz，frame 为 `lidar_frame`，量程 0.02-25m；
  IMU 约 47Hz，frame 为 `imu_link`；`/odom_raw` 约 47-48Hz，但继续按开环命令
  积分处理。
- `he-dimos-sense` 已持续运行约 30 分钟且无重启，仅监听 `0.0.0.0:9877`；
  端口 7779/9878 未启动。Rerun 配置仍为 256MB，Aurora 原始点云关闭。
- 当前根分区约 23GB 可用；系统约 3.2-3.5GiB 已用、3.9GiB available、
  swap 约 588MiB。六核短时 CPU 约 13%-36%，GPU 0%，温度约 61-62C。
- 初次长跑中 `he-dimos-sense` cgroup 从约 698MB 缓慢升至约 757MB，增长来自
  Rerun 进程而不是 ROS 传感器进程。HE 蓝图随后启用了项目现有的
  `latest_only_entities`，覆盖 `world/lidar`、`world/odom`、`world/imu` 和
  `world/camera_pointcloud`，让实时查看器按最新状态显示；Rerun 服务端记录窗口
  继续限制为 256MB。
- `he-dimos-sense.service` 现增加 systemd cgroup 护栏：`MemoryHigh=1G`、
  `MemoryMax=1280M`。重启后五分钟的采样从约 556MiB 增至约 603MiB，最终只读
  验收约 609MiB、整机 available 约 3.9GiB，`NRestarts=0`。这段短时采样仍不能
  证明自然平台已经到达，但 1.25GiB cgroup 硬上限已经生效。256MB 是 Rerun 记录
  仓库上限，不是整个 DimOS 服务的 RSS 上限；cgroup 上限负责阻止整个服务异常
  拖垮 Orin。
- Aurora `/aurora/points2` 实测为 1 个驱动发布者、0 个订阅者。没有远程 viewer
  连接时，10 秒 Wi-Fi 采样约为 RX 0.008Mbps、TX 0.013Mbps，未出现原始点云
  跨 Wi-Fi 传输。

软件级安全测试已覆盖默认关闭、线/角速度限幅、去除横向速度、NaN/Inf 归零、
200ms 命令失效归零和退出三次零速，共 6 项通过。该结果不能替代物理急停、
车轮离地、遥控覆盖、客户端断连和服务停止的实车测试，因此
`HEConnection.enabled` 继续保持 `false`。

只读复验脚本已保存为
`dimos/robot/he/deployment/verify-he-readonly.sh`。它检查必要服务、重复控制服务、
两个串口的唯一所有者、`/cmd_vel` 零发布者、LD19 单发布者、Aurora 点云零订阅者、
RF2O 残留、9877 端口、服务内存和三类实时 ROS 样本。当前实机执行结果为
`HE read-only sensor gate: PASS` 和 `Motion gate: CLOSED`；该脚本不会发布任何
控制消息，也不能替代物理安全门。

### 11.9 隔离 ROS 控制干跑

为验证 `HEConnection` 的真实 ROS 发布行为，同时确保底盘不会收到命令，新增
`dimos/robot/he/deployment/verify-he-control-dry-run.py`。脚本带有硬保护：只允许
发布到 `/he_safety_test/cmd_vel`，如果测试 topic 被改成 `/cmd_vel`、不在
`/he_safety_test/` 命名空间，或真实 `/cmd_vel` 已经存在发布者，脚本立即失败。

Orin 实测结果：

- 测试前真实 `/cmd_vel` 为 0 个发布者、1 个底盘订阅者。
- 输入 `linear.x=0.50`、`linear.y=0.20`、`angular.z=-1.0` 后，隔离 topic 实际
  收到 `linear.x=0.10`、`linear.y=0`、`angular.z=-0.30`。
- 停止刷新 250ms 后实际收到零速度，覆盖 200ms 看门狗行为。
- 执行退出零速后，隔离 topic 最终收到零速度。
- 测试退出后 `/he_safety_test/cmd_vel` 不再存在，真实 `/cmd_vel` 仍为 0 个
  发布者，没有测试进程残留。

结合 6 项单元测试，软件层已经验证默认禁用、数值合法性、限幅、去除横向速度、
命令过期归零和退出归零。该干跑刻意没有连接真实底盘，因此不能证明控制板、
电机驱动或车辆在断连和异常时能够物理停车；集成门 A 仍需现场急停、抬轮、
遥控覆盖、客户端断连和停止服务测试。

### 11.10 当前验收状态

截至 07:41，远程只读验收再次通过：五个必要服务 active 且 `NRestarts=0`，
重复控制服务 disabled/inactive，两个串口各一个所有者，真实 `/cmd_vel` 为 0 个
发布者，Aurora 原始点云为 0 个订阅者，仅 9877 监听。`he-dimos-sense` 约
689MiB，低于 1GiB pressure 和 1.25GiB hard limit，整机约 3.8-3.9GiB
available。

当前部署任务先完成环境、静态传感和离地控制证据，再形成完整交付记录。车辆落地
前不再继续移动建图/定位测试。需要真实运动的 LD19 零度确认、相机外参、视觉
SLAM 轨迹、回环和自主探索均列入下一阶段；在此之前保持
`HEConnection.enabled=False`，不新增 `he-nav-headless`。

### 11.11 现场抬轮控制安全门测试

用户确认现场安全措施已完成且车辆已经可靠抬起后，开始真实底盘低速测试。常驻
`he-teleop-headless` 仍保持 `HEConnection.enabled=False`；所有非零命令仅由带
`--confirm-lifted` 保护的短时验证器产生，初始线速度限制为 0.03m/s。

首先修复了两项真实安全缺口：

- `HEConnection._publish_stop()` 原先连续三次零速没有间隔，在 ROS publisher
  depth=1 下可能合并。现改为按 20Hz 间隔发送三次零速，6 项安全单元测试通过。
- 原有 `AckermannChassis.set_velocity(..., reset_servo=True)` 没有使用
  `reset_servo`，零速只停电机、不回正前轮。修复后零速实际输出四电机 `rps=0`
  和舵机中位 `1500`。

抬轮脉冲通过 `HEConnection` 实际进入控制板链路，结果如下：

| 案例 | 关键下游结果 | 停止结果 |
| --- | --- | --- |
| forward 0.03m/s | motor2 `+0.1123rps`、motor4 `-0.1123rps` | 约 208ms 后连续五帧全零，舵机 1500 |
| reverse -0.03m/s | motor2 `-0.1123rps`、motor4 `+0.1123rps` | 约 208ms 后连续五帧全零，舵机 1500 |
| left 0.03m/s, 0.10rad/s | 舵机 1160，两侧后轮差速 | 约 208ms 后全零并连续回中 1500 |
| right 0.03m/s, -0.10rad/s | 舵机 1839，两侧后轮反向差速 | 约 208ms 后全零并连续回中 1500 |

两次早期脚本曾报告“最终电机仍非零”或“没有电机样本”，原因是探针没有等待
DDS endpoint 完成发现且没有持续 spin，读到了积压帧。修正为后台持续采集并要求
最后连续五帧零速后，四个案例全部通过。每次脚本退出后命令发布者均消失，并额外
发送最终零速。

#### 11.11.1 命令所有权收敛

检查发现原系统没有真正的遥控优先级：`/cmd_vel`、`/controller/cmd_vel` 和
`/app/cmd_vel` 都直接进入 `odom_publisher`，手柄还绕过运动学层直接发布转向
PWM。已升级为：

```text
HEConnection -> /he/nav_cmd_vel (priority 10, timeout 100ms) --┐
joystick     -> /controller/cmd_vel (priority 100, timeout 100ms) -- twist_mux
twist_mux    -> /he/final_cmd_vel -> odom_publisher -> motor/PWM
```

- 安装 `ros-humble-twist-mux 4.3.0` 和 `twist-mux-msgs 3.0.1`，总磁盘增量约
  2.7MB。
- 升级 `diagnostic_updater 4.0.6 -> 4.0.7`，解决新 twist_mux 所需
  `libdiagnostic_updater.so` 缺失。
- 旧三个直接输入已 remap 到禁用 topic；`odom_publisher` 只订阅
  `/he/final_cmd_vel`。
- 手柄的 `disable_servo_control=True` 现真正生效，PWM topic 从两个发布者收敛
  为唯一的 `odom_publisher`。
- 非零摇杆保持不动时会持续刷新手柄命令；摇杆回中只发送一次零速，避免高优先级
  零速永久压住导航。
- 最终出口统一限制为 0.10m/s、0.30rad/s，并增加独立 100ms 看门狗。mux 与
  最终 watchdog 均为 100ms，因此发布者或 mux 消失后的最坏级联上限约 200ms。

隔离和真实链路验证结果：

- 模拟手柄覆盖：导航 motor2 `+0.0749rps`，手柄覆盖后
  `-0.0562rps`，手柄超时后导航恢复；两路停止后 66ms 电机归零。
- 原始 Joy 完整链路：保持相同后退摇杆得到 20 个刷新样本；0.125m/s 输入被最终
  限制到 0.10m/s，Joy 发布者直接断开后 116ms 电机归零。
- twist_mux 进程 SIGKILL：最终出口 60ms 内归零。mux 自动重启，但旧导航
  publisher 没有自动恢复输出；这是安全的 fail-closed 行为，后续导航服务必须在
  mux 重启后显式重启/重新授权，不能自动续跑。
- `odom-publisher.service` 在运动命令期间停止后，服务变为 inactive，
  `/dev/rrc` 所有者释放；命令发布者结束后重新启动，串口恢复唯一所有者。

ROS Python 单包构建过程中还发现遗留的
`~/.local/lib/python3.10/site-packages/setuptools/config` 文件系统 I/O 错误。
使用 `PYTHONNOUSERSITE=1` 虽可构建，但会屏蔽用户目录中的 `colcon-ros` 扩展，
使 `controller/package.dsv` 丢失 Ament prefix hook。已恢复该 hook 并验证
`ros2 pkg prefix controller` 与服务启动。正式维护时仍应离线修复该损坏目录，
不要再用 `PYTHONNOUSERSITE=1` 构建 ament_python 包。

可复现文件已保存于 `dimos/robot/he/deployment/`：twist_mux 配置与服务、odom
systemd drop-in、controller 最终安全补丁、Ackermann 回中补丁、joystick mux
补丁及抬轮验证器。当前只读验收再次通过；HE 导航发布者为 0，常驻真实运动仍
关闭。现场仍需人工确认四个案例的肉眼轮向/转向与命令名称一致，才能把控制门从
“软件与下游 topic 通过”升级为“物理观察通过”。

### 11.12 现场安全复核后的完整重测

09:08，现场再次确认车辆已可靠抬起。测试前只读门通过，传感服务约 892MiB，
根分区剩余 23GB；`/he/nav_cmd_vel` 为 0 个发布者。为保证单一命令所有权，测试
期间临时停止 `joystick-control.service`，结束或异常时均由 shell trap 自动恢复。

前进、后退、左转均一次通过。右转首次因验证探针未发现 DDS 样本而失败关闭，
验证器退出时执行零速，手柄服务自动恢复；增加端点稳定等待后右转重试通过。
最终四项下游结果均符合预期：前进/后退电机符号相反，左转舵机 1160，右转舵机
1839；各案例末尾连续五帧电机为零、连续三帧舵机为 1500。右转重试的下游归零
时间为 210ms。

测试结束后的安全状态为：`odom-publisher`、`joystick-control`、`he-twist-mux`、
`he-dimos-sense` 全部 active，mux 与传感服务 `NRestarts=0`，导航输入仍为 0 个
发布者，最终出口保持唯一发布者。常驻 `HEConnection` 和导航蓝图仍未启用。

补充运行注意事项：Orin 上现有 `.venv` 能正常运行，但缺少
`.venv/bin/activate`。不要为了补一个激活脚本重建正在工作的环境；脚本和人工
命令应直接调用 `.venv/bin/python`、`.venv/bin/dimos`，或显式设置
`VIRTUAL_ENV=$PWD/.venv` 并把 `.venv/bin` 加到 `PATH`。最终只读复核再次通过，
VM 与 Orin 的 HE 源码聚合校验值一致。

### 11.13 静态传感质量复核与定位路线调整

新增只读验证器 `dimos/robot/he/deployment/verify-he-sensors.py`，不订阅 Aurora
原始点云、不发布运动命令。Orin 实测 30 帧 LD19：10.00Hz、每帧 508 bins、
有效点 91.1%、量程 0.02-25m；当时距离分布 p05 为 0.279m、中位 0.809m、
p95 为 3.528m。IMU frame 为 `imu_link`，`/odom_raw` 为
`odom -> base_footprint` 消息但明确标记为 `UNTRUSTED(command-integrated)`，
RGB CameraInfo 为 `rgb_camera_link`、640x400。脚本退出后节点消失，
`/aurora/points2` 恢复 0 个订阅者，`/he/nav_cmd_vel` 保持 0 个发布者。

TF 复核确认静态树包含 `base_footprint -> base_link -> lidar_frame/camera_link0`
以及 `camera_link0 -> depth_camera_link -> rgb_camera_link`。名义安装位置为相机
相对底盘前移 0.057m、高 0.120m，雷达前移 0.011m、高 0.164m；这些数值来自
现有 URDF/静态服务，尚不是现场实测标定。动态 `odom` frame 不存在，原因是现有
`odom_publisher_node.py` 的 TransformBroadcaster 被注释，仅发布命令积分的
`/odom_raw` 消息。

Aurora 深度图静态快照为 `mono16` 640x400，非零像素约 18.6%，有效值主要位于
图像上半部，光心附近 80x25 ROI 全零。该现象可能来自安装遮挡、双 ToF 布局、
融合模式或标定问题；未查清前不能直接用于 RGB-D SLAM，也不能用它证明 LD19
零度方向。Aurora 参数 `slam_mode=0` 在驱动中只是 mToF+sToF 数据模式，不会
发布 pose 或 odometry。

平台只有单线 LD19，用户决定后续以视觉 SLAM 为建图定位主路线。车辆当前抬起，
本轮停止 RF2O、SLAM Toolbox、DINOv3 和导航集成工作，先完成 DimOS 静态部署、
回归和文档交付。所有临时 RF2O 进程均已清理。

## 12. 下一阶段：视觉 SLAM 与 DimOS 自动探索

本节是下一阶段入口，不属于当前静态部署的完成条件。开始前必须让车辆安全落地，
确认相机安装、时钟和外参，并准备可人工接管的低速测试区域。

### 12.1 算法分层

视觉建图定位不应被简化为“安装一个 DINOv3”。建议按以下边界选型：

1. **几何前端**：从 RGB-D、单目/双目加 IMU 中估计连续相对运动、尺度和关键帧。
2. **后端优化**：执行局部 BA、位姿图优化、回环约束和地图持久化。
3. **学习特征（可选）**：DINOv3 或其他视觉基础特征用于特征匹配、地点识别、
   回环候选和重定位增强，不单独输出可信六自由度位姿。
4. **定位健康层**：输出跟踪状态、协方差/质量、丢失与重定位事件；质量不达标时
   必须阻断自动探索和运动命令。
5. **DimOS 适配层**：把可信 pose、地图和健康状态转换到 DimOS，不让 SLAM
   模块直接发布 PWM、电机或底盘速度。

### 12.2 候选评估方式

先评估成熟的 RGB-D/VIO/视觉 SLAM 引擎，再决定是否加入 DINOv3。候选至少覆盖：

- RGB-D SLAM：能利用 Aurora 深度提供尺度，但前提是修复当前深度有效区问题并
  完成 RGB-depth 标定与同步。
- 视觉惯性 SLAM：利用 RGB 和控制板 IMU，但必须验证 IMU 时间戳、轴向、噪声、
  相机-IMU 外参和硬件同步；仅有 topic 同时存在不等于可融合。
- 学习特征增强：在弱纹理、重复纹理和跨视角回环数据集上比较 DINOv3 与传统
  特征，只有精度收益覆盖 Orin 的算力、显存/内存和延迟成本时才部署。

不在 Orin 上直接试装多个重型框架。先在外部电脑用同一份 HE 数据离线比较，再把
一个候选裁剪后部署到 Orin。每个候选记录 ATE/RPE、静止漂移、回环成功率、跟踪
恢复时间、CPU、GPU、RAM、swap、温度和传感丢帧。

### 12.3 数据与测试顺序

1. 修复/解释 Aurora 深度有效区，测量 `base_link -> camera` 和 camera-IMU 外参。
2. 录制静止、直线、原地小角度转向、矩形、闭环、弱纹理和短时遮挡数据；同步
   保存 RGB、深度、IMU、LD19、控制命令和人工测量基准。
3. 外部电脑离线回放并选型，不连接底盘控制。
4. Orin 影子模式运行，只发布隔离的候选位姿和健康状态，不发布导航命令。
5. 人工遥控低速建图，比较闭环前后误差和重复路线重定位。
6. 通过定位门后接 DimOS 地图和自动探索空跑，仍断开 `HEConnection`。
7. 最后才在低风险区域启用低速自动探索，并保留遥控覆盖和定位失效停车。

### 12.4 DimOS 自动探索接入

目标链路为：

```text
Aurora RGB-D + IMU -> visual SLAM -> trusted pose/map + localization health
                                      |
                                      v
DimOS map adapter -> frontier/exploration -> path planner -> speed/control
                                      |
                                      v
MovementManager -> HEConnection -> twist_mux -> final watchdog -> chassis
```

自动探索必须订阅定位健康状态。出现跟踪丢失、时间戳异常、TF 跳变、地图重置或
资源超限时，先取消目标并输出零速，不能让规划器继续沿旧位姿运行。地图/探索与
控制之间保留模块边界，使视觉 SLAM、探索、规划和跟踪算法可以独立替换和回放。

## 13. 当前静态部署封板结果

截至 09:41，当前阶段要求的 DimOS 轻量环境、HE 硬件适配、静态传感和离地控制
安全链已经完成可重复回归。该结论不包含车辆落地运动、视觉 SLAM、地图、规划或
自动探索。

最终回归结果：

- `.venv/bin/dimos list` 可发现 `he-sense-headless` 和
  `he-teleop-headless`；HE Python 文件语法编译通过。
- `python -m unittest -v dimos.robot.he.test_connection` 的 6 项默认关闭、
  限幅、非有限值、命令新鲜度和退出三次零速测试全部通过。
- `verify-he-control-dry-run.py` 通过；只在 `/he_safety_test/cmd_vel` 发布，
  0.50/-1.0 输入被限制为 0.10/-0.30，超时和退出为零，真实 `/cmd_vel`
  始终为 0 个发布者。
- `verify-he-sensors.py` 再次通过：LD19 10.00Hz、507 bins、91.1% 有效点；
  IMU、CameraInfo 和开环 odom 的 frame/时间戳通过。
- `verify-he-readonly.sh` 通过；运动门关闭，`/he/nav_cmd_vel` 为 0 个发布者，
  `/he/final_cmd_vel` 为唯一发布/订阅链，Aurora 原始点云为 0 个订阅者。
- `odom-publisher`、`joystick-control`、`he-twist-mux`、`he-ld19`、
  `he-camera-tf`、`he-dimos-sense` 和 `aurora930` 均为 active/enabled，
  `NRestarts=0`。
- systemd 单元语法验证通过，近 15 分钟上述服务无 warning/error。系统自身
  `snapd`/NVIDIA 旧单元的兼容性提示与 HE 单元无关，没有据此修改系统服务。
- 仅 `0.0.0.0:9877` 在 HE 可视化端口集合中监听；未启动本机 viewer、RViz、
  仿真、SLAM、RTAB-Map、RF2O 或视觉模型。
- `he-dimos-sense` 约 892MiB，`MemoryHigh=1GiB`、`MemoryMax=1.25GiB`；
  整机约 3.6GiB available，swap 约 531MiB，根分区约 23GB 可用。
- 所有临时探针和隔离 topic 均已清理。增强后的 `verify-he-readonly.sh` 还会硬性
  检查七个服务 active/enabled/零重启、手柄/mux/odom/PWM 唯一所有权、内存硬限、
  端口以及无 GUI/SLAM/导航进程。VM 与 Orin 的 `dimos/robot/he` 聚合 SHA-256
  均为 `062e0e2b931148ddf4f4ff353a845ce5ed431dd24f6130f4982b3bc263b25cd7`。
- 一键静态封板脚本最终实机返回 `STATIC_CLOSEOUT_RC=0`。前置和最终只读门均
  通过，部署完整性检查通过，过程中未创建真实导航发布者。

封板后的运行策略：保持传感器服务和现有手柄安全链；保持常驻
`HEConnection.enabled=False`；不新增 `he-nav-headless`。下一次工作从第 12 节
视觉 SLAM 数据与选型阶段开始，而不是继续调单线雷达定位。

10:06 再次执行增强只读门和部署完整性门，结果均为 PASS，导航输入仍为 0 个
发布者。当前静态部署已无待办；整体任务阻塞在车辆落地、真实移动数据采集、相机
标定和视觉 SLAM 方案确认。现场条件改变并确认启动下一阶段前，不继续安装算法、
修改常驻服务或启用运动输出。

### 13.1 离地底盘命令特性

用户要求进一步摸清速度和前轮转向特性后，在车辆保持抬起条件下运行 83 次真实
ROS 命令链试验。详细记录位于
`dimos/robot/he/docs/chassis-characterization-2026-07-11.md`，原始 JSON 位于 Orin
`logs/he-chassis-characterization-20260711.json`。

核心结果：

- 速度输入覆盖正反向 0.001-0.15m/s；0.15m/s 在最终执行层限制为 0.10m/s。
- 转向输入覆盖 +/-0.02 至 +/-0.50rad/s；角速度限制为 +/-0.30rad/s，名义前轮
  转角限制为 +/-34 度，对应左/右 PWM 1122/1877。
- 上行到 `/he/final_cmd_vel` 中位 1.272ms，到 motor RPS 中位 2.897ms，到转向
  PWM 中位 3.802ms；显式零速到 motor 归零中位 2.959ms。
- 停止刷新但不显式发零时，motor 归零 112.772-150.913ms，中位 129.586ms；
  `twist_mux` 超时后静默，独立 odom watchdog 执行电机归零和转向回中。
- 83 次的 motor RPS、PWM 和开环 odom 命令数值误差为零，证明的是软件下发转换，
  不是物理轮速或实际前轮角度精度。

当前没有轮速编码器和前轮角度传感器，无法测量物理低速死区、轮速误差、舵机
机械到位时间、回差和负载下转角。现有链路也没有 acceleration/jerk 平滑，速度
变化以阶跃命令下发。要声称物理控制反馈闭环，必须增加编码器/转角反馈或外部
视觉测量，并完成车辆落地后的标定。

### 13.2 最小/最大可执行指令边界

在相同抬车安全条件下，追加 74 次专门的边界测试。测试覆盖正反速度的软件门槛、
最终限幅，以及左右转向的舵机门槛、PWM 整数量化、34 度饱和和最终角速度限幅。
原始记录位于 Orin
`logs/he-chassis-command-limits-20260711.json`，SHA-256 为
`7a96c21fad3527022ca23aa238ee3049d1e8ae6bebd114c1bb9b0166331dc5fe`。

速度指令边界：

- `|linear.x| < 1e-8m/s` 时，ROS 和命令积分 odom 仍保留该数值，但阿克曼层发布
  零电机 RPS。
- `|linear.x| = 1e-8m/s` 是正反方向首个产生非零电机 RPS 的软件指令，RPS
  幅值约 `3.7448e-8`。这不代表电机能克服静摩擦实际转动。
- `+/-0.10m/s` 是当前最大下游执行速度，对应直行驱动轮 RPS 幅值约
  `0.3744822`；`0.100001`、`0.15` 和 `0.50m/s` 输入均被限制到该值。

转向指令边界（测试线速度 `0.05m/s`）：

- `|angular.z| < 1e-8rad/s` 时舵机保持 PWM 1500。正向左转在
  `+1e-8rad/s` 首次输出 1499；负向右转因 `int()` 向零截断，直到约
  `-0.00045rad/s` 才首次输出 1501。这是软件量化不对称，不是已测得的机械死区。
- 0.00044/0.00045rad/s 测试将右转首个 PWM count 阈值夹在两者之间，理论值
  约 `0.00044358rad/s`。左侧极小正输入立即跳一个 count，后续应在具备转角反馈
  后改为显式 rounding 与对称、可标定死区。
- 34 度几何饱和在该线速度下对应约 `0.19047456rad/s`；实测 0.190 与
  0.191rad/s 两侧已确认 PWM 端点为左 1122、右 1877。继续增加角速度时前轮
  PWM 不再增加，但后轮差速仍会变化到角速度最终限幅。
- `+/-0.30rad/s` 是当前最大下游角速度；`0.300001` 和 `0.50rad/s` 输入均被
  限制到该值。零线速度下发送 `+/-0.30rad/s` 不支持原地打方向，结果是电机
  RPS 为零、舵机回中 1500。

因此当前可确认的是“软件/PWM 可执行范围”：速度 `[-0.10,+0.10]m/s`，角速度
`[-0.30,+0.30]rad/s`，前轮命令端点 PWM 1122/1877。车辆真实最小起步速度、
真实最大轮速、最小可重复转角、最大机械转角、到位延迟和回差仍无法由当前硬件
闭环测得；这些指标必须依赖轮速编码器、转角传感器或外部视觉测量，不能用
`/odom_raw` 或命令值替代。

### 13.3 Git 基线与 Aurora 全模态迁移

从本节开始，VM `/home/markus/work/dimos_wd_m20` 是 HE 唯一开发基线，所有
代码、部署单元、验证器和本方案均必须经过 Git commit 与 push。仓库采用标准
fork 工作流：

- `origin=git@github.com:T-Markus-Liang/dimos_m20.git`，用于推送；
- `upstream=git@github.com:MeloLong/dimos.git`，用于跟踪 WD M20 来源；
- 开发分支为 `codex/he-orin`；
- 轻量 clone 不持有私有 LFS 对象，推送使用
  `GIT_LFS_SKIP_PUSH=1 git push`，只推送源码和 LFS pointer。

第一份稳定 HE 基线已提交并推送，commit 为
`fcfb09c6369427e88398ff0ed0e468d52b005b6d`，包含此前通过验证的 HE 模块、
控制安全链、部署脚本、测试和文档。Aurora 迁移作为后续独立提交，不与该稳定点
混合，便于回滚和审查。

Aurora 迁移 commit 为 `968207d5633839d3f46db1934be33526b8cd1aef`。Orin
运行目录已在核对 `git write-tree` 与该远端 commit tree 完全一致后，切换为干净的
`codex/he-orin` checkout，并跟踪 `origin/codex/he-orin`。因此 VM 开发目录、GitHub
远端和 Orin 运行目录现在共享同一版本链，不再依赖无法审计的手工散落文件。

LD19 已从 HE 默认架构完全退出：`he-ld19.service` 停止、disable 后从 `/etc`
和仓库部署目录删除，`/scan` 不再存在，`HESensorBridge`、只读门和部署完整性门
均不再依赖 `/dev/lidar`。旧 LD19/RF2O 内容只保留为历史调查记录，不代表当前
运行架构。

Aurora 当前六路 ROS 输出全部默认进入 `HESensorBridge`：

原始帧率、桥接限流、资源代价和未来 SLAM 分流原则的集中参考位于
`dimos/robot/he/docs/aurora-sensor-rate-reference.md`。后续调整算法参数或优化
传感链前，必须先核对该文档，不能把当前 Rerun 频率误认为传感器硬件上限。

| ROS 输入 | 实测格式/频率 | DimOS 输出 | 默认桥接频率 |
| --- | --- | --- | ---: |
| `/aurora/rgb/image_raw` | BGR8 640x400，约 15Hz | `color_image` | 5Hz |
| `/aurora/depth/image_raw` | mono16 640x400，约 15Hz | `depth_image`，保留 uint16 | 5Hz |
| `/aurora/ir/image_raw` | mono8 640x400，约 15Hz | `ir_image` | 5Hz |
| `/aurora/points2` | 256,000 点，约 13-15Hz | `pointcloud` | 1Hz，stride 8 |
| `/aurora/rgb/camera_info` | `rgb_camera_link` | `camera_info` | 1Hz |
| `/aurora/ir/camera_info` | `depth_camera_link` | `depth_camera_info` | 1Hz |

桥接输出实测约为 RGB/深度/IR 各 4.4Hz、点云 1Hz、两路 CameraInfo 1Hz；IMU
和开环 odom 继续输入。Rerun 对这些实体使用 latest-only，recording window 保持
256MB。内部 LCM 吞吐约 7.3MB/s，但 10 秒 Wi-Fi 实测仅约 18.6KB TX，内部
multicast 没有把该带宽外发到无线网络。

当前限流只面向 DimOS/Rerun 可视化链。未来视觉 SLAM 如果需要 13-15Hz 原始数据，
应新增本机同步的全帧率算法路径，同时继续保留 5Hz 图像、1Hz 下采样点云的远程
可视化路径；不应通过把所有 Rerun 输出直接提高到 15Hz 来实现算法输入。

启用全模态后的 `he-dimos-sense` 两分钟内稳定在约 1008-1010MiB，`NRestarts=0`，
仍低于 `MemoryHigh=1GiB` 和 `MemoryMax=1.25GiB`，整机约 3.5GiB available。
余量明显小于旧传感配置，后续视觉 SLAM 接入前必须继续优化或拆分 Rerun/图像
处理内存，不能直接叠加重型模型。

最终一键静态封板通过：10 项 HE 单测、隔离控制 dry-run、Aurora 六路数据质量、
部署完整性和前后只读门全部 PASS；`/he/nav_cmd_vel` 保持 0 个发布者，真实运动
仍为 disabled。深度图有效像素比例本轮为 17.6%-17.7%，与此前异常一致，是
视觉 SLAM 阶段的首个待解决问题，不能因为六路数据已经接通就宣称 RGB-D 定位可用。

## 14. 视觉导航候选审计与数据准入（2026-07-11）

视觉导航阶段已启动，但仍保持真实控制断开。统一候选矩阵、官方来源、DimOS
内部分支审计和测试顺序集中记录在
`docs/he/visual-navigation-candidate-evaluation.md`，避免把排行榜、不同数据集和
HE 实测混为同一评分。

当前优先测试顺序是：

1. 先解决 Aurora 深度空间覆盖、RGB/depth/IR/point cloud/IMU 时间关系、内参、
   camera-to-base 和 camera-to-IMU 外参；
2. 第一可部署候选调整为 RTAB-Map 0.23.7 RGB-D；官方仓库已经提供与当前
   Ubuntu Jammy、ROS 2 Humble、arm64 匹配的二进制包；
3. Isaac ROS RGB-D 从 4.4 才出现，而 release-4 apt 仅提供 Noble/Jazzy，当前
   Jammy/Humble 可用的 release-3.2 没有 RGB-D。除非后续明确升级整套系统，
   不在当前 Orin 上强行安装或把 3.2 当作等价候选；
4. OpenVINS 仅在相机/IMU 同步通过后作为轻量 VIO 备选；DPVO 作为离线 learned
   comparator；DROID-SLAM 因官方要求至少 11GB GPU 内存不进入 NX 8GB 部署；
5. DINOv3 只能作为地点识别、回环或重定位增强，不能代替几何位姿估计。

仓库新增两项无运动工具：

- `diagnose-he-aurora.py`：有界采样并输出跨模态最近时间戳偏差、帧率、深度中心
  ROI、3x3 空间有效率和有效量程分位数；
- `record-he-visual-dataset.sh`：默认 10 秒，录制原始 RGB/depth/IR/point cloud、
  IMU、CameraInfo、TF、诊断和控制 topic，并生成 manifest 与 SHA-256。脚本拒绝
  在剩余空间低于 8GiB 时运行，也不会发布控制命令。

本阶段的静态录制可以在车辆抬起时进行。直线、转弯、矩形、大闭环、遮挡和
重定位数据必须等待新的车辆落地现场安全确认。任何候选在没有 HE 数据和 Orin
实测前都不能写入最终 ADR，也不能接入 `MovementManager` 或 `HEConnection`。

首轮修正后的传感诊断表明，IMU 相对 RGB 最近时间戳偏差中位数约 5.81ms、P95
约 10.29ms；相机流多数帧时间戳相同，但存在约一帧缺口，RGB-depth P95 达
68.35ms。驱动当前为 `align_mode=true`、`depth_correction=true`、
`rgbd_enable=false`。驱动文档说明开启 RGB-D 模式后 RGB、depth、IR 和点云来自
同一个 RGB-D frame，因此下一步要做隔离 A/B 测试，不能仅依赖当前时间戳相同帧。

同次测量的深度全局有效率约 20.51%，中心 40% 约 15.76%，下方三块仅约
4.9%-5.7%，不满足导航准入。JSON 证据和静态数据集索引保存在
`docs/he/evidence/`。静态 bag 实际 3.541s、280MiB、669 条消息，六路 Aurora
各 52 帧、IMU 171 帧，控制命令为 0 条；修复自包含 checksum 清单后所有文件
通过 SHA-256 校验，录制前后只读安全门均 PASS。

Aurora `rgbd_enable` 隔离 A/B 已完成。开启后全局深度有效率只从 20.75% 变为
21.01%，RGB-depth P95 仍约 65ms；点云从 14.49Hz 降到 12.20Hz，RGB-pointcloud
P95 从 51.45ms 恶化到 125.20ms。因此保持部署默认 `rgbd_enable=false`，算法侧
必须按 header 做显式配对并监控丢帧。临时 launch 不响应单次 SIGINT，清理后已
恢复原 systemd 服务；最终 sensor gate 和只读门 PASS，未修改持久配置。

## 15. RTAB-Map 视觉 SLAM shadow 集成（2026-07-11）

当前采用官方 ROS 2 Humble arm64 RTAB-Map 0.23.7 作为 HE 第一条可部署的
shadow baseline，但不代表真实导航获批。架构决策和替代方案记录于
`docs/he/adr-001-rtabmap-shadow-baseline.md`。

静态实测中 RGB-D odometry 为 6.31Hz，零 tracking loss，inliers 中位/最小
79/63，消息延迟中位/P95 约 108/137ms。odometry RSS 峰值约 214MiB，mapping
短测约 255MiB，CPU 约占一个核心 58%，GPU 为 0%。动态
`he_map -> he_visual_odom -> base_link` 已验证。

地图输出接口成立，但质量未通过：82x59、0.05m 的地图只有 2.52% cells known，
其中 free 21、occupied 101。`HELocalizationHealth` 默认要求至少 10% known，
因此返回 `map_known_ratio_low`；`HEVisualMapAdapter` 不会把该地图发布为规划器的
`global_costmap`。

新增 `he-visual-slam-shadow` 蓝图包含：

- `HERTABMapShadowRunner`：管理 native RTAB-Map 进程组并在退出时清理；
- `HEVisualSlamBridge`：转换 ROS odometry、occupancy、trajectory、TF 和 tracking；
- `HELocalizationHealth`：对时效、tracking、inliers、TF 跳变和地图覆盖 fail-closed；
- `HEVisualMapAdapter`：只有地图质量门通过时才输出 DimOS `global_costmap`；
- 256MB、latest-only Rerun shadow 可视化。

该蓝图没有 `MovementManager`、`HEConnection` 或速度输出。车辆真实移动、ATE/RPE、
回环、重定位、地图可通行性和自动探索仍等待新的车辆落地安全确认。

集成 shadow soak 的完整记录位于
`docs/he/evidence/2026-07-11_1448_dimos-shadow-soak.md`。运行时 RTAB-Map
进程组 RSS 约 493-533MiB，整机 available memory 约 3.33GiB，`/he/nav_cmd_vel`
持续为 0 个发布者。health 正确输出约 138ms odom latency，并以
`map_known_ratio_low` 保持 unhealthy。

测试发现不能在视觉 odom 每次归零的同时默认恢复旧 incremental database；该
组合触发了 RTAB-Map `Memory::addLink()` fatal。runner 已改为默认创建时间戳数据库、
最多保留 5 份、单实例锁、`wait -n` 子进程回收和 parent-death cleanup。现在模式
契约为 fail-closed：`mapping` 拒绝任何已存在的显式数据库；`localization` 必须指定
已存在、非空且可读的 `HE_RTABMAP_DB`，并强制
`Mem/IncrementalMemory=false`、`Mem/InitWMWithAllNodes=true`、
`Mem/LocalizationReadOnly=true` 和 `Mem/LocalizationDataSaved=false`。这只建立安全的
地图加载链路。启动前还会用 Python SQLite read-only URI 核对 `Admin/Data/Info/Node`
核心表，非 SQLite 或错误 schema 会在 RTAB-Map 启动前拒绝；静止同场景重载、异地
启动和移动重定位必须分别验证。

```bash
# 新建 mapping database，目标路径必须不存在
HE_RTABMAP_MODE=mapping HE_RTABMAP_DB=/var/tmp/he-rtabmap/he-map-new.db \
  .venv/bin/dimos run he-visual-slam-shadow --daemon

# 只读加载已有 map database
HE_RTABMAP_MODE=localization HE_RTABMAP_DB=/var/tmp/he-rtabmap/he-map.db \
  .venv/bin/dimos run he-visual-slam-shadow --daemon
```

首次 Orin 部署发现 ROS wrapper 将 `Mem/*` 算法参数声明为 string，而不是 ROS bool。
使用 `-p Mem/IncrementalMemory:=true` 会抛
`InvalidParameterTypeException` 并在创建地图前退出。runner 已改为传递显式 YAML
字符串标量（例如 `Mem/IncrementalMemory:='true'`）。原生 0.23.7 探针确认该形式被
解析为 RTAB-Map 字符串参数并正常进入 SLAM mode；失败尝试没有生成可复用数据库。

修正后的静止实测已完成 mapping -> localization-only 重载。mapping DB 最终为
659456 bytes、1 个 Node、SQLite integrity `ok`；localization 加载后输出相同的
83x60 occupancy、pose 和动态 TF，零 tracking loss，并恢复 saved map correction。
RTAB-Map 报告一次 good localization candidate。运行前、中、后数据库 size、mtime 和
SHA-256 `144b31d0...0cd7e7f` 完全不变，证明 read-only 生效。地图 known ratio 仍只有
2.851%，所以 planner map 继续被门禁阻断。完整证据见
`docs/he/evidence/2026-07-11_2237_static-map-reload.md`。

OccupancyGrid 是 latched/event-driven，静止时不重发不代表地图失效。因此 map age
默认作为诊断值，不直接阻断 health；需要该门时可显式设置 `max_map_age_s`。pose、
TF、tracking、inliers、latency、RSS 和地图质量仍为默认门禁。

受控终止 SLAM 子进程后，odometry 在 6 秒检查前已同步清理，health 报告
`slam_process_down`，无原生进程残留。后续时间戳审计纠正了停止超时归因：
`RerunBridgeModule` 约 73ms 已停止，真正超过 CLI 5 秒 grace period 的是 RTAB-Map
shell runner 对三个 zombie 子进程串行执行 `kill -0` 轮询，最坏约 7.5 秒才回收。
runner 已改为共享时间窗内并行 SIGINT -> SIGTERM -> SIGKILL，并最终统一 `wait`；
完整设计和待执行 Orin 复测见
`docs/he/evidence/2026-07-11_2128_shadow-graceful-shutdown.md`。

第一轮 Orin 普通 stop 实测仍在 7.099 秒升级 SIGKILL，证明 child cleanup 不是唯一
阻塞。新日志显示 coordinator 在 `RerunBridgeModule.stop()` RPC 等满 5 秒，但父进程
升级后 worker 本地仅约 1.2ms 就完成 Rerun stop；问题是 bridge 在视觉消息持续输入时
无法及时处理 stop RPC。`he-visual-slam-shadow` 因此调整生命周期顺序：Rerun 第一个
启动、最后一个停止；RTAB-Map runner 最后启动、最先停止。连接关系和五个无运动
模块不变，先切断生产者再关闭可视化。该顺序由测试锁定，仍需第二轮 Orin 普通 stop
实测确认。

第二轮按该顺序实测仍在 6.971 秒升级，日志也确认 runner 已第一个进入 stop，因此
顺序并非最后阻塞。core 审计发现 `RpcCall.stop()` 在 `call_nowait` 发出远端 stop 后，
同步关闭调用方自己的 RPC client；本地 LCM handler thread join 最长正好 5 秒。
也就是说 coordinator 卡在 caller backend 清理，不是 remote module stop。修复为 stop
消息仍同步发出，caller RPC backend 在具名 daemon thread 异步关闭并保留异常日志。
新增 core 测试让 cleanup 故意阻塞，验证 stop 调用 100ms 内返回、cleanup 已启动且
释放后线程退出；36 项相关 core 测试和 39 项 HE 测试通过，待第三轮 Orin 实测。

第三轮 Orin 普通 stop 已不再升级 SIGKILL：CLI 报告 `Stopped with SIGTERM`，耗时
4926ms，native 进程和 Rerun 端口均无残留。这证明 caller RPC backend 是此前的五秒
主阻塞，但日志仍出现 6 次 `can only join a child process`，所以该轮不能视为干净通过。
根因是 worker 在 `daemonize()` 双重 fork 前创建；daemon 继承
`multiprocessing.Process` 对象后已不是其父进程，不能调用 `Process.join()`。

修复保持原父进程使用 `multiprocessing.join()`，daemon/non-parent 改用已有 `psutil`
按 PID 等待；五秒优雅窗口和 SIGTERM/SIGKILL fallback 不变。run registry 同时把
zombie PID 视为已退出，避免残留状态误报。RPC cleanup thread 增加最多 100ms 的
有界 join，兼顾普通测试清理和繁忙 LCM backend 下的非阻塞 stop。49 项相关 core
测试、39 项 HE 测试、Ruff 和 diff 检查已在 VM 通过；最终 Orin 无异常日志普通 stop
复测仍待执行。

第四轮在 `7dae71b6` 上验证 non-parent assertion 已消失，视觉里程计正常输出且导航
发布者仍为 0，但普通 stop 用时 7111ms 并再次升级 SIGKILL。时间戳证明第一次完整
停机其实在约 2.45 秒内完成；随后 signal handler 在主进程退出前执行通用 tagged
process sweep。Python `resource_tracker` 会忽略 SIGTERM，通常要等父进程关闭 pipe
才退出，因此该 sweep 等满两秒；之后 `sys.exit()` 展开到 `ModuleCoordinator.loop()`
的 finally，又重复调用一次 coordinator stop。

修复移除 signal handler 中冗余的预退出 sweep；独立 watchdog 仍会在主 PID 消失后
执行同一清理，异常退出和孤儿进程保护不变。`ModuleCoordinator.stop()` 增加锁保护
的幂等状态，signal shutdown 与 loop finally 不会再重复停模块和 manager。50 项相关
core 测试、39 项 HE 测试及静态检查已在 VM 通过，待第五轮 Orin 普通 stop 实测。

第五轮在 `1d2dcf6a` 上已功能通过：CLI 报告 `Stopped with SIGTERM`，没有升级、异常
或残留，日志只有 5 个模块 stop 和 1 轮 worker manager shutdown；停止前视觉里程计
正常且导航发布者为 0。完整 CLI 命令耗时 5228ms，虽然 coordinator 本体约 2.52 秒
已完成。剩余可避免成本是 5 个模块各自最多等待 100ms caller cleanup，累计约 0.5 秒。

将该观察窗口缩短为 10ms，仍给立即完成的 cleanup 机会，同时保持繁忙 backend 下
真正的非阻塞语义；RPC 测试时限恢复为 100ms。50 项 core、39 项 HE 及静态检查在
VM 再次通过，待第六轮 Orin 时序复测确认低于 5 秒并保留全部清理结果。

第六轮在 `1aada0ac` 上最终通过。停止前 `/he/visual_odom` 正常输出，
`/he/nav_cmd_vel` 为 0 个发布者；CLI 报告 `Stopped with SIGTERM`，该结果按源码语义
证明主 PID 在发出信号后的 `50 x 100ms` 窗口内退出。外层 shell 计时 5500ms 还包含
Python CLI 冷启动和信号前 registry 查询，不应误作 signal-to-exit 时间。日志只有 5 个
模块 stop 和 1 轮 worker shutdown，没有 assertion、worker error、traceback 或 SIGKILL；
DimOS、RTAB-Map、watchdog、Rerun 进程及 7779/9877/9878 端口均无残留。

收尾已恢复 `he-dimos-sense`：服务 active、`NRestarts=0`，RGB/depth/IR/点云/IMU
实时质量门通过，本轮 depth valid 28.4%，独立只读门通过，导航发布者仍为 0。由此
优雅启停子任务关闭；车辆移动、ATE/RPE、回环和重定位门仍未开放。

新增只读 `benchmark-he-localization-health.py`，直接订阅 DimOS
`/localization_health` pLCM 通道，保存每个有界样本、reason 计数、pose/map/TF 最大
age 以及 `(healthy, reasons)` 状态转换。当前地图覆盖不足会让正常基线自带
`map_known_ratio_low`；传感失效测试必须验证新增 `pose_stale`/`tf_stale` 等原因，
以及输入恢复后这些新增原因消失，不能错误地要求整体 `healthy=true`。

```bash
.venv/bin/python dimos/robot/he/deployment/benchmark-he-localization-health.py \
  --duration 30 --output /tmp/he-localization-health.json
```

静止真实故障注入已验证完整 Aurora 输入中断。8 秒基线 135 个样本始终只有
`map_known_ratio_low`。Aurora inactive 后 0.459 秒新增 `pose_stale`，1.032 秒新增
`tf_stale`，5.031 秒后变为 `tf_unavailable`；服务 active 后 3.947 秒移除
`pose_stale`，3.994 秒完全恢复原基线。恢复后的独立 5 秒样本 84 条，仍只有原基线
原因。首次短帧率检查处于启动收敛期，额外等待后 RGB/IR 约 14.29Hz、depth
13.89Hz、有效深度 28.1%，点云正常。完整证据见
`docs/he/evidence/2026-07-11_2345_visual-input-outage.md`。

该结果关闭“完整相机输入消失”的 freshness 检测，但不关闭坏图像仍持续到达、单个
模态丢失或运动中 tracking loss；这些必须分别注入和验证。

## 16. 公开基准与视觉外参准入复核（2026-07-11）

公开数值基准已从官方论文补齐到
`docs/he/visual-navigation-candidate-evaluation.md`。结果按数据集、输入模态、轨迹
对齐方式和测试硬件分别记录，不生成跨数据集总排名。关键工程结论是：DPV-SLAM
在 RTX 3090 上可达到约 50 FPS/5GB，但仍缺少 metric scale、ROS 2、occupancy 和
aarch64 证据；MASt3R-SLAM 的官方约 14.6 FPS 来自 RTX 4090；DROID-SLAM 的
长序列后端和当前官方最低显存要求均超过 NX 8GB。论文精度不能替代 HE 实测。

同时完成了不涉及运动的实时 TF 审计。Aurora 驱动发布的
`depth_camera_link -> rgb_camera_link` 约 10mm 基线，来自设备内部标定；这是当前
唯一有设备标定来源的视觉外参。其余链路为：

- `base_link -> camera_link0 = [0.057373, 0.000079, 0.091864]m`，零旋转；
- `camera_link0 -> depth_camera_link` 为零平移和约 `[-90, 0, -90]deg` 轴向转换；
- `base_link -> imu_link = [0.040, -0.015, 0.050]m`，yaw 约 90deg；
- 组合后的 `imu_link -> depth_camera_link` 约为
  `[0.015, -0.017, 0.042]m`、RPY `[-90, 0, -180]deg`。

这些 camera-to-base 和 camera-to-IMU 数值只来自现有 Ackermann URDF 与静态
服务，没有现场尺寸复核、标定板求解或不确定度。`camera_link0 -> depth_camera_link`
使用零平移也不能证明光心与安装 frame 重合。控制板 IMU 的 orientation quaternion
为全零，只能把该 topic 当作 raw angular velocity/acceleration，不能当姿态真值。

因此 OpenVINS 或其他紧耦合 VIO 仍未通过准入；后续必须在车辆允许运动后完成
camera-IMU 空间/时间标定、IMU 轴向与噪声标定。RTAB-Map 可以继续作为受限 shadow
输出验证，但其 pose/map 不能批准给导航。完整审计证据位于
`docs/he/evidence/2026-07-11_1539_visual-benchmark-extrinsics-audit.md`。

同步后的静态封板首次在 live sensor gate 间歇报告 `RGB timestamp is stale`。
调查确认 Aurora 最新帧仍在发布，误报来自验证器收集期间保存全部 callback，却截取
最早 N 帧执行 freshness 检查；等待较慢点云或 DDS 发现时，最早 RGB 可能已经超过
2 秒。验证器已改为检查最后 N 帧。真实停流仍会因为“最新帧”过期而失败，不会
降低传感准入标准。

封板脚本原本还在传感验证后反复调用 `ros2 topic list` 和 `ros2 node list` 轮询临时
DDS endpoint；临时节点已退出时，该重复 ROS CLI 会话仍可能中断整个封板进程。
现改为等待 2 秒后直接执行权威 final read-only gate。最终门本身已检查测试 topic、
Aurora subscription count、导航进程、控制发布者和端口，因此删除重复轮询没有降低
准入标准。

只读门同时增加不吞错的 `ERR` 诊断，失败时输出具体行号和命令，便于区分安全条件
失败与 ROS CLI 生命周期问题；该诊断不会捕获错误或把失败改为通过。

最终确认此前“输出停在 cleanup/final gate”是 `systemd-run --pipe` 在 rclpy 退出后
丢失输出通道，并非封板 unit 失败。改用不带 pipe 的 transient user unit 执行原始
脚本，再独立查询 `he-static-final-1635.service`，结果为 `Result=success`、
`ExecMainCode=0`、`ExecMainStatus=0`。封板后传感服务 active、零重启、约 1005MiB，
工作区干净，`/he/nav_cmd_vel` 仍为 0 个发布者。

## 17. Aurora 深度空间覆盖诊断升级（2026-07-11）

Aurora930 0.2.11 驱动源码审计确认，公共参数表混合了 Aurora、Nebula 和 Stellar
产品参数。`slam_mode`、`mtof_crop_up/down`、mToF/sToF filter level、frequency
fusion、scatter threshold 和 `filter_type` 没有在 Aurora930 设备初始化路径调用，
即使能从 `/aurora/aurora` 参数服务器读到，也不会改变当前相机输出。Aurora930
实际应用的是 remove-filter threshold、深度上下限、alignment、depth correction、
laser mode、resolution mode 和 RGB-D stream selection。完整调用链证据见
`docs/he/evidence/2026-07-11_1644_aurora-depth-driver-audit.md`。

`diagnose-he-aurora.py` 已升级为有界空间和时间诊断：区分零值、非零低于下限、
有效、超过上限和 `65535`；输出逐行、逐列、bounding box、90% 稳定 mask、最大
稳定连通区域；同时比较 depth/IR 强度关系，并统计点云 finite/zero/usable XYZ。
这些指标用于判断当前约 20% 覆盖究竟是稳定设备 mask、滤波结果还是随机丢失，
不能把全局有效率轻微变化误判为导航可用。

新增聚焦测试后 HE unittest 从 29 项增加到 33 项，全部通过；Ruff 和
`git diff --check` 通过。代码同步到 Orin 后先采集默认基线，再只对 Aurora 真正
生效的参数做单变量、无运动 A/B。任何实验后都必须恢复 systemd 默认值并重新
通过 sensor/read-only gates。

为避免临时 launch 遗留子进程或异常退出后相机服务未恢复，新增
`run-he-aurora-depth-ab.sh`。脚本只接受 Aurora930 实际生效的单个参数覆盖，实验前
先通过只读门；停止 canonical systemd 服务后用独立进程组启动临时驱动；无论正常
或异常退出都清理完整进程组、恢复 `aurora930.service`，并重新执行 live sensor 和
read-only gates。每轮同时保存 Git HEAD、canonical 参数值和 test value sidecar，
不能用动态 `ros2 param set` 冒充设备 SDK 已重新配置。

脚本首次在 Orin 调用时，ROS 2 `setup.bash` 在 `set -u` 下读取未定义的
`AMENT_TRACE_SETUP_FILES` 并立即退出；退出发生在安装 restore trap 和停止
systemd 服务之前，因此没有改变相机状态。修复为只在 source ROS/Aurora 环境期间
临时关闭 nounset，加载完成后立即恢复。后续 Bash 脚本若启用 `set -u`，必须沿用
这一兼容方式，不能把环境脚本失败误判成相机或 SDK 故障。

首轮完整参数实验生成 JSON 并恢复服务后，立即执行的 read-only gate 曾看到临时
driver 的 DDS publisher 尚未过期，与 canonical publisher 短时并存；数秒后重复
权威门即通过。runner 因此在 canonical service active 后等待 5 秒再验证，不删除或
放宽 publisher-count 断言。同时修复 `restore_service()` 内部 `set +e` 泄漏到主流程
的问题，任何 sensor/read-only gate 失败现在都会保持非零退出，不能打印伪成功。

静态 A/B 完成后没有参数满足持久化条件。`threshold_size=30` 将全局/中心有效率从
同阶段基线 24.26%/18.57% 降到 21.84%/15.66%；室内 laser mode 2 与同 runner 的
自动 mode 1 对照仅差 0.17/0.05 个百分点；关闭 alignment 或 depth correction 均未
恢复下方稀疏区域。所有实验的非零低于范围、超过范围和 `65535` 比例均为零，点云
zero XYZ 与 depth zero 精确对应，说明当前无效编码为零值。

最终保留 threshold 110、laser auto、alignment/depth correction 开启、RGB-D 关闭、
150-4000mm 和 resolution mode 2。完整结果、比较边界和恢复证明见
`docs/he/evidence/2026-07-11_1831_aurora-depth-parameter-ab.md`。当前稳定 mask 最大
连通区域仍低于整图 8%，RGB-D 导航准入继续失败；下一步应转向安装遮挡/场景几何、
USB 拓扑和厂商固件/SDK 支持调查，而不是继续随机调公共 ROS 参数。

诊断工具新增显式 `--snapshot-dir`，仅在指定时保存最近 RGB、IR、原始 16-bit mm
depth、显示用 depth colormap、valid mask 和时间偏差元数据。默认运行仍不写图片，
不会变成无界 recording。该快照用于直接检查固定 mask 是否对应车体、支架、地面、
近距离盲区或场景无反射区域，不用 Web viewer 的采样画面替代原始证据。

原始快照检查显示 RGB/IR 视场完整，没有车体或支架遮挡下半画面；相机安装很低且
几乎水平，下半画面主要是深色光滑木地板。上半图 depth 有效率 48.69%，下半仅
7.51%，而下半 IR 平均亮度反而更高。深度在柜体、门窗、桌腿等垂直表面连续有效，
大面积零值沿地板与低入射角区域分布。因此当前证据更支持低安装高度、掠射角和地板
材质反射造成 ToF 失效，不支持固定 software crop 或支架遮挡。仍需用哑光标定板和
可控相机俯仰验证，不能仅凭室内单场景宣布相机硬件故障。

USB 审计确认 Aurora 位于 `1-2.4`，通过共享 480Mbps USB 2.0 hub；10Gbps root
当前没有设备。内核没有 reset/stall/overflow/bandwidth 错误，图像帧也完整，因此
USB 2 更可能影响点云吞吐而不是制造固定 mask。后续获得现场物理操作同意后，应把
Aurora 直连高速 root 并在固定场景做成对测试。隐私相关 RGB 原图不进入 Git，只在
Orin `/tmp` 和本机临时证据目录保留；仓库保存脱敏统计和文件 SHA-256。完整报告见
`docs/he/evidence/2026-07-11_1843_aurora-field-of-view-usb-audit.md`。

厂商 `Aurora 900 SDK Developer guide` V1.7（2025-03-04）复核确认，当前
150-4000mm 是 `FilterOutRangeDepthMap` 的可配置过滤窗口，不是厂商公布的硬件额定
量程；indoor/outdoor API 文档描述曝光/增益适配，也没有承诺提高深度覆盖。手册未给
Aurora930 的 FOV、反射率/距离精度、掠射角、环境光、USB 带宽或安装高度规格，不能
用来证明当前地板 mask“符合规格”。SDK 虽然有 `GetSupportInfo.depth_range`、edge
trim、温度和 laser current API，但 ROS 2 驱动没有调用/发布。完整证据见
`docs/he/evidence/2026-07-11_1848_aurora-sdk-guide-audit.md`；不得在缺少厂商依据时
增加猜测参数或修改 laser current/firmware。

## 18. RTAB-Map 长时静态资源与数据库边界（2026-07-11）

完整五模块 `he-visual-slam-shadow` 完成 600 秒静态 soak，全程没有
`MovementManager`、`HEConnection` 或速度发布者。整套 shadow RSS 约
1.82-1.84GiB，CPU 约 132-147% 单核，GPU 6-23%，最高温度 64.25C；available
memory 最低约 3.11GiB，swap 仅增加 3.75MiB，没有 OOM 或服务重启。

但测试确认原有“最多保留五个数据库”只限制跨运行文件数量，不限制当前数据库。
视觉 odom 在 90 秒内最终位置漂移只有 4.72mm、最大 8.25mm，却累计产生 0.480m
逐帧抖动。RTAB-Map 因而持续提交静止节点，数据库在 590 秒内从 16.7MiB 增长到
126.7MiB，约 11.2MiB/min；该行为不能部署到长期运行的 NX 8GB。

第一版曾将 RTAB-Map 的 `RGBD/LinearUpdate/AngularUpdate` 设为 0.02m/0.01rad，
Orin 实测 121 秒数据库已经达到 33.1MiB，未抑制增长。复核 0.23.7 源码后确认这两个
参数默认均为 0.1，且 rehearsal 发生在运动门之前；默认
`Mem/NotLinkedNodesKept=true` 仍会把未链接、被 rehearsal 合并或删除的节点写入库。
降低阈值反而增加了提交频率。

修正版显式恢复 `RGBD/LinearUpdate=0.1m`、`RGBD/AngularUpdate=0.1rad`，并设置
`Mem/NotLinkedNodesKept=false`。已链接地图节点和 RGB-D binary data 仍保留，只取消
从未进入图的 rehearsal/deleted node 持久化。第二层是独立 active-database
watchdog：默认 256MiB，每两秒检查一次，触限后让
runner 联动停止并回收 odometry 与 SLAM，不能继续无界写盘。可配置范围为：

- `HE_RTABMAP_MAX_DB_MIB=1..4096`，默认 256；
- `HE_RTABMAP_DB_POLL_SECONDS=1..60`，默认 2。

零值、非整数和越界值在启动前直接失败。watchdog 是故障停机边界，不是 rolling
database；不能在不保证图一致性时删除活动节点。完整基线、里程计和资源原始证据见
`docs/he/evidence/2026-07-11_2027_extended-shadow-soak.md`。修复部署后还必须完成
第二次同长度静态 soak，证明数据库增长被实质抑制后才能关闭该缺陷。

修正版完成 detached 600 秒复测。主采样覆盖 590 秒，active database 从
344,064 bytes 增至 1,458,176 bytes，净增约 1.06MiB，即约 0.108MiB/min；原基线
同窗口净增约 110.0MiB，下降约 99.0%。这证明静止 rehearsal 节点写库已被实质
抑制，但不是绝对零增长，因此 256MiB watchdog 仍必须保留。

复测期间整栈 RSS 平均/峰值约 1.73/1.77GiB，RTAB-Map RSS 平均/峰值约
481/509MiB；CPU 平均约 134%，GPU 平均/峰值约 11/26%，最高温度 63.28°C；
available memory 最低约 3.18GiB，swap 零增长。所有采样点
`/he/nav_cmd_vel` publishers=0。

测试编排还暴露两点：不能让高频 native log 长期绑定 SSH pipe，否则断开时可能产生
SIGPIPE 141；不能同时保留多个带 restore trap 的 soak timer，否则旧 timer 到期会
停止新 run。最终测试使用 Orin 本地 detached stdout/stderr 且只有一个 restore owner。
shutdown 后两个 native 进程均退出，传感服务 active/零重启；sensor verifier 的临时
DDS subscription 收敛后，独立 read-only gate PASS。原始修正版 TSV 见
`docs/he/evidence/2026-07-11_2105_bounded-shadow-*.tsv`。

## 19. IMU orientation 准入调查（2026-07-12）

控制板原始 `/ros_robot_controller/imu_raw` 约 47Hz，frame 为 `imu_link`，角速度和
线加速度有效，但 orientation quaternion 持续为 `[0, 0, 0, 0]`。RTAB-Map 0.23.7
源码会明确忽略这种 orientation，因此现有 RGB-D shadow 实际未使用 IMU。Orin 已有
`imu_filter_madgwick` 2.1.5，无需新增依赖。

一次不发布 TF、不使用磁力计且不改配置的隔离探针证明 Madgwick 能从 raw gyro/
acceleration 输出约 46.7Hz 的单位四元数，并保留角速度、加速度和 `imu_link`。但该
输出的 orientation covariance 为全零，不能解释为零不确定度；无磁力计时 yaw 依赖
陀螺积分，且现有 camera-to-IMU 外参仅是 nominal URDF 值，尚未物理标定。因此这只
证明滤波器可运行，不证明视觉惯性融合可信，也不批准紧耦合 VIO。

新增有界只读诊断：

```bash
.venv/bin/python dimos/robot/he/deployment/diagnose-he-imu.py \
  --duration 30 --output /tmp/he-imu-raw.json

.venv/bin/python dimos/robot/he/deployment/diagnose-he-imu.py \
  --duration 30 --filtered-topic /he/imu/orientation_probe \
  --output /tmp/he-imu-filtered.json
```

工具记录输入率、header 时间戳间隔、四元数范数、RPY/旋转漂移、gyro 与 acceleration
均值/标准差/模长以及 orientation covariance 状态。下一步先保存 30 秒静止 raw 与
filtered 对照；只有数值稳定且安全门保持关闭时，才允许把 Madgwick 作为可选的
RTAB-Map shadow orientation prior 做 A/B。任何 camera-IMU 紧耦合、移动精度或导航
放行仍必须等待物理空间/时间标定和新的车辆落地安全确认。

30 秒静止对照已完成。raw/filtered 实测速率均约 46.56Hz；raw 1269/1269 个
orientation 全为零，filtered 1394 个四元数全部归一化。但 filtered 最终/最大姿态
漂移为 1.207/1.218deg，yaw 变化 -1.187deg；静态 gyro x 均值约 0.03327rad/s，
acceleration 模长中位数 9.9910m/s2，filtered orientation covariance 1394/1394
全零。该结果没有通过 IMU prior 准入。

因此保持 RGB-D RTAB-Map shadow 配置不变，不设置 `wait_imu_to_init=true`，也不将
Madgwick 作为常驻子进程。下一步必须先完成 IMU bias/noise/axis、camera-to-IMU
空间外参和时间偏移标定，再重新做静止/移动 A/B。完整证据见
`docs/he/evidence/2026-07-12_0024_imu-qualification.md` 和同名 JSON。采样后的 live
sensor/read-only gates 均通过，两服务 active/零重启，导航发布者为零。

控制板驱动审计确认固件以 6 个 float 直接上传 ax/ay/az/gx/gy/gz；SDK 不做比例
换算，ROS 节点仅将 acceleration 从 g 转为 m/s2、gyro 从 deg/s 转为 rad/s。驱动没有
零偏、温漂、尺度或轴向标定，也没有发布传感器型号和量程元数据。因此静止 x 轴约
0.033rad/s 不是 ROS 单位漏转换，但还不能区分板载 IMU 固有偏置、温度影响或安装轴
问题。诊断现已增加 60 秒分段均值、多个 cluster duration 的 non-overlapping Allan
deviation 和静止 gyro 均值积分量；这些只量化一姿态时域稳定性，不会自动生成或应用
补偿。

10 分钟 Orin 静态基线已完成：27,918 条样本覆盖 598.022 秒 header 时间，均值
46.682Hz、无非递增 timestamp，并形成 9 个完整 60 秒窗口。gyro x/y/z 均值为
0.032530/-0.002002/-0.001835rad/s，60 秒窗口均值跨度仅
0.000479/0.000283/0.000199rad/s；x 轴均值约 1.864deg/s，若不补偿在本次 capture
内等效积分 1114.61deg。0.107/1.007/10.004/60.001 秒 cluster 的 x 轴
non-overlapping Allan deviation 分别约 0.000426/0.000195/0.000189/0.000184rad/s。
这证明偏置相对稳定但绝对量不可接受，当前 raw gyro 不准直接接入 VIO。

完整证据见 `docs/he/evidence/2026-07-12_0134_imu-static-stability.md` 和同名 JSON。
结束后 read-only gate 通过、服务 active/零重启、导航发布者为零。六面标定、物理轴向、
温度特性和 camera-to-IMU 空间/时间标定仍需现场操作；不得把本次单姿态均值直接写成
生产补偿参数。

## 20. Fresh visual fault 注入工具（2026-07-12）

为验证“图像 timestamp 持续更新但内容失效”的健康门，新增只向
`/he/fault/rgb/*` 和 `/he/fault/depth/*` 发布的有界代理。代理等待 RTAB-Map RGB 与
depth subscriber 后，依次执行正常透传、指定模态全零、恢复透传；不会发布到
canonical `/aurora/*`，不会发布任何 command topic。runner 默认输入完全不变，只有
显式设置 `HE_RTABMAP_RGB_TOPIC`、`HE_RTABMAP_DEPTH_TOPIC` 和
`HE_RTABMAP_CAMERA_INFO_TOPIC` 才会使用隔离输入，且非法 ROS topic 在启动前拒绝。

Orin 已完成 `blank-rgb` 和 `blank-depth` 三阶段实测。blank RGB 后 0.248 秒出现
`pose_stale`、0.694 秒出现 `tracking_lost/inliers_low`、0.853 秒出现 `tf_stale`；
恢复后 0.451 秒回到原有 `map_known_ratio_low` 基线。blank depth 没有新的
`OdomInfo.lost=true`，但 0.477 秒出现 `pose_stale`、1.012 秒出现 `tf_stale`，并在
恢复后 0.440 秒回到原基线。这证明 RGB 内容失效由 tracking/inlier + freshness
共同检测，depth 内容失效由 pose/TF freshness fail-closed 兜底，不能声称 depth 有
独立 tracking-loss reason。

两个测试的只读数据库 hash 均不变，结束后 live sensor/read-only gates 通过，服务
active/零重启、导航发布者为零。完整时间线、代理吞吐限制和原始 JSON 见
`docs/he/evidence/2026-07-12_0041_fresh-visual-faults.md`。静态 bad-but-fresh
RGB/depth 检查关闭；移动 tracking loss、CameraInfo 单独失效和动态场景仍未关闭。

代理已扩展并验证 `drop-camera-info`：RGB/depth payload 与 timestamp 全程透传，只在
fault 阶段停止隔离 RGB CameraInfo 发布。实测 fault 阶段 RGB/depth 各发布 43 帧，
RGB CameraInfo 收到 42 帧但发布 0，depth CameraInfo 收发各 42 帧。0.316 秒后出现
`pose_stale`、0.719 秒出现 `tf_stale`、4.771 秒变为 `tf_unavailable`；恢复
CameraInfo 后 0.244 秒回到原基线。该模式没有新的 tracking/inlier reason，证明
CameraInfo 同步缺失由 pose/TF freshness fail-closed 兜底。

数据库 hash 不变，最终 sensor/read-only gates 通过、服务零重启、导航发布者为零。
完整证据见 `docs/he/evidence/2026-07-12_0052_camera-info-fault.md`。静态
CameraInfo-only 缺口关闭；malformed-but-present calibration 和移动同步仍未关闭。

bridge 直接 CameraInfo 校验与 `corrupt-camera-info` 已完成 Orin 验证。校验覆盖
dimensions、frame、K/P 长度与有限性、正焦距、主点范围和齐次矩阵项，并在 health
输出 `camera_info_missing/invalid/stale`。零焦距 CameraInfo 持续发布时，
`camera_info_invalid` 0.363 秒触发，合法内参恢复后 0.009 秒消失、0.209 秒回到原
基线。新版 CameraInfo drop 约 0.946 秒触发 `camera_info_stale`，恢复后 0.103 秒
消失、0.327 秒回到基线。

数据库 hash 不变，最终 sensor/read-only gates 通过。完整证据见
`docs/he/evidence/2026-07-12_0107_camera-info-health-gate.md`。静态 missing 和结构性
malformed CameraInfo 已关闭；plausible-but-wrong 数值与物理外参仍需标定基线验证。

新增版本化运行内参基线：640x400、fx/fy 417.2417/418.1166、cx/cy
320.1967/191.8275；焦距允许 2% 相对偏差，主点允许 2px 偏差。该基线用于检测运行时
配置漂移，不代表物理标定已通过。`shift-camera-intrinsics` 已在 Orin 完成静态隔离
验证：fault 阶段保持 RGB/depth 有效并发布 31 条结构合法但焦距放大 10%、主点偏移
10px 的 RGB CameraInfo；`camera_info_invalid` 在 0.286 秒触发，恢复合法内参后
0.135 秒消失，并在 0.510 秒回到原 `map_known_ratio_low` 基线。随后约 1.030 秒出现
`tf_stale`、约 5.083 秒转为 `tf_unavailable`，说明直接内参门早于下游 TF freshness
兜底。只读数据库 SHA-256 全程不变，最终 sensor/read-only gates、服务零重启和零导航
发布者均通过。完整证据见
`docs/he/evidence/2026-07-12_0118_intrinsic-baseline-drift.md`。运行时超容差配置漂移已
关闭；标定板物理内参验证和 camera-to-base/camera-to-IMU 外参仍是准入门。

## 23. Aurora SDK 设备能力只读探针（2026-07-12）

厂商 SDK 1.1.22 的 `Aurora900` 正式声明了 `GetSupportInfo`、
`GetCameraTemperature`、`GetLaserCurrent`、`GetDeviceInfo`，通用 `Device` 还提供
`GetCameraParameters`。SDK Guide 明确 `GetSupportInfo.depth_range` 表示设备最小/最大
深度能力，`GetLaserCurrent` 单位为 mA；但 `depth_range` 在 ABI 中是不透明 `Data`
buffer，文档没有公布二进制编码，不能假设它等于当前 150-4000mm 软件过滤窗口。

新增 `probe-he-aurora-sdk.cc` 只调用设备枚举、Open、上述 getter 和 Close，不创建
stream、不调用 setter/reboot/upgrade。输出省略 serial number，保留 getter return
code、depth-range 长度/hex/可打印文本、三类 temperature raw value、laser current、
SDK/firmware 版本和设备内部 RGB/IR 标定。`run-he-aurora-sdk-probe.sh` 在停服务前完成
编译和 read-only gate，使用 EXIT trap 恢复 canonical Aurora service，并在结束后运行
live sensor/read-only gates。VM 已用真实 1.1.22 header 通过 `-Werror` 编译，runner
Bash syntax 通过。

首轮 Orin live probe 证明 `GetSupportInfo` 无需 stream/SetMode 即成功：设备返回 6 字节
ASCII `0.3~1m`（hex `30 2e 33 7e 31 6d`）、`running_7x24_hours=1`、
`synced_two_images=0`；三类 temperature raw value 为 camera/VCSEL/CPU
65/63/70，laser current 为 1450mA。该设备声明范围明显窄于 150-4000mm 软件过滤
窗口；同时既有 live baseline 的有效 depth p50/p95 为 1240/2522mm。两者语义未对齐，
因此 `0.3~1m` 只能记为设备自报 support field，150-4000mm 仍只是软件过滤窗口；在
厂商解释前，二者都不能单独当作硬件精度保证或算法裁剪边界。

同次调用中 `GetDeviceInfo/GetCameraParameters` 返回 `-1`，SDK stderr 明确要求先成功
调用 `Open + SetMode`。getter-only 探针不为此调用 SetMode；修复版对失败 getter 输出
`null`，不再序列化未初始化字段，并将含设备 serial 的 SDK stdout/stderr 限制在临时
文件且退出时删除。首轮最终 read-only gate 还观察到旧 DDS publisher 短暂残留，EXIT
trap 的下一轮 gate 已通过；恢复等待从 5 秒增至 10 秒。修复版 Orin rerun 待完成。

修复版 rerun 的结构化 JSON 已正确将两项失败 getter 及其字段输出为 `null`，临时 SDK
日志也在退出后清除；但固定 10 秒后仍可能观察到旧 DDS publisher，而 EXIT trap
稍后的完整 gate 再次通过。固定 sleep 因此改为最多 6 次、间隔 3 秒的完整 read-only
gate 有界重试；只有整套 gate 成功才结束，18 秒内仍不收敛则保留最后错误并失败。
第三次主路径已成功：pre-stop read-only、post-restore live sensor 和最终 read-only gate
均通过。最终 temperature raw 为 65/63/72、其他 support/laser 结果与前两次一致；
临时 SDK 日志和 binary 无残留，服务 active/零重启，导航发布者为零。完整证据见
`docs/he/evidence/2026-07-12_0213_aurora-sdk-support-probe.md` 和同名 JSON。

## 24. HE Sense 内存窗口优化（2026-07-12）

全模态 `he-dimos-sense` 当前 cgroup `MemoryCurrent` 约 1001MiB，已接近
`MemoryHigh=1GiB`。一次只读进程拆分显示，主要占用不是 `/dev/shm`，而是 Python
private anonymous memory：coordinator 约 128MiB、`HESensorBridge` worker 约 155MiB、
Rerun worker 约 559MiB，其中一个 anonymous mapping resident 约 420MiB；两个由
dedicated-worker capacity policy 保留的空闲 worker 各约 72MiB。

本阶段不修改全局 worker policy。该行为来自上游 dedicated worker 设计，贸然改变会
影响所有 DimOS 蓝图。先使用新增的只读 profiler 建立同口径证据：

```bash
sudo .venv/bin/python dimos/robot/he/deployment/profile-he-sense-memory.py \
  --service he-dimos-sense.service \
  --output /tmp/he-dimos-sense-memory.json
```

profiler 记录 systemd/cgroup-v2 内存、每个进程的 PSS/private dirty、fd/thread 数和最大
anonymous mappings；不重启服务、不读取传感器 payload，也不常驻。跨用户 system
service 受 procfs 权限保护时必须使用 `sudo`。A/B 测试用固定间隔重复执行同一快照，
避免测量工具本身长期占用资源。

第一项 scoped 优化只针对 `he_sense_headless`：先保存当前 Rerun `256MB` recording
window 的 10 分钟基线，再测试 `128MB`。必须保留八个 latest-only entity、Aurora
RGB/depth/IR/point cloud/CameraInfo、IMU 和 odom；不得同步修改 teleop 或 visual-SLAM
蓝图。只有 cgroup 内存实测明显下降、服务零重启、所有模态帧率和远程 Rerun 可用性
无回归、`/he/nav_cmd_vel` 仍为零发布者时才保留 128MB，否则恢复 256MB。

256MB canonical baseline 已在不重启既有服务的条件下完成 11 次快照，覆盖
2026-07-12 02:30:31 至 02:40:36 CST。cgroup `MemoryCurrent` 最小/中位/最大为
1047842816/1050038272/1055834112 bytes（999.3/1001.4/1006.9MiB）。Rerun worker
PSS 中位 595964928 bytes、private dirty 中位 570478592 bytes，最大 anonymous
mapping 中位 430915584 bytes；HESensorBridge worker PSS 中位 172328960 bytes。
`MemAvailable` 中位约 3.30GiB，swap used 起止不变，`NRestarts=0`。

后置 live gate 通过：RGB 15.62Hz、depth 10.10Hz/25.7% valid、IR 16.13Hz、点云
256000 点，RGB 与 IR/depth CameraInfo 均存在。`9877` 从 macOS 可连接，服务 active，
`/he/nav_cmd_vel` 为 0 个发布者。最终原始 profiler JSON 保存为
`docs/he/evidence/2026-07-12_0240_he-sense-memory-256mb.json`，SHA-256
`4257eed850bc64937d09a73c7d654062f0bea789b47fdf94abd53e3e6aae1d05`；完整 11 次
runtime 目录保留在 Orin
`/home/ubuntu/he/logs/he-memory-ab/20260712_023031_256mb`。

基于该基线，源码只将 `he_sense_headless` 改为 `128MB`；teleop 和 visual-SLAM
继续为 256MB。新增结构测试锁定蓝图仍只有 `HESensorBridge + RerunBridgeModule`、
八个 latest-only entity 和全部默认 Aurora modality。VM 上 53 项 HE unittest、Ruff、
blueprint registry 检查和 diff 检查通过。

128MB 候选已通过 Git 提交 `40c563a5` 部署，且只受控重启
`he-dimos-sense.service`。11 次快照覆盖 02:48:59 至 02:59:24 CST。cgroup 内存中位从
1001.395MiB 降到 870.500MiB，下降 130.895MiB（13.1%）；最大值从 1006.922MiB
降到 872.691MiB，使 `MemoryHigh` 下的最大值余量从 17.078MiB 增至 151.309MiB。
Rerun worker PSS 中位下降 178.117MiB，最大 anonymous mapping 中位下降
188.082MiB。HESensorBridge CPU 为 52.5%，与基线 51.6% 接近；两轮 swap 均零增长，
服务均零重启。

后置 60 点云样本诊断为 RGB/depth/IR/point cloud/IMU
14.599/14.286/14.925/13.333/46.820Hz，depth valid 中位 25.941%，两路 CameraInfo
存在。macOS 可连接 `9877`，最终独立只读门 PASS，`/he/nav_cmd_vel` 为零发布者。
因此保留 `he_sense_headless=128MB`；teleop、visual-SLAM 和全局 worker policy 保持
不变。完整 A/B 与边界见
`docs/he/evidence/2026-07-12_0302_he-sense-memory-ab.md`。

## 25. Shadow 资源健康 fail-closed 门（2026-07-12）

审计发现既有 `HELocalizationHealth` 只检查 RTAB-Map 进程组 RSS 是否超过 768MB，
但 `slam_runtime_status` 本身没有时效门；缺失或 NaN RSS 会通过默认 0 避开超限。
同时目标要求 shadow 后至少保留 1GiB available memory，且不能依赖持续 swap，原状态
并未携带这两项系统证据。

`HERTABMapShadowRunner` 现每秒随既有 runtime status 发布：

- `rss_mb`：native shadow 进程组 RSS；
- `system_available_mb`：`/proc/meminfo` 的 `MemAvailable`；
- `swap_used_mb`：扣除 `SwapFree` 和 `SwapCached` 后的系统 swap 使用量；
- `swap_growth_mb`：相对本次 runner 启动首个有效样本的非负增长。

默认 health 门为：runtime status 最长 2.5 秒、RSS 不超过 768MB、system available
不少于 1024MB、swap growth 不超过 64MB。缺字段、非有限值和负值均 fail-closed，
分别输出 `runtime_status_invalid/stale`、`slam_memory_invalid/high`、
`system_memory_invalid/low`、`swap_usage_invalid`、`swap_growth_invalid/high`。
`LocalizationHealth.details`
保留原始资源值，benchmark summary 新增最大 runtime status age。

该实现没有新增常驻模块或依赖，也没有改变 RTAB-Map、数据库、传感器或控制参数。
VM 上 visual-SLAM 24 项和全部 HE 56 项 unittest、Ruff、diff 检查通过。

Orin 静态验证使用真实 runner 字段，并仅通过配置把 available 门从 1GiB 临时提高到
8GiB。强制轮 184 个 health 样本全部包含 `system_memory_low`；恢复默认后 187 个样本
全部清除该 reason，只保留既有 `map_known_ratio_low`。两轮 RSS 约 434-435MB、available
约 3.29-3.30GiB、swap growth 为零、runtime age 最大约 1.08 秒，均普通 SIGTERM
停止且无残留。恢复 Sense 后 live sensor/read-only gate PASS，导航发布者为零。完整证据
见 `docs/he/evidence/2026-07-12_0325_slam-resource-health.md`。

本轮也确认当前 Coordinator RPC 是 host-global：常驻 `he-dimos-sense` 与完整 shadow
不能作为两个 DimOS coordinator 并发；第一次并发尝试在 RTAB-Map 和数据库启动前
fail-fast。验证流程必须停 Sense 并用 EXIT trap 恢复。目标中的“本机 full-rate SLAM +
sampled Aurora Rerun 两条路径同时常驻且独立限资源”仍是未关闭的架构门，不能用本轮
顺序运行结果代替并发验收。

## 26. 单 Coordinator 双路径 shadow（2026-07-12）

针对 host-global Coordinator 限制，采用最小 HE 局部修复，不修改 DimOS 全局 RPC：
`he_visual_slam_shadow` 直接加入 `HESensorBridge`。运行 shadow 时仍先停止独立 Sense
service，但同一个 shadow coordinator 内同时存在两条功能路径：

```text
Aurora raw ROS 13-15Hz -> native RTAB-Map odom/mapping

Aurora raw ROS -> HESensorBridge sampled outputs
               -> bounded latest-only Rerun
```

Rerun window 锁定 14 个 latest-only entity：原有 color/depth/IR/
pointcloud、两路 CameraInfo、odom、IMU，加 visual odom/map/path/status、localization
health 和受门禁的 global costmap。原始高带宽图像和点云仍不通过 Rerun 提升到全帧率；
SLAM 继续直接订阅本机原始 ROS。

蓝图仍无 `MovementManager`、`HEConnection`、follower 或速度输出。结构测试锁定
`HESensorBridge` 存在、14 个 entity 完整和 runner 保持最后启动。
VM 上 24 项 visual-SLAM、全部 56 项 HE unittest、Ruff、blueprint registry 和 diff
检查通过。

第一版 256MB、4 个 dedicated module 的 Orin 组合实测没有通过资源门。worker policy
把 4 个初始 worker 扩到 8 个；14 个 tagged process 的补充快照总 PSS 约 1.43GiB。
11 个系统样本的 available 最低仍约 2.56GiB，主循环 swap 增长约 24.25MiB，但相对
runner 启动到最终 health 采样累计增长 84.25MiB，超过 64MiB 门。251 个最终 health
样本全部正确包含 `swap_growth_high`；配置不能按“功能有数据”视为验收。

第一版 sampled 输出从开始到结束保持：图像约 3.7-4.0Hz、点云约 0.89Hz、两路
CameraInfo 约 0.96Hz、odom/IMU 约 16Hz。native SLAM 和 Rerun 同时工作，温度最高
66.375C，所有时间点 `/he/nav_cmd_vel` 为零，普通 SIGTERM 与 EXIT restore 均通过。
功能面成立，但资源失败优先级更高。

第二版只做两项证据驱动优化：`HERTABMapShadowRunner` 不再占专属 Python worker，
使 3 个 dedicated module 对应 6-worker policy；combined Rerun 使用 HE Sense 已完成
10 分钟 A/B 的 128MB window。runner 仍最后启动并保留 native process-group cleanup，
全局 worker policy 不变。结构测试锁定这两个条件，VM 56 项 HE 测试通过，随后按
同口径执行 Orin soak。

第二版同口径实测已通过：worker 日志确认总数为 6；11 个样本中 tagged process 始终
为 13，总 PSS 最小/中位/最大约 1.28/1.31/1.32GiB，available 最低约 2.85GiB，主循环
和 runner-relative swap growth 均为零，温度最高 66.75C。native process-group RSS
结束时约 430.81MB，runtime age 最大 1.083 秒，259 个 health 样本没有资源 reason。

八路 sampled 输出从开始到结束均存在：RGB 4.218->4.022Hz、depth
4.129->3.755Hz、IR 3.983->3.707Hz、点云 0.883->0.836Hz、两路 CameraInfo 约
0.97Hz、odom/IMU 约 16Hz。3 个样本短暂触发 `pose_stale`，最大 0.531 秒，随后自动
恢复；不放宽 0.5 秒门，留给更长和移动测试继续观察。所有系统样本导航发布者为零，
普通 SIGTERM、无残留、Sense 恢复、live sensor/read-only gate 和 macOS `9877` 连接
均通过。因此保留 6-worker/128MB 组合，完整证据见
`docs/he/evidence/2026-07-12_0411_dual-path-shadow-soak.md`。

## 27. Shadow systemd cgroup 隔离（2026-07-12）

双路径 shadow 的 10 分钟资源验收覆盖了受 tag 标记的 13 个进程，但此前仍依赖临时
shell 和 EXIT trap 停止 Sense、启动 shadow。为避免现场误并发两个 host-global DimOS
Coordinator，并让 systemd 对完整进程树执行硬资源边界，新增两个互斥运行模式：

- `he-dimos-sense.service`：默认 enabled/active 的常驻传感模式；
- `he-dimos-shadow.service`：没有 `[Install]` 的 static 服务，只允许显式切换；
- 两个 unit 通过双向 `Conflicts=` 保证不能同时运行；
- shadow 前台运行，`Restart=no`，避免失败后自动创建新的 mapping 数据库；
- shadow 整个 cgroup 使用 `MemoryHigh=2G`、`MemoryMax=2560M`、
  `OOMPolicy=stop` 和 `TasksMax=512`。

部署后只使用受控入口：

```bash
sudo dimos/robot/he/deployment/switch-he-dimos-mode.sh shadow
sudo dimos/robot/he/deployment/switch-he-dimos-mode.sh status
sudo dimos/robot/he/deployment/switch-he-dimos-mode.sh sense
```

切到 shadow 前先执行常规只读门。shadow active 后，专用门核对 Sense inactive、shadow
static/零重启、`/he/nav_cmd_vel` 零发布者、无运动/GUI/仿真进程、native RTAB-Map
进程存在、9877 为唯一 DimOS 监听端口、cgroup memory 未触及硬上限，以及 localization
health 中没有 stale/invalid/resource failure。任一步失败都会停止 shadow 并恢复 Sense。
恢复 Sense 时再次执行常规只读门。脚本不提供 `--force` 路径。

这项变更只建立服务级隔离和故障恢复，不改变已验收的 6-worker/128MB shadow 参数，
也不开放控制链。安装后的 Orin 实测还必须确认 systemd 属性、生效 cgroup、无 OOM/
重启/swap 增长、普通 SIGTERM 清理和 Sense 恢复，才能关闭本节部署门。

`systemctl is-active` 只代表主进程已经进入 running，不代表 DimOS worker 和 ROS 订阅
已经完成注册。首次从 shadow 切回 Sense 时，立即执行只读门曾在 Aurora topic 的
`dimos_he_sensors` 订阅检查上短暂失败，数秒后同一门通过。切换脚本因此对 Sense 和
shadow 使用相同的有限 readiness 重试：最多 6 次、间隔 5 秒；每次仍执行完整原门，
不放宽 topic、资源或运动条件，超时仍视为失败。

修复后的 Orin 服务级验收通过。10 分钟内 11 个 cgroup 样本的 memory
min/median/max 为 1346.7/1359.0/1366.7MiB，349 tasks 恒定，available 最低
3011.9MiB，swap 为 558MiB 零增长，`memory.events` high/max/oom/oom_kill、服务
重启和导航发布者全部为零，最高温度 66.187C。末端 shadow 门通过，修复后的完整
`Sense -> shadow -> Sense` 往返也通过；普通停止后没有 native 残留，最终 Sense
enabled/active、shadow static/inactive。短往返中的 runner-relative swap 增长约
44MiB，低于 64MiB 门，保留为更长运行观察项。完整证据见
`docs/he/evidence/2026-07-12_0448_shadow-systemd-cgroup.md`。

## 28. 有界长时间视觉同步诊断（2026-07-12）

既有 `diagnose-he-aurora.py` 为了计算深度时域稳定性，会保留采集到的 RGB、depth、IR
和 point-cloud message，适合短采样，不适合几分钟以上的同步观测。新增
`diagnose-he-visual-timing.py` 只保存五路输入的 source timestamp 和 ROS callback
receipt timestamp，不保留 payload；默认每路最多 200000 个样本，持续时间限制为
10-3600 秒，因此不会随相机字节流形成无界内存。

输出分别记录 RGB、depth、IR、point cloud 和 IMU 的中位周期帧率、全窗口有效帧率、
interval median/P95/max、时间戳回退与重复、按中位周期估计的缺帧数/比例、callback age，
以及以 RGB 为参考的最近时间戳偏差。开始和结束都检查 `/he/nav_cmd_vel` 零发布者。
该工具用于关闭长时软件时间同步证据缺口，不代表硬件同步，也不能替代车辆落地后的
同步 rosbag、ATE/RPE、回环或重定位验证。VM 上 59 项 HE unittest、Ruff、blueprint
registry 和 diff 检查通过；Orin 长时结果仍待部署实测。

首轮 10 分钟实测暴露出只报告中位周期会掩盖间歇性整帧缺失：多数相邻帧仍是
68-75ms，但有效样本总数明显更低。工具因此补充 source/receipt span rate 和估计
missing ratio，并使用实际 monotonic 运行时长。该修复不改变订阅或 payload 行为；
需要用更新版本执行 Sense 并发与隔离单订阅者 A/B 后再给出同步准入结论。

同场景相邻 120 秒 A/B 已证明 HESensorBridge 是部分负载来源。Sense 并发时
depth/point-cloud span rate 为 13.13/9.65Hz、missing ratio 为 10.8%/34.0%；停止
Sense 后改善到 14.47/12.35Hz 和 1.6%/16.1%。但隔离点云仍缺失约 16%，USB2/驱动
风险没有关闭。

两线程 Python executor 候选没有通过：depth/point-cloud missing ratio 进一步恶化到
14.6%/37.1%，span rate 降到 12.57/9.22Hz，点云对 RGB 的 alignment P95 从 79ms
恶化到 124ms。候选回退到单线程。下一软件优化必须在 Python 反序列化前进行 native/
driver 侧预限频，同时保留默认 point-cloud surface；不能通过降低验收阈值或隐藏模态
解决。完整 10 分钟、订阅负载 A/B 和候选结果见
`docs/he/evidence/2026-07-12_0525_visual-timing-and-executor-ab.md`。
