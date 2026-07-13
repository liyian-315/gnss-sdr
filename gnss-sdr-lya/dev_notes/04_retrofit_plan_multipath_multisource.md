# 04 · 改造方案：每卫星双径捕获+跟踪，用于提升定位（已定向 🟢）

> 本篇是**行动纲领**。方向已随用户 3 项决策锁定（见 §0）。每完成一个 Stage，更新 README 进度看板 + `05` 日志。
> 动手前读本篇 + 文档 02（捕获核心）+ 文档 03（数据结构）。

## 本篇小目录
0. 已锁定的决策 & 一个关键认知（必读）
1. B1I 速查表（改造前先记住这些数）
2. 总体架构：A（捕获双峰）+ B（跟踪多相关器）+ PVT 整合
3. Stage 0：环境 + 数据 + 观察（前提，当前阻塞点）
4. Stage 1：架构 A —— 捕获搜 Top-2 峰 + 跟踪两条径
5. Stage 2：架构 B —— 跟踪域多相关器分辨近距多径
6. Stage 3：PVT 整合 —— 把双径变成"更好的定位"
7. 前提与风险清单

---

## 0. 已锁定的决策 & 一个关键认知

**用户 3 项决策（2026-07-12）**：
1. **最终用途 = 提升定位精度** → 两条径要影响 PVT，**必须处理下游 RTKLIB 同 PRN 冲突**。
2. **两径间隔 = 近距 + 远距都要覆盖** → 捕获域（A）只能分远距（>1 码片）；**近距（<1 码片）必须上跟踪域多相关器（B）**。
3. **原型信号 = BeiDou B1I**。

> ⚠️ **关键认知（务必理解，否则方向会错）**：
> "跟踪两条径来提升定位"**不等于**"把两条径的两个伪距都塞进 PVT 解算"。
> 反射径（NLOS）的伪距是**偏长的**，直接当独立观测量喂给解算器只会**让定位更差**。
> 正确做法：跟踪两条径 → **判别哪条是直射（LOS，通常最早到达的那条）** → 用直射径（或经多径参数**校正后**的伪距）
> 进 PVT，**每颗卫星最终只给解算器一条干净观测量**；第二条径用于"判别 + 校正 + 分析"，不是独立定位输入。
> 这也顺带说明：RTKLIB "同 PRN 覆盖" 的行为，其实和"每星一条观测量"的物理需求是一致的——我们本就不该塞两条进去。
> （若用户确实想要"两条独立观测量进解算"，那是另一种设计，一般对精度不利，需另行确认。）

---

## 1. B1I 速查表

| 参数 | 值 | 出处 / 含义 |
|------|----|-----------|
| 码率 | 2.046 Mcps | `Beidou_B1I.h:33` |
| 码长 | 2046 chips | `:34` |
| 码周期 | 1 ms | `:38` |
| **1 码片 ≈ 146.6 m** | — | 近距/远距多径的分界线 |
| 捕获推荐采样率 | 10 MHz | `:37`（示例 conf 里实际用 25 MHz） |
| NH 二级码 | 20 bit / 20 ms | `:41`（D1 信号 MEO/IGSO 有；D2/GEO 无）——跟踪比特同步相关 |
| 示例 conf 内部采样率 | 25 MHz | conf 里 `internal_fs_sps`，→ **~12.2 样点/码片** |
| 捕获 dump | 已开 (`./bds_acq*.mat`) | conf `Acquisition_B1.dump=true` |
| 捕获核心 | 复用 `pcps_acquisition` | 适配器 `beidou_b1i_pcps_acquisition.cc` 很薄，改核心即生效 |
| 跟踪核心 | `dll_pll_veml_tracking` | 适配器 `beidou_b1i_dll_pll_tracking.*` |

---

## 2. 总体架构：A + B + PVT

