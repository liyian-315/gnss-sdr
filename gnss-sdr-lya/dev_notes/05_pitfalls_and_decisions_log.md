# 05 · 踩坑与决策日志（按日期追加）

> **追加式**日志：新条目加到最上面（倒序，最新在前）。记录三类东西：
> - 🧭 **决策**（Decision）：为什么这么做，考虑过哪些方案。
> - 🕳️ **坑**（Pitfall）：遇到的问题、原因、解法/绕法。
> - ❓ **疑问**（Open Question）：暂未解决、需后续确认的点。
>
> 维护提示：**只往这里追加**，不改历史条目；避免每次都要重读全部文档，省 token。

---

## 2026-07-15

### 🕳️ 实时全星双路径仍 overflow：默认运行配置降为保守档

**现象**：用户每次运行：

```bash
./build-conda/src/main/gnss-sdr \
  --config_file=dev_notes/sim/my_bds_b1i_twopath.conf 2>&1 | tee run.log
```

都会出现 USRP overflow。

**判断**：当前已经不是 GNU Radio FFT 损坏问题，而是实时处理负载超过测试机稳定吞吐。原配置虽然关了 acquisition dump，但仍有：

- `Channels_B1.count=12`：双路径下最多 6 颗星，每颗两条径。
- `Channels.in_acquisition=4`：最多 4 路捕获并发跑 PCPS FFT。
- `doppler_step=250` + `max_dwells=2`：捕获计算量较大。
- `Tracking_B1.dump=true`、`PVT.dump=true`、`Monitor.enable_monitor=true`：持续输出叠加 I/O/调度压力。

这些叠在 B210 实时流上，会导致采样消费不及时；一旦 overflow，后续主峰/第二峰/伪距判断都不可信。

**本轮处理：把 `my_bds_b1i_twopath.conf` 改成实时保守档**

- 加 `SignalSource.IF_bandwidth_hz=2000000`，显式设置 B210 RF 带宽。
- `Channels_B1.count: 12 -> 4`，先最多 2 颗星各两条径。
- `Channels.in_acquisition: 4 -> 1`，实时只跑一路捕获。
- `Acquisition_B1.doppler_step: 250 -> 500`，减少 Doppler bins。
- `Acquisition_B1.max_dwells: 2 -> 1`，先保实时吞吐。
- `Tracking_B1.dump: true -> false`，避免连续 tracking dump。
- `PVT.dump: true -> false`，减少 I/O。
- `Monitor.enable_monitor: true -> false`，减少实时旁路负载。
- 暂时保留 `Observables.dump=true`，因为它是当前“两条径伪距输出”的主要证据；如果仍 overflow，再临时关它做纯稳定性测试。

**后续调参顺序**

1. 先用保守档跑 30~60 秒，确认没有 `overflow`。
2. 若仍 overflow：先把 `Observables.dump=false`，再把 `Channels_B1.count=2`。
3. 若不 overflow：逐步恢复 `Channels_B1.count=6/8/12`，每次只改一个旋钮；不要一口气恢复全量。
4. 多径谱峰/3D 图验证继续走“录制干净数据 -> File 源离线 dump”路线，不在实时配置里开 acquisition dump。

### ✅ 补全检查：Claude 新增 3D 捕获谱峰绘图脚本已可用

**背景**：用户让 Claude 根据提示新增 3D 谱峰图脚本；Claude 输出中出现 429，中断风险不明，因此本轮检查脚本是否完整。

**检查结论**

- `dev_notes/sim/plot_acq_3d.py` 文件存在，主流程不是半截：能读 HDF5 `.mat` 的 `acq_grid`，绘制 Doppler × 码相位 × 相关值的 3D 曲面，并保存 PNG。
- 但原版偏“刚写完可跑”，缺少实测保护：glob 无匹配会 `IndexError`，输出默认落当前目录，路径分隔只按 `/`，没有显式标注第二径。

**本轮补全**

