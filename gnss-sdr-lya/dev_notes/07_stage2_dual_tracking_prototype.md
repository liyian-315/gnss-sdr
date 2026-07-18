# 07 - Stage 2 最小双跟踪原型交接记录

## 目标

第一阶段已经验证：GPS L5I 比 B1I 更适合在捕获谱峰面上分离远距多径。第二阶段先不大改通道管理器，先做一个最小可运行原型：

- 同一颗 L5 PRN 同时生成两条跟踪链路。
- `Signal_Path=0` 跟踪捕获最强峰，标记为 `primary`。
- `Signal_Path=1` 跟踪捕获阶段找到的第二峰，标记为 `second`。
- PVT 仍只消费 `Signal_Path=0`，避免把反射径当成独立卫星观测量喂给 RTKLIB。
- observables dump 直接输出伪距、Doppler、C/N0、路径标签，便于比较两条径的持续跟踪结果。

## 本次实现

### 0. 第二步：多颗卫星通用化

新增文件：

```text
dev_notes/sim/make_l5_dualpath_conf.py
```

用途：按 PRN 列表生成多颗 GPS L5I 卫星的双路径 tracking 配置。每颗 PRN 固定分配两个通道：

```text
PRN18 -> Channel0 path0 + Channel1 path1
PRN20 -> Channel2 path0 + Channel3 path1
PRN21 -> Channel4 path0 + Channel5 path1
```

生成示例：

```bash
python3 dev_notes/sim/make_l5_dualpath_conf.py \
  --prns 18,20,21 \
  --input /tmp/gps_l5_multi.dat \
  --output /tmp/l5_dualpath_multi.conf
```

运行：

```bash
./build-conda/src/main/gnss-sdr \
  --config_file=/tmp/l5_dualpath_multi.conf \
  2>&1 | tee l5_dualpath_multi_run.log

python3 dev_notes/sim/read_observables_dump.py \
  gps_l5_dualpath_observables.dat \
  --channels 6 \
  --tail 50 \
  --pairs
```

说明：

- 这里选择“显式 PRN 列表”而不是完全自动扫 PRN 池，是为了测试阶段可控、可复现。
- 底层 `GNSSFlowgraph` 已支持 `Channels_L5.signal_paths=2` 自动生成 `(PRN,path)` 信号池；后续要做“全可见星自动每星两径”时可以继续复用这个机制。

### 1. 扩展 observables dump

新增配置项：

```ini
Observables.dump_extended=true
```

默认值为 `false`，旧配置和旧 dump 格式不变。

开启后，Hybrid_Observables 每通道每历元从 7 个 double 扩展为 9 个 double：

```text
rx_time_s, tow_s, doppler_hz, carrier_cycles, pseudorange_m, prn, valid,
signal_path, cn0_db_hz
```

修改位置：

- `src/algorithms/observables/libs/obs_conf.h`
- `src/algorithms/observables/adapters/hybrid_observables.cc`
- `src/algorithms/observables/gnuradio_blocks/hybrid_observables_gs.cc`

### 2. 新增 L5 双路径配置

新增文件：

```text
dev_notes/sim/l5_dualpath_prn18.conf
```

这是文件源配置，默认读取：

```text
/tmp/gps_l5_prn18_twopath.dat
```

核心配置：

```ini
Channels_L5.count=2
Channels_L5.signal_paths=2
Channel0.satellite=18
Channel0.signal_path=0
Channel1.satellite=18
Channel1.signal_path=1
Acquisition_L5.multipath_detection=true
Acquisition_L5.multipath_max_delay_chips=90
Observables.dump=true
Observables.dump_extended=true
```

实现假设：

- `pcps_acquisition.cc` 已有逻辑：`Signal_Path==1` 会触发第二峰搜索，并把第二峰的 `Acq_delay_samples/Acq_doppler_hz` 交给 tracking。
- `rtklib_pvt_gs.cc` 已有逻辑：只用 `Signal_Path==0` 的观测量做 PVT。

