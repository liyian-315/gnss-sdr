# GNSS-SDR 改造项目 · 主索引（总纲）

> **给下一个无记忆 AI 的话**：这是本项目的**导航入口**。你**不需要**一次性读完所有文档。
> 先读本文件（约几百行，很小），了解**整体结构、当前进度、每篇讲什么、该读哪篇**，
> 然后**只按需**打开你这次任务真正相关的那一两篇详情文档。这样可以避免上下文爆炸。

---

## 0. 一句话项目目标

阅读并理解 GNSS-SDR（CTTC 出品的软件定义 GNSS 接收机，C++/GNU Radio）的信号解析源码，
**重点搞懂它的二维谱峰搜索（信号捕获 / Acquisition）**，然后在此基础上改造，加入
**① 多径（multipath）识别** 和 **② 多源信号（multi-source）处理** 两大能力。

- 当前工作副本（本地/Windows）：`D:\work\project\usrp_gnss\gnss-sdr-main-gaizao\gnss-sdr\gnss-sdr-lya`
- 测试机（Ubuntu18.04 + USRP B210）：`~/lya/gnss-sdr/gnss-sdr-lya`，**必须在 conda 环境 `gnsssdr` 里、用 `build-conda/` 编译运行**（见 `06`）。
- 上游是标准开源项目（GPL-3.0），我们把它当**工作副本**改造，不追求合并回上游。

---

## 1. 文档地图（按阅读顺序 / 重要性）

| 编号 | 文件 | 讲什么 | 什么时候读 | 状态 |
|------|------|--------|-----------|------|
| 00 | `README.md`（本文件） | 总纲、进度看板、导航 | **每次都先读** | 维护中 |
| 01 | `01_architecture_overview.md` | 整体信号处理链、Channel、FlowGraph 如何串起来 | 需要大局观 / 改动跨模块时 | ✅ 初稿 |
| 02 | `02_acquisition_2d_peak_search.md` | **★核心★** 二维谱峰搜索（PCPS）算法细节、逐函数拆解 | 改捕获 / 做多径识别时**必读** | ✅ 初稿 |
| 03 | `03_data_structures_interfaces.md` | 关键数据结构（Gnss_Synchro、Acq_Conf）与接口层级 | 需要传参 / 扩字段 / 加配置项时 | ✅ 初稿 |
| 04 | `04_retrofit_plan_multipath_multisource.md` | 改造方案：多径识别 + 多源信号的切入点与设计 | 动手改造前 / 定方案时 | 🟡 规划中 |
| 05 | `05_pitfalls_and_decisions_log.md` | 踩坑、关键决策、疑问（按日期追加） | 遇到怪问题 / 想知道"为什么这么做"时 | 🟡 持续追加 |
| 06 | `06_b210_multipath_test_usage.md` | **★运行手册★** conda环境+B210多径测试：B1I/L5I 录制、离线分析、画图、调参、排错 | **在测试机上跑测试前必读** | ✅ 权威 |

> 图例：✅ 已成稿可用 · 🟡 进行中 · ⬜ 未开始

---

## 2. 进度看板（Progress Board）

> **维护约定**：每完成一个里程碑，更新这一节 + 在 `05_pitfalls_and_decisions_log.md` 追加一条。
> 只改这里和相关的那一篇，不要动无关文档，省 token。

**当前阶段：`B1I/B210/双模拟器多径捕获实测已跑通 ✅ → 远距多径可由捕获域识别 → 近距多径进入跟踪域方案`（详见 `05` 2026-07-16；运行手册 `06 §2C`）**

