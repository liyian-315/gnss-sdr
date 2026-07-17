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
rm -f bds_b1i_acq*.mat bds_b1i_observables.dat run.log
./build-conda/src/main/gnss-sdr \
    --config_file=dev_notes/sim/my_bds_b1i_twopath.conf 2>&1 | tee run.log
# 跑 30~60 秒后 Ctrl-C 停
```
**看什么：**
- `Tracking of Beidou B1I signal started on channel N for satellite Beidou PRN X` —— 捕获+跟踪正常（真实天上北斗星）。
- `MULTIPATH B <PRN>: 2nd path at X chips (main Y, delta Δ), power ratio Z dB` —— **有多径的星**。
  真实干净信号通常没有（各星单径）；**上模拟器给某星加延迟径后，这里应出现**。
- 当前实时保守配置不会生成 `bds_b1i_acq*.mat`，因为 `Acquisition_B1.dump=false`。要画谱峰必须走下面的“录制 -> 离线”流程。

## 2A. 天线 OTA 单路径验收（先过这一关，再做 1000m 多径）
天线发射/接收比馈线直连弱很多。手机能看到 PRN9 只能说明手机链路可见，不代表 B210 + 当前天线 + GNSS-SDR 已过捕获门限。验收标准是离线 acquisition 的 `test_statistic > threshold` 且 `positive=1`。

1. 确保环境干净：
```bash
pkill -9 -x gnss-sdr 2>/dev/null || true
pkill -x firefox 2>/dev/null || true              # 实时测试前关掉高 CPU 浏览器
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya
```

2. 录一段原始样点。OTA 建议从高增益开始，同时确认不削顶：
```bash
python3 dev_notes/sim/record_b210.py --secs 2 --gain 76 --ant RX2 \
  --freq 1561098000 --rate 4000000 -o /tmp/b1i_ant.dat
```

3. 临时把录样作为离线输入，打开 acquisition dump：
```bash
cp /tmp/b1i_ant.dat /tmp/b1i_prn9.dat
rm -f bds_b1i_acq*.mat
./build-conda/src/main/gnss-sdr --config_file=dev_notes/sim/b1i_offline_prn9.conf \
  2>&1 | tee offline_ant.log
python3 dev_notes/sim/check_acq.py "bds_b1i_acq_*_sat_9.mat"
```

4. 判断结果：
- `positive=1` 且 `test_statistic > threshold`：单路径 OTA 已被 B210/GNSS-SDR 捕获，可以继续做第二径/1000m 多径。
- `positive=0` 且 `test_statistic < threshold`：不要继续做多径；先提高模拟器发射功率、打开功放/PA、缩短天线距离或更换/确认 B1I 接收天线。

**2026-07-16 实测记录**：在“天线收发、无补偿、功率与直连一致”条件下，RX2/TX-RX 两个口、70/76 dB 均无削顶，但离线捕获最高只有 `test_statistic≈40 < threshold=54.22`，实时 45 秒也 `tracking=0`。因此当前 OTA 单路径还没过 B210 捕获门限。

降低门限诊断：`b1i_offline_prn9.conf` 当前把 `Acquisition_B1.pfa` 设为 `0.01`，比默认 `0.001` 门限低一些。2026-07-16 对同一 OTA 录样扫到 `pfa=0.1` 仍未稳定捕获（`positive=0`），所以不要靠继续降门限硬判；应优先增强 RF/天线链路。

## 2B. 双模拟器 1000m 多径捕获识别
前提：两台模拟器单独打开时都能被 B210 捕获。正式识别时：

- 模拟器 A：BDS B1I PRN9，无补偿。
- 模拟器 B：BDS B1I PRN9，`+1000m` 补偿。
- 两台同时发射，功率尽量接近；USRP 用新接收天线，`RX2`，`gain=76`。

录制并离线分析：
```bash
python3 dev_notes/sim/record_b210.py --secs 10 --gain 76 --ant RX2 \
  --freq 1561098000 --rate 4000000 -o /tmp/b1i_twosim_1000m.dat

cp /tmp/b1i_twosim_1000m.dat /tmp/b1i_prn9.dat
rm -f bds_b1i_acq*.mat bds_b1i_acq*.png

