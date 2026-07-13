# 05 · 踩坑与决策日志（按日期追加）

> **追加式**日志：新条目加到最上面（倒序，最新在前）。记录三类东西：
> - 🧭 **决策**（Decision）：为什么这么做，考虑过哪些方案。
> - 🕳️ **坑**（Pitfall）：遇到的问题、原因、解法/绕法。
> - ❓ **疑问**（Open Question）：暂未解决、需后续确认的点。
>
> 维护提示：**只往这里追加**，不改历史条目；避免每次都要重读全部文档，省 token。

---

## 2026-07-12

### ✅ 工具就绪：面向真实 B1I 数据的多径检测 + 双路径跟踪（明天可直接用）
**背景**：用户明天采真实 B1I 数据；今晚把工具做到"换数据路径即用"。真实数据走 `File_Signal_Source`（不经内置发生器），故"发生器不支持 B1I"无影响；多径检测在共享 `pcps_acquisition` 核心，B1I 直接受益。

**代码改动④（多径巡检日志）**：`send_positive_acquisition` 加 `LOG(INFO)`——每颗有第二径的卫星打印
`MULTIPATH <sys> <PRN>: 2nd path at X chips (main Y, delta Δ), power ratio Z dB, 2nd Doppler`。
⚠️ **glog 的 INFO 默认写文件不上屏 → 运行加 `GLOG_logtostderr=1` 才能在屏幕看到**（控制台的 "Tracking..." 是 cout，另一回事）。

**交付物（都在 `dev_notes/`）**：
- `USAGE_B1I.md`：明天的操作手册（改数据参数→跑 survey→读日志/分析→双路径跟踪→调参→局限）。
- `sim/bds_b1i_multipath.conf`：多径**扫描**（自动搜星，每星打印多径）。
- `sim/bds_b1i_dualpath.conf`：对指定 PRN **双路径跟踪**（成对固定通道，奇数通道 acquire_second_path）。
- `sim/analyze_multipath.py`：读 dump 出多径表（`--code-length 2046` 给 B1I；GPS 用 1023），自动按码长换算码片/米。

**校验（无真实数据，用假噪声文件烟测）**：B1I 全 12 通道正常构建、多径参数被接受、管线跑到 EOF 无错、退出码 0。
GPS L1 双径 sim 上多径日志实测正常（delta≈6码片、ratio≈4.6dB）。analyze_multipath.py 在 GPS dump 上验证出表。

### 🕳️ 坑：conditioner 的 DataTypeAdapter 必须匹配 item_type（烟测抓到）
- 初版 B1I 配置误把 `DataTypeAdapter=Pass_Through` 接 `byte` 数据 + `Freq_Xlating(input=short)` → `itemsize mismatch` 连接失败。
- 正解：`byte→Byte_To_Short`、`ishort→Ishort_To_Complex`、`gr_complex→Pass_Through`。已在两个 B1I 配置修正并加注释。
- 教训：**无真实数据也要用假文件烟测配置**，能提前抓出连接/类型错误。

### 🕳️ 补充：内置发生器 `data_flag=true` 也救不了持续跟踪
- 试 `data_flag=true`：跟踪照样反复丢锁，且无可解码电文（无 NAV message/PVT）。确认是**发生器保真度**问题，非数据位问题。
- → "双伪距→PVT/定位"必须靠**真实数据**（或高保真仿真）。这与"B1I 需真实数据"合流。

### ✅ Stage 1b 机制打通：两个通道同 PRN，分别跟踪直射/反射（零改 flowgraph/channel/FSM）
**关键调研结论**（Explore agent + 读码）：
- **两通道可跟同一 PRN，纯配置即可**：`Channel0.satellite=1`+`Channel1.satellite=1`+`Channels_1C.count=2`+`Channels.in_acquisition=2`。
  固定通道（satellite≠0）**不从 pool 抽取**，故通道0捕获成功时的 `remove_signal` 不影响通道1（`gnss_flowgraph.cc` assign_channels/acquisition_manager）。发现有 `duplicated_satellites_test`（利好 Stage 3）。
