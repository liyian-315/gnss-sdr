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

### 0.1 应用背景与场景定义（★必读·防止方向性误解★）

**应用场景 = 室内定位（indoor positioning），不是室外抗多径。**

信号链路：室外卫星信号经**室分天线（DAS，室内分布系统）**引入室内 → 室内**多个天线同时主动转发同一颗卫星、同一频段**的信号 → 接收机（单接收天线）收到第一径、第二径……

> ⚠️ **本项目语境下的"多径"含义与传统教科书相反，务必分清：**
> - **不是**"一条直射（LOS）+ 若干弱反射/回波"，**第二径也不是"畸变（distortion）"**。
> - 第一径、第二径……**都是室内天线主动辐射出来的、强度相当的有意义信源**（每条径≈一个室分天线）。
> - 因此目标**不是**"留直射、压反射"（multipath *mitigation*），
>   **而是把每条径都当作有用信源，估计其（延迟 / 幅度 / 相位 / 时间一致性），用于室内定位**（multi-source *separation & estimation*）。
> - 这就是 `09` 里的 reframe：**协同多源 / 伪卫星 / 虚拟发射机**（SuperGPS、Channel-SLAM），**不是盲多径抑制**。
> - 台架模拟：**两台模拟器发同一 PRN、其一补偿 +X m** = 模拟两个室分天线；**等/近功率是正常工况，不是难点边缘**。

**一个必须保留的技术准确性**（别过度纠正）：即便每条径都"有意义"，接收机仍**只有一根接收天线**，
dense 相关器看到的仍是**多个 R(τ) 相关峰的叠加**。所以**信号处理方法不变**——依旧是
**dense 相关器 + 多分量拟合（MEDLL/CADLL 思路，见 `09`/`11`）**；**变的是目标与解读**：
输出是"**所有信源的参数**"，第二径要**保留并使用**，**不是丢弃**。"不是畸变"≠"不需要拟合"，恰恰相反，拟合正是为把这些有用信源分开。

