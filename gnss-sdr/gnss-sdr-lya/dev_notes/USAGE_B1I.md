# 明天用真实 B1I 数据操作 · 使用手册

> 目标读者：拿到真实 BeiDou B1I 采集数据后，直接用本工具做**多径检测**与**双路径跟踪**。
> 工具已就绪：修改过的 `gnss-sdr` 二进制 + 配置 + 分析脚本，都在 WSL2 里可跑。
> 背景/进度看 `dev_notes/README.md`；代码改动与验证看 `dev_notes/05`。

## 0. 已经为你做好的东西
- **改过的接收机**：`build/src/main/gnss-sdr`（捕获层已加：第二峰检测、`acquire_second_path`、多径日志）。
- **配置**（在 `dev_notes/sim/`）：
  - `bds_b1i_multipath.conf` —— **多径扫描**：每颗可见卫星捕获时检测并打印第二径。
  - `bds_b1i_dualpath.conf` —— **双路径跟踪**：对指定卫星同时跟直射+反射两条径。
- **分析脚本**：`dev_notes/sim/analyze_multipath.py`（读 dump 出多径表）。

## 1. 前提
- WSL2 Ubuntu（已装好依赖，已编译）。Windows 里 `D:\...` 在 WSL 里是 `/mnt/d/...`。
- 若改了源码要重编：`cd /mnt/d/work/project/usrp_gnss/gnss-sdr && cmake --build build -j20`

## 2. 第一步：多径扫描（先跑这个）
**① 放数据 + 改配置** `dev_notes/sim/bds_b1i_multipath.conf` 里标了 `★ 改这里` 的几行：
- `SignalSource.filename` = 你的数据文件（WSL 路径，如 `/mnt/d/work/data/xxx.dat`）
- `SignalSource.item_type` = 采样格式：`byte`/`ibyte`/`ishort`/`gr_complex`/`short`（看你的采集）
- `SignalSource.sampling_frequency` 和 `GNSS-SDR.internal_fs_sps` = 你的采样率
- `InputFilter.IF` = 数据中频（**复数基带填 0**）
- 若是**复数基带 I/Q**（如 USRP）：把 `InputFilter.implementation` 改成 `Pass_Through`，
  `DataTypeAdapter.implementation` 改成对应类型（如 `Ishort_To_Complex`）。

**② 运行**（`GLOG_logtostderr=1` 才能在屏幕看到多径日志）：
```bash
cd /mnt/d/work/project/usrp_gnss/gnss-sdr/dev_notes/sim
GLOG_logtostderr=1 /mnt/d/work/project/usrp_gnss/gnss-sdr/build/src/main/gnss-sdr \
    --config_file=./bds_b1i_multipath.conf 2>&1 | grep -E "Successful acquisition|MULTIPATH"
```
**③ 看输出**：每颗有多径的卫星会打印一行，例如：
```
MULTIPATH C 6: 2nd path at 361 chips (main 355 chips, delta 6 chips), main/2nd power ratio 4.6 dB, 2nd Doppler 1500 Hz
```
- `delta N chips` = 反射比直射滞后 N 个码片（B1I 1码片≈146.6m，故 6 码片≈880m 额外路程）。
- `power ratio X dB` = 直射比反射强 X dB（越小反射越强、越危险）。

**④ 详细分析相关面 dump**（dump_channel=0 那一路）：
```bash
python3 analyze_multipath.py --pattern "bds_b1i_acq_C_B1_ch_0_*_sat_*.mat" --code-length 2046
```
出一张表：每份 dump 的 主径/第二径/延迟(码片+米)/功率比dB。

## 3. 第二步：对某颗星双路径跟踪
从扫描结果挑出有明显多径的卫星（如 PRN 6），编辑 `bds_b1i_dualpath.conf`：
- 改数据源那几行（同上）。
- `Channel0.satellite` 和 `Channel1.satellite` 都填该 PRN（如 6）。
- 要跟多颗：把 `Channels_B1.count` 加到 2×颗数，复制通道对 + 对应的 `Acquisition_B1<奇数通道>` 块。

运行：
```bash
GLOG_logtostderr=1 /mnt/d/.../build/src/main/gnss-sdr --config_file=./bds_b1i_dualpath.conf 2>&1 \
    | grep -E "started on channel"
```
应看到**同一 PRN 在两个通道都开始 Tracking**：通道0 跟直射、通道1 跟反射。
跟踪 dump 在 `./bds_b1i_dp_trk*`，可对比两路的码相位/伪距差 ≈ 多径延迟。

## 4. 调参（真实数据可能要调）
在 `Acquisition_B1[.*]` 段：
| 参数 | 含义 | 调法 |
|------|------|------|
| `multipath_threshold_fraction` | 第二峰判定灵敏度(×主峰门限) | 漏检→调小(0.15)；误报→调大(0.35) |
| `multipath_max_delay_chips` | 主峰邻域搜索窗(码片) | 只关注近多径→调小(2~3)；远反射→调大 |
| `max_dwells` | 非相干积分次数(压噪) | 弱反射浮不出来→调大(5~10)，但更慢 |
| `pfa` | 主峰虚警率 | 弱信号漏捕→略调大 |
| `doppler_max/step` | 多普勒范围/步进 | 静态平台可减小 doppler_max 提速 |

## 5. 结果怎么判读
- **有多径的卫星**：`delta` 为正的小值(几码片内)、`power ratio` 较小(如 <8dB)。
- **无多径**：要么没有 MULTIPATH 行，要么 `power ratio` 很大(第二"峰"只是噪声)。
- **NLOS(直射被挡)**：可能主峰本身就是反射；结合 `delta` 与后续跟踪判断。

## 6. 目前的局限（诚实告知）
- **伪距进 PVT**：两条径伪距同时进 RTKLIB 会在同 PRN 处冲突（**Stage 3 待做**）。当前先出"双径各自跟踪 + 观测量"，
  定位融合(判直射LOS、每星一条干净伪距进解算)是下一步。见 `dev_notes/04 §0/§6`。
- **近距多径(<1码片)**：捕获域分不开，需**跟踪域多相关器**（Stage 2 待做）。当前工具擅长 ≥1 码片的可分多径。
- **相关面 dump 只 dump_channel 那一路**；但**多径日志覆盖所有卫星**，扫描用日志即可。
- B1I 相关面 dump 较大(25MHz 下每份~20MB)，注意磁盘。

## 7. 出问题时
- 没有任何捕获/跟踪：多半是数据源参数不对（格式/采样率/IF）。先确认库存接收机能跑通你的数据
  （把 `multipath_detection` 关掉，看能否正常捕获跟踪）。
- 看不到 MULTIPATH 行：确认加了 `GLOG_logtostderr=1`，且 `Acquisition_B1.multipath_detection=true`。
- 编译/环境问题、参数含义：查 `dev_notes/05`（踩坑日志）和 `dev_notes/03`（配置项）。

---
*工具于 2026-07-12 就绪。改动全在捕获层，B1I 与 GPS 共用同一核心。*
