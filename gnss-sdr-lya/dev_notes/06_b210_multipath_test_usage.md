# 06 · 运行手册：conda 环境 + USRP B210 + 多径捕获测试

> **这是当前唯一权威的"怎么编译、怎么跑 B210 多径测试"手册。** 早期文件名里带 B1C，但当前已经扩展为 B1I、GPS L5I 等多信号测试入口。
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

## 1A. 最短复制版：直接跑一次离线多径测试

如果只是想自己做一次测试，优先复制本节命令。下面命令会自动完成：

`B210录样 -> 样点幅度统计 -> 生成临时conf -> 跑GNSS-SDR离线捕获 -> 分析.mat -> 自动选择best dump画2D/3D图`

### GPS L5I PRN18

```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya

bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 \
  --prn 18 \
  --tag gps_l5_prn18_twosim_1000m \
  --secs 30 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100
```

长时间测试不要手工 `sed` 改脚本。直接传 `--secs 100`，脚本会自动切成 30 秒以内的小段，例如 `100s = 30+30+30+10`，分别录制和分析，最后从所有片段里挑 best dump：

```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 \
  --prn 18 \
  --tag gps_l5_prn18_twosim_1000m_100s \
  --secs 100 \
  --expected-delay-m 1000 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100
```

如果本次补偿是 300m，把 `--expected-delay-m` 和 `--tag` 改成 300。注意：`--expected-delay-m` 只用于额外打印“哪个候选最接近预期”的提示，不参与最终伪距差统计。

```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 \
  --prn 18 \
  --tag gps_l5_prn18_twosim_300m_100s \
  --secs 100 \
  --expected-delay-m 300 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100
```

如果本次补偿是 2000m，L5 对应约 `68.2 chips`，第二峰搜索窗必须大于这个值。当前 L5 离线配置默认已改为 `90 chips`，也可以显式写在命令里：

```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 \
  --prn 18 \
  --tag gps_l5_prn18_twosim_2000m_30s \
  --secs 30 \
  --chunk-secs 10 \
  --expected-delay-m 2000 \
  --max-delay-chips 90 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100
```

这样做是为了避免 L5 `10 Msps × complex64` 在 100 秒时形成约 `8GB` 的单个连续写盘流。测试机上这种长时间大文件连续写入会触发磁盘 flush/调度抖动，进而让 USRP/GNU Radio 缓冲来不及消费并出现大量 overflow。脚本现在会按片段执行“录制 -> `sync` 落盘 -> 离线分析 -> 再录下一段”，避免多个大文件的后台写回叠在下一次 B210 采样期间。

如果只想复用上次录好的 `/tmp/gps_l5_prn18_twosim_1000m.dat`，不重新采样：

```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 \
  --prn 18 \
  --tag gps_l5_prn18_twosim_1000m \
  --skip-record
```

### BDS B1I PRN9

```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya

bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal b1i \
  --prn 9 \
  --tag b1i_prn9_twosim_1000m \
  --secs 30 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100
```

### 运行完看哪里

脚本最后会打印这些文件：

```text
/tmp/<tag>_record.log     # 录样日志，看 overflow
/tmp/<tag>_run.log        # GNSS-SDR 运行日志
/tmp/<tag>_analyze.log    # 多径分析表
/tmp/<tag>_best.mat       # 自动选出的最高 test dump
/tmp/<tag>_best.png       # 2D 谱峰图
/tmp/<tag>_best_3d.png    # 3D 谱峰图
```

如果用了 `--secs 100` 这类分段测试，还会额外生成：

```text
/tmp/<tag>_part01_record.log
/tmp/<tag>_part01_analyze.log
/tmp/<tag>_part01_best.png
...
```

总的 `/tmp/<tag>_best.*` 仍然是脚本从所有片段里自动挑出的最好结果。

客观测量结果看：

```text
/tmp/<tag>_summary.log
/tmp/<tag>_summary.tsv
```

其中 `objective_abs_delta_m_median/mean/std` 是从所有 `positive_acq=1 && has2=1` 的有效 dump 自动统计出来的真实相对伪距差；它不使用 `--expected-delay-m`。

正式成功要同时满足：

- `positive_acq=1` 或分析表对应 dump 的 `test_statistic > threshold`
- `has2=1`
- `abs(Δ米)` 接近模拟器补偿距离，比如 `1000m`