1. 增加无匹配文件、缺 `acq_grid`、`acq_grid` 非二维的错误提示。
2. 改用 `pathlib.Path` 生成输出路径，默认保存到输入 `.mat` 同目录，文件名为 `<stem>_3d.png`。
3. 增加 `--max-code-points` 控制码相位方向降采样，避免大矩阵 3D 渲染过慢。
4. 增加 `--elev` / `--azim` 调整视角。
5. 在 3D 图中用红色 `x` 标主峰；如果 dump 里 `has_second_peak=1` 且有 `acq_delay_samples_2`，用白色点标第二径。
6. 输出打印主峰码相位、Doppler、grid shape、samples/chip、has2。

**验证**

- `python -m py_compile dev_notes/sim/plot_acq_3d.py plot_acq_grid.py analyze_multipath.py` 通过。
- 在临时目录构造合成双峰 HDF5：`acq_grid=(41,8000)`，主峰与第二峰相距约 27 samples，`has_second_peak=1`；运行 `plot_acq_3d.py` 成功生成 PNG（约 207 KB），输出主峰 `511.5 chip, 0 Hz`。

**关于用户的 1000m 双径模拟设计**

- 1000m 对 B1I 约为 `1000 / 146.6 ≈ 6.8 chips`，在 4 Msps 下约 `13.6 samples`，大于捕获码相位采样间隔，理论上属于可在捕获相关面分开的远距双峰。
- 两路等功率有利于“看到两个峰”，但会让“哪条是直射”变得不唯一；这是后续 LOS 判别问题，不是谱峰分辨问题。
- 如果 3D 图上连单个尖峰都没有，应优先怀疑录制/限带/overflow/信号源，而不是 1000m 设计本身不可分辨。

### 🧭 Codex 跟进：SDR 已跑通，当前进入测试优化/效果验证阶段

**本轮已读**：`dev_notes/README.md`、`05_pitfalls_and_decisions_log.md`、`06_b1c_b210_two_path_usage.md`、`dev_notes/sim/my_bds_b1i_twopath.conf`、`b1i_sim_prn9.conf`、`record_b210.py`、`check_acq.py`。

**当前进度判断**

- 环境问题已过：系统 GNU Radio 3.7 FFT 坏的问题已通过 conda GR3.10 + `build-conda/` 绕开；B210 实收 B1I 已能 Tracking，阶段从“跑起来”进入“测试优化”。
- 当前效果不理想的首要嫌疑不是 B1I/B1C 代码链路，而是测试数据质量和验证方式：
  1. 实时 USRP 跑复杂捕获/跟踪时容易 overflow，样点一旦丢失，主峰/第二峰都会随机跳，多径判断失真。
  2. 只发单颗 PRN9 做模拟器验证时，其它 PRN 容易出现互相关/噪声假捕获，所以应先固定 PRN9 两通道验证机制，再扩到所有星。
  3. 真实天空干净信号未必有明显第二径，不能用“没有 MULTIPATH 日志”直接判定算法无效；需要模拟器可控延迟径或离线 dump 相关面确认。

**建议优化路线**

1. 先用 `record_b210.py` 录一段干净 B1I 原始采样，确认录制时没有 overflow。
2. 用 File 源离线处理这段数据，离线时再打开 acquisition dump，避免实时 I/O 把采样打坏。
3. 用 `check_acq.py` 看 `positive_acq / test_statistic / threshold`，先区分“真捕获”还是“噪声 argmax”。
4. 再用 `analyze_multipath.py` / `plot_acq_grid.py` / `plot_acq_3d.py` 看第二峰是否在预期延迟附近。
5. 若 PRN9 + 1000m 模拟多径仍检不稳，再调 `multipath_max_delay_chips`、`multipath_threshold_fraction`、`pfa`、通道数和采样率；不要先改 PVT。

**协作注意**