> 📌 **对下游 PVT 的影响（待重估）**：`04`/看板里早期写的"每星只放行 path0(直射) 进 PVT、第二径旁路"是按**室外抗多径**框架定的；
> 在**室内 DAS 多源**框架下，额外的径恰恰是**有用信号**，PVT 整合应走**伪卫星/多源测距（TDOA/几何）**方向而非丢弃第二径。此点后续在 `04` 单独重估，勿照搬旧结论。

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
| 07 | `07_stage2_dual_tracking_prototype.md` | **L5 双路径持续跟踪原型（架构 A 工程化）**：L5 固定 PRN 两通道持续 tracking，扩展 observables dump 输出路径标签、伪距、C/N0。⚠️文件名带 stage2 是历史遗留，非 `04` 的 Stage 2 | 改跟踪逻辑 / 验证两条径持续输出前必读 | 🟡 原型 |
| — | `USAGE_B1I.md` | B1I 专用早期操作手册（多径扫描 + 双路径跟踪的第一版流程） | 只在翻 B1I 早期 conf 时参考 | ⚪ 早期·大部分被 `06` 取代 |
| 08 | `08_field_triage_runbook.md` | **★现场排查 runbook★** 从“噪声谱面”到“可信多径检出”的门禁式逐步流程：单星干净捕获→假警基线→导线注入→几何自检→距离阶梯 | **拿到设备手动排查/改进前必读** | ✅ 权威 |
| 09 | `09_academic_reference_multipath_algorithms.md` | **★学术参考/算法笔记★** MEDLL、CADLL、RAKE、多特征 LOS/NLOS 分类等论文的工作、可借鉴点、对当前卡点的启发和待讨论问题 | 暂停调参、准备算法改造/和 Claude 讨论论文前必读 | 🟡 持续更新 |
| 10 | `10_branch_cleanup_handoff_20260724.md` | **★分支/数据目录交接★** v0.1 后研究分支、`build/` 不再入 Git、NUC 实验数据目录规范：`~/lya/gnss_data/{raw,logs,outputs,analysis}` | 切分支、同步 NUC、保存采集数据前必读 | ✅ 冻结 |
| 11 | `11_dense_tracking_correlator_export.md` | **dense tracking correlator export 开发记录**：跟踪域密集复数相关器导出，用于 MEDLL/CADLL 离线拟合和参考相关函数标定 | 开发/验证 dense correlator dump 前必读 | 🟡 开发中 |
| 12 | `12_phaseb_path0_diagnostic_report_20260729.md` | **Phase B path0 诊断报告**：真实 delay-Doppler 图、faithful path0 synthetic、path0 removal 结果、移动接收机轨迹分离重构建议 | 和 Claude 讨论 Phase B 下一步算法方向前必读 | 🟡 新增 |
| 13 | `13_trackb_moving_trajectory_prototype.md` | **Track B 移动接收机轨迹原型**：几何驱动双源生成、delay-Doppler 候选、物理连续性轨迹提取、faithful synthetic 正负对照 | 继续移动场景算法或设计真实移动采集前必读 | 🟡 原型通过 |
| 14 | `14_trackb_postcorrelation_ekf.md` | **Track B 相关域 EKF 基线**：delay/rate 状态、条件线性复幅度、多假设初始化、协方差与可靠性门禁 | 继续概率跟踪、RBPF 或真实移动采集前必读 | 🟡 离线基线通过 |
| 15 | `15_trackb_cross_reference_benchmark.md` | **Track B 跨纹理评测**：23 组真实 A-only 纹理、7 个 PRN、DP/EKF 正负对照、跨 PRN 泛化边界 | 判断 Track B 是否可进入真实移动采集、定位纹理依赖前必读 | 🟡 可行但未泛化 |
| 16 | `16_static_four_antenna_space_time_plan.md` | **静态四天线空间-时延路线**：四通道同步与校准、共同载波参考、实测阵列流形、联合 GLRT/ML、0.5 chip 分阶段验收 | 开发四通道采集或开展静态阵列实验前必读 | 🟡 规划完成 |
| 17 | `17_l5_dualpath_productization.md` | **GPS L5 Dual-Path Receiver v1 产品化主记录**：冻结范围、C++链路审计、质量状态机、静态配置、测试与打包门禁 | 在产品分支开发、验收或发布前必读 | 🟡 开发中 |
| 18 | `18_l5_dualpath_product_review.md` | **L5 Dual-Path v1 独立审查报告**：BLOCK_RELEASE 裁决、3 条 BLOCKING（失联后假 RELIABLE / 负对照配置无效 / 发布包目标机不符）、10 条 MAJOR 与精确修改要求、证据-宣传对照表 | 修复产品分支或再次提交发布前必读 | ✅ 冻结 |
| 19 | `19_l5_dualpath_release_blocking_fix_round1.md` | **L5 Dual-Path v1 发布阻断修复 Round 1**：B-1/B-2/B-3 根因与修复、NUC `run_tests`、单/双源回放、发布包自校验和剩余验证缺口 | Claude 第二轮审查或继续产品验收前必读 | 🟡 CODE_COMPLETE |
| 21 | `21_tunnel_das_balance_tool.md` | **隧道 DAS 双端覆盖测量与功率配平工具**：测点输入、END_A/END_B 物理身份关联、`TUNNEL_DAS_STATUS` 实时输出、中点 UNRESOLVED 边界、单测与集成编译结果 | 现场做隧道双端覆盖测量或改身份判据前必读 | 🟡 待射频实测 |
| 22 | `22_tunnel_das_software_completion.md` | **Tunnel DAS 软件收尾与硬件交接**：空历元时钟根因、掉线/重捕获语义、时序集成测试、配置自检、B210/replay 入口与硬件验收缺口 | 下一次拿到 NUC + B210 + 双端设备前必读 | 🟡 待硬件验证 |
| 23 | `23_停车场四阵元线阵圆阵方阵对比与选型.md` | **停车场四阵元几何与算法仿真**：ULA/UCA/2×2 方阵的全场空间相干、安装角扫描、直接 MUSIC/合法平滑能力 | 讨论候选几何和相干 DOA 算法时参考；不能单独据此定型 | 🟡 理想几何结果；制作结论暂缓 |
| 24 | `24_方阵GNSS相干双源分离文献证据审查.md` | **方阵 GNSS 双源文献证据审查**：2×2 SAGE/STAP、MUSIC/波束形成、二维空间平滑阵元下限，以及本项目 GLRT/重构/门控的证据等级 | 决定方阵算法复现路线或制作天线前必读 | ✅ 文献边界已核对 |
| 25 | `25_方阵SAGE_STAP与线阵FBSS公平复现报告.md` | **方阵 SAGE/STAP 与线阵 FBSS 公平复现**：逐路径迭代、论文参数 Monte Carlo、同核同噪声停车场延迟/功率阶梯、ULA 半平面镜像边界 | 比较 ULA/2×2 或继续接入实测核前必读 | 🟡 理想核完成；实测核待补 |
| 26 | `26_四阵元线阵真实GNSS波形与FBSS仿真报告.md` | **四阵元 ULA 北斗 B2a 波形实验台**：B2a data/pilot 码、同源功分/线缆模型、C/N0 换算、直接 MUSIC 与 FBSS、复相关时延、公平 DOA 基准及 270 次球面波/有限距离失配扫描 | 制作 ULA 样机或讨论手机 C/N0 与阵列可分离性前必读 | 🟡 公平远场 DOA 30/30；有限距离容忍曲线已建立 |

