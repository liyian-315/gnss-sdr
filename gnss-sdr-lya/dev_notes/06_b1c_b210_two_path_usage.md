# 06 · 运行手册：conda 环境 + USRP B210 + B1I 双路径

> **这是当前唯一权威的"怎么编译、怎么跑测试"手册。** 以前的 B1C 版说明已过时（见文末历史）。
> 测试机 = NUC7i7 / Ubuntu 18.04 / USRP B210。

## 0. 为什么必须用 conda（一句话背景）
测试机系统自带的 **GNU Radio 3.7.11 的 FFT 是坏的**（`gr::fft::fft_complex` 构造就抛异常，任何捕获通道都连不上，报 `Can't connect channel 0`）。
所以我们在 `$HOME` 用 **conda 装了隔离的 GNU Radio 3.10.11** 并重新编译。**跑测试前必须进 conda 环境，并用 `build-conda/` 下的程序**（不是 `build/`，那是坏的系统 3.7 版）。详见 `05`(2026-07-14)。

## 1. 每次测试的固定开头（★必做★）
```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh    # 每开一个新终端都要 source 一次
conda activate gnsssdr                             # 进虚拟环境；提示符会变成 (gnsssdr) ...
cd ~/lya/gnss-sdr/gnss-sdr-lya
```
确认环境对：
```bash
./build-conda/src/main/gnss-sdr --version          # GNU Radio 应是 3.10.11（不是 3.7）
```
> ⚠️ 忘了 `conda activate gnsssdr`、或误用了 `build/src/main/gnss-sdr`（系统坏 FFT 版）→ 又会 `Can't connect channel 0`。

## 2. 跑 B210 · B1I 双路径
```bash
uhd_find_devices                                   # 确认认得 B210（第一次或换机可能要先 uhd_images_downloader）
./build-conda/src/main/gnss-sdr \
    --config_file=dev_notes/sim/my_bds_b1i_twopath.conf 2>&1 | tee run.log
# 跑 30~60 秒后 Ctrl-C 停
```
**看什么：**
- `Tracking of Beidou B1I signal started on channel N for satellite Beidou PRN X` —— 捕获+跟踪正常（真实天上北斗星）。
- `MULTIPATH B <PRN>: 2nd path at X chips (main Y, delta Δ), power ratio Z dB` —— **有多径的星**。
  真实干净信号通常没有（各星单径）；**上模拟器给某星加延迟径后，这里应出现**。
- 停止后当前目录产物：`bds_b1i_acq*.mat`（相关面 dump）、`bds_b1i_tracking_ch_*`（两路径跟踪）、`bds_b1i_observables.dat`、`bds_b1i_PVT*`。

## 3. 分析多径（读 dump 出表）
```bash
python3 dev_notes/sim/analyze_multipath.py --pattern "bds_b1i_acq_*_sat_*.mat" --code-length 2046
```
输出每份 dump 的：主径/第二径码片、Δ延迟(码片和米)、功率比 dB、has2 标志。B1I：1 码片≈146.6m。

画谱峰图（需要先有 acquisition dump）：
```bash
# 2D 热图 + 峰值 Doppler 行 + 主峰附近放大
python3 dev_notes/sim/plot_acq_grid.py "bds_b1i_acq_*_sat_9.mat" --code-length 2046

# 3D 曲面：Doppler × 码相位 × 相关值；会标出主峰，若 has2=1 也标第二径
python3 dev_notes/sim/plot_acq_3d.py "bds_b1i_acq_*_sat_9.mat" --code-length 2046
```
若 3D 图上连单个尖峰都没有，先查录制限带、overflow、频点/增益和模拟器输出；不要先怀疑 1000m 双径不可分辨。

## 4. 配置文件（已整理，只留必要）
- **`dev_notes/sim/my_bds_b1i_twopath.conf`** —— 唯一在用的运行配置：
  - B210 直采（`UHD_Signal_Source`），B1I 频点 `freq=1561098000`，`signal=B1`，全 stock `BEIDOU_B1I_*` 链路。
  - `Channels_B1.signal_paths=2` —— 每颗 PRN 自动 2 条通道：`Signal_Path=0` 跟主峰(直射)、`Signal_Path=1` 跟第二峰(反射)。
  - PVT 只用 `Signal_Path=0`；第二径进 dump/monitor 做多径分析（不污染定位）。
