# 18 · GPS L5 Dual-Path Receiver v1 独立产品审查

> 审查对象：`product/l5-dualpath-receiver-v1`（Codex 提交）
> 审查人：Claude（独立审查，未参与本产品分支开发）
> 审查日期：2026-08-08
> 结论：**BLOCK_RELEASE**

---

## 1. 审查分支与提交

| 项 | 值 |
|---|---|
| 审查分支 | `review/l5-dualpath-receiver-v1` |
| 产品提交 SHA | `6eedc51aa4f706190e7f589945fa89c7e13c470f` |
| 研究基线 SHA | `5271ccb8d21ccaf53bbfdfaf0b3c89ecb541b5c0`（`research/multipath-correlator-fit`）|
| 区间 | `5271ccb8d..6eedc51aa`，7 commits，39 files，`+2002 / -79` |

⚠️ **任务书事实更正**：任务书把 `5271ccb8d21ccaf53bbfdfaf0b3c89ecb541b5c0` 写成"Codex 产品提交"，
但该 SHA 实际是**研究基线** `research/multipath-correlator-fit` 的 HEAD。真正的产品提交是
`6eedc51aa`。本审查按真实区间 `5271ccb8d..6eedc51aa` 执行。审查分支已存在且指向产品 HEAD，
未做 detach 重建。

**无关改动检查：通过。** diff 文件清单中没有阵列（`16`）、Track B（`13`/`14`/`15`）、
Python 拟合器或 dense correlator 实验改动泄漏。改动集中在 acquisition 第二峰门禁、
observables 配对状态机、产品配置/文档/打包四块。

产品分支提交序列：

```
d5fe6aecc product: freeze v1 scope and branch baseline
81a98020c fix: prevent path1 fallback to primary peak
88a50fb4f feat: add configurable second peak quality gates
876a33aed feat: add dual-path quality state machine
1cc3cff1b feat: add versioned dual-path status output
96339c3b3 test: add single-source and dual-source regressions
6eedc51aa package: add L5 dual-path release bundle
```

---

## 2. 阅读的文件

**dev_notes**：`README.md`、`05_pitfalls_and_decisions_log.md`、`07_stage2_dual_tracking_prototype.md`、
`08_field_triage_runbook.md`、`17_l5_dualpath_productization.md`（`11`/`12` 按索引与摘要核对，
未逐行读——它们与本产品分支无代码交集）。

**产品文档**：`product/l5_dualpath/README_CN.md`、`README_EN.md`、`KNOWN_LIMITATIONS.md`、
`CHANGELOG.md`、`VERSION`、`tests/README.md`、`tests/replay_manifest.example.csv`。

**C++**：`pcps_acquisition.cc/.h`、`acq_conf.cc/.h`、`acquisition_path_selector.h`、
`second_peak_gate.h`、`hybrid_observables_gs.cc/.h`、`hybrid_observables.cc`、
`dual_path_pair_manager.cc/.h`、`dual_path_status_formatter.cc/.h`、`obs_conf.h`、
两处 `CMakeLists.txt`、`tests/test_main.cc` 与 4 个新单测。

**配置/脚本/包**：4 个产品 conf、`build_release.sh`、`check_runtime.sh`、`check_status_log.sh`、
`dist/l5-dualpath-v1.0.0-code-complete-x86_64/` 全部内容。

---

## 3. 执行的测试（含未执行项，如实记录）

### 3.1 已执行

| # | 内容 | 结果 |
|---|---|---|
| 1 | Git 区间/无关改动核对 | PASS，无阵列/Track B 泄漏 |
| 2 | 产品宣传边界逐条核对（§4） | PASS |
| 3 | path1 回退主峰的代码路径穷举（§5.1） | 主峰回退已修复 |
| 4 | 配对键与时间对齐审查 | 键含 system/signal/PRN + 时间窗，合格 |
| 5 | 状态机全分支走查 + 反例构造 | 发现 BLOCKING-1 |
| 6 | 线程/状态生命周期审查 | 无静态全局、无需 mutex，合格 |
| 7 | 采样率/samples-per-chip 量化推导 | 发现 MAJOR-4 |
| 8 | 输出字段/locale/N-A 语义核对 | 发现 MAJOR-10 |
| 9 | 发布包解包、文件清单、元数据核对 | 发现 BLOCKING-3 |
| 10 | tar.gz SHA256 手工比对 | 摘要一致 `cf2c1e21…`；但 `.sha256` 不可用（BLOCKING-3）|
| 11 | 包内敏感物扫描（原始 IQ / 构建缓存 / 密钥 / 个人路径）| PASS，未发现 |
| 12 | 全仓 grep 确认 UHD/B210 路径是否打印 `overflow` | **不打印** → MAJOR-9 |
| 13 | 新增 2 个单元测试（多 PRN 不交叉配对 + 总失联缺陷规格） | 已提交 |

### 3.2 **未执行**（本次环境不具备，必须在 NUC 上补做）

本次审查在 Windows 工作副本上进行，会话期间无可用 C++ 工具链，且无 Linux 运行环境、
无回放 IQ、无 B210。以下项目**一律未执行**，不得视为通过：