- **按通道配置捕获**：工厂 `get_role_name`(`gnss_block_factory.cc:236`)——`Acquisition_1C1` 仅当其 `.implementation` 存在时启用，
  **且不继承共享 `Acquisition_1C` 参数**（per-channel 块要写全）。

**代码改动③（Stage 1b，仍全在捕获层）**：
- `acq_conf.h/.cc`：加 `acquire_second_path`(bool)
- `pcps_acquisition.cc` 三处：① `acquire_second_path` 也触发 `find_second_peak`；② `update_synchro` 在该模式下把**第二峰**(index_time2/doppler2)写入 `Acq_delay_samples/Acq_doppler_hz` 交给跟踪；③ `acquisition_core` 判定：该模式下以 `has_second_peak` 为正捕获条件（无第二径不跟幽灵）。假定 `make_2_steps=false`。

**验证（`dev_notes/sim/gpsl1_2ch.conf`，脚本 `verify_stage1b.py`）**：
- 冷启动首份 dump：**通道0 交跟踪 355.0chip（直射）；通道1 交跟踪 361.1chip（反射）** ——两通道各锁一条径。
- 控制台：channel 0 与 channel 1 **同时都在 Tracking PRN 01**。
- 结论：**每卫星双径同时跟踪的机制打通**，零改 flowgraph/channel/FSM/tracking。

### 🕳️ 局限：仿真数据下产不出稳定伪距（跟踪反复丢锁）
- `data_flag=false` 无导航电文 → 电文解不出 TOW → **无伪距/PVT**；且发生器保真度有限 → 跟踪反复 Loss-of-lock 重捕。
- 影响：Stage 1b 的**机制**已验证，但"稳定输出两条伪距→进 PVT"需**更好的信号**：`data_flag=true` 的发生器 或 **真实数据**。与"B1I 需真实数据/扩展发生器"是同一问题。
- 待办：试 `data_flag=true` 看能否持续锁定出电文；或推进"给发生器加 B1I + 更真实信号"。
- 小遗留：dump 的第二峰变量目前只在 `multipath_detection` 下写；`acquire_second_path` 通道的 dump 里 has2/delay2 为空（不影响结果，acq_delay_samples 已正确）。可后续把 dump 门控也加上 `acquire_second_path`。

### ✅ Stage 1a 完成：捕获检测并报告第二径（多径），GPS L1 仿真验证通过
**代码改动②（对捕获核心的第一次实质修改，信号无关，B1I 同样受益）**：
- `acq_conf.h/.cc`：新增 3 个配置项
  - `multipath_detection`(bool, 默认 false)：开关
  - `multipath_max_delay_chips`(float, 默认 5)：主峰邻域搜索窗（±码片）
  - `multipath_threshold_fraction`(float, 默认 0.3)：第二峰判定门限 = 该比例 × 主峰 CFAR 门限
- `pcps_acquisition.h`：`AcquisitionResult` 加 `has_second_peak/index_time2/doppler2/test_statistics2/peak_ratio`；声明 `find_second_peak()`
- `pcps_acquisition.cc`：
  - 新增 `find_second_peak()`：定位主峰所在多普勒 bin → 在**同 bin**、主峰 **±window 码片**内、**排除 ±1 码片主瓣**后取次高点 = 第二峰；
    记录位置/多普勒/`ts2=mag2/input_power`/`peak_ratio=mag1/mag2`；`has_second_peak = ts2 > fraction×get_threshold()`
  - `acquisition_core` 在 `compute_statistics()` 后调用（仅非 step_two）；纯检测/记录，**不改跟踪交接**（那是 1b）
  - `dump_results` 加 `has_second_peak/acq_delay_samples_2/acq_doppler_hz_2/test_statistic_2/peak_ratio`；`log_acquisition` 加第二峰日志