> 🔧 **实测根因（2026-07-15，非改造代码）**：实时失锁/overflow/无定位 = ①12个Ctrl+Z挂起进程叠罗汉 ②Firefox吃95%CPU ③增益太低欠量化(gain45→70)。清空+关扰+gain70 后单星PRN9 45s 零失锁、CN0 82。饱和已实测排除。
> **规范**：一次只跑一个实例；停止用 Ctrl+C 不用 Ctrl+Z；跑前关 Firefox；实时增益 ~65–70。离线看谱峰走"录制→File源+dump"。
> 📡 **2026-07-16 OTA 天线收发补充**：无补偿、功率同直连时，B210 侧 RX2/TX-RX + 70/76dB 均未削顶但也未捕获，离线最高 `test_statistic≈40 < threshold=54.22`。天线链路需先增强到单路径 `positive=1`，再谈 1000m 多径。
> 📡 **2026-07-16 双模拟器进展**：换无源天线后，B210/RX2 能稳定捕获 BDS B1I PRN9。双源等功率下，`+200m` 检出 `abs(Δ)≈225m`，`+1000m` 检出 `abs(Δ)≈1049m`，`+1030m` 检出 `abs(Δ)≈974m`。`+70m` 未被捕获域分开，符合 `<1 chip` 近距多径需要跟踪域多相关器的判断。
> 📡 **2026-07-17 L5/字段判读补充**：GPS L5I PRN18 曾在 `max_dwells=10` 下检出 `abs(Δ)≈1019m`；后续复测当前现场未过主捕获门限。每次采样测试、样点质量检查、`.mat` 关键字段和正式判定标准已整理到 `06 §2E`。

> 🔧 **目标 = B1I**。运行用 stock B1I 链路 + `signal_paths=2` 两路径机制。测试机系统 GNU Radio 3.7 的 FFT 坏了，
> 已用 **conda 装 GR3.10 隔离重编**（`build-conda/`，**跑前必须 `conda activate gnsssdr`**）。见 `06`/`05`(2026-07-14)。

🎯 **方向已锁定**（用户 2026-07-12 决策）：目标信号 **BeiDou B1I**；用途 **提升定位精度**（两条径要影响 PVT）；
覆盖 **近距+远距**两种多径。方案为 **A（捕获双峰）+ B（跟踪多相关器）+ PVT 整合** 三阶段，详见 `04`。

⚠️ **关键认知（回应"会不会违背目标"）**：目标"**追踪两条径的伪距信息**"**已满足**——两条径都跟踪、都进 observables/dump/monitor 输出。
争议只在"**要不要把两条径都塞进 PVT 解算器**"：反射径偏长，当第二个观测量塞进 RTKLIB 会把定位**拉偏变差**，所以**只放行直射径(path0)**，第二径走旁路。
**独立佐证**：另一副本 `gnss-sdr-xinghe`（另一 AI）的 `rtklib_pvt_gs.cc` 也是"只放行 path0"——两个 AI 收敛到同一设计。
**⚠️ 但注意**：现阶段第二径只是"输出/分析"，**还没用来改善定位**；要真正"提升定位精度"，下一步须用第二径做 **LOS 判别 + 多径校正**（见"下一步"）。

📌 **已对代码做的实质修改**（详见 `05` / `06`）：① 注册 Signal_Generator；② 第二峰检测；③ `acquire_second_path`；④ 多径巡检日志；
⑤ B1C acquisition；⑥ `Signal_Path` 两路径通道；⑦ B1C tracking adapter；⑧ B210 直采配置。

- [x] 读懂 acquisition 核心 + 整体架构 + 文档体系；双径可行性调研；锁定方向 + 分阶段方案
- [x] **Stage 0**：WSL2 编译通过；注册 Signal_Generator；GPS L1 仿真链路 + h5py 分析
- [x] **Stage 1a**：捕获检测并报告第二峰（邻域搜索+门限闸控+dump）。双径 has2=1，单径 has2=0
- [x] **Stage 1b**：`acquire_second_path` + 两通道同 PRN（纯配置配对）。通道0跟直射、通道1跟反射
- [x] **面向真实数据的工具就绪**：`USAGE_B1I.md` + `bds_b1i_multipath.conf`(扫描) + `bds_b1i_dualpath.conf`(双路径跟踪)
      + `analyze_multipath.py`。多径巡检日志(需 `GLOG_logtostderr=1`)。假数据烟测通过（B1I管线构建/运行 OK）
