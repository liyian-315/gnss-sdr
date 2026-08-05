# 17 GPS L5 Dual-Path Receiver v1 产品化记录

## 1. 基线与状态

- 产品分支：`product/l5-dualpath-receiver-v1`
- 研究基线分支：`research/multipath-correlator-fit`
- 基线 SHA：`5271ccb8d21ccaf53bbfdfaf0b3c89ecb541b5c0`
- 分支创建时间：`2026-08-05 10:05:53 +08:00`
- GNSS-SDR 版本：`0.0.21.git-<branch>-<sha>`
- 本地审计环境：Windows / CMake 3.20.3（只做源码审计和轻量测试）
- 目标构建环境：NUC / Ubuntu 18.04 / conda `gnsssdr` / GNU Radio 3.10 /
  UHD 4.7 / USRP B210；构建目录 `build-conda/`
- 当前产品状态：`IN DEVELOPMENT`，不是 release candidate。

## 2. v1 冻结范围

产品名称：**GPS L5 Dual-Path Receiver v1**。

v1 只处理捕获相关面中已经存在明显分离峰的同 PRN 双源：

1. 捕获最强峰和可信第二峰；
2. 用两条标准 tracking 链持续跟踪；
3. C++ 实时输出两路伪距、CN0、多普勒、距离差及质量状态；
4. 第二路失锁后独立重捕，不重启主路；
5. 默认关闭原始 IQ、acquisition、tracking、dense correlator 和 observables
   大体量 dump；
6. 产品运行不依赖 Python。

v1 明确不处理：亚码片/0.5-chip 分离、阵列、运动超相关、三路以上、
第二径进入 PVT、研究 Python 拟合器实时 C++ 移植。

## 3. 改动前 C++ 信号链审计

### 3.1 现有链路

`pcps_acquisition::find_second_peak()` 在主峰同 Doppler bin 的延迟窗口内找
第二峰。`update_synchro()` 根据 `Signal_Path` 把主峰或第二峰的粗码相位/
Doppler 写入 `Gnss_Synchro`。每个 Channel 有独立 FSM、acquisition、tracking
和 telemetry。Hybrid Observables 计算伪距后输出 `DUALPATH_OBS` 和
`DUALPATH_PAIR`。RTKLIB PVT 只消费 `Signal_Path == 0`。

### 3.2 已实现能力

- `Signal_Path=0/1` 两条固定身份通道；
- 第二峰同 Doppler、排除主峰主瓣、延迟窗和相对 CFAR 门；
- path1 普通失锁事件只重启自己的 acquisition，代码路径不重启 path0；
- observables 可输出 path、伪距、CN0和 Doppler；
- PVT 不使用 path1；
- dump 和 monitor 均可关闭。

### 3.3 产品风险

1. `update_synchro()` 在判断 acquisition 成败前执行。没有第二峰时它会把
   主峰写入 path1 的同步结构；普通分支随后拒绝 tracking，但 bit-transition
   分支没有第二峰专用成功门，仍存在回退主峰的风险。
2. 第二峰门只有主峰排除、最大延迟和门限比例，缺少最小延迟、局部噪声
   突出度、功率比和窗口边界拒绝。
3. 当前 `DUALPATH_PAIR` 仅核对 PRN/path/瞬时 valid，未同时检查 system、
   signal和接收时间。
4. stdout 是瞬时有效快照，没有持久状态、重捕计数、滚动中位数/MAD或
   Doppler一致性。
5. 尚无冻结的静态产品配置、C++低频CSV、长跑检查和发布包。

## 4. 分阶段修改与验收

### Commit 1：范围冻结

- 本文、总索引和决策日志记录基线与边界。
- 验收：分支来源可追溯，研究历史不改写。

### Commit 2：禁止 path1 回退主峰

- path1 只有通过第二峰专用门才允许正捕获和更新 tracking 初值；
- bit-transition 与普通分支语义一致；
- 单源测试证明 path0 可捕获、path1 不进入主峰 tracking。

### Commit 3：质量状态机

- 新增可单测的双路径配对/质量管理器；
- 键为 system/signal/PRN；
- 状态至少包含 `SEARCHING/CANDIDATE/RELIABLE/DEGRADED/`
  `NO_SECOND_SOURCE/LOST`；
- 固定窗口中位数和 MAD；重捕后重新进入 `CANDIDATE`。

### Commit 4：稳定输出

- 保留 `DUALPATH_OBS`/`DUALPATH_PAIR` 兼容输出；
- 新增版本化 `DUALPATH_STATUS version=1` 和可选 C++ CSV；
- 配对检查 system/signal/PRN/时间；无第二径时输出 `N/A`，不伪造数值；
- 默认每秒一次，间隔可配置。

### Commit 5：回归与静态配置

- 单源、同伪距、弱第二峰、边界峰、低 CN0、Doppler差、距离突变、失锁/
  重捕、状态转换和格式测试；
- 新增 B210 10/20 Msps、文件回放和单源负对照静态配置；
- 所有研究型大 dump 默认关闭。

### Commit 6：产品包

- 产品中英文说明、限制、变更记录、构建/运行检查、VERSION；
- 生成含二进制、配置、许可证、build-info、ldd、Git SHA和校验和的 tar.gz；
- 没有 NUC/B210 实测时最多标记 `CODE COMPLETE` 或 `OFFLINE VALIDATED`。

## 5. 验证状态表

| 层级 | 当前状态 |
|---|---|
| 已实现 | 研究原型 Top-2、双通道、observables 输出、path0-only PVT |
| 单元测试 | 产品测试尚未增加 |
| 文件回放 | 已有研究记录，产品门禁尚未执行 |
| 实时 B210 | 研究原型曾运行；本产品分支尚未验证 |
| 已知失败 | 近距融合峰、现场噪声化第二峰、亚码片 |
| 后续版本 | 空间阵列、运动轨迹、第二径定位融合 |

## 6. 实施进度

### 2026-08-05 / Commit 2：禁止 path1 回退主峰

- 新增 `select_acquisition_path()` 纯策略函数，明确主径与第二径的接受语义；
- path1 必须同时满足主峰有效和第二峰有效，缺少第二峰时清空 acquisition 初值并继续搜索；
- path1 不再通过主峰的 bit-transition 或 two-step 捷径进入 tracking；
- path0 的既有捕获行为保持不变；
- 新增四组单元测试，覆盖主径成功、第二径缺失、第二径成功和主峰无效；
- WSL 全量链接生成 `build-wsl-codex/src/main/gnss-sdr`，`--version` 正常；
- 独立 C++ 断言冒烟测试通过。GNU Radio/gtest 完整测试和 NUC/B210 行为测试尚未执行，不能据此标记硬件验收通过。

### 2026-08-05 / 第二峰质量门禁

- 新增最小/最大延迟、局部峰噪比、主次峰最大功率比和搜索窗边界保护配置；
- 第二峰仍需通过原有相对 CFAR 门限，所有门禁为逻辑与关系；
- 局部噪声采用同 Doppler、有效延迟搜索区间内功率中位数；
- acquisition 日志与可选 MAT dump 增加上述诊断量；
- 库级新增门限默认保持旧行为，产品配置必须显式给出经离线数据校准的数值，禁止把暂定值写成已验证阈值。
- 独立门禁断言测试通过；WSL/CMake Release 主程序完整重编译并链接通过。尚未执行历史 IQ 文件回放，因此产品阈值仍处于待标定状态。

-- Codex (GPT-5), 2026-08-05