- 当前主线仍是 B1I；B1C CNAV1 不阻塞这个阶段。
- 测试机必须 `conda activate gnsssdr` 且运行 `build-conda/src/main/gnss-sdr`。
- `my_bds_b1i_twopath.conf` 文件头里的旧命令还写 `GLOG_logtostderr=1 ./build/src/main/gnss-sdr`，容易误导；后续应改为 conda + `build-conda` 写法。

## 2026-07-13

## 2026-07-14

### 🕳️ 关键坑：USRP overflow → 样点损坏 → 多径检测/跟踪全是垃圾（模拟器验证时暴露）
- **现象**：B210 实时跑 `b1i_sim_prn9.conf`，满屏 `usrp_source: overflows occurred`；`analyze_multipath` 里**主径 chip 满量程乱跳**（1082→106→35→1584…，正常应平滑缓变）；有多径(1000m)和无多径两组结果**几乎一样**、Δ随机。
- **诊断**：**不是多径逻辑 bug**。overflow 丢样点 → 捕获在损坏数据上做相关 → 主峰都是随机的 → 第二峰自然随机。跟踪也因丢样点锁不住。**"主峰乱跳"是样点损坏的铁证。**
- **两个元凶（配置）**：① `Acquisition_B1.blocking=true`——实时下捕获同步跑、算 FFT 卡住采样消费 → overflow（实时 USRP **必须 `blocking=false`**）；② `Acquisition_B1.dump=true`——每份~7MB、狂重捕一次跑出 2737 份 → 磁盘 I/O 爆 → overflow。
- **已修（本地 `b1i_sim_prn9.conf` 与 `my_bds_b1i_twopath.conf`）**：`blocking=false`、`dump=false`。
- **多径验证正解**：实时开 dump 必溢出 → 改**离线**：先录一小段干净 B210 数据到文件，再用 File 源离线处理（无实时约束，随便 dump，可复现）。待 overflow 治好后做。
- **注意**：只发 PRN9 一颗星出不了 PVT 定位（需≥4星）；要复现"带定位/NMEA"的结果需模拟器多发几颗星或对真实天空多星测。

### 🧭 工作流变更：改本地文件 + GitHub 两边同步（不再直接改服务器）
- 用户要求：**Claude 只改本地 `gnss-sdr-lya` 文件，经 GitHub push/pull 同步到测试机**，不再给"服务器上 sed"命令。
- 影响：后续配置/代码/文档改动都落在本地副本；用户负责 git 同步。给命令时默认"文件已通过 git 同步到服务器"。

### 🧭 设计澄清：两条径进 PVT 的处理 + 与 xinghe 副本对比（回应"关键认知是否违背目标"）
- **用户疑问**：README 的"关键认知"（第二径不进 PVT、走旁路）会不会违背目标"追踪两条径的伪距信息"？
- **结论：不违背。** 目标是"追踪+输出两条径的伪距信息"——两条径都跟踪、都进 observables/dump/monitor **已达成**。
  争议仅在"要不要把两条径都塞进 PVT 解算"：反射径偏长，塞进 RTKLIB 当第二颗星观测会**拉偏定位**，故**只放行 path0**。
- **独立佐证**：平行副本 `../gnss-sdr-xinghe`（另一 AI）的 `rtklib_pvt_gs.cc:2077` 也是 `if (... && Signal_Path == 0U)`，
  注释同为"reflected path retained by Observables/monitors/dumps, but must not be interpreted as an additional satellite by RTKLIB"。**两 AI 收敛同一设计。**
- **两副本捕获层实现不同**（都能检第二径，可互鉴）：
  - `lya`（本副本）：独立 `find_second_peak()` + 邻域窗 `multipath_max_delay_chips` + 门限 `multipath_threshold_fraction` + `has_second_peak`；`Signal_Path==1` 触发。
  - `xinghe`：改 `first_vs_second_peak_statistic` + 可配 `second_peak_exclusion_chips`。