| 任务书要求 | 状态 |
|---|---|
| 单源负对照 | **未执行**（且当前配置无法执行，见 BLOCKING-2）|
| 已知长距离双源回放 | 未执行 |
| 约 200–220 m 双源回放 | 未执行 |
| 已知近距离失败条件 | 未执行 |
| path1 中途关闭 / 重新打开 | 未执行（仅单测级别覆盖）|
| 多 PRN 配对 | 已加单测，**未在真实流图上执行** |
| 30 分钟无 overflow 长跑 | 未执行 |
| 产品包解压后最小启动测试 | 未执行（Linux ELF，无法在本机运行）|
| `run_tests` / `check` 目标编译运行 | 未执行（Codex 也未执行，见 MAJOR-8）|

**因此本产品目前不存在任何可引用的产品级验证证据。**

---

## 4. 产品范围审查：**通过**

这是本次提交最扎实的一块。逐条核对结果：

**只声称了允许的内容** —— GPS L5、同 PRN 双源、要求相关峰已可分、两路持续跟踪、
实时输出伪距/CN0/多普勒/距离差、可靠性状态、单 B210 单接收通道、
`PVT 只消费 Signal_Path=0`。`README_CN.md:3` / `README_EN.md:3` 状态标注为
`CODE COMPLETE，尚未完成正式文件回放和实时 B210 产品验收`。

**没有越界宣传** —— 全仓检索 `README_CN/EN`、`KNOWN_LIMITATIONS`、`CHANGELOG`、`17`：
无亚码片/0.5 chip 声称（`KNOWN_LIMITATIONS.md:3` 显式否认）、无阵列测向、
无"单天线静态亚码片已解决"、无 Python EKF 实时移植、无第二径参与定位
（`KNOWN_LIMITATIONS.md:6` 显式否认）、无"任意距离都能分开"
（`KNOWN_LIMITATIONS.md:12` 显式拒绝给出最小可分距离）。
`build_release.sh:44` 把 `validation=CODE COMPLETE; realtime B210 validation pending`
写进包内 `build-info.txt`，`README_CN.md:59` 明确"在实时 B210 验收完成前不生成 `v1.0.0-rc1`"。

**无 BLOCKING 级越界宣传。** 唯一的文档缺口见 MAJOR-7（path 身份未写清），属必须补充，
不属虚假宣传。

---

## 5. BLOCKING 问题

### BLOCKING-1 · 总失联后 `RELIABLE` 会带着失联前的数据复活

**位置**：`src/algorithms/observables/libs/dual_path_pair_manager.cc:109-251`

`update()` 用当前历元的观测构造 `std::map<DualPathKey, CurrentPair> current`，
然后**只遍历 `current` 里出现的 key**。当某 PRN 的 path0 和 path1 在同一历元同时消失时，
`d_records[key]` 根本不会被访问，于是 `state`、`consecutive_good`、
`deltas_m/primary_cn0/second_cn0/doppler` 全部滑窗、`pair_start_time_s` 全部**冻结**。

失联结束后第一个成对历元：

- `record.state` 仍是 `RELIABLE`，不等于 `LOST` → `dual_path_pair_manager.cc:161` 的重捕分支**不触发**；
- `record.has_seen_second` 为真 → `:171` 的首次分支也**不触发**；
- `record.consecutive_good++` 从失联前的值继续累加 → 立刻 `>= reliable_confirmations`；
- MAD 由**失联前的旧窗口**计算 → 轻易通过。

结果：**失联后第一个历元就直接输出 `state=RELIABLE`**，且
`valid_count` 是失联前的满窗、`track_age_s` 把整段失联时间算进跟踪时长、
`reacquisition_count` 保持 0（重捕从未被计数）。

**为什么这不是边角情况**：`hybrid_observables_gs.cc:288-292` 和 `:305-309`，
PVT 时钟修正与 `reset TOW` 命令会对**所有通道**调用
`d_gnss_synchro_history->clear(n)`。此后若干历元里 `interp_trk_obs()` 全部失败，
`epoch_data[n]` 被置空（`PRN=0`），而 `report_dual_path_observables()`
（`hybrid_observables_gs.cc:330`）对 `PRN == 0` 直接 `continue` —— 即**每次 PVT 时钟修正，
每颗星都会整体消失若干历元**。这是常规运行行为，不是异常。USRP overflow 突发、
深衰落、天线断开同样会造成两路同时消失。

**影响**：产品的核心承诺字段（`state` / `valid_count` / `track_age_s` / `reacquisition_count`）
在正常运行中会系统性说谎。任务书 §四.4「可靠状态是否真的有意义」与
§五「窗口是否会混入重捕获前旧值」在此处同时失守。

**已加测试**：`dual_path_pair_manager_test.cc` 中
`DualPathPairManager.DISABLED_TotalOutageMustNotRepublishStaleReliable`
（当前代码下必然失败，故先以 `DISABLED_` 提交，作为修复规格，修好后去掉前缀）。

**精确修改要求**（退回 Codex）：

1. `update()` 增加对**本历元缺席**记录的处理：或对 `d_records` 中未出现的 key 走一次
   "无观测" tick（等价于 `primary_valid=false, second_valid=false`），或引入
   `last_seen_rx_time_s` 并在 `rx_time_s` 间隔超过 `lost_confirmations * observable_interval` 时
   强制进入 `LOST`；