- [x] **B1C/B210 直采原型**：`my_bds_b1c_multipath.conf` 改为 UHD/B210 实时采集，`Channels_C1.signal_paths=2`
      自动给每颗星分配主径/第二径。B1C tracking adapter 已接入。
- [x] **服务器 GR3.7 编译通过但 FFT 运行时坏**：`gr::fft::fft_complex` 构造抛异常 → `Can't connect channel 0`（gdb 定位，见 `05`）。
- [x] **✅ conda GR3.10 重编成功 + B210 实收真实 B1I 跑通**：`build-conda/`，一大批真实北斗星 Tracking，无 FFT 崩溃。
      踩坑链(glog→absl / 关 ZMQ,LimeSDR,OSMOSDR,RAW_UDP / CNAV1 无守卫 glog)全解，完整配方见 `06 §5`。
- [x] **仓库整理**：`sim/` 只留 `my_bds_b1i_twopath.conf`+`analyze_multipath.py`，历史入 `sim/archive/`，删 dump + 加 `.gitignore`。
- [x] **B1I 双模拟器多径捕获实测**：B210/RX2 + 无源天线 + 双模拟器 PRN9。`+200m/-40/-40`、`+1000m/-40/-40`、`+1030m/-40/-40` 均得到 `positive=1 && has2=1` 的捕获域双峰；`+70m` 未分开，证明近距多径不能继续依赖捕获域 Top-2。
- [ ] ⏳ **连续统计 + 单路校准**：对 `+200m/+1000m/+1030m` 每组连续采 5 次，统计 `abs(Δm)` 均值/方差；必要时分别单开两台模拟器验证码相位差。
- [ ] absl 日志下 `MULTIPATH` 可见性微调（验证多径时一并处理）。
- [ ] Stage 2：跟踪域多相关器（近距<1码片多径）；Stage 3：LOS 判别 + PVT 整合。
- [ ] （搁置）B1C CNAV1 telemetry decoder —— B1C 专用，**B1I 目标不需要**。

**下一步 · 三步路线**（目标：对每颗卫星搜最强两条径、跟踪、并最终用第二径**提升定位**）：
1. **[已完成基本验证，待统计] 验证机制**：双模拟器 PRN9 实测已确认捕获域能检出 `+200m`、`+1000m`、`+1030m` 的第二峰；下一步补 5 次重复统计和单路校准，避免把一次采样窗口/等功率主次峰翻转当成稳定结论。
2. **回到通用（所有卫星、每星两径）**：`signal_paths=2` 自动搜所有 PRN。要解决两个现场问题——
   ① **假捕获**（现场只有PRN9时，别的PRN搜到互相关假峰）→ 提高门限/加互相关剔除，或真实多星时自然缓解；
   ② **USRP overflow**（通道多CPU过载）→ 降通道数/采样率或提升算力。此步产出"每星两条径的伪距信息"（目标的"输出"部分达成）。
3. **用第二径提升定位（真正的"提升定位精度"）**：现在第二径只输出、未改善定位。需 **LOS 判别**（哪条是直射）+ **多径校正**（用两径估计并扣除直射径的多径偏差），把校正后的观测量送 PVT。这对应 `04` 的 Stage 2(跟踪域多相关器)/Stage 3(PVT整合)。
> 参考：`gnss-sdr-xinghe` 是另一 AI 的平行副本，捕获第二峰实现不同（改 `first_vs_second_peak_statistic` + `second_peak_exclusion_chips`），但 PVT 处理与 lya 一致。可互相借鉴。

---

## 3. 核心结论速查（不用翻详情也能记住的几条）