**验证（配置 `dev_notes/sim/gpsl1_1sat.conf` 单径 / `gpsl1_2path.conf` 双径，分析脚本 `verify_stage1a.py`）**：
- 双径(直射355chip/50dB + 反射361chip/45dB，间隔6码片)：**每份 dump 都 has2=1，第二峰稳定在主峰+6码片、同多普勒**；#1 主峰355.0/第二峰361.1，与生成值分毫不差。ts2=31–68，peak_ratio=2.4–4.1。
- 单径(仅355chip)：**每份 has2=0**（窗内次高点只是噪声，ts2=6–13，peak_ratio=10–23）。
- 结论：算法能**判别多径 vs 单径**，不是"总能凑个次峰"。

### 🕳️ 坑：第二峰门限**不能用主峰门限**（第二径本就更弱）
- 反射比直射弱 5dB → ts2(反射)=30–65 却 < 主峰 CFAR 门限(=106.3, max_dwells=10)。用 `get_threshold()` 直接判会把真反射全判 0。
- **对策**：门限取主峰门限的**一个比例** `multipath_threshold_fraction`。数据：噪声 ts2≤17、反射 ts2≥30 → 取 **0.2×门限≈21** 稳妥分开（默认 0.3 偏严，-5dB 反射在噪声波动下会漏；测试配置里设 0.2）。**这是可调灵敏度旋钮**，弱多径可再降。
- 记录数值：threshold=106.3；单径主峰 ts=152、ts2=7；双径主峰 ts=165、ts2=65、peak_ratio=2.5。

### 🕳️ 坑：Python heredoc 里中文/f-string 转义易碎 → 一律写 `.py` 脚本文件跑
- `dev_notes/sim/` 下：`analyze_peaks.py`(相关面top峰)、`verify_stage1a.py`(第二峰变量)、`show_thresh.py`(门限/统计量)。

### ✅ Stage 0 完成：环境编译通过 + 仿真数据链路打通 + 双径可分辨验证
**环境**：WSL2 Ubuntu24.04，`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF` 配置通过；
`cmake --build build -j20` 编译成功（**坑**：首次用 `nohup &` 在 WSL 内跑被 SIGHUP 杀；改用工具的 `run_in_background` 保活 wsl.exe 进程即可）。产物 `build/src/main/gnss-sdr`（v0.0.21）。

**代码改动①（我们对仓库的第一处修改）——注册内置信号发生器为可用 SignalSource**：
- 目的：内置发生器没进工厂（`GetSignalSource` 无此实现），无法在 `.conf` 里用。注册后可造仿真数据。
- 改了 3 个文件 4 处：
  1. `src/algorithms/signal_generator/adapters/signal_generator.h`：基类 `GNSSBlockInterface`→`SignalSourceInterface`，
     include 换成 `signal_source_interface.h`，实现 `getRfChannels(){return 1;}`（该接口唯一多出的纯虚方法）。
  2. `src/core/receiver/gnss_block_factory.cc`：加 `#include "signal_generator.h"` + `else if (implementation=="Signal_Generator") return make_unique<SignalGenerator>(...)`。
  3. `src/core/receiver/CMakeLists.txt`：`core_receiver` 链接列表加 `signal_generator_adapters`。
- 增量重编通过，`SignalSource.implementation=Signal_Generator` 可用。

**验证数据链路（配置见 `dev_notes/sim/`）**：
- `gpsl1_1sat.conf`：单星 GPS L1 PRN1，捕获成功，dump 出相关面 `.mat`。用 h5py 读 `acq_grid`(40×4000=doppler×code)，
  峰值 `acq_doppler_hz=1500`、`acq_delay_samples=1388`(=355chip×4000/1023)，与生成参数**完全吻合**。分析脚本 `dev_notes/sim/analyze_peaks.py`。
- WSL 有 `python3 + h5py 3.10 + numpy 1.26`，可直接分析 dump。