2. 进入 `LOST` 时清空全部滑窗、`consecutive_good=0`、重置 `pair_start_time_s`；
3. 恢复后必须重新走满 `reliable_confirmations` 才允许 `RELIABLE`，且
   `reacquisition_count` 必须自增；
4. 补一条断言：`window_samples >= reliable_confirmations` 是 `RELIABLE` 的必要条件。

---

### BLOCKING-2 · 出厂"单源负对照"配置无法测试它命名的失效模式

**位置**：`product/l5_dualpath/conf/l5_singlepath_negative_control.conf`

该文件头两行写着 `This must never produce a sustained RELIABLE second path`，但它：

- `Channels_L5.count=1`、`Channels_L5.signal_paths=1`、只有 `Channel0.signal_path=0`
  → **根本不存在 path1 通道**；
- `Acquisition_L5.multipath_detection=false` → **第二峰检测整体关闭**。

也就是说它在结构上不可能产生第二径，`NO_SECOND_SOURCE` 是**恒真的**，测不出任何东西。
真正需要的负对照是：**用完整双路径配置（2 通道、path0+path1、`multipath_detection=true`、
产品门限）去跑单源信号**，看 path1 会不会假捕获、会不会被判 `RELIABLE`。

更糟的是，该文件**省略了全部 `Observables.dual_path_*` 质量门限**，于是回落到库默认值
（`obs_conf.h:41-49`）：`min_primary_cn0=0`、`min_second_cn0=0`、
`max_doppler_difference=1e6`、`max_delta_jump=1e6`、`max_delta_mad=1e6`、
`min_abs_delta=1.0 m`。这是**可能的最宽松门限组合**——即使把它改成双通道，
它也会是最容易产生假 `RELIABLE` 的配置，而不是对照。

**影响**：任务书 §十「单源负对照和失锁测试必须通过」在当前交付物下**无法被执行**。
`tests/README.md` Layer 2/3 把单源负对照列为必做，但出厂配置不支持。

**精确修改要求**：

1. 把该文件改成 `Channels_L5.count=2` / `signal_paths=2` / `Channel1.signal_path=1` /
   `multipath_detection=true`，并**逐字复制** 20 Msps 产品配置的全部
   `Acquisition_L5.multipath_*` 与 `Observables.dual_path_*` 数值；
2. 文件头改写为"用产品门限跑单源，期望 path1 永不进入 `CANDIDATE` 以上状态"；
3. `check_status_log.sh` 增加判据：单源日志中 `state_RELIABLE` 与 `state_CANDIDATE`
   必须为 0，否则退出非零；
4. 若确实还需要一个"机制关闭"的对照，另起文件名（如 `l5_singlepath_baseline.conf`），
   不要占用 negative-control 这个名字。

---

### BLOCKING-3 · 发布包不能在项目文档规定的目标机上运行，且校验步骤失效

**位置**：`dist/l5-dualpath-v1.0.0-code-complete-x86_64/`、
`product/l5_dualpath/scripts/build_release.sh`

包内 `build-info.txt` 显示：

```
host=Linux lya-Y7000 6.18.33.2-microsoft-standard-WSL2 ... x86_64
compiler=c++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0
uhd=UHD 4.6.0.0+ds1-5.1ubuntu0.24.04.1
gnuradio=3.10.9
```

即**在开发笔记本的 WSL2 Ubuntu 24.04 上构建**。而 `dev_notes/README.md §0` 与 `06`
规定的目标机是 **NUC / Ubuntu 18.04 / conda `gnsssdr` / `build-conda/`**（另一台是
RK3588 / apt / `build/`）。`ldd-report.txt` 显示 100 个动态依赖全部指向
`/lib/x86_64-linux-gnu/`（glibc 2.39、boost 1.83、GR 3.10.9、UHD 4.6），
包内既无 `lib/` 也无 RPATH 打包，**在 Ubuntu 18.04 上不可能启动**。

同时：

1. **校验和文件不可用**：`build_release.sh:48` 执行
   `sha256sum "$archive" > "$archive.sha256"`，而 `$archive` 是绝对路径，
   于是 `.sha256` 内容是
   `cf2c1e21…  /mnt/d/work/project/usrp_gnss/…/dist/l5-dualpath-v1.0.0-code-complete-x86_64.tar.gz`。
   任何接收方执行 `sha256sum -c *.sha256` 都会 `FAILED open or read`。
   （我手工比对过，摘要本身正确：`cf2c1e218001aa8706dcbd63135ba2edde973b495492bcba33a2b2b3b0913a70`。）
2. **包内缺少依赖说明**：只有机器可读的 `ldd-report.txt`，没有任何"需要哪些运行时、
   怎么装"的人类可读说明。任务书 §六要求包内含"依赖说明"，未满足。
3. **包内 README 存在死链**：`README_CN.md:61` 链接 `tests/README.md`，
   但 `build_release.sh:30` 从未拷贝 `tests/`。

**未执行说明**：本次无 Linux 运行环境，`bin/gnss-sdr --version` 与最小回放启动测试
**均未执行**。上述结论基于 `build-info.txt` + `ldd-report.txt` + 项目文档规定的目标机做出的
静态判定。

