# 方阵 SAGE/STAP 与线阵 FBSS 公平复现报告

**日期：** 2026-08-13

**作者：** Codex

**分支：** `research/coherent-music-parking-array`

## 1. 目标与结论边界

本工作按用户要求完成第一阶段：

1. 实现 `2×2` 方阵 SAGE/STAP multicorrelator 的逐路径迭代；
2. 实现四阵元 ULA 的 FBSS-MUSIC + 时延估计基线；
3. 两种方法使用相同路径、相同核、相同块数、相同噪声策略；
4. 放入两根发射天线相距 20 m 的停车场几何，扫描时延和功率比。

当前是**论文结构复现与理想核公平比较**，不是最终天线定型实验。NUC 在本轮不可达，仓库又没有 Phase A `Rtau CSV`，因此正式结果使用论文矩形码自相关核。脚本已支持 `--kernel-csv`，但真实核门禁尚未完成。

## 2. 复现的方法

### 2.1 `2×2` 方阵 SAGE/STAP

每条路径模型为：

$$
\mathbf x_l
=c_l\left[
\mathbf d(\nu_l)\otimes
\mathbf a(\theta_l)\otimes
\mathbf r(\tau_l)
\right],
$$

其中：

- $\mathbf d(\nu_l)$：20 个 `1 ms` 块上的多普勒相位；
- $\mathbf a(\theta_l)$：`2×2` 半波长方阵空间响应；
- $\mathbf r(\tau_l)$：20 个相关 tap 上的码相关响应；
- $c_l$：该路径的复幅度。

第 $i$ 次迭代、第 $l$ 条路径的隐藏数据是：

$$
\widehat{\mathbf x}^{(i)}_l
=\mathbf y-
\sum_{k\ne l}\widehat{\mathbf x}^{(i)}_k.
$$

在角度、时延和多普勒网格上最大化匹配似然：

$$
(\hat\theta_l,\hat\tau_l,\hat\nu_l)
=\arg\max_{\theta,\tau,\nu}
\frac{|\mathbf q^H(\theta,\tau,\nu)\widehat{\mathbf x}_l|^2}
{\|\mathbf q(\theta,\tau,\nu)\|^2},
$$

再更新：

$$
\hat c_l=
\frac{\mathbf q^H\widehat{\mathbf x}_l}{\mathbf q^H\mathbf q}.
$$

这是真正的逐径消除与更新，不是把旧 GLRT 改名为 SAGE。

### 2.2 ULA + FBSS

ULA 使用四个半波长阵元，取两个重叠的三阵元子阵。前后向空间平滑协方差为：

$$
\mathbf R_{\mathrm{FBSS}}
=\frac{1}{2}\left(
\frac{1}{L}\sum_{p=1}^{L}\mathbf R_p
+\mathbf J
\left[\frac{1}{L}\sum_{p=1}^{L}\mathbf R_p\right]^*
\mathbf J
\right).
$$

三维子阵中估计两个源，仍有一维噪声子空间，可以运行 MUSIC。角度恢复后，用两个空间导向矢量对**全部 multicorrelator taps**做最小二乘解混，再分别在同一个相关核上搜索码时延。

初版只用 Prompt tap 形成协方差，会在第二径接近 `1 chip` 时人为隐藏第二径；已修正为所有历元、所有 taps 共同形成空间协方差。两种方法现在使用相同观测信息。

## 3. 论文参数结构复现

复现参数：

| 项目 | 设置 |
|---|---|
| 阵列 | 四阵元 `2×2` 方阵 |
| 阵元间距 | `0.5 λ` |
| 积分块 | `20 × 1 ms` |
| 相关 tap | `P=20` |
| tap 间隔 | `Cs=0.1 chip` |
| 直达径 | 方位 `131°`、相对时延 `0`、相对多普勒 `0 Hz` |
| 第二径 | 方位 `-65°`、时延 `0.1 chip`、多普勒 `5 Hz`、功率 `-3 dB` |

单次结果：

- 直达径：`135° / 0 chip / 0 Hz`；
- 第二径：`-59° / 0.1 chip / 5 Hz`；
- SAGE 残差：`34.09 → 11.21`，迭代后不再上升。

100 次 Monte Carlo：

| 指标 | 结果 |
|---|---:|
| 直达径方位 RMSE | `3.83°` |
| 第二径方位 RMSE | `5.79°` |
| 第二径时延 RMSE | `0 chip`（受 `0.02 chip` 网格限制） |
| 第二径多普勒 RMSE | `0 Hz`（真值落在 `1 Hz` 网格） |
| 中位残差下降 | `4.89 dB` |

上述结果证明结构与迭代链路可运行，但不是论文全部曲线的数值复现：当前固定俯仰角，只搜索方位切片；未复现 CRB；真值又恰好落在时延/频率网格上。因此时延和多普勒零 RMSE 不能解释为无限精度。

## 4. 停车场公平比较

### 4.1 条件