### 🕳️ 关键发现：捕获"次峰"检测受**噪声底**限制 → 直接影响 Stage 1a 设计
- 单径信号（无反射）相关面里也有 ~-5dB 的伪峰 → 是**噪声底**不是反射。理论对得上：CN0=45dBHz/1ms/单积分 → 峰噪比~15dB，4000点最大噪声峰~主峰下 -3~-5dB。
- 后果：**天真地"全局找第二高峰"会选到噪声/伪峰，不是反射**。
- **对策（已验证有效）**：① 提高积分（`max_dwells=10` 非相干积分把噪声底压低~10dB）；② 提高 CN0；③ Stage 1a 里应在**主峰邻域内**找第二峰（多径是同星延迟副本，码相位近、同多普勒），而非全局。
- **验证成功的双径配方**（`gpsl1_2path.conf`）：同 PRN1 两条径，直射 CN0=50@355chip、反射 CN0=45@361chip、`max_dwells=10`
  → 直射峰 355.0chip(1.27e13)、**反射峰 360.9chip(4.36e12) 成为干净的第二峰**（高出噪声底 3.3×，幅度比 -4.6dB≈设定 -5dB）。

### 🕳️ 坑：内置信号发生器**不支持 BeiDou**（只 G/R/E）
- `signal_generator_c.cc` 三处生成循环（`:113/:173/:358`）只有 `system=="G"/"R"/"E"`，**无 "C" 分支**；适配器引 `Beidou_B1I.h` 仅用于算 `vector_length`。
- 影响：**用内置发生器造不出 B1I 仿真数据**。
- **对策**：Stage 1a 核心改动信号无关 → **先在 GPS L1 C/A 仿真多径验证**，再给发生器加 B1I 分支（复用 `beidou_b1i_signal_replica`）或用真实数据。目标仍是 B1I。

### 🧭 技巧：多径仿真数据"靠配置就能造"（无需改发生器，限 ≥1 码片）
- 发生器把每颗配置的星**叠加**进同一路输出（`:343-348`），每颗可独立配 `PRN/CN0_dB/doppler_Hz/delay_chips`。
- **给同一 PRN 配两条不同 `delay_chips`、不同 `CN0` 的信号 = 直射+反射双径**。
- 限制：`delay_chips` 是整数（`:360`），只能造 **≥1 码片**可分离多径（对应架构 A）。近距 <1 码片需给发生器加分数码片时延（Stage 2）。

### 🕳️ 坑：WSL 里 **sudo 需要密码** → 依赖安装须用户执行
- AI 无法非交互 apt 安装。装完依赖后 cmake/make/运行**不需要 sudo**，可由 AI 驱动。
- 备选：用户开免密 sudo 则 AI 可全自动。
- **依赖安装命令（Ubuntu 24.04，已核验包名均可得，仅 `libgnutls-openssl-dev` 缺→用 `libssl-dev` 代）**：
  ```bash
  sudo apt update && sudo apt install -y \
    build-essential cmake git pkg-config \
    gnuradio-dev libboost-all-dev \
    libarmadillo-dev libgflags-dev libgoogle-glog-dev \
    libmatio-dev libpugixml-dev libprotobuf-dev protobuf-compiler \
    libblas-dev liblapack-dev libgtest-dev python3-mako \
    libpcap-dev libspdlog-dev libfmt-dev libssl-dev
  ```
- 环境已探明：WSL2 Ubuntu 24.04.4，20 核/11GB/919GB 空闲；源码在 WSL 路径 `/mnt/d/work/project/usrp_gnss/gnss-sdr`（就地 build，`/mnt/d` I/O 偏慢但可接受）。
- 构建：`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF && cmake --build build -j20`；运行 `./build/src/main/gnss-sdr --config_file=<conf>`。

### 🧭 决策锁定：目标 B1I / 提升定位 / 覆盖近距+远距 → 三阶段方案
- **用户 3 项回答**：① 用途=**提升定位精度**；② 两径间隔=**近距+远距都要**；③ 原型信号=**BeiDou B1I**。
- **推导出的方案骨架**（详见文档 04 定稿）：
  - **A（捕获搜 Top-2 峰）**：处理远距(>1码片)可分离两径，贴合用户设想，先做、易验证。拆 1a(捕获报告两峰) + 1b(接第二跟踪器，倾向 A-i 扩展 Channel)。
  - **B（跟踪域多相关器）**：处理近距(<1码片)多径，捕获域分不开，必须做；MEDLL/峰形拟合，研究级。
  - **PVT 整合**：每星只送一条干净/校正观测量，天然避开 RTKLIB 同 PRN 覆盖。