说明：本文后面的 `<TAG>`、`<PRN>`、`<dump.mat>` 是模板占位符，不能原样复制。要直接复制运行，用本节的 `run_b210_offline_multipath_test.sh`。

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
python3 dev_notes/sim/record_b210.py --secs 30 --gain 76 --ant RX2 \
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

python3 dev_notes/sim/record_b210.py --secs 30 --gain 76 --ant RX2 \
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

## 2D. GPS L5I 多径捕获分离测试

L5 可以复用今天 B1I 的“录制 -> 离线 acquisition dump -> 分析/画图”流程，但不能直接照搬所有参数：

- 频点改为 GPS L5：`1176.45 MHz`。
- 建议采样率改为 `10 Msps`。L5 码率是 `10.23 Mcps`，继续用 B1I 的 `4 Msps` 太窄，不适合做 L5 捕获谱分离。
- 分析脚本继续用同一套，但 `--code-length` 必须改成 `10230`。
- L5 1 chip 约 `29.3m`，所以 `200m≈6.8 chips`、`1000m≈34.1 chips`，比 B1I 更容易在捕获域分开。

新增离线配置：

```bash
dev_notes/sim/l5_offline_prn1.conf
```

先按你的模拟器 PRN 修改：

```bash
# 如果不是 PRN1，改这里
Channel0.satellite=1

# 如果录样文件名不同，改这里
SignalSource.filename=/tmp/l5_prn1.dat
```

推荐测试命令：

```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya

TAG=gps_l5_twosim_1000m_equal_power
RAW=/tmp/${TAG}.dat

python3 dev_notes/sim/record_b210.py --secs 30 --gain 76 --ant RX2 \
  --freq 1176450000 --rate 10000000 -o "$RAW"

cp dev_notes/sim/l5_offline_prn1.conf /tmp/${TAG}.conf
sed -i "s#^SignalSource.filename=.*#SignalSource.filename=${RAW}#" /tmp/${TAG}.conf
# 如果模拟器不是 GPS L5 PRN1，也一起改：
# sed -i "s#^Channel0.satellite=.*#Channel0.satellite=<PRN>#" /tmp/${TAG}.conf

rm -f gps_l5_acq*.mat gps_l5_acq*.png
./build-conda/src/main/gnss-sdr --config_file=/tmp/${TAG}.conf \
  2>&1 | tee /tmp/${TAG}_run.log

python3 dev_notes/sim/analyze_multipath.py \
  --pattern "gps_l5_acq_*_sat_*.mat" --code-length 10230

python3 dev_notes/sim/plot_acq_grid.py \
  "gps_l5_acq_*_sat_*.mat" --code-length 10230 --zoom-chips 80

python3 dev_notes/sim/plot_acq_3d.py \
  "gps_l5_acq_*_sat_*.mat" --code-length 10230
```

判定仍然一样：

- `positive=1`：主捕获通过。
- `has2=1`：第二峰通过多径判定。
- `abs(Δm)` 接近模拟器补偿距离。

注意：如果只新增 L5 配置，不改脚本，**可以分析和画图**；只是每次命令都要显式传 `--code-length 10230`。如果后续嫌麻烦，可以再给脚本加一个 `--signal l5` 的便捷参数。

## 2E. 每次采样测试与字段判读清单

这一节记录目前每次 SSH 测试实际使用的判断流程。核心原则：**先看录样质量，再看主捕获是否过门限，最后才看第二峰距离**。如果 `positive_acq=0`，即使第二峰距离接近目标补偿，也只能算候选，不能算正式多径检出。

### 2E.1 标准测试链路

1. 录 B210 原始样点：

```bash
python3 dev_notes/sim/record_b210.py --secs 30 --gain 76 --ant RX2 \
  --freq <频点Hz> --rate <采样率Hz> -o /tmp/<TAG>.dat \
  2>&1 | tee /tmp/<TAG>_record.log
```

常用频点和码长：

| 信号 | 频点 | 采样率 | 分析码长 | 1 chip |
|------|------|--------|----------|--------|
| BDS B1I | `1561098000` | `4000000` | `2046` | 约 `146.5m` |
| GPS L5I | `1176450000` | `10000000` | `10230` | 约 `29.3m` |

2. 用离线配置跑 GNSS-SDR：