# 建议正式识别用严格门限 pfa=0.001；需要时临时把 b1i_offline_prn9.conf 的 pfa 改回 0.001
./build-conda/src/main/gnss-sdr --config_file=dev_notes/sim/b1i_offline_prn9.conf \
  2>&1 | tee offline_twosim.log

python3 dev_notes/sim/analyze_multipath.py --pattern "bds_b1i_acq_*_sat_9.mat" --code-length 2046
python3 dev_notes/sim/plot_acq_grid.py "bds_b1i_acq_*_sat_9.mat" --code-length 2046 --zoom-chips 20
python3 dev_notes/sim/plot_acq_3d.py "bds_b1i_acq_*_sat_9.mat" --code-length 2046
```

判定标准：
- `positive=1`：PRN9 捕获成功。
- `has2=1`：捕获域检测到第二峰。
- B1I 1 chip 约 `146.5m`，`1000m` 对应约 `6.8 chips`；若输出 `Δ≈6~7 chips`，说明 1000m 第二径识别成功。

**2026-07-16 成功实测**：双模拟器 `0m + 1000m` 同时发射，默认 `pfa=0.001` 下 `positive=1`、`has2=1`，检测到 `Δ≈6.65 chips ≈ 974m`，与设置的 `1000m` 匹配；已生成 2D/3D 谱峰图。

## 2C. 2026-07-16 标准化双模拟器测试命令

今天在服务器上反复使用的流程如下，后续 Claude 或新的 AI 接手时优先照这个跑。它的特点是：**先用 B210 录原始样点，再用 File source 离线跑 acquisition dump**，这样不会受实时 CPU/overflow 影响，也能稳定画 2D/3D 谱峰图。

### 2C.1 测试前人工确认

1. Windows 模拟器侧确认：
   - 两台模拟器都发 **BDS B1I PRN9**。
   - 一台无补偿，另一台设置目标补偿，如 `+200m`、`+1000m`、`+1030m`。
   - 记录两路发射功率，例如 `-40/-40 dBm` 或 `-40/-50 dBm`。
2. USRP/B210 侧确认：
   - 接收口：`RX2`。
   - 当前实测可用设置：`gain=76`，`rate=4 Msps`，`freq=1561.098 MHz`。
   - 测试前不要有残留 `gnss-sdr` 进程；实时测试前关 Firefox，离线测试也建议保持机器干净。

### 2C.2 一条命令跑完整离线测试

把下面的 `TAG` 和 `RAW` 改成这次测试的名字。示例假设测试是 `+1000m`、两路 `-40/-40 dBm`：

```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya

TAG=b1i_twosim_1000m_equal_power
RAW=/tmp/${TAG}.dat

rm -f bds_b1i_acq_C_B1_ch_0_1_sat_9.mat \
      bds_b1i_acq_C_B1_ch_0_1_sat_9.png \
      bds_b1i_acq_C_B1_ch_0_1_sat_9_3d.png

python3 dev_notes/sim/record_b210.py --secs 10 --gain 76 --ant RX2 \
  --freq 1561098000 --rate 4000000 -o "$RAW" \
  > /tmp/${TAG}_record.log 2>&1

cp dev_notes/sim/b1i_offline_prn9.conf /tmp/${TAG}_pfa001.conf
sed -i "s#^SignalSource.filename=.*#SignalSource.filename=${RAW}#" /tmp/${TAG}_pfa001.conf
sed -i "s#^Acquisition_B1.pfa=.*#Acquisition_B1.pfa=0.001#" /tmp/${TAG}_pfa001.conf

./build-conda/src/main/gnss-sdr --config_file=/tmp/${TAG}_pfa001.conf \
  > /tmp/${TAG}_run.log 2>&1

python3 dev_notes/sim/analyze_multipath.py \
  --pattern "bds_b1i_acq_C_B1_ch_0_1_sat_9.mat" --code-length 2046 \
  | tee /tmp/${TAG}_analyze.log

python3 dev_notes/sim/plot_acq_grid.py \
  "bds_b1i_acq_C_B1_ch_0_1_sat_9.mat" --code-length 2046 --zoom-chips 30

python3 dev_notes/sim/plot_acq_3d.py \
  bds_b1i_acq_C_B1_ch_0_1_sat_9.mat --code-length 2046