```
                 ┌──────────────── 一个卫星通道（扩展后）─────────────────┐
 采样 → 捕获(PCPS)│  Stage1-A: 搜 Top-2 峰                                  │
                 │     ├─ 峰1(直射候选) → 跟踪器1 ─┐                        │
                 │     └─ 峰2(反射候选) → 跟踪器2 ─┤                        │
                 │  Stage2-B: 跟踪器内多相关器重建相关函数 → 近距多径分解    │
                 │                               ↓                        │
                 │              Stage3: LOS 判别 + 多径校正                 │
                 └───────────────────────────────┬────────────────────────┘
                                                  ↓ 每星一条"干净/校正"观测量 (+ 第二径信息旁路)
                                        Observables → PVT(RTKLIB) → 定位
```

- **A** 负责"看得见的两个峰"（远距、可分），也是用户设想的直接实现，产出快、易验证。
- **B** 负责"糊在一起的近距多径"，是把双径真正转成定位增益的核心（MEDLL 思路）。
- **PVT 整合** 负责把 A/B 的判别结果变成"每星一条干净观测量"，解决同 PRN 冲突。

---

## 3. Stage 0：环境 + 数据 + 观察（**当前阻塞点：待用户装依赖**）

**目标**：能编译、能跑通库存接收机、能 dump 出真实相关面，先"看清"多径长什么样。

### 3.1 环境（WSL2）——已探明
- WSL2 **就绪**：Ubuntu 24.04.4 LTS，**20 核 / 11 GB 内存 / 919 GB 空闲**。默认发行版 `Ubuntu`。
- 依赖包在 apt 全部可得（gnuradio-dev 3.10 含 VOLK、armadillo、matio、protobuf、gflags/glog、boost、blas/lapack、gtest、mako、spdlog/fmt）。
- ⚠️ **sudo 需要密码** → 安装依赖这一步**必须用户执行**（或用户开免密 sudo 让 AI 全自动）。装完后 cmake/make/运行都**不需要 sudo**，可由 AI 驱动。
- **构建位置**：源码在 Windows 侧 `D:\...\gnss-sdr`，WSL 里是 `/mnt/d/work/project/usrp_gnss/gnss-sdr`。
  在此就地 build（`/mnt/d/...`）→ AI 在 Windows 侧改的代码 WSL 立即可见；缺点是 `/mnt/d` 跨文件系统 I/O 较慢（20 核可缓解）。
- **依赖安装命令**（用户在 WSL 跑一次）：见 README 或 `05` 日志 2026-07-12 记录的命令块。
- **构建命令**（依赖就绪后 AI 跑）：
  `cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF && cmake --build build -j20`
  运行：`./build/src/main/gnss-sdr --config_file=<conf>`（无需 install）。

### 3.2 数据（内置信号发生器）——已探明**重大限制**
- 内置 `Signal_Generator` **只支持 G(GPS)/R(GLONASS)/E(Galileo)，没有 C(BeiDou) 分支**
  （`signal_generator_c.cc` 三处生成循环 `:113/:173/:358` 均无北斗；适配器引 `Beidou_B1I.h` 仅用于算长度）。→ **它生成不了 B1I 测试数据**。
- ✅ **多径靠配置即可造**（无需改发生器）：发生器把每颗配置的星**叠加**进同一路输出（`:343-348`），
  每颗可独立配 `PRN / CN0_dB / doppler_Hz / delay_chips`。**给同一 PRN 配两条不同 `delay_chips`、不同 `CN0` 的信号 = 直射+反射双径**。
  但 `delay_chips` 是**整数**（`:360` 换算为样点）→ 只能造 **≥1 码片**的可分离多径（正好对应 Stage 1/架构 A）；
  **近距 <1 码片需要给发生器加"分数码片时延"**（Stage 2 再做）。