```bash
cp dev_notes/sim/<offline.conf> /tmp/<TAG>.conf
sed -i "s#^SignalSource.filename=.*#SignalSource.filename=/tmp/<TAG>.dat#" /tmp/<TAG>.conf
sed -i "s#^Channel0.satellite=.*#Channel0.satellite=<PRN>#" /tmp/<TAG>.conf

rm -f bds_b1i_acq*.mat gps_l5_acq*.mat bds_b1i_acq*.png gps_l5_acq*.png
./build-conda/src/main/gnss-sdr --config_file=/tmp/<TAG>.conf \
  2>&1 | tee /tmp/<TAG>_run.log
```

3. 分析 `.mat` dump：

```bash
# B1I
python3 dev_notes/sim/analyze_multipath.py \
  --pattern "bds_b1i_acq_*_sat_*.mat" --code-length 2046 \
  | tee /tmp/<TAG>_analyze.log

# L5
python3 dev_notes/sim/analyze_multipath.py \
  --pattern "gps_l5_acq_*_sat_*.mat" --code-length 10230 \
  | tee /tmp/<TAG>_analyze.log
```

4. 画图：

```bash
python3 dev_notes/sim/plot_acq_grid.py "<dump.mat>" --code-length <2046或10230> --zoom-chips <窗口>
python3 dev_notes/sim/plot_acq_3d.py "<dump.mat>" --code-length <2046或10230>
```

### 2E.2 录样质量先看什么

先看 `/tmp/<TAG>_record.log`：

- 有无 `usrp_source :error ... overflows occurred` 或终端 `O`。少量开头 overflow 不一定让文件完全不可用，但正式结论优先用无 overflow 的样本。
- `actual: rate=... freq=... gain=... bw=...` 是否和本次测试一致。
- `done: /tmp/<TAG>.dat` 是否正常结束。

再看样点幅度，排除削顶和过弱：

```bash
python3 - <<'PY'
import numpy as np, os
p="/tmp/<TAG>.dat"
x=np.fromfile(p,dtype=np.complex64)
a=np.abs(x)
print("bytes", os.path.getsize(p), "samples", x.size)
print("rms", float(np.sqrt(np.mean(a*a))), "mean_abs", float(a.mean()), "max_abs", float(a.max()))
print("gt0.1", int((a>0.1).sum()), "gt0.2", int((a>0.2).sum()), "gt0.5", int((a>0.5).sum()))
print("real_minmax", float(x.real.min()), float(x.real.max()))
print("imag_minmax", float(x.imag.min()), float(x.imag.max()))
PY
```

经验读法：

- `max_abs` 接近 1 或大量 `gt0.5/gt0.8`：可能削顶，先降增益或发射功率。
- `rms` 明显比历史成功样本低：链路可能变弱，先检查模拟器、天线、线缆和频点。
- L5 最近成功样本约 `rms≈0.020`；这个值不是门限，只是现场对比参考。

### 2E.3 `.mat` 里主要看哪些字段

用这个命令查看某个 dump 的字段：

```bash
python3 - <<'PY'
import h5py, numpy as np
f="<dump.mat>"
with h5py.File(f,"r") as h:
    for k in h.keys():
        a=np.array(h[k])
        print(k, a.shape, a.dtype, a.reshape(-1)[:5])
PY
```

当前多径判断主要字段：

| 字段 | 含义 | 怎么看 |
|------|------|--------|
| `PRN` | 当前 dump 对应卫星号 | 必须等于本次模拟器 PRN |
| `positive_acq` | 主捕获是否通过 | 正式结果必须为 `1` |
| `test_statistic` | 主峰捕获统计量 | 必须大于 `threshold` |
| `threshold` | 当前 PFA/积分参数算出的门限 | `max_dwells` 增大时门限也可能变大 |
| `has_second_peak` | 是否检出第二峰 | 多径判断需要为 `1` |
| `acq_delay_samples` | GNSS-SDR 交给跟踪的主峰样点位置 | 用于计算主峰位置 |
| `acq_delay_samples_2` | 第二峰样点位置 | 用于计算第二径距离 |
| `acq_grid` | Doppler × 码相位相关谱面 | 画 2D/3D 图、独立找主峰 |
| `peak_ratio` | 主峰/第二峰功率比 | 转成 dB 后越小，第二径越强 |
| `test_statistic_2` | 第二峰统计量 | 可辅助计算主/副峰比 |
| `acq_doppler_hz` | 主峰 Doppler | 看本次命中的 Doppler 是否合理 |
| `num_dwells` | 实际非相干积分次数 | 确认 `max_dwells=10` 是否生效 |
| `input_power` | 捕获输入功率估计 | 用于同一配置下横向比较强弱 |
| `sample_counter` | dump 对应样点时间位置 | 多 dump 时可看出现在哪个时刻 |