- **⚠️ 重要**：现阶段第二径只"输出/分析"，**尚未用于改善定位**。要真正"提升定位精度"，须下一步用第二径做 **LOS 判别 + 多径校正**（Stage 2/3）。README"下一步"已写三步路线。
- **PRN9 固定配置只是验证用**（`b1i_sim_prn9.conf`）：证明机制正确性；最终形态仍是通用 `signal_paths=2` 搜所有星（待解假捕获 + overflow）。

### ✅✅ 里程碑：conda GNU Radio 3.10 重编成功，B210 实收真实 B1I、多路径链路跑通
**结果**：`build-conda/src/main/gnss-sdr` 编译成功，`ldd` 确认链的是 conda 的 `libgnuradio-fft/runtime .so.3.10.11` + `libvolk.so.3.1`（不再是坏的系统 3.7）。B210 直采，**一大批真实北斗 B1I 卫星正常 Tracking**（PRN 01/02/03/04/06/07/09/11/12/14/17/20/22/25/26/27/28/30/... 二号+三号），**再无 `Can't connect channel 0`**。FFT 坑彻底解决。

**从 FFT 坏到跑通，踩的坑链（都在 conda 重编时）**：
1. **glog 头文件不兼容**：conda 新版 glog(0.7) 要 `GLOG_USE_GLOG_EXPORT`，GNSS-SDR 老式检测没设 → `<glog/logging.h> was not included correctly`。**修**：`-DENABLE_GLOG_AND_GFLAGS=OFF` 改用 Abseil（+`conda install abseil-cpp`）。
2. **系统 GR3.7 模块混入**：ZEROMQ/LimeSDR 解析到 `/usr/lib` 的 GR3.7 库，会和 conda 3.10 冲突。**修**：`-DENABLE_ZMQ=OFF -DENABLE_LIMESDR=OFF -DENABLE_OSMOSDR=OFF`。
3. **缺 pcap.h**：`gr_complex_ip_packet_source`(UDP源)无条件编译要 libpcap。**修**：`-DENABLE_RAW_UDP=OFF`（或 `conda install libpcap`）。
4. **CNAV1 无守卫 glog**：`beidou_cnav1_navigation_message.cc:38` 无守卫 `#include <glog/logging.h>`（GSoC2019 老代码），absl 模式下 `undefined reference to google::LogMessage`。**修**：改成 stock 守卫写法 `#if USE_GLOG_AND_GFLAGS ... #else #include <absl/log/log.h> #endif`。其它 B1C 文件都已带守卫，只此一个。

**完整重编配方 + 运行步骤**：见 `06`（已重写为 conda/B210/B1I 权威运行手册）。

**文档/仓库整理**：`dev_notes/sim/` 只留 `my_bds_b1i_twopath.conf`(主力) + `analyze_multipath.py`；历史配置/脚本移入 `sim/archive/`；删除可再生的 `.mat/.dat` dump（100MB+），加 `.gitignore`。

**遗留/下一步**：
- absl 日志下 `MULTIPATH`(LOG INFO) 可见性待调（真实干净信号本就无多径，等模拟器验证时处理）。
- ❓ 观察：`signal_paths=2` 下所有通道都在 Tracking（含 path=1）；真实无多径时 path=1 是否锁到噪声次峰，待模拟器加多径后核对门限。
- **下一步（用户主导）**：配 B1I 模拟器，给一路加延迟/补偿模拟北斗多径，验证第二径检测+双路径跟踪是否正确。

### 🧭 定案：ffttest 坐实 GNU Radio 3.7.11 FFT 损坏 → conda 隔离装 GR3.10（不动系统）
- **铁证**：`/tmp/ffttest`（独立最小程序，仅 `gr::fft::fft_complex f(4000,true,1)`）输出 `FFT threw: type=St9exception what=std::exception`。
  → 与 GNSS-SDR/B1I/B1C/多径**完全无关**，纯 GNU Radio 3.7.11 FFT 在本机就坏；`rm ~/.gr_fftw_wisdom` 无效（已排除 wisdom）。