**精确修改要求**：

1. 发布包必须在**目标机**（NUC conda `build-conda`，或 RK3588）上构建，`build-info.txt`
   增加 `target_machine=` 字段并与 `dev_notes/06` 对齐；混构建产物必须视为无效包。
2. `build_release.sh` 改为 `(cd "$dist_dir" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256")`，
   使校验和为相对路径。
3. 包内新增 `RUNTIME_REQUIREMENTS.md`（GNU Radio / UHD / boost / glibc 最低版本 + 安装命令），
   并在两个 README 顶部引用。
4. `build_release.sh` 拷贝 `tests/README.md` 与 `tests/replay_manifest.example.csv`，
   或删掉 README 中的链接。
5. 打包后新增自检：在**干净目录**解包 → `sha256sum -c` → `ldd | grep "not found"` →
   `bin/gnss-sdr --version` → `check_runtime.sh`，全部通过才产出 `dist/`。

---

## 6. MAJOR 问题

### MAJOR-1 · 第二峰门限往**危险方向**改动，且违背 `08` 的标定流程

`acq_conf.h:57` 库默认 `multipath_threshold_fraction = 0.3F`，产品配置改为 **0.12**
（`l5_dualpath_b210_20msps.conf:50` 等三处），**放宽 2.5 倍**。

`dev_notes/08` Step 2 是本项目对这个参数的权威标定流程，原文要求：
"上调 `multipath_threshold_fraction`（0.25→0.35→0.5）+ 收窄 `multipath_max_delay_chips`
（90→40）直到单路 `has2≈0`。**记下标定值。**"

同时 `multipath_max_delay_chips` 从默认 5.0 改为 **40.0**：20 Msps 下
`window = round(40 × 2) = 80` samples ≈ **±1199 m**。`dev_notes/05`（2026-07-18）明确记录
宽窗正是现场"第二峰随机游走（Δ 从 −2600 m 到 +2400 m）"的成因。

Step 2 从未执行（`tests/README.md` Layer 2 全部 pending）。
`KNOWN_LIMITATIONS.md:8` 确实标注了 provisional，这点是对的；但**参数移动方向**
与文档化的标定方向相反，且缺少强制的单源假警基线，使出厂配置事实上是一台未标定的假警机。

**要求**：执行 `08` Step 2，把标定值写回配置并在 `17` 记录数据来源；
在标定完成前，`multipath_threshold_fraction` 不得低于库默认 0.3。

### MAJOR-2 · `max_dwells` 改变第二峰门限的含义

`pcps_acquisition.cc:477` 中 `d_input_power` 按 `d_num_noncoherent_integrations_counter`
归一，而 `get_threshold()`（`:935`）是与 dwell 数无关的固定 CFAR 值。
`test_statistics2 = second_magnitude / d_input_power`（`:644`）随非相干累加增长，门限不变，
于是**第二峰的等效虚警率随 `max_dwells` 漂移**，无任何补偿或文档说明。

更关键的是 `find_second_peak()` 在**每个 dwell** 都执行并独立判决
（`acquisition_core()` 每 dwell 调用一次，`:852-855`），`max_dwells=8` 意味着
一次捕获尝试里有 8 次独立抽样机会，而捕获本身会无限重试。
20 Msps 下合格搜索区间约 154 个 bin（`(80-3)×2`）。历史上 L5 1000 m 那次检出用的是
`max_dwells=10`，产品配置是 8，两者不可互相引用。

**要求**：给第二峰门限一个显式的、与 dwell 数绑定的定义（例如按
`d_num_noncoherent_integrations_counter` 缩放门限，或只在最后一个 dwell 判决），
并在 `17` 中给出每次捕获尝试的目标 Pfa 及其推导。

### MAJOR-3 · 搜索窗边界保护是单边的

`pcps_acquisition.cc:648`：
`second_boundary_distance_bins = max(0, window - second_abs_distance)`，
门禁 `second_peak_gate.h:33` 只检查 `boundary_distance_bins >= reject_boundary_bins`。
这只保护**外边界**。落在 `min_delay` **内边界**外一格的峰——也就是主峰主瓣裙边这个
最经典的假第二峰位置——`boundary_distance_bins` 很大，畅通无阻。

**要求**：`SecondPeakMetrics` 增加内边界距离，门禁改为
`(|dist| - min_delay) >= reject_boundary_bins && (window - |dist|) >= reject_boundary_bins`。

### MAJOR-4 · 延迟门限按整数 samples-per-chip 量化，配置值不等于生效值

`acq_conf.cc:150`：`samples_per_chip = ceil(fs / chips_per_second)`，
`pcps_acquisition.h:210` 声明为 `const uint32_t`。GPS L5 码率 10.23 Mcps：

| 配置采样率 | 真实 samples/chip | 代码用值 | `min_delay` | 首个合格 bin | 实际最小延迟 | 延迟量化步长 |
|---|---|---|---|---|---|---|
| 20 Msps | 1.955 | 2 | `round(1.25×2)=3` | 4 samples | ≈ **60 m**（2.05 chip）| 15.0 m |
| 10 Msps | 0.977 | 1 | `round(1.25×1)=1` | 2 samples | ≈ **60 m**（2.05 chip）| 30.0 m |