### 2E.4 第二峰距离怎么换算

`analyze_multipath.py` 的常规读法：

- 从 `acq_grid` 的峰值行独立找主峰码相位。
- 读取 `acq_delay_samples_2` 得到第二峰码相位。
- 用 `spc = acq_grid.shape[1] / code_length` 得到每 chip 多少样点。
- `Δchip = 第二峰chip - 主峰chip`。
- `Δm = Δchip × 每chip米数`。

对于 GPS L5 最近的手工统计，也可按样点差直接算环形最短距离：

```python
CODE_CHIPS = 10230.0
SAMPLES_PER_CODE = 10000.0
CHIP_M = 299792458.0 / 10.23e6
ds = ((d2 - d1 + SAMPLES_PER_CODE / 2) % SAMPLES_PER_CODE) - SAMPLES_PER_CODE / 2
dchip = ds * CODE_CHIPS / SAMPLES_PER_CODE
dm = dchip * CHIP_M
```

注意：

- 双源等功率时，主峰/第二峰按强度排序，不一定按直射/反射排序，所以 `Δm` 可能为负；判断补偿量时看 `abs(Δm)`。
- B1I 4 Msps 下采样点约 `75m`，几十米级台阶误差正常。
- L5 10 Msps 下每 chip 约 `29.3m`，`1000m` 约 `34.1 chips`。
- 如果目标补偿超过 `multipath_max_delay_chips × 每chip米数`，第二峰搜索窗不覆盖目标延迟；例如 L5 旧配置 `60 chips` 只覆盖约 `1758m`，测 `2000m` 会落在窗边/其他峰上，常见现象是 `positive_acq=1` 但 `has_second_peak=0`，此时不能把 `Δm` 当成有效多径距离。

### 2E.5 正式判定标准

一轮测试建议按这个顺序写结论：

1. 录样是否可信：无严重 overflow、无削顶、频点/采样率/天线口正确。
2. 主捕获是否通过：`positive_acq=1` 且 `test_statistic > threshold`。
3. 第二峰是否通过：`has_second_peak=1`。
4. 第二峰距离是否匹配：`abs(Δm)` 接近模拟器补偿距离。

结论分类：

| 结果 | 解释 |
|------|------|
| `positive_acq=1, has_second_peak=1, abs(Δm)` 接近补偿 | 正式多径检出成功 |
| `positive_acq=1, has_second_peak=0` | 主信号捕获成功，但没有有效第二峰 |
| `positive_acq=0`，但有很多 `abs(Δm)` 接近补偿的候选 | 只能说谱面里有候选结构，不能作为正式检出 |
| `test_statistic` 接近但低于 `threshold` | 现场链路可能接近可用，优先复测/稳链路，再考虑临时调 `pfa` |
| 3D 图没有清晰尖峰 | 先查频点、限带、overflow、模拟器信号和天线，不要先怀疑多径算法 |

### 2E.6 临时统计多个 dump 的常用脚本

当 `.mat` 很多时，用下面脚本按 `test_statistic` 和 1000m 附近候选排序。B1I/L5 只需要改 `PATTERN`、`CODE_CHIPS`、`SAMPLES_PER_CODE` 和 `CHIP_M`。

