# GNSS-SDR 改造项目 · 主索引（总纲）

> **给下一个无记忆 AI 的话**：这是本项目的**导航入口**。你**不需要**一次性读完所有文档。
> 先读本文件（约几百行，很小），了解**整体结构、当前进度、每篇讲什么、该读哪篇**，
> 然后**只按需**打开你这次任务真正相关的那一两篇详情文档。这样可以避免上下文爆炸。

---

## 0. 一句话项目目标

阅读并理解 GNSS-SDR（CTTC 出品的软件定义 GNSS 接收机，C++/GNU Radio）的信号解析源码，
**重点搞懂它的二维谱峰搜索（信号捕获 / Acquisition）**，然后在此基础上改造，加入
**① 多径（multipath）识别** 和 **② 多源信号（multi-source）处理** 两大能力。

- 项目根目录：`D:\work\project\usrp_gnss\gnss-sdr`
- 本文档目录：`D:\work\project\usrp_gnss\gnss-sdr\dev_notes`
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

> 图例：✅ 已成稿可用 · 🟡 进行中 · ⬜ 未开始

---

## 2. 进度看板（Progress Board）

> **维护约定**：每完成一个里程碑，更新这一节 + 在 `05_pitfalls_and_decisions_log.md` 追加一条。
> 只改这里和相关的那一篇，不要动无关文档，省 token。

**当前阶段：`工具就绪✅ → 等明天真实 B1I 数据`（手册见 `USAGE_B1I.md`）**

🎯 **方向已锁定**（用户 2026-07-12 决策）：目标信号 **BeiDou B1I**；用途 **提升定位精度**（两条径要影响 PVT）；
覆盖 **近距+远距**两种多径。方案为 **A（捕获双峰）+ B（跟踪多相关器）+ PVT 整合** 三阶段，详见 `04`。

⚠️ **关键认知**：不是把两条径的两个伪距都塞进 PVT（反射径偏长，直接塞会**变差**）；而是跟踪两条径 →
判别直射(LOS) → 每星只送**一条干净/校正后**观测量进解算器，第二径走旁路做分析。（详见 `04 §0`）

📌 **已对代码做的实质修改**（全在捕获层，详见 `05`）：① 注册 Signal_Generator；② 第二峰检测；③ `acquire_second_path`；④ 多径巡检日志。

- [x] 读懂 acquisition 核心 + 整体架构 + 文档体系；双径可行性调研；锁定方向 + 分阶段方案
- [x] **Stage 0**：WSL2 编译通过；注册 Signal_Generator；GPS L1 仿真链路 + h5py 分析
- [x] **Stage 1a**：捕获检测并报告第二峰（邻域搜索+门限闸控+dump）。双径 has2=1，单径 has2=0
- [x] **Stage 1b**：`acquire_second_path` + 两通道同 PRN（纯配置配对）。通道0跟直射、通道1跟反射
- [x] **面向真实数据的工具就绪**：`USAGE_B1I.md` + `bds_b1i_multipath.conf`(扫描) + `bds_b1i_dualpath.conf`(双路径跟踪)
      + `analyze_multipath.py`。多径巡检日志(需 `GLOG_logtostderr=1`)。假数据烟测通过（B1I管线构建/运行 OK）
- [ ] ⏳ **等真实 B1I 数据**（用户明天采集）：跑 survey 扫多径 → 双路径跟踪 → 看是否出双伪距
- [ ] Stage 2：跟踪域多相关器（近距<1码片多径）
- [ ] Stage 3：LOS 判别 + PVT 整合（每星一条干净观测量；参考 `duplicated_satellites_test`）

**下一步（明天）**：用户拿到真实 B1I 数据 → 按 `USAGE_B1I.md` 操作。之后据实测结果推进 Stage 2/3。

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

*最后更新：2026-07-12 · 阶段一理解阶段 · 由 Claude 维护*
