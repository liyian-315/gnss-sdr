# 08 · 现场排查 runbook：从"噪声谱面"到"可信多径检出"（手动逐步）

> **给拿到设备的人**：本篇是**按顺序手动执行**的排查+改进流程。触发原因见 `05` 2026-07-18：
> 现场 3D 谱面是一片**噪声草皮、无干净主峰**（`ratio≈4dB`），且 `50/100/200m` 补偿结果**无差别**
> → 铁证是**根本没干净捕获目标星**，多径分析全是空中楼阁。
>
> **门禁原则（最重要）**：**不跳步**。上一步"✅通过标准"没达到，就不进下一步。**多径永远是最后一步。**
> 每步给 [命令] + [✅通过标准] + [❌不过怎么办]。前置固定开头见 `06 §1`。相关字段判读见 `06 §2E`。

---

## 本次现场参数（先填，后面命令直接引用）

```
PRN         = 18          # 目标卫星，必须与模拟器一致
FREQ        = 1176450000  # GPS L5 中心频率 Hz
RATE        = 10000000    # 10 Msps
GAIN        = 76          # 起始增益，后面按削顶/欠量化调
ANT         = RX2
DEV         = serial=30F4100
SIM_A_COMP  = ?           # 模拟器A补偿(m)
SIM_B_COMP  = ?           # 模拟器B补偿(m)
```

## Step 0 · 环境（必做）

```bash
source ~/lya/miniforge3/etc/profile.d/conda.sh
conda activate gnsssdr
cd ~/lya/gnss-sdr/gnss-sdr-lya
ls build-conda/src/main/gnss-sdr   # 二进制在否；若刚 git pull 需重编见 06 §5
```

---

## Step 1 · 【最关键的门】单模拟器 → 干净捕获

**关掉第二台模拟器，只留一台发 PRN18。** 先证明接收机能干净看到一颗星。

**1.1 录 10 秒**
```bash
python3 dev_notes/sim/record_b210.py --secs 10 --gain 76 --ant RX2 \
  --device-args serial=30F4100 --freq 1176450000 --rate 10000000 \
  -o /tmp/l5_prn18_single.dat
```

**1.2 录样质量自检**（削顶/欠量化，`06 §2E.2` 的读法）
```bash
python3 - <<'PY'
import numpy as np, os
p="/tmp/l5_prn18_single.dat"; x=np.fromfile(p,dtype=np.complex64); a=np.abs(x)
print("samples",x.size,"rms",float(np.sqrt(np.mean(a*a))),"max_abs",float(a.max()))
print("gt0.5",int((a>0.5).sum()),"gt0.8",int((a>0.8).sum()))
PY
```
- ✅ `max_abs` 不贴近 1、`gt0.8` 很少（没削顶）；`rms` 不明显低于历史 L5 成功值 `~0.020`。
- ❌ 削顶 → 降 `--gain`（76→70→65）；太弱 → 升增益、查模拟器功率/天线/线缆/频点。

**1.3 离线跑捕获**（先只测单峰，把 `multipath_detection` 关掉排除干扰）
```bash
# 改 l5_offline_prn1.conf：filename→/tmp/l5_prn18_single.dat；Channel0.satellite=18
sed -i 's#^SignalSource.filename=.*#SignalSource.filename=/tmp/l5_prn18_single.dat#' dev_notes/sim/l5_offline_prn1.conf
sed -i 's#^Channel0.satellite=.*#Channel0.satellite=18#'                             dev_notes/sim/l5_offline_prn1.conf
sed -i 's#^Acquisition_L5.multipath_detection=.*#Acquisition_L5.multipath_detection=false#' dev_notes/sim/l5_offline_prn1.conf
rm -f gps_l5_acq_*_sat_18.mat
./build-conda/src/main/gnss-sdr --config_file=dev_notes/sim/l5_offline_prn1.conf
```

**1.4 判定捕获是否干净**（新脚本 `acq_health.py`，比 positive_acq 可靠）
```bash
python3 dev_notes/sim/acq_health.py "gps_l5_acq_*_sat_18.mat" --code-length 10230
python3 dev_notes/sim/plot_acq_3d.py  "gps_l5_acq_*_sat_18.mat" --code-length 10230
```
- ✅ **VERDICT=CLEAN**：`margin_db` 中位数 `>10`、`peak2floor_db > ~13`、`code_phase_std < 1 chip`；
  3D 图一根**尖峰清晰立在噪底之上**（不是草皮），主峰码相位多份 dump 稳定。
- ❌ **VERDICT=NOISE**（就是你现在的情况）→ 按下面排查树逐项排除，**不要动多径算法**：

  | 怀疑点 | 怎么查 / 怎么改 |
  |--------|----------------|
  | **频点** | 模拟器真在 L5(1176.45MHz)？发的是 L1/L2 就啥都没有。核对 `--freq` |
  | **PRN 错** | dump 文件名若是 `sat_23` 而非 `sat_18` = 互相关假峰/搜到别的星。config `Channel0.satellite` 必须=模拟器 PRN |
  | **增益** | 削顶(降gain) 或 欠量化(升gain)。回 1.2 看 `max_abs`/`rms` |
  | **天线口** | `--ant RX2` 是否接对；OTA 无源天线太弱可换直连 |
  | **模拟器** | 是否真在发射、功率够不够、两台是否共 10MHz/1PPS |
  | **采样格式** | 录样 `gr_complex@10Msps` 与 conf `internal_fs_sps=10000000`、`item_type=gr_complex` 一致 |
  | **积分不够** | `max_dwells` 已是 10；弱信号可再加长相干/非相干积分 |