（20 Msps 下 1 sample ≈ 14.99 m，10 Msps 下 ≈ 29.98 m。取整后两者的米制下限恰好都落在
约 60 m，但**这是取整的巧合**，不是配置意图；两者真正的差别在延迟量化步长差一倍。）

`multipath_min_delay_chips=1.25` 声明的是 36.6 m，实际生效是 **≈60 m**，
**偏大 64 %**。`second_delay_chips`（`:645`）也用取整后的整数做除法，系统性偏差 −2.3 %。
`KNOWN_LIMITATIONS.md:4` 写的"1.25-chip minimum acquisition separation"
不是任一出厂配置的实际行为，会让读者低估产品的近距边界。

**要求**：用浮点 `resampled_fs / chips_per_second` 计算延迟门限与 `second_delay_chips`；
在两个配置里把生效的米制下限与量化步长写成注释；把 `KNOWN_LIMITATIONS` 第 4 条改成
按采样率给出的实际米制下限。

### MAJOR-5 · 局部噪声中位数取自搜索窗自身

`pcps_acquisition.cc:639-641` 用**合格搜索区间内所有 bin 的中位数**当噪声底。
20 Msps 下样本数（约 154）尚可，但该区间紧贴主峰裙边，且**包含真实第二径本身**。
`multipath_min_peak_to_noise_db=3.0`（2 倍功率余量）没有任何标定依据。
10 Msps 下若收窄窗口，样本数会迅速不足以支撑中位数估计。

**要求**：噪声底改用远离主峰的独立区间（或复用 `d_input_power` 的反相 Doppler bin 思路），
并给出 `min_peak_to_noise_db` 的标定数据。

### MAJOR-6 · observables 的"已分离"门限与 acquisition 的物理下限不一致

`Observables.dual_path_min_abs_delta_m=10.0`，而 acquisition 在 20 Msps 下根本不可能
产生小于约 60 m 的第二峰（MAJOR-4）。也就是说，一个已经被 DLL 拉回到距 path0 仅 12 m 的
path1 仍会通过"已分离"判据。两层门限应当一致。

**要求**：把 `min_abs_delta_m` 与生效的 acquisition 最小延迟绑定（按采样率给出，
20/10 Msps 均取 ≥ 60 m），或在代码里从 acq 配置推导。

### MAJOR-7 · `path0`/`path1` 身份定义未写入产品说明书，且可能互换

代码中的实际定义：

- **primary** = 整个 Doppler-码相位网格上的**最强峰**（`max_to_input_power_statistic()` /
  `first_vs_second_peak_statistic()`），**不是最早径**；
- **second** = 以主峰为中心、`±window` 内的**最强合格 bin**。窗口是**对称**的
  （`pcps_acquisition.cc:594-608` 用 `adist = |dist|`），所以 **path1 可能比 path0 更早到达**。

室内 DAS 等功率双源下，重捕后两台天线的强弱关系完全可能翻转，导致
**path0/path1 与物理发射天线的对应关系互换**。状态机能间接察觉（±2Δ 的跳变会触发
`max_delta_jump_m=100` 判据 → `DEGRADED` → `LOST` → 重置），但：

- 输出中**没有任何字段标记发生了身份互换**；
- `README_CN.md` / `README_EN.md` / `KNOWN_LIMITATIONS.md` 中**没有一句话**说明
  path0/path1 不是发射天线的永久身份标签。

任务书 §四.3 明确要求产品说明书必须写清这一点。

**要求**：

1. 两个 README 与 `KNOWN_LIMITATIONS` 各加一条：
   "`path0` = 本次捕获中的最强峰，`path1` = 搜索窗内的次强合格峰；两者**不是**
   发射天线的永久编号，重捕后可能互换，`path1` 也可能**早于** `path0` 到达
   （`delta_m` 为负）。跨重捕比较必须以 `reacquisition_count` 分段。"；
2. `DUALPATH_STATUS` 增加 `delta_sign_flips` 或在 `reacquisition_count` 旁给出
   `delta_median_m` 的符号，便于下游识别互换。

### MAJOR-8 · 注册的测试目标从未构建过

`tests/README.md:9` 自述："the four focused GoogleTest suites were compiled and run directly"，
即 Codex **绕过了 `run_tests` / `check` 目标**，单独编译了 4 个 suite。
`build_release.sh:18` 又用 `-DENABLE_UNIT_TESTING=OFF` 配置，发布路径也不构建测试。

我静态核对了 CMake 接线，结论是**应该**能编译通过：
`acquisition_libs` / `observables_libs` 各自把源码目录挂在
`INTERFACE_INCLUDE_DIRECTORIES` 上，并经 `*_gr_blocks`（PUBLIC）→ `*_adapters`（PUBLIC）
传到 `run_tests`。但这是分析，不是构建。

**要求**：在 NUC `build-conda` 上执行
`cmake -DENABLE_UNIT_TESTING=ON` + `make run_tests` + `./run_tests --gtest_filter='DualPath*:Acquisition*:SecondPeak*'`，
把实际输出贴进 `17`。

### MAJOR-9 · `check_runtime.sh` 的 overflow 判据大概率检不出 UHD overflow