cp bds_b1i_acq_C_B1_ch_0_1_sat_9.mat /tmp/${TAG}_pfa001.mat
cp bds_b1i_acq_C_B1_ch_0_1_sat_9.png /tmp/${TAG}_pfa001.png
cp bds_b1i_acq_C_B1_ch_0_1_sat_9_3d.png /tmp/${TAG}_pfa001_3d.png
```

### 2C.3 判定方法

正式判定必须同时看三个量：

- `positive=1`：主捕获通过，`test_statistic > threshold`。
- `has2=1`：第二峰通过多径判定。
- `abs(Δm)` 是否接近设置的补偿距离。

注意：两路等功率时，算法按强度选主峰，不按先到/后到选主峰，所以 `Δm` 可能为负。判断补偿距离时看 `abs(Δm)`。

B1I 在 4 Msps 下每 chip 约 `146.5m`，每个采样点约 `0.51 chip ≈ 75m`。因此捕获域第二峰距离会有几十米级台阶误差，`974m`、`1049m` 这类结果都可视为 1000m 量级匹配。

### 2C.4 今日实测结论速表

| 设置 | 功率 | 结果 | 结论 |
|------|------|------|------|
| `+70m` | `-40/-50 dBm` | `positive=1, has2=0` | 70m≈0.48 chip，捕获域不可分，需跟踪域多相关器 |
| `+200m` | `-40/-50 dBm` | `positive=1, has2=0` | 第二径弱 10 dB 时未过判定 |
| `+200m` | `-40/-40 dBm` | `positive=1, has2=1, abs(Δ)≈225m` | 捕获域能检出，接近 200m |
| `+1000m` | `-40/-40 dBm` | `positive=1, has2=1, abs(Δ)≈1049m` | 远距双峰检出成功 |
| `+1030m` | `-40/-40 dBm` | `positive=1, has2=1, abs(Δ)≈974m` | 远距双峰检出成功，量化/排序导致几十米级偏差 |

今天生成的代表性图片都在 `dev_notes/sim/`，文件名形如 `bds_b1i_twosim_<距离>_<条件>_pfa001_3d.png`。

## 3. 分析多径（读 dump 出表）
注意：当前 `my_bds_b1i_twopath.conf` 是实时保守档，`Acquisition_B1.dump=false`，所以实时跑完**不会**生成 `bds_b1i_acq_*.mat`。`analyze_multipath.py` 和 2D/3D 谱峰图只能用于 acquisition dump，通常应配合离线配置 `b1i_offline_prn9.conf` 使用。

```bash
python3 dev_notes/sim/analyze_multipath.py --pattern "bds_b1i_acq_*_sat_*.mat" --code-length 2046
```
输出每份 dump 的：主径/第二径码片、Δ延迟(码片和米)、功率比 dB、has2 标志。B1I：1 码片≈146.6m。

看 observables 里的伪距：
```bash
python3 dev_notes/sim/read_observables_dump.py bds_b1i_observables.dat --channels 4 --tail 20
```
GNSS-SDR 默认不会把每个通道的 `Pseudorange_m` 持续打印到终端；当前配置把它写入 `bds_b1i_observables.dat`。这个文件是二进制，不要直接 `cat`，用上面的脚本看。

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
  | `Acquisition_B1.pfa` | 捕获虚警率，越大门限越低 | OTA 诊断可用 0.01；0.05/0.1 只适合临时扫门限，假捕获风险高 |
  | `multipath_threshold_fraction` | 第二峰判定灵敏度 | 漏检调小(0.18)、误报调大(0.3) |
  | `multipath_max_delay_chips` | 主峰邻域搜索窗(码片) | 近多径 2~3，远反射更大 |
  | `SignalSource.gain` | B210 增益 | 弱信号/OTA 可试 70~76；直连或开功放后必须复测削顶 |
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
| 一颗星都捕不到 | 先走 `2A` 离线验收。若 `test_statistic < threshold`，就是 B210 侧信号不够强/天线链路不对；手机能看到不算通过 |
| 编译报缺 `xxx.h` | 某可选功能缺 conda 包 → `conda install -c conda-forge <包>` 或 `-DENABLE_XXX=OFF` |

---
*2026-07-14 重写为 conda/B210/B1I 权威运行手册。历史（B1C 早期思路、系统 GR3.7 编译）见 `05` 与本文件 git 历史。*