> ⛔ **Step 1 不 CLEAN，后面全白搭。** 反复调到 CLEAN 再往下。

---

## Step 2 · 单路假警基线（标定第二峰门限）

仍**单模拟器**，打开多径检测。单路理论上**不该**有第二径。
```bash
sed -i 's#^Acquisition_L5.multipath_detection=.*#Acquisition_L5.multipath_detection=true#' dev_notes/sim/l5_offline_prn1.conf
rm -f gps_l5_acq_*_sat_18.mat
./build-conda/src/main/gnss-sdr --config_file=dev_notes/sim/l5_offline_prn1.conf
python3 dev_notes/sim/acq_health.py "gps_l5_acq_*_sat_18.mat" --code-length 10230
```
- ✅ `has_second_peak_rate ≈ 0`：单路不误报第二径。门限合适。
- ❌ 单路也大量 `has2=1` → 当前 `multipath_threshold_fraction`/搜索窗就是**假警机**。
  上调 `Acquisition_L5.multipath_threshold_fraction`（0.25→0.35→0.5）+ 收窄
  `Acquisition_L5.multipath_max_delay_chips`（90→40）直到单路 `has2≈0`。**记下标定值。**

---

## Step 3 · 【黄金标准】导线注入双路，已知延迟

**强烈建议先做这个**：两模拟器输出经**功率合路器** + 一路**已知长度延迟线**（或用模拟器内置双路径/延迟功能）→ **直连** B210（不走 OTA）。
延迟已知、无几何歧义、无天线弱信号 —— 这是验证"**算法本身对不对**"的唯一干净方式。

- 先设**大延迟**（如 1000m = 34 chip），搜索窗收到 ±40：
```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 --prn 18 --tag l5_conducted_1000m \
  --secs 30 --chunk-secs 10 --gain 76 --ant RX2 --device-args serial=30F4100 \
  --max-delay-chips 40 --expected-delay-m 1000
python3 dev_notes/sim/multipath_consistency.py /tmp/l5_conducted_1000m_summary.tsv --chip-m 29.3
```
- ✅ 3D 图**两根清晰尖峰**；`multipath_consistency.py` 给 **CONSISTENT**、`|Δ|≈1000m`。
- ❌ 导线注入下都还是噪声 → 问题 100% 在 **RF 电平/配置**，回 Step 1，不是算法。
- 💡 **若导线注入 CONSISTENT 但 OTA 噪声 → 元凶是 OTA 几何/链路（见 Step 4），算法没错。**

---

## Step 4 · 几何自检（若坚持 OTA）

- ⚠️ **站两天线正中间 → 两路程差 ≈ 0，不是 50m！** 物理间距 ≠ 接收端看到的 Δ伪距。
  `expected Δ` 要用**几何 + 补偿**算，别拿"物理 50m"当预期。
- 让接收机**明显偏向一侧**，或用**不等补偿**制造一个已知的、够大的 Δ。
- 两模拟器**必须共 10MHz/1PPS**；不共时钟 → 码相位随时间漂，第二峰不可能稳定聚集。

---

## Step 5 · 距离阶梯 + 时间一致性（找分离下限）

主捕获 CLEAN、门限标定好之后，才做这步。依次 `1000→700→350→200→100→50m`：
```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 --prn 18 --tag l5_ladder_200m \
  --secs 30 --chunk-secs 10 --gain 76 --ant RX2 --device-args serial=30F4100 \
  --max-delay-chips 20 --expected-delay-m 200
python3 dev_notes/sim/multipath_consistency.py /tmp/l5_ladder_200m_summary.tsv --chip-m 29.3
```
每级要求：目标 PRN 正确 + `acq_health=CLEAN` + `multipath_consistency=CONSISTENT`（Δ 聚集、std 小）+ 3D 稳定双峰。
- **记录"哪一级开始 SCATTERED"** = 捕获域分离下限 = 转跟踪域（架构B）的交接点。**这是本项目的关键实验结论。**

---

## Step 6 · 结论与转场

- `200m 稳、100/50m 散` → 确认捕获域到底。近距（<~2 chip）**必须**转 `04` 的 Stage 2：
  `dll_pll_veml_tracking` 加密相关器抽头重建相关函数 → MEDLL/double-delta 估计直射+反射。
- 连 **导线注入 1000m** 都噪声 → 不是算法，回 Step 1 修 RF/链路/配置。

---

## 附 · 本篇用到的脚本清单

| 脚本 | 用途 | 状态 |
|------|------|------|
| `sim/record_b210.py` | B210 录样 | 已有 |
| `sim/l5_offline_prn1.conf` | L5 离线捕获配置（改 filename/PRN/门限） | 已有 |
| `sim/run_b210_offline_multipath_test.sh` | 录样→离线跑→分析→画图一条龙 + summary.tsv | 已有 |
| `sim/acq_health.py` | **判定捕获是否干净**（CLEAN/MARGINAL/NOISE） | 🆕 首次用请先冒烟 |
| `sim/multipath_consistency.py` | **时间一致性**判据（CONSISTENT/SCATTERED），否掉噪声游走 | 🆕 首次用请先冒烟 |
| `sim/plot_acq_3d.py` / `plot_acq_grid.py` | 谱峰面 3D/2D 图 | 已有 |
| `sim/analyze_multipath.py` | dump 多径表 | 已有 |
| `sim/check_acq.py` | 快速看前几份 dump 的 positive/test/threshold | 已有 |

---

*最后更新：2026-07-18 · 承接 `05` 2026-07-18 噪声谱面根因诊断 · 新增 acq_health.py / multipath_consistency.py*