- **约束**：测试机有他人重要环境，**不能重装/升级系统**。
- **定案路线**：**conda-forge 在 `$HOME` 装隔离的 GNU Radio 3.10 + UHD + 全依赖，用 conda 的编译器重编 GNSS-SDR**（对话里给了 4 段逐步命令）。
  - 关键：`conda create -n gnsssdr -c conda-forge cxx-compiler gnuradio-core gnuradio-uhd uhd boost-cpp armadillo openblas gflags glog libmatio pugixml libprotobuf protobuf openssl mako ...`
  - 重编：`cmake -S . -B build-conda -DCMAKE_PREFIX_PATH=$CONDA_PREFIX ...`；产物 `build-conda/src/main/gnss-sdr`，`--version` 应显示 GR3.10。
  - UHD：conda 的 `uhd_images_downloader` 下匹配固件，再跑 B210。
- **验证目标**：conda 版跑 `my_bds_b1i_twopath.conf` 不再 `Can't connect channel 0`，能出 `MULTIPATH`/双通道 Tracking。
- **⚠️ 给 Codex/后续 AI**：修复在**运行环境**（conda GR3.10），**不要**改 GNSS-SDR 代码来绕 FFT。系统那份 GR3.7 build 保留但弃用，实测用 `build-conda`。

### 🕳️ FFT 最小复现已确认：不重装系统，优先做隔离修复

**新增证据**：用户在测试机执行 `/tmp/ffttest`，输出：

```text
FFT threw: type=St9exception what=std::exception
```

这说明问题已经脱离 GNSS-SDR 配置、B1I/B1C 改造和 UHD 采集链路，可以用独立 FFT 最小程序复现。当前结论从“Channel0 创建阶段疑似 GNU Radio FFT 异常”升级为“测试机 GNU Radio FFT/FFTW 运行环境确实异常或不兼容”。

**约束**：测试机上还有他人重要环境，不能重装系统，也不应做大范围系统升级。

**处理优先级**

1. 先做无破坏验证：备份/移走 GNU Radio FFTW wisdom 后重跑 `/tmp/ffttest`，排除坏 wisdom。
2. 如果仍失败，优先采用用户目录隔离环境：在 `$HOME` 下用 conda/mamba 或本地 prefix 安装 GNU Radio/FFTW/UHD，再用该环境重新编译 GNSS-SDR。
3. 只有在确认是系统包文件损坏、且用户允许 sudo 的情况下，才考虑 `apt --reinstall` 精确重装 `libgnuradio-fft` / `libfftw3` 相关包；不要做 `dist-upgrade`、不要重装系统。
4. 继续避免改 GNSS-SDR 的 B1I/B1C 逻辑来绕这个问题；当前失败点在 FFT 运行时。

**建议下一步命令（测试机）**

```bash
mkdir -p ~/lya/fft_debug
ldd /tmp/ffttest | egrep 'gnuradio|fftw|volk|boost' | tee ~/lya/fft_debug/ffttest_ldd.txt
dpkg -l | egrep 'gnuradio|libfftw|volk|uhd' | tee ~/lya/fft_debug/gnuradio_fft_packages.txt
mv ~/.gr_fftw_wisdom ~/.gr_fftw_wisdom.bak.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
/tmp/ffttest 2>&1 | tee ~/lya/fft_debug/ffttest_after_wisdom_reset.txt
```

如果最后一条仍然抛异常，按“用户目录隔离环境”路线推进。