1. **"二维谱峰搜索" = 信号捕获（Acquisition），算法叫 PCPS（Parallel Code Phase Search，并行码相位搜索）。**
   - 两个维度：**多普勒频率**（串行外循环）× **码相位/时延**（FFT 并行一次算完）。
   - 二维搜索面存在 `d_magnitude_grid[doppler_index][code_phase]` 这个网格里。
2. **核心算法文件**：`src/algorithms/acquisition/gnuradio_blocks/pcps_acquisition.cc`（872 行）。
   最关键函数是 `doppler_grid()`（做相关）和 `compute_statistics()`（找峰）。
3. **多径识别的天然切入点**：`first_vs_second_peak_statistic()`——它已经会排除主峰 ±1 码片去找次峰。
   多径在相关函数上表现为**主峰畸变 / 相邻的次峰**，这里和 tracking 的相关器是两个主战场。
4. **多源信号的落点**：FlowGraph 里可挂多个 SignalSource，Channel 是"每信号一路"的抽象；
   融合发生在 observables/PVT 层。（细节待第二阶段补充）
5. **捕获结果**通过 `Gnss_Synchro` 结构体（`Acq_delay_samples`、`Acq_doppler_hz`、`Acq_samplestamp_samples`）
   交接给 tracking，交接由 `ChannelFsm::Event_valid_acquisition()` 触发。

---

## 4. 关键路径速查表（懒人指引）

| 你想干的事 | 直接看这个文件 |
|-----------|---------------|
| 改二维搜索算法本身 | `src/algorithms/acquisition/gnuradio_blocks/pcps_acquisition.cc` |
| 加/改捕获配置项 | `src/algorithms/acquisition/libs/acq_conf.h` + `acq_conf.cc` |
| 改某信号(如GPS L1)的捕获适配器 | `src/algorithms/acquisition/adapters/gps_l1_ca_pcps_acquisition.*` + `base_pcps_acquisition.*` |
| 给捕获/跟踪结果加字段 | `src/core/system_parameters/gnss_synchro.h` |
| 改跟踪相关器（多径） | `src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.*` + `libs/cpu_multicorrelator_real_codes.*` |
| 改捕获→跟踪交接逻辑 | `src/algorithms/channel/libs/channel_fsm.*` |
| 加新块/改工厂 | `src/core/receiver/gnss_block_factory.*` |
| 看示例配置 | `conf/gnss-sdr.conf` 及 `conf/File_input/` |

---

## 5. 术语表（Glossary）

- **PCPS** — Parallel Code Phase Search，并行码相位搜索，本项目的主力捕获算法。
- **Acquisition（捕获）** — 从原始采样里初步找到卫星信号，估计粗略的多普勒 + 码相位。即"二维谱峰搜索"。
- **Tracking（跟踪）** — 捕获成功后持续锁定信号，DLL(码环)+PLL(载波环)，用 early/prompt/late 相关器。
- **码相位（code phase）** — 本地 PRN 码相对接收信号的对齐位置（时延），单位样点/码片。
- **多普勒（Doppler）** — 卫星运动引起的载波频偏，单位 Hz。
- **CFAR** — 恒虚警率检测，本项目用"峰值/输入功率"构造检验统计量并按 Pfa 定门限。
- **非相干积分（non-coherent integration）** — 多次 dwell 的幅度网格累加，提升弱信号检测。
- **Gnss_Synchro** — 贯穿全链路的同步数据结构体，捕获/跟踪/观测量都往里写。
- **VOLK** — 向量优化内核库（`volk_*` 函数），做 SIMD 加速的复数乘、FFT 取模等。
- **多径（multipath）** — 信号经反射到达，叠加在直射信号上，使相关峰畸变、测距有偏。
- **多源（multi-source / multi-constellation / multi-frequency）** — 多个信号源/星座/频点同时接收与融合。

---

*最后更新：2026-07-17 · B1I/L5I B210 双模拟器多径捕获实测与字段判读阶段 · Codex/Claude 协同维护*