```bash
python3 - <<'PY'
import glob, h5py, numpy as np, os, re

PATTERN = "gps_l5_acq_G_L5_ch_0_*_sat_18.mat"
CODE_CHIPS = 10230.0
SAMPLES_PER_CODE = 10000.0
CHIP_M = 299792458.0 / 10.23e6

rows=[]
for f in glob.glob(PATTERN):
    with h5py.File(f,"r") as h:
        g=lambda k: np.array(h[k]).reshape(-1)[0]
        pos=int(g("positive_acq"))
        test=float(g("test_statistic"))
        thr=float(g("threshold"))
        has2=int(g("has_second_peak"))
        d1=float(g("acq_delay_samples"))
        d2=float(g("acq_delay_samples_2")) if "acq_delay_samples_2" in h else np.nan
        ds=((d2-d1+SAMPLES_PER_CODE/2)%SAMPLES_PER_CODE)-SAMPLES_PER_CODE/2
        dchip=ds*CODE_CHIPS/SAMPLES_PER_CODE
        dm=dchip*CHIP_M
        ratio=10*np.log10(float(g("test_statistic"))/float(g("test_statistic_2"))) if "test_statistic_2" in h and float(g("test_statistic_2"))>0 else np.nan
        dop=float(g("acq_doppler_hz"))
        m=re.search(r"_0_(\d+)_sat_", f)
        idx=int(m.group(1)) if m else -1
        rows.append((f,idx,pos,test,thr,has2,dchip,dm,ratio,dop))

print("dump_count", len(rows))
print("positive", sum(r[2] for r in rows), "positive_has2", sum(1 for r in rows if r[2] and r[5]))
print("near_abs_800_1200m(has2)", sum(1 for r in rows if r[5] and 800 <= abs(r[7]) <= 1200))
print("near_abs_800_1200m(positive_has2)", sum(1 for r in rows if r[2] and r[5] and 800 <= abs(r[7]) <= 1200))

print("\nTOP_BY_TEST")
for r in sorted(rows, key=lambda x:x[3], reverse=True)[:12]:
    print(os.path.basename(r[0]), "idx",r[1], "pos",r[2], "test",f"{r[3]:.2f}", "thr",f"{r[4]:.2f}",
          "has2",r[5], "dchip",f"{r[6]:.1f}", "dm",f"{r[7]:.0f}", "ratio_db",f"{r[8]:.1f}", "dop",f"{r[9]:.0f}")

print("\nNEAR_1000_BY_ABS")
for r in sorted([r for r in rows if r[5]], key=lambda x: abs(abs(x[7])-1000))[:12]:
    print(os.path.basename(r[0]), "idx",r[1], "pos",r[2], "test",f"{r[3]:.2f}", "thr",f"{r[4]:.2f}",
          "dchip",f"{r[6]:.1f}", "dm",f"{r[7]:.0f}", "ratio_db",f"{r[8]:.1f}", "dop",f"{r[9]:.0f}")
PY
```

## 2F. 如何指定 PRN，以及如何锁多颗卫星

### 单颗卫星：改 `Channel0.satellite`

锁哪颗卫星是在配置文件里指定的，不在脚本里。核心参数是：

```conf
Channel.signal=<信号名>
Channel0.satellite=<PRN>
```

B1I 当前离线配置示例：

```conf
Channels_B1.count=1
Channel.signal=B1
Channel0.satellite=9
```

GPS L5I 当前离线配置示例：

```conf
Channels_L5.count=1
Channel.signal=L5
Channel0.satellite=1
```

如果你的 L5 模拟器发的是 PRN9，就把 L5 配置改成：

```conf
Channel0.satellite=9
```

### 多颗卫星：增加通道数并逐个指定 PRN

可以锁两颗、三颗或更多。做法是把 `Channels_<signal>.count` 改成通道数，然后给每个通道指定卫星。

GPS L5I 三颗星示例：

```conf
Channels_L5.count=3
Channels.in_acquisition=1
Channel.signal=L5

Channel0.satellite=1
Channel1.satellite=2
Channel2.satellite=9
```

B1I 三颗星示例：

```conf
Channels_B1.count=3
Channels.in_acquisition=1
Channel.signal=B1

Channel0.satellite=3
Channel1.satellite=6
Channel2.satellite=9
```

离线分析时，多个通道会生成多份 `.mat`。分析和画图命令用通配符即可：

```bash
# GPS L5I
python3 dev_notes/sim/analyze_multipath.py \
  --pattern "gps_l5_acq_*_sat_*.mat" --code-length 10230

# B1I
python3 dev_notes/sim/analyze_multipath.py \
  --pattern "bds_b1i_acq_*_sat_*.mat" --code-length 2046
```

### 每颗卫星两条径：通道数要按 `卫星数 × 2`

如果目标不是只看捕获谱，而是“每颗卫星两条径都持续跟踪”，需要双路径机制。B1I 当前已有这套机制：

```conf
Channels_B1.count=6          ; 3 颗星 × 2 条径
Channels_B1.signal_paths=2
Channel.signal=B1
```

L5 当前新增的是**离线捕获谱验证配置**，用于看 acquisition dump 里是否能分出两峰；它还不是完整的 L5 双路径实时跟踪配置。也就是说：

- 只做 L5 多径捕获分离测试：新增的 `l5_offline_prn1.conf` 足够。
- 要做 L5 每星两径实时跟踪：后续还需要按 B1I 的 `signal_paths=2` 机制补一份 L5 实时/双路径配置，并实测 flowgraph 是否完整支持。

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