### 🕳️ 根因定位：`Can't connect channel 0` = GNU Radio 3.7.11 的 `gr::fft::fft_complex` 构造抛异常
- **现象**：测试机(NUC/Ubuntu18.04)上**任何 B1I 配置**（单路径/双路径/文件源/UHD 源都一样）Channel 0 捕获块创建即 `std::exception` → `Can't connect channel 0 internally`。
- **定位手段**：文件源复现(去掉 UHD 噪声) + `gdb -ex "catch throw" -ex run -ex "bt 15"`。调用栈铁证：
  ```
  #1 gr::fft::fft_complex::fft_complex(int,bool,int)  ← libgnuradio-fft.so.3.7.11 抛的
  #2 pcps_acquisition::pcps_acquisition(Acq_Conf const&)
  #4 BasePcpsAcquisition::...  #5 BeidouB1iPcpsAcquisition::...
  ```
- **结论**：**stock 代码**（非 B1C、非多径改动）。`pcps_acquisition` 构造时建 FFT（`gnss_sdr_fft.h`：GR<3.9 走 `gr::fft::fft_complex(size,forward)` 路径），在 **GNU Radio 3.7.11 运行时抛异常**。fft_size=4000（4MHz×1ms B1I，合法）。
  → 本质是 **GNSS-SDR 0.0.21（面向 GR3.8-3.10）在 GR3.7.11 上运行时不兼容**：能编过(cmake 最低要求 3.7.3 已过时)，但 FFT 运行时坏。
- **排查中（待用户测试机结果）**：① 独立最小测试 `gr::fft::fft_complex f(4000,true,1)` 是否也抛(拿真实 type/what)；② `rm ~/.gr_fftw_wisdom` 是否救。
- **大概率的根治**：换 **GNU Radio ≥3.8**（不动 18.04 则用 **conda-forge** 装 gnuradio 3.10 重编 GNSS-SDR；或升级 OS 20.04/22.04）。
- **⚠️ 给 Codex/后续 AI**：这是**环境/版本**问题，不是代码逻辑 bug——别再去改 B1C/多径/配置找它。修复方向是运行环境的 GNU Radio 版本。

### 🧭 Codex 协作接手：先按 README/05 对齐，再继续 B210 B1I 实测

**背景**：用户说明 Claude 已经处理过一轮，要求先查看文件结构和 README；后续 Codex 自己的判断、操作也要记录下来，方便多智能体协同。

**本轮已读**

- `dev_notes/README.md`：确认它是当前项目入口索引，后续接手先读这里。
- `dev_notes/05_pitfalls_and_decisions_log.md`：确认它是 append-only 的踩坑/决策日志。
- `dev_notes/USAGE_B1I.md`：确认当前 B210 测试目标应先落在 B1I 双路径跟踪，而不是继续把 B1C 当作阻塞项。
- `dev_notes/sim/my_bds_b1i_twopath.conf` / `my_bds_b1c_multipath.conf`：注意后者文件名仍容易误导，当前实测优先使用 B1I 配置链路。

**当前判断**

1. B210 之前日志中 USRP 初始化、RX2/LO/中心频率均正常，失败点是 Channel0 内部块创建/连接阶段，不是射频未采到信号导致。
2. 测试机日志仍显示旧的 `std::exception`，没有出现本地新增的 `Exception while creating GNSS channels...` 细分诊断，说明测试机很可能还没有重新编译/运行到最新二进制。
3. Ubuntu 18.04 + CMake 3.10.2 不支持新式 `cmake --build build ... -jN` 写法，应该使用：

```bash
cmake --build build --target gnss-sdr -- -j$(nproc)
# 或
cd build && make gnss-sdr -j$(nproc)
```

4. 当前协作原则：B1I 实测优先；B1C CNAV1/Telemetry 完整支持继续改造，但不阻塞 B210 对 B1I 双路径采集、跟踪和伪距输出验证。
5. 在 Windows PowerShell 下直接读中文 Markdown 可能出现乱码，后续查看中文文档优先使用 `Get-Content -Encoding UTF8`，或在 Ubuntu/WSL 下用 `cat/sed`。

**后续操作记录约定**

- 修改代码、配置或运行验证后，把关键判断追加到本文件对应日期下。
- 如果改变了项目阶段、推荐入口配置或运行步骤，再同步更新 `dev_notes/README.md`。
- 不覆盖 Claude 或用户已有记录；只追加自己的结论、命令和证据。