`check_runtime.sh:45` 用 `grep -qi 'overflow' "$log"` 作为 30 分钟长跑的门禁。
我对全仓 `src/algorithms/signal_source/` 做了检索：打印字面量 `overflow` 的只有
AD936x/IIO/FPGA 系列源；**B210 走的 `UHD_Signal_Source` → `gr::uhd::usrp_source`
在溢出时输出的是裸字符 `O`（`OOO`），不含 `overflow` 字样**。
（`gr_complex_ip_packet_source.cc:324` 同样只打 `o`。）

因此"30 分钟无 overflow"这条产品验收有可能在**持续溢出**的情况下通过。

**要求**：判据改为同时匹配 `overflow` 与流式 `O`/`o` 标记（例如统计
`grep -c '^O\+$'` 与行内连续 `O`），并在一次**故意制造溢出**的运行上验证该判据确实会失败，
把验证记录写进 `17`。

### MAJOR-10 · `DUALPATH_STATUS` 文本与 CSV 对同一字段用了不同名字，且文本名有误导

`dual_path_status_formatter.cc:52-59` 文本形式输出：

```
primary_cn0_db_hz=<滚动中位数>  second_cn0_db_hz=<滚动中位数>
primary_doppler_hz=<滚动中位数> second_doppler_hz=<滚动中位数>
```

而 CSV 表头（`:70`）对**同样的值**用的是
`primary_cn0_median_db_hz` / `second_cn0_median_db_hz` /
`primary_doppler_median_hz` / `second_doppler_median_hz`。

更严重的是同一份日志内部就有歧义：`DUALPATH_PAIR` 行
（`hybrid_observables_gs.cc:380-381`）打印的 `primary_cn0_db_hz=` / `second_cn0_db_hz=`
取自 `status.primary_cn0_db_hz`（`dual_path_pair_manager.cc:235`），是**瞬时值**；
而 `DUALPATH_STATUS` 行里**字面完全相同**的 `primary_cn0_db_hz=` 是**滚动中位数**。
`DUALPATH_OBS` 的 `cn0_db_hz=` 同样是瞬时值。
一个自称"稳定产品接口"的 v1 不应该让同名字段在相邻两行里表示不同的量。

**要求**：`DUALPATH_STATUS` 文本字段改名为
`primary_cn0_median_db_hz` / `second_cn0_median_db_hz` /
`primary_doppler_median_hz` / `second_doppler_median_hz`，与 CSV 表头一字不差；
同步更新 `dual_path_status_formatter_test.cc` 的精确字符串断言、两个 README，
并在文档里明确 `DUALPATH_OBS` / `DUALPATH_PAIR` 是瞬时值、`DUALPATH_STATUS` 是滚动统计。

---

## 7. MINOR 问题

1. `DualPathPairManager::reset()` 是死代码，从未被调用。PVT 的 `reset TOW` 命令
   （`hybrid_observables_gs.cc:301-311`）清了通道历史却没有重置配对管理器，
   `pair_start_time_s` 停留在旧时钟系，`track_age_s` 被 `std::max(0.0, …)` 压成 0。
2. `d_records` 按 `(system, signal, PRN)` 索引，容量受 PRN 数天然限制，**不存在无限增长**；
   但已落山的卫星条目永不清除。仅备案。
3. `second_delay_chips` 丢弃符号，只有 `delta_m` 保留 path1 是早还是晚。
4. `DUALPATH_OBS` 没有版本标签，而 `DUALPATH_STATUS` 有。兼容输出建议也加
   `version=` 或在文档中明确它不受版本承诺保护。
5. `d_dual_path_csv_file.flush()` 每次报告都调用。1 Hz 下无影响，但
   `dual_path_interval_ms` 若配到接近 `observable_interval_ms`（20 ms）就是 50 次/秒的
   同步写，且发生在 GNU Radio 调度线程上。建议给该参数设下限并在配置里注明。
6. `build-info.txt` 含构建主机名 `lya-Y7000`。属溯源信息，可接受，仅提示。
7. 包内**未发现**原始 IQ、构建缓存、密钥或个人路径（`ldd-report.txt` 全为系统路径）。

---

## 8. 线程安全与状态管理：**通过**

- `DualPathPairManager` 是 `hybrid_observables_gs` 的普通成员（`hybrid_observables_gs.h:91`），
  只在 `report_dual_path_observables()` 内被访问，而该函数只在 `general_work()` 中调用
  （`hybrid_observables_gs.cc:1103`）→ **单线程，无需 mutex**。
- **无静态全局容器**；CSV `ofstream` 是成员，析构函数中关闭（`:257-267`）。
- 通道重建即块重建，记录随对象销毁。
- 多 PRN 容器有界（见 MINOR-2）。
- stdout 量级：默认 1 Hz × 3 行，可通过 `dual_path_interval_ms` 控制，不会淹没日志。

唯一遗留：`general_work()` 不持有 `d_setlock`，而 `msg_handler_pvt_to_observables()` 持有。
这是上游 GNSS-SDR 的既有形态（GNU Radio 在块线程内派发消息），**非本次提交引入**，
不计入本次问题清单。

---

## 9. 配对正确性：**通过**（含一处需补测）