- **由此调整验证策略**（重要）：
  - Stage 1a 的核心改动在 `pcps_acquisition`，是**信号无关**的 → **先在 GPS L1 C/A 仿真多径上验证**（发生器完整支持），
    算法验证通过后**自动适用于 B1I**。
  - B1I 专项验证：随后**给发生器加 BeiDou B1I 分支**（复用 `beidou_b1i_signal_replica`，仿 Galileo/GPS 分支，改动可控），或将来用真实 B1I 数据。
  - **结论：目标仍是 B1I，但"先 GPS L1 验核心、再扩发生器验 B1I"，共享核心改动零浪费。**

### 3.3 Stage 0 清单
- [ ] 用户在 WSL 装依赖（sudo）
- [ ] AI：cmake 配置 + 编译**库存源码**（先确认源码树能干净编译、工具链通）
- [ ] AI：用 `Signal_Generator` 造 **GPS L1 C/A 单径**数据，跑通库存接收机（验证端到端 + dump 相关面）
- [ ] AI：造 **GPS L1 C/A 双径**数据（同 PRN 两条 delay_chips），dump 相关面**观察两个峰**（为 Stage 1a 准备基准）

**验证**：库存接收机能在 GPS L1 仿真数据上正常捕获/跟踪/定位，并 dump 出相关面 `.mat`。

---

## 4. Stage 1：架构 A —— 捕获搜 Top-2 峰 + 跟踪两条径

> 这是用户设想的直接实现，处理**可分离（>1 码片）**的两条径。拆成 1a（易、可视）+ 1b（plumbing）降风险。

### Stage 1a · 捕获检测并报告 Top-2 峰（低风险、先出成果）
改 `pcps_acquisition.*` + `acq_conf.*`：
- **加配置项**（文档 03 §2"三处齐动"）：如 `num_peaks`(默认1) 或 `multipath_acq=true`。
- **新增 `find_top2_peaks()`**：复用 `first_vs_second_peak_statistic` 里"排除主峰 ±1 码片再找次峰"的现成逻辑
  （`pcps_acquisition.cc:484-519`），返回两个峰的 (doppler, code_phase, 峰值/统计量)。
- **扩展 `AcquisitionResult`**：容纳第二个峰（第二 doppler / 第二 code phase / 第二统计量）。
- **报告 + dump**：先在日志/`.mat` 里输出两个峰（`dump_results` 已写 grid，加两峰坐标即可）。
- **验证**：跑通后看 dump——每星是否稳定给出两个峰、间隔多少码片、第二峰强度。**此步不动跟踪，纯观测**。

### Stage 1b · 把第二个峰接到第二个跟踪器（plumbing，较重）
本质要"一次捕获 → 播种两个跟踪实例"。三种落地方式，**倾向 A-i**：
- **A-i（扩展 Channel，推荐）**：让 `Channel` 持有 `acq + trk1 + trk2 + synchro1 + synchro2`；捕获成功时
  峰1→synchro1、峰2→synchro2，FSM 同时 `start_tracking` 两个跟踪器。两路输出各自下行。
  - 改：`channel/adapters/channel.*`、`channel/libs/channel_fsm.*`、捕获报告两结果的接口。
  - 优点：两条径同属一颗星、同一通道，便于 Stage 3 做 LOS 判别；不动 flowgraph 的 PRN 池。
- **A-ii（两个固定 PRN 通道，快速原型 hack）**：conf 里把两个通道钉同一颗星（现配置就是固定 PRN 模式），
  但需让"第二通道"的捕获排除峰1区域取峰2——存在**跨通道协调难题**（两个独立捕获默认都取峰1）。仅作快速试验备选。
- **A-iii（独立通道 + PRN 池改造）**：改 `gnss_flowgraph.cc`（`remove_signal`、`search_next_signal` 的 pop）
  允许同 PRN 双通道。**不推荐**（协调难题依旧 + 池改造）。见 `05` 日志。

**验证**：两个跟踪器分别锁定两个峰，各自输出 `Code_phase_samples`/伪距；dump 跟踪环看两路是否稳定。

---

## 5. Stage 2：架构 B —— 跟踪域多相关器分辨近距多径

> 处理**近距（<1 码片）**多径——捕获域根本分不开的情形。是把双径转成定位增益的核心。