> 图例：✅ 已成稿可用 · 🟡 进行中 · ⚪ 历史/已被取代 · ⬜ 未开始

---

## 2. 进度看板（Progress Board）

> **维护约定**：每完成一个里程碑，更新这一节 + 在 `05_pitfalls_and_decisions_log.md` 追加一条。
> 只改这里和相关的那一篇，不要动无关文档，省 token。

**当前阶段：`Phase A 单源参考库(L5)已建 ✅ → Phase B 静态快照分离墙已量化 🟡 → Track B 移动轨迹 DP + 相关域 EKF faithful synthetic 已通过 🟡 → 23 组跨纹理评测确认可行但仍有 run 依赖 🟡 → 真实移动采集待验证 🔴`（Phase B 全程与权威目标定义见 `11`；Track B 见 `13`/`14`/`15`）**

🎯 **Phase B 量化分辨率目标（双模式 · 2026-07-29 重构 · 权威定义见 `11`/`13`/`15`）**——静态同码同钟快照亚码片分离已实测确认为**欠定的墙**(`12`：三种快照架构同样失败、path1 埋于 path0 残差下约 30 dB)；最低目标的真正归宿是**运动模式**(接收机运动=合成孔径，`13`/`14`)：
- **静态模式（诚实的墙）**：只报**可分离下限 + 不确定度**。分离径(>~1.5 chip)可信；亚码片静态**报"不可分/多解"**，不硬输出第二径——这正是高挑战档"可靠地报不可分"的价值。
- **运动模式（最低目标归宿）**：真实硬件稳定分离 **Δτ=0.5 chip≈14.7 m**（2nd 径≥−6 dB、CN0≥43 dB-Hz、多相位；成功率≥90%、虚警≤5%、RMSE≤0.1 chip）。**现状(`15`)**：faithful synthetic 已证可行(PRN28 亚米级；静态/真负例正确拒绝)，但**23 组跨纹理仅 EKF 8/19 · DP 14/19，run/纹理依赖，尚未 cross-PRN 稳健**；真实 path0 逐历元纹理是主障碍。
- **较强 / 高挑战**：0.3 chip≈8.8 m（覆盖 −10 dB、置信区间+失败告警）；0.1–0.2 chip≈2.9–5.9 m（不强求全成，重在**明确报告可分/不可分/多解**）。
- **下一杠杆(`15`)**：纹理感知接收/初始化 + 失配感知 EKF 协方差 + 多假设一致性 + truth-free 置信门(轨迹最优–次优边距 + 运动/几何一致性)；**不是**再调阈值或再来一个快照算法。**纪律**：延迟接近注入值 ≠ 成功，须幅度+残差改善+条件数+采集质量同时过关。