- 键为 `{system, signal, prn}`（`dual_path_pair_manager.h:29-36`），
  `signal` 取 `Gnss_Synchro::Signal` 前两字符（`hybrid_observables_gs.cc:80-92`）
  → **不同信号体制不会误配**。
- 时间对齐：`|primary.rx_time_s - second.rx_time_s| <= max_time_difference_s`（默认 0.05 s，
  产品配置 0.05 s）→ **旧观测不会与新观测误配**（在同一历元内）。
- 失锁通道：`epoch_data` 里失效通道被置空且 `PRN=0` 被跳过 → **不会继续使用过期值**。
- 多 PRN：键含 PRN → **不会交叉配对**。我补了单测
  `DualPathPairManager.KeepsSeparatePrnsFromCrossPairing` 覆盖此项（Codex 原测试集无此用例）。
- **例外**：跨历元的过期问题见 BLOCKING-1——总失联时记录冻结，这正是"用过期状态"的
  另一种形态。

---

## 10. path1 回退主峰：**已修复**

任务书 §四.1 的核心问题。逐路径核对 `pcps_acquisition.cc:857-919`：

`requires_second_path = acquire_second_path || Signal_Path == 1`；
`select_acquisition_path()`（`acquisition_path_selector.h:16-26`）对该情形返回
`accepted = main_peak_valid && second_peak_valid`，`use_second = accepted`。

- **未通过**时走 `invalidate_second_path_synchro()`（`:750-755`），把
  `Acq_delay_samples / Acq_doppler_hz / Acq_samplestamp_samples` 全部清零，
  **不会**把主峰的 `index_time/doppler` 写进 path1 的同步结构；
- **未通过**时 `d_state = 1` 继续搜索，只有 `max_dwells` 耗尽或 `bit_transition_flag`
  才走 `handle_integration_done()` 发负捕获；
- `handle_second_path_threshold_reached()`（`:758-767`）不走 `make_2_steps` 两步细化、
  也不走 bit-transition 捷径——修掉了旧代码里 `if (result.test_statistics > d_threshold)`
  这条会让 path1 以主峰成功的分支（见 `17 §3.3` 风险 1）。

**结论：主峰回退路径已封死，`select_acquisition_path` 的四个组合均有单测覆盖。**
但这只证明 path1 不会拿主峰的参数，**不证明 path1 不会锁上噪声**——后者取决于
MAJOR-1/2/3/5 的门限标定，而标定尚未做，且负对照配置无法执行（BLOCKING-2）。

---

## 11. 证据与宣传对照表

| 主张 | 证据 | 证据类型 | 可写入 README | 可写入论文 | 风险 |
|---|---|---|---|---|---|
| path1 不会回退主峰 | 代码走查 + 4 个选择器单测 | UNIT_TEST | ✅ | ⚠️ 需补集成级证据 | 单测只覆盖纯策略函数 |
| 配对含 system/signal/PRN/时间 | 代码 + 单测（含我新增的多 PRN 用例）| UNIT_TEST | ✅ | ⚠️ | 跨历元过期未覆盖（BLOCKING-1）|
| 输出格式稳定、locale 安全 | 精确字符串单测 + `std::locale::classic()` | UNIT_TEST | ✅ | ✅ | 字段命名不一致（MAJOR-10）|
| 状态机能拒绝等伪距/弱 CN0/Doppler 失配/突跳 | 7 个状态机单测 | UNIT_TEST | ✅（限"在配置门限下"）| ❌ | 门限值本身无数据依据 |
| `RELIABLE` 表示质量门通过 | 代码 | UNIT_TEST | ⚠️ 必须同时写明 BLOCKING-1 未修 | ❌ | 总失联后会假 `RELIABLE` |
| 运行不依赖 Python | 代码 + 4 个 conf + 2 个 bash 脚本，全链路无 Python | 代码审查 | ✅ | ✅ | 本项**通过**，是本次交付的实打实成果 |
| 双源约 219 m 连续输出 | 用户截图（研究原型，早于本分支）| USER_SCREENSHOT | ⚠️ 只能作演示 | ❌ | 非本分支代码、非产品配置、非受控实验 |
| 1000 m 可捕获 | `dev_notes/README` 2026-07-17 记录，`max_dwells=10`，**复测未过主捕获门限** | FILE_REPLAY（单次，且有失败复测）| ❌ | ❌ | 单次观测 + 已知复现失败 |
| 200 m/1000 m/1030 m 双峰可分 | 2026-07-16 B1I 记录 | FILE_REPLAY | ⚠️ 标明是 B1I 不是 L5 | ❌ | 信号体制不同，不可外推到 L5 产品 |
| 50 m 可分 | 2026-07-18 实测**失败**（Δ 随机游走） | FAILED_CONTROL | 必须写入限制 | ✅ 作为负结果 | 已在 `05` 记录，产品文档未点名 |
| 单源不误报第二径 | **无** | UNVERIFIED | ❌ | ❌ | 出厂负对照无法执行（BLOCKING-2）|
| 30 分钟无 overflow | **无**，且判据可能失效（MAJOR-9） | UNVERIFIED | ❌ | ❌ | — |
| 发布包可运行 | **无**，且目标机不匹配（BLOCKING-3） | UNVERIFIED | ❌ | ❌ | — |

**特别提示（按任务书 §十）**：