- **常调参数**（都在 `Acquisition_B1` 段 / SignalSource 段）：
  | 参数 | 含义 | 建议 |
  |------|------|------|
  | `Channels_B1.count` | 通道总数 = 想覆盖星数 × 2 | 实时先用 4；无 overflow 后再加到 6/8/12 |
  | `Channels.in_acquisition` | 并发捕获数 | 实时先用 1；确认稳定后再加 |
  | `Acquisition_B1.doppler_step` | Doppler 搜索步进 | 实时先用 500；离线/算力足再用 250 |
  | `multipath_threshold_fraction` | 第二峰判定灵敏度 | 漏检调小(0.18)、误报调大(0.3) |
  | `multipath_max_delay_chips` | 主峰邻域搜索窗(码片) | 近多径 2~3，远反射更大 |
  | `SignalSource.gain` | B210 增益 | 40~60 现场试 |
- **单路径基线**：临时把 `signal_paths=2` 改成 `1`（只跟主径，验证 B210/B1I 基本通）。
- **历史配置**在 `dev_notes/sim/archive/`（GPS 内置发生器仿真、旧的 B1I 文件源版、命名混乱的 `my_bds_b1c_multipath.conf` 等），只作参考，不用。

## 5. 如果需要重新编译（conda 版完整配方）
> 只有改了 C++ 源码才需要重编；改 `.conf` 不用重编。
```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh && conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya
# 首次若缺包：conda install -y -c conda-forge abseil-cpp libpcap
cmake -S . -B build-conda -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF \
  -DCMAKE_PREFIX_PATH="$CONDA_PREFIX" \
  -DENABLE_GLOG_AND_GFLAGS=OFF \
  -DENABLE_ZMQ=OFF -DENABLE_LIMESDR=OFF -DENABLE_OSMOSDR=OFF -DENABLE_RAW_UDP=OFF
cmake --build build-conda --target gnss-sdr -j$(nproc)
```
**这些 `-D` 开关的原因**（每个都踩过坑，见 `05` 2026-07-14）：
- `ENABLE_GLOG_AND_GFLAGS=OFF` → 改用 Abseil 日志（conda 的新版 glog 头文件与 GNSS-SDR 不兼容）。
- `ENABLE_ZMQ/LIMESDR/OSMOSDR=OFF` → 否则会链到系统 GR3.7 的 gnuradio 模块，和 conda 的 3.10 冲突崩溃。
- `ENABLE_RAW_UDP=OFF` → 那个 UDP 源要 `pcap.h`（也可改成 `conda install libpcap`）。
- conda 环境自带新 cmake（支持 `-S/-B`）和新 gcc；系统 cmake 3.10.2 不支持 `-S/-B`（那是另一台/另一种坑）。

## 6. MULTIPATH 日志看不到？（absl 日志）
改用 Abseil 后，`LOG(INFO)`（含 `MULTIPATH` 行）默认可能不在屏幕。上模拟器做多径验证时，若 `run.log` 里 grep 不到 `MULTIPATH`：
1. 先确认**确实有多径**（真实干净信号本来就没有）——看 dump：`analyze_multipath.py` 里 has2=1 才算检到。
2. 若确有多径但日志不显示，告诉我，我调 absl 的 stderr 阈值开关（或改用 dump/observables 作为主证据）。

## 7. 排错速查
| 症状 | 原因 / 解法 |
|------|------------|
| `Can't connect channel 0 internally` | 没进 conda 环境，或跑了 `build/`（系统坏FFT版）。→ `conda activate gnsssdr` + 用 `build-conda/` |
| `--version` 显示 GNU Radio 3.7 | 同上，环境不对 |
| 满屏 `usrp_source: overflows occurred` | 实时处理跟不上。先用 `my_bds_b1i_twopath.conf` 的保守档：`Channels_B1.count=4`、`Channels.in_acquisition=1`、`doppler_step=500`、关 tracking/PVT/monitor dump；仍溢出就临时关 `Observables.dump` 或降到 `Channels_B1.count=2` |
| 一颗星都捕不到 | 信号/频点不对（确认 B1I@1561.098MHz、天线、增益）、或 B210 没被 conda UHD 认到 |
| 编译报缺 `xxx.h` | 某可选功能缺 conda 包 → `conda install -c conda-forge <包>` 或 `-DENABLE_XXX=OFF` |

---
*2026-07-14 重写为 conda/B210/B1I 权威运行手册。历史（B1C 早期思路、系统 GR3.7 编译）见 `05` 与本文件 git 历史。*