- **加密相关器抽头**：`dll_pll_veml_tracking` 的相关器是 N 抽头可扩展（当前 3/5，`:611-652`）。
  增大 `d_n_correlator_taps`、扩 `d_local_code_shift_chips[]`（在 ±1.5 码片内布多个抽头），即可**重建相关函数形状**。
  相关器实现 `cpu_multicorrelator_real_codes.*` 的 VOLK 核随抽头数线性扩展，改动机械。
- **多径估计**：用重建的相关函数做 MEDLL / 峰形拟合 / double-delta 等，分解出直射 + 反射的 (幅度, 时延, 相位)。
- **输出**：直射径的**校正后**码相位/伪距 + 多径参数（供 Stage 3 与分析）。写入 `Gnss_Synchro` 新增字段（文档 03 §4：末尾加、给默认值）。
- **验证**：对已知多径的仿真数据，检验估计出的时延/幅度是否接近真值；校正后伪距残差是否下降。

> ⚠️ Stage 2 需要先**通读 tracking**（当前尚未细读，README 待办已列）。算法偏研究，建议在 Stage 0 看清数据后再决定深度。

---

## 6. Stage 3：PVT 整合 —— 把双径变成"更好的定位"

- **LOS 判别**：综合"最早到达 + 强度 + 相关对称性 + 跟踪稳定性"判定哪条是直射径。
- **给 PVT 的观测量**：每颗卫星**只送一条**——直射径 或 多径校正后的伪距——**天然避开 RTKLIB 同 PRN 覆盖问题**。
  第二径信息与多径指标走**旁路**（Gnss_Synchro 新字段 / monitor / dump）供分析与质量控制，不进解算器的 obsd_t。
- **可选加权**：把多径质量指标接入 RTKLIB 的观测权重（down-weight 受多径污染的星）。
- **相关文件**：`observables/gnuradio_blocks/hybrid_observables_gs.*`（按 Channel_ID，不冲突）、
  `PVT/gnuradio_blocks/rtklib_pvt_gs.*`、`PVT/libs/rtklib_solver.cc`（obsd_t 装配，冲突点，见 `05` 日志）。
- **验证**：对比"改造前 vs 后"的定位残差/精度（有真值或长时静态点最好）。

---

## 7. 前提与风险清单

| 项 | 说明 | 影响 |
|----|------|------|
| **Windows 编译** | GNSS-SDR 原生 Windows 极难，通常需 WSL2/Linux + 一堆依赖(GNU Radio/VOLK/Armadillo/gflags…) | 阻塞一切验证，**优先解决** |
| **B1I 数据** | 示例 conf 指向 Linux 路径的特定数据集；用户是否有？ | 无数据无法验证；可考虑 signal_generator 造带多径仿真 |
| **近距多径难度** | Stage 2 的 MEDLL/多相关器估计是研究级 | 工期与效果不确定，建议 Stage 0 看清数据后再评估 |
| **改动扩散** | Gnss_Synchro 加字段影响序列化/monitor（文档 03 §4）；Channel/FSM 改动是共享基础设施 | 小步、加末尾字段、每步可回退 |
| **实时性** | 多相关器 + 双跟踪器增加算力 | 离线 File_Source 无碍；实时/FPGA 暂不碰 |

---

## 待办小结（滚动更新，细节见 README 进度看板）
- [ ] Stage 0：定编译路线（WSL?）、确认/准备 B1I 数据、跑通 dump 观察相关面
- [ ] Stage 1a：捕获 Top-2 峰检测 + dump（先出成果）
- [ ] Stage 1b：第二峰 → 第二跟踪器（倾向 A-i 扩展 Channel）
- [ ] Stage 2：跟踪多相关器（先读 tracking）
- [ ] Stage 3：LOS 判别 + PVT 整合

---

*最后更新：2026-07-12 · 用户 3 项决策后定稿 · 待 Stage 0 环境/数据落实后进入实施*