### 3. 更新 dump 读取脚本

修改文件：

```text
dev_notes/sim/read_observables_dump.py
```

脚本现在兼容旧 7 列格式和新 9 列格式。新格式下会输出：

- `path`: `primary` / `second`
- `pseudorange_m`
- `doppler_hz`
- `cn0_db_hz`
- `--pairs` 下输出同一 PRN 的 `second - primary` 伪距差

第三步增加稳定机器输出：

```bash
python3 dev_notes/sim/read_observables_dump.py \
  gps_l5_dualpath_observables.dat \
  --channels 6 \
  --tail 200 \
  --format-out csv \
  --out gps_l5_dualpath_observables.csv

python3 dev_notes/sim/read_observables_dump.py \
  gps_l5_dualpath_observables.dat \
  --channels 6 \
  --tail 200 \
  --format-out jsonl \
  --out gps_l5_dualpath_observables.jsonl
```

稳定字段名：

```text
epoch, channel, system, signal, prn, signal_path, role,
rx_time_s, tow_s, pseudorange_m, doppler_hz, carrier_cycles,
cn0_db_hz, valid
```

约定：

- `role=primary` 等价于 `signal_path=0`。
- `role=second` 等价于 `signal_path=1`。
- 旧 7 列 dump 没有 C/N0，CSV 中 `cn0_db_hz` 为空，JSONL 中为 `null`。

## 使用步骤

先录制 L5 PRN18 双模拟器信号：

```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya

python3 dev_notes/sim/record_b210.py \
  --secs 30 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100 \
  --freq 1176450000 \
  --rate 10000000 \
  -o /tmp/gps_l5_prn18_twopath.dat
```

再运行双跟踪原型：

```bash
./build-conda/src/main/gnss-sdr \
  --config_file=dev_notes/sim/l5_dualpath_prn18.conf \
  2>&1 | tee l5_dualpath_prn18_run.log
```

读取两条径的伪距和 C/N0：

```bash
python3 dev_notes/sim/read_observables_dump.py \
  gps_l5_dualpath_observables.dat \
  --channels 2 \
  --tail 50 \
  --pairs
```

## 如何判读

期望看到：

- 同一 epoch、同一 PRN 同时有 `primary` 和 `second` 两行。
- 两行 `valid` 均为有效，因此默认输出会显示出来。
- `--pairs` 表中出现连续的 `delta_m = second - primary`。
- `cn0_db_hz` 不是 0 或异常值，说明 tracking 层持续给出了载噪比估计。

如果没有成对输出：

- 先看运行日志是否有 path1 的捕获成功和 tracking started。
- 确认采样文件确实含两路 L5 PRN18，且第二峰落在 `Acquisition_L5.multipath_max_delay_chips=90` 覆盖范围内。
- 用第一阶段脚本先跑捕获谱峰验证：

```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 \
  --prn 18 \
  --tag l5_prn18_check \
  --secs 30 \
  --chunk-secs 10 \
  --gain 76 \
  --ant RX2 \
  --device-args serial=30F4100
```

## 当前边界

这是“最小双跟踪原型”，不是最终通用版。

- 当前配置固定 PRN18、两条通道。
- 还没有把所有可见卫星自动扩展为“每星两条持续 tracking 输出”的最终工作流。
- 第二径目前只用于输出和分析，不参与 PVT 修正。
- 近距多径小于约 1 chip 时，仍需要后续 tracking 域多相关器/多峰估计改造。

## 下一步建议

1. 在服务器拉取本分支，编译 `gnss-sdr`。
2. 用已有 L5 双模拟器记录文件先跑 `l5_dualpath_prn18.conf`，确认 observables 扩展 dump 能连续成对输出。
3. 若 path1 容易失锁，再调 tracking 带宽和 `multipath_threshold_fraction`。
4. 原型稳定后，再从“固定 PRN 两通道”升级到“多 PRN 每星两路径自动输出”。