### ✅ 服务器(Ubuntu18.04/gcc7/GR3.7)编译通过 + B1I 双路径配置就绪
- **服务器环境**：NUC7i7，`gcc 7.3.0 / Boost 1.65.1 / UHD 3.10.3 / cmake 3.10.2`（≈Ubuntu 18.04）。代码在此**编译通过**，产物 `gnss-sdr 0.0.21`。
- **cmake 3.10.2 两个坑（之前报错主因）**：① `cmake -S . -B build` 语法要 cmake≥3.13，3.10.2 不支持 → 必须老式 `mkdir build && cd build && cmake ..`；② 拷来的旧 build 目录 CMakeCache 指向旧机路径 → 先 `rm -rf build*`。
- **版本门槛其实都过**：GNSS-SDR 要求 cmake≥2.8.12 / Boost≥1.53 / GNU Radio≥3.7.3，18.04 全满足；代码在 gcc7/GR3.7 也能编（不只 24.04）。
- **目标澄清 = B1I（不是 B1C）**：运行配置 `my_bds_b1c_multipath.conf`（名字有误导）其实是 **B1I**——`freq=1561098000`、`signal=B1`、全 `BEIDOU_B1I_*` stock 链路 + 多径检测。**B1C 那套代码本目标用不到**（且 B1C 缺 CNAV1 电文解码；B1I 电文/伪距 stock 就有，更适合"输出伪距"目标）。
- **双路径机制确认(读码)**：`Gnss_Synchro::Signal_Path` 驱动——`pcps_acquisition.cc:689/798/811` 里 `Signal_Path==1` 的通道**自动**捕获第二峰；`rtklib_pvt_gs.cc:2077` 只放行 `Signal_Path==0`。`Channels_<sig>.signal_paths=2`(`gnss_flowgraph.cc:1568` 等)信号无关，B1I 直接可用。
- **交付**：`dev_notes/sim/my_bds_b1i_twopath.conf`（B1I + `signal_paths=2` + dump）。服务器上可由 sed 从现有 B1I 配置生成（见对话）。
- **待用户**：B210 实跑结果（MULTIPATH 日志 / 同 PRN 两通道 Tracking / observables 双径伪距）；**确认信号确为 B1I@1561.098MHz**（若实发 B1C 则捕不到）。

### 🔎 Claude 重新接手（re-onboard）+ 报错排查中
- **上下文**：项目已从 `D:\...\gnss-sdr` 迁到本副本 `D:\...\gnss-sdr-main-gaizao\gnss-sdr\gnss-sdr-lya`；用户在此加了大量 B1C 支持，"还在报错"，要求重新了解并排查。
- **已确认（读 README/06/05 + 静态检查）**：B1C 接线**完整正确**——
  - CMakeLists：`beidou_b1c_telemetry_decoder(_gs)` 和 `beidou_b1c_dummy_telemetry_decoder(_gs)` 均已加入 telemetry_decoder 的 adapters/gnuradio_blocks CMakeLists。
  - 工厂 `gnss_block_factory.cc`：4 个 B1C 实现全注册（PCPS_Acquisition / DLL_PLL_Tracking / Telemetry_Decoder(真) / Dummy_Telemetry_Decoder），信号映射 `C1`/`B1C` 均在。
  - → 说明报错**不是**"新块没注册/没进 CMake"这类常见问题。
- **在 `/mnt/d` 上增量编译 8 分钟未编完也未报错**（印证 06 §4：Windows 挂载盘编大文件极慢）。已转后台全量编译 `build-wsl-codex/full_build.log` 复现。
- **待用户补**：① 确切报错文本（编译错？运行错？哪台机/哪个 build？指向哪个文件行）；② **目标到底是 B1I 还是 B1C**——本副本全是 B1C(1575.42MHz)，但最新口径说"B1I 频率"；注意 **stock GNSS-SDR 本就有 B1I 全链路**，若真做 B1I 未必需要自建 B1C。
- 最近活跃改动：`beidou_b1c_telemetry_decoder_gs.cc`(17:43)——正把 dummy 占位换成真 CNAV1 解码，报错很可能在此。