- **B1I 关键数**：码率 2.046Mcps / 码长 2046 / 周期 1ms / **1码片≈146.6m** / 示例 conf 用 25MHz(~12.2样点/码片) / NH 二级码 20bit / 捕获 dump 默认开。

### 🧭 关键认知：提升定位 ≠ 把两个伪距都塞进 PVT
- 反射径(NLOS)伪距**偏长**，作为独立观测量喂解算器会**恶化**定位。正解：双径→判别直射(LOS)→每星**一条**干净/校正伪距进 PVT，第二径走旁路做分析/校正/加权。
- 推论：RTKLIB "同 PRN 覆盖"其实与"每星一条观测量"的物理需求一致，不是纯障碍。**若用户真要两条独立观测进解算需再确认**（一般不利精度）。

### 🕳️ 坑（环境层，未踩先防）：Windows 编译 + 数据缺失
- 用户在 **Windows 11**，但 GNSS-SDR 原生 Windows 编译极难（依赖 GNU Radio/VOLK/Armadillo/gflags 等），通常需 **WSL2/Linux**。
- 示例 conf `gnss-sdr_BDS_B1I_byte.conf` 的数据指向 Linux 路径 `/archive/BDS3_datasets/BdsB1IStr01.dat`（byte,25MHz,IF≈6.25MHz），用户机器上大概率没有。
- **对策**：Stage 0 优先确认编译路线 + 数据来源（或用 signal_generator 造带多径仿真）；无数据时可先做 **Stage 1a 纯代码改造**，环境就绪再验证。
- 仓库现状：`main` 分支(v0.0.21 era)，**无 build 目录**（未编译），仓库内无采样数据。

### 🧭 需求明确 + 可行性调研：每颗卫星捕获两条径、同时跟踪各自伪距
- **用户需求（明确版）**：谱峰搜索时对每颗卫星找**强度最强的两条径（两个峰）**，**同时跟踪**这两条径，各自得到伪距等信息。
- **三点关键结论**（读码 + 3 个 Explore 定向调研，均有源码佐证）：
  1. **跟踪可行**：跟踪块自包含。用第二个峰的 `Acq_delay_samples`/`Acq_doppler_hz` 播种第二个跟踪实例即可独立跟第二条径
     （`dll_pll_veml_tracking.cc:791-800`）。相关器为 N 抽头、可扩展（当前 3/5 抽头，`:611-652`）。
  2. **分辨率硬约束**：捕获现有 `first_vs_second_peak_statistic` 找次峰时**排除主峰 ±1 码片**（`pcps_acquisition.cc:484-509`）。
     → 捕获域只能分开 **≳1 码片**的两径；**近距多径（<1 码片，最常见最有害）在捕获域分不开**，需在**跟踪域**用多相关器/超分辨。
  3. **下游冲突**：observables 按 `Channel_ID` 组织（不冲突）；但 **RTKLIB 解算器**按卫星号打包观测，
     同 (系统,PRN,信号) 的第二条观测**很可能覆盖第一条**（`rtklib_solver.cc` 观测装配循环，**待实测确认**）。
     → 两条径伪距**同时进同一定位解会冲突**；若只做"测量/导出"则无碍。
- **两条候选架构**（待用户定，详见文档 04）：
  - **A｜单通道两跟踪器**：一次捕获出两峰 → peak1/peak2 各播种一个跟踪块。贴合"捕获搜两峰"的心智，改动含 channel/FSM，无需动 PRN 池。
  - **B｜单跟踪器多相关器**：一个跟踪块内加密抽头、内部分辨两径（MEDLL 类）。贴合近距多径物理，但鉴别器算法复杂、双伪距输出需自定义。