- 用户截图的约 219 m 连续输出是**可用的演示证据**，不是产品验收；
- 1000 m 历史捕获成功**不等于**新版产品长时间持续跟踪已验证，且该条记录本身带着一次复测失败；
- 延迟数值接近期望**不等于**第二源真实——`08` Step 3 的导线注入是唯一干净判据，未做；
- 单源负对照与失锁测试**均未通过**（前者无法执行）；
- 近距离失败**已**在 `KNOWN_LIMITATIONS` 以"不声称最小可分距离"的形式回避，
  但**没有点名 50 m/10 Msps 这个已实测失败的具体条件**，建议补入。

---

## 12. 逐项结论

| 任务书要求项 | 结论 |
|---|---|
| **8. 单源虚警结果** | **未取得**。出厂负对照配置结构上无法测试该模式（BLOCKING-2），本次也无运行环境。 |
| **9. 双源稳定结果** | **未取得**。无回放、无实时运行。仅有 7 个状态机单测证明逻辑分支正确。 |
| **10. 重捕获结果** | **部分且不合格**。单测覆盖"path1 单独失锁→恢复"（`TracksIndependentLossAndReacquisition`，通过）；但**两路同时失联**的重捕行为存在 BLOCKING-1 缺陷，且该场景在 PVT 时钟修正时常规发生。 |
| **11. 长时间运行结果** | **未取得**。且长跑门禁的 overflow 判据本身可能失效（MAJOR-9）。 |
| **12. 发布包结果** | **不合格**。tar.gz 完整性 OK（摘要手工比对一致），但校验和文件不可用、目标机不匹配、缺依赖说明、README 死链（BLOCKING-3）。包内无原始 IQ / 构建缓存 / 密钥 / 个人路径。 |
| **13. 产品最小已验证距离** | **无**。本分支未做过任何距离验证。`KNOWN_LIMITATIONS.md:12` 拒绝声称最小距离，这是**正确**的姿态，必须保持。可参考但不可引用的历史值：L5 1000 m（单次，复测失败）、B1I 200 m/1000 m/1030 m（不同信号体制）。 |
| **14. 已知不能处理的条件** | 亚码片 / 0.5 chip / 融合峰；小于生效 acquisition 下限（20 Msps 与 10 Msps 均约 60 m，见 MAJOR-4）的间距；50 m 等功率 CN0 35–40（`05` 2026-07-18 实测失败）；两路同时失联后的状态正确性（BLOCKING-1）；三路及以上；阵列测向；接收机运动轨迹；第二径参与 PVT；两台模拟器不共 10 MHz/1PPS 时的码相位漂移。 |

---

## 13. 最终裁决

# BLOCK_RELEASE

**理由（三条 BLOCKING 各自独立成立）**：

1. **BLOCKING-1** —— 产品的核心承诺字段 `state=RELIABLE` 在**常规运行**（每次 PVT 时钟修正）
   后会带着失联前的滑窗、失联前的 `track_age_s` 和归零的 `reacquisition_count` 复活。
   这不是精度问题，是可靠性判据在正常工况下失真。
2. **BLOCKING-2** —— 出厂"单源负对照"配置在结构上无法产生 path1，
   任务书与 `tests/README.md` 都列为必过的单源假警测试**用现有交付物无法执行**。
3. **BLOCKING-3** —— 发布包构建于非目标机（WSL2 Ubuntu 24.04）、无依赖说明、
   校验和文件因绝对路径不可用、README 存在死链。

**应当肯定的部分**（修复后可快速复审）：

- 产品范围冻结与宣传边界**处理得非常克制**，没有任何越界声称，`CODE COMPLETE` 标签诚实；
- path1 回退主峰这个最危险的缺陷**已经真正修掉**，不是文档层面的敷衍；
- 配对键补齐 system/signal/PRN/时间、输出 `std::locale::classic()`、
  N/A 语义明确、字段顺序有精确字符串测试锁定——这些都是正确的产品化动作；
- **运行不依赖 Python 已经实打实做到**，全部 conf 与脚本链路无 Python 依赖。

**复审门槛**：BLOCKING-1/2/3 修复 + MAJOR-1（执行 `08` Step 2 标定）+ MAJOR-7（身份说明）
+ MAJOR-8（在 NUC 上真实构建并运行 `run_tests`）+ MAJOR-9（overflow 判据在故意溢出的
运行上验证）完成后，方可重新提交。届时最低复审证据为：单源负对照 30 min + 一组
200–220 m 双源回放 + 一组已知近距失败对照 + 发布包在 NUC 上解包启动。

---

## 14. 本次审查引入的代码改动

仅两处，均为测试，不改算法：

1. `tests/unit-tests/signal-processing-blocks/observables/dual_path_pair_manager_test.cc`
   新增 `KeepsSeparatePrnsFromCrossPairing`（**通过**，补齐任务书 §四.2 的多 PRN 覆盖空白）；
2. 同文件新增 `DISABLED_TotalOutageMustNotRepublishStaleReliable`
   （BLOCKING-1 的修复规格，当前代码下必然失败，故以 `DISABLED_` 提交；
   Codex 修好后去掉前缀即可）。

未新增任何平行算法实现。

-- Claude (Opus 5)，2026-08-08