### ✅ B1C + USRP B210 直采双路径原型

**背景**：用户确认测试机为 USRP B210，要求 GNSS-SDR 本身采集后直接做多径检测，不要依赖固定采样文件；目标信号为 B1C，并要求每颗卫星两条路径持续跟踪并输出路径信息。

**关键改造**：
- 运行配置 `dev_notes/sim/my_bds_b1c_multipath.conf` 改为 `UHD_Signal_Source`，默认 `freq=1575420000`、`sampling_frequency=4000000`、`gain=50`、`antenna=RX2`。
- B1C 在运行链路里使用 `C1`，因为 `Gnss_Synchro.Signal` 是两字符字段，不能直接塞 `B1C` 三字符。
- `Channels_C1.signal_paths=2`：每颗 B1C PRN 自动生成 `Signal_Path=0/1` 两条通道；path 0 用主峰，path 1 自动用捕获阶段接受的第二峰。
- 新增 `BEIDOU_B1C_DLL_PLL_Tracking` 适配器，并在 `dll_pll_veml_tracking.cc` 里接入 B1C pilot/data 本地码生成。
- PVT/RTCM 侧只消费 `Signal_Path=0`，第二径保留在 tracking/observables/monitor dump 里做多径分析，避免反射径直接污染 RTKLIB。

**验证**：
- `tracking_gr_blocks` 编译通过。
- `tracking_adapters` 编译通过，并生成包含 `beidou_b1c_dll_pll_tracking.cc.o` 的 `libtracking_adapters.a`。
- `core_monitor` 编译通过，protobuf monitor 的 `signal_path` 字段可用。
- `gnss_flowgraph.cc.o` 和 `gnss_block_factory.cc.o` 单独编译完成。
- 当前 Windows/WSL `/mnt/d` 路径上完整 `gnss-sdr` Release 全量重编非常慢；已有 `build-wsl-codex/src/main/gnss-sdr` 可执行产物能输出 `gnss-sdr version 0.0.21`。测试机建议放 Linux 本地磁盘编译。

### ⚠️ 坑：B1C CNAV1 电文解码尚未完成

B1C acquisition 和 tracking 已经接入，但 native B1C CNAV1 telemetry decoder 还没有实现。

影响：
- 可以做 B210 直采、B1C 捕获、多径第二峰检测、两路径持续跟踪、tracking dump、monitor 输出。
- 如果没有 B1C CNAV1 解码，带 TOW 的有效伪距和 PVT 可能仍然无效。
- 配置里的 `TelemetryDecoder_C1.implementation=BEIDOU_B1C_Dummy_Telemetry_Decoder` 是直通占位，只负责把 tracking 输出继续送到 observables，不代表 B1C 电文解码已经完成。

### ✅ 修复：B1C 配置不能使用 GPS L1 C/A telemetry decoder

测试机日志显示：B210 已正常识别和调谐，但 Channel 0 实例化后工厂捕获 `std::exception`，随后 `Can't connect channel 0 internally`。原因是 `TelemetryDecoder_C1.implementation=GPS_L1_CA_Telemetry_Decoder` 不接受 `C1/B1C` 信号。

处理：
- 新增 `BEIDOU_B1C_Dummy_Telemetry_Decoder`。
- 内部 GNU Radio block 输入/输出都是 `Gnss_Synchro`，原样透传，但强制 `Flag_valid_word=false`、`Flag_valid_pseudorange=false`。
- 这样采集、捕获、两路径跟踪、dump/monitor 能跑通；有效伪距/PVT 仍等待 native B1C CNAV1 decoder。

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