- **通道 PRN 池备注**：若改走"两个独立通道同 PRN"，需改 `gnss_flowgraph.cc`（`remove_signal`@~1845、`search_next_signal`@~2290 的 pop）；
  但独立通道还有"第二通道怎么拿到第二个峰"的协调难题，不如 A 方案（一次捕获出两峰）干净。→ **不推荐独立通道路线**。

### ❓ 待用户确认（阻塞方案选型）
- 两条径伪距的**最终用途**（多径研究/测量 vs 提升定位 vs 抗欺骗）→ 决定要不要处理 RTKLIB 冲突。
- 关注的两径**间隔尺度**（>1 码片可分 vs <1 码片近距）→ 决定主战场在捕获域还是跟踪域。
- **原型目标信号**（建议 GPS L1 C/A 起步）。

### 🧭 决策：文档采用"索引优先 + 模块化多文件"结构
- **背景**：用户要求维护一份能让"无记忆 AI"快速接手的进度文档，但又不能让上下文爆炸。
- **方案**：`README.md` 作总纲（目标 / 文档地图 / 进度看板 / 结论速查 / 术语），
  详情拆成 01~05 独立文件，每篇开头有小目录和"何时读"。维护时只动 README 进度看板 + 相关那一篇 + 本日志。
- **好处**：接手的 AI 先读小的 README 建立全局观，再**按需**读一两篇详情，不必全量载入。

### 🧭 决策：文档放 `gnss-sdr/dev_notes/`，文件名用 ASCII
- 放仓库内便于随代码走、易被发现；文件名用 ASCII（如 `02_acquisition_2d_peak_search.md`）避免
  Windows/Git Bash 下中文路径在某些命令行工具里的编码问题；**正文用中文**。

### 🧭 决策：先吃透"捕获（Acquisition）"再动手
- 用户重点是"二维谱峰搜索"，已确认它 = 信号捕获 = PCPS 算法，核心在 `pcps_acquisition.cc`。
- 已通读该文件全 872 行，产出文档 02（核心篇）。

### 🕳️ 坑（预警，未踩但要小心）：`Gnss_Synchro` 加字段影响面
- 它按 `sizeof(Gnss_Synchro)` 在 GNU Radio 流端口间传递，且可能被 dump/序列化/外部监视工具消费。
- **对策**：新字段加在结构体**末尾**并给默认值 `{}`；改动前检查是否有 boost::serialization / 二进制 dump / monitor 依赖。

### 🕳️ 坑（预警）：捕获核心计算段在"解锁"状态运行
- `acquisition_core()` 里 `doppler_grid()`+`compute_statistics()` 跑在 `d_setlock` **解锁**期间（`pcps_acquisition.cc:677-684`）。
- **对策**：若在这段加共享状态，注意线程安全；写回 `d_gnss_synchro` 的部分要在重新上锁后做。

### 🧭 决策：改造遵循"小步快跑、先捕获层后跟踪层、每步用 dump 验证"
- 见文档 04 §4 的分阶段计划。先不碰 FPGA/OpenCL/实时分支。

### ❓ 疑问：待用户澄清的 6 个关键问题
- 见文档 04 §5（"多源"具体指哪种、多径做到哪一步、目标信号、数据来源、实时性、交付形态）。
- 这些直接影响改造方向与工作量，**建议尽早和用户确认**。

### ❓ 疑问 / 待办：尚未验证的事项
- [ ] 还没实际**编译/运行**过项目，也没 dump 出真实相关面 `.mat`（文档 02/04 里的算法理解来自读码，待跑通验证）。
- [ ] tracking 模块（多径的主战场）**还没读**，文档 04 §2.B 尚是占位，需下一步补。
- [ ] observables/多源架构还没细看，文档 04 §3 待细化。
- [ ] 文档 01/03 里的**行号是近似值**（部分来自 Explore 代理扫描），动手改前以实际文件为准。

---

*（新条目请加在本行上方、日期区块内）*