- 两根发射天线：`(-10,0)` 与 `(10,0)` m；
- 接收机位置：`(0,5)`、`(-5,5)`、`(0,15)`、`(15,5)` m；
- 相对时延：`0.1/0.3/0.5/1.0 chip`，即 `2.93/8.79/14.65/29.3 m`；
- 第二路相对功率：`0/-6/-10 dB`；
- 每条件：每位置 20 次，共 80 次；
- 成功判据：两路角度 RMSE `≤5°` 且时延 RMSE `≤6 m`；
- 两方法均使用 40 个块、31 个 taps、同一理想核与相同噪声策略。

ULA 单独报告两个口径：

- `ULA_FBSS_blind`：不提供发射源所在半平面；
- `ULA_FBSS_halfplane`：只提供“两个停车场发射源位于接收机下方”的半平面先验，不提供两路真值角度。

### 4.2 总体结果

| 方法 | 总成功率 | 中位角度 RMSE | 中位时延 RMSE |
|---|---:|---:|---:|
| `2×2 SAGE/STAP` | `85.5%` | `0.69°` | `0 m` |
| `ULA+FBSS`，无半平面先验 | `0%` | `62.65°` | `0 m` |
| `ULA+FBSS`，有停车场半平面先验 | `100%` | `0.31°` | `0 m` |

ULA 的 `0%` 不是 FBSS 没解开相干源，而是四阵元直线阵存在前后镜像；加入场景中可事先知道的半平面后恢复正常。这两个口径都必须保留，否则会分别夸大或掩盖 ULA 的几何限制。

### 4.3 近距边界

`2×2 SAGE/STAP` 在 `0.3 chip` 及以上为 `100%`；在 `0.1 chip` 时：

| 第二路功率 | 成功率 |
|---:|---:|
| `0 dB` | `16.3%` |
| `-6 dB` | `50.0%` |
| `-10 dB` | `60.0%` |

第二路越弱反而更容易成功不是合理的物理趋势。检查显示等功率、极近时延下，逐径初始化容易发生路径交换与局部极值。这是当前 SAGE 初始化/模型阶数门控的缺陷，不能选择性报告 `-10 dB` 的最好结果。

`ULA+FBSS_halfplane` 在本轮理想核条件下全部通过。原因是空间平滑先利用角度解开两个相干源，再分别估计时延；该结果高度依赖理想 ULA 流形、明确半平面和理想核，真实互耦、安装误差、反射与场景半平面变化都尚未加入。

## 5. 当前能否决定天线几何

**不能。** 本轮得到的是比之前更可信的算法基线，但还缺两项决定性证据：

1. 用同一份 Phase A 实测 L5 核重新跑完整阶梯；
2. 加入实测阵列流形或至少通道复增益、群时延、互耦误差的 faithful synthetic。

目前只能说：

- 方阵 SAGE/STAP 能直接估计二维方向、时延与多普勒，不依赖 ULA 半平面消歧；
- ULA+FBSS 在停车场半平面已知时是非常强的成熟基线；
- 方阵 SAGE 在 `0.1 chip` 等功率条件下仍有初始化病态；
- 不能根据“全向几何更漂亮”或某一格成功率决定制作方阵。

## 6. 运行方法

一行运行全部理想核复现：

```bash
python -u dev_notes/sim/sage_stap_array_comparison.py --mode all --trials 20
```

接入同一实测核：

```bash
python -u dev_notes/sim/sage_stap_array_comparison.py --mode all --trials 20 --kernel-csv /path/to/trustworthy_Rtau.png.csv
```

测试：

```bash
python -m unittest -v dev_notes/sim/test_sage_stap_array_comparison.py
```

主要产物在 `dev_notes/sim/results/sage_stap_reproduction/`：

- `SAGE_STAP论文参数复现.json`；
- `SAGE方阵与ULA_FBSS停车场公平比较.csv`；
- `SAGE方阵与ULA_FBSS停车场公平比较.json`；
- `SAGE方阵与ULA_FBSS停车场成功率.png`；
- `SAGE方阵与ULA_FBSS延迟功率阶梯.png`。

## 7. 复现状态

| 工作 | 状态 |
|---|---|
| SAGE 逐路径空间-时延-多普勒迭代 | ✅ |
| 论文 `2×2/P=20/Cs=0.1/N=20` 结构复现 | ✅ |
| 100 次论文参数 Monte Carlo | ✅ |
| ULA+FBSS 全 multicorrelator 公平基线 | ✅ |
| 停车场延迟×功率×位置阶梯 | ✅ 理想核 |
| Phase A 实测核重跑 | ⬜ NUC 当前不可达 |
| 实测 ULA/方阵阵列流形 | ⬜ 需要硬件 |
| 天线几何定型 | ⬜ 暂缓 |

**2026-08-13，Codex：** 本轮完成的是可以审计的第一阶段复现，不把理想核结果扩大成硬件结论。真实核与阵列流形两道门禁通过后，再讨论 ULA 或 `2×2` 方阵制作。