> 📚 **2026-07-23 算法研究转向**：暂停继续盲调 `pfa/cn0_min/lock_fail` 等参数，新增 `09_academic_reference_multipath_algorithms.md` 作为 Codex/Claude 共用学术参考。当前论文梳理显示：近距/融合多径不应继续依赖 acquisition Top-2 峰，而应转向 tracking 域多相关器 + MEDLL/CADLL 类相关峰形参数估计；RAKE 捕获可作为候选初始化，多特征分类用于后续可信度判别。

> ✅ **2026-07-24 v0.1 gate 后清理**：NUC smoke test 已通过；当前算法研究线切到 `research/multipath-correlator-fit`。`build/` 已从 Git 跟踪移除并加入忽略，实验数据目录规范冻结为 `~/lya/gnss_data/{raw,logs,outputs,analysis}`，详见 `10_branch_cleanup_handoff_20260724.md`。

> 🟡 **Stage 2 进行中（2026-07-17→18，详见 `07`）**：改用 **GPS L5I**（谱峰面比 B1I 更易分远距多径）做最小双跟踪原型。已落地：① `Observables.dump_extended`（每通道 7→9 个 double，加 `signal_path`+`cn0_db_hz`）；② L5 双路径 conf + `make_l5_dualpath_conf.py`（多 PRN 通用化 / `--source uhd` 实时 / `--enable-monitor`）；③ `read_observables_dump.py` 兼容新旧格式、稳定 CSV/JSONL 字段；④ monitor-only 长跑方案（`watch_dualpath_monitor.py` 免 protobuf 依赖 + `gnss_synchro_monitor.cc` 改为“始终 consume、按抽样发送”）避免实时 overflow。**⚠️ C++ 改动仅过 Python 侧自测，尚需测试机 `build-conda` 完整编译 + B210/离线实跑验证。**

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
- [~] **架构A · L5 双路径持续跟踪原型（机制已落地，待测试机编译验证）**：`Observables.dump_extended`(9列) + `l5_dualpath_prn18.conf` + `make_l5_dualpath_conf.py`(多PRN/实时/monitor) + `read_observables_dump.py` + monitor-only 长跑方案。详见 `07`。⚠️ C++ 改动仅过 Python 自测，需 `build-conda` 完整编译 + B210/离线实跑。
  > 术语澄清：`07`（文件名带 stage2）实为**架构 A(捕获双峰)在 L5 上的持续跟踪 + observables/monitor 工程化**，并非 `04` 定义的 Stage 2（跟踪域多相关器）。近距 <1 码片多径的**多相关器分解仍未动**。
- [ ] 🔴 **真实环境第二峰噪声化攻关（2026-07-18 双模拟器实测暴露）**：50m/等功率/CN0 35-40 场景下，`find_second_peak` 在宽窗内选到的"第二峰"随机游走(Δ从-2600m到+2400m)，`valid_positive_has2=0`。需收窗+时间一致性判据+单路基线标定，详见 `05` 2026-07-18。
- [ ] ⏳ **连续统计 + 单路校准**：对 `+200m/+1000m/+1030m` 每组连续采 5 次，统计 `abs(Δm)` 均值/方差；必要时分别单开两台模拟器验证码相位差。
- [ ] absl 日志下 `MULTIPATH` 可见性微调（验证多径时一并处理）。
- [ ] **架构 B**：跟踪域多相关器（近距<1码片多径，MEDLL/峰形拟合，研究级，`04` 的 Stage 2）；**Stage 3**：LOS 判别 + PVT 整合。
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

*最后更新：2026-07-18 · 3D 谱面确认现场根本没干净捕获→新增 `08` 现场排查 runbook(门禁式) + `acq_health.py`/`multipath_consistency.py` 两个判定脚本 · Stage 2 L5 原型 + 索引对齐 · Codex/Claude 协同维护*
