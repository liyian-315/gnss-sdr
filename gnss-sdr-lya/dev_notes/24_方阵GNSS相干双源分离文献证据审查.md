# 方阵 GNSS 相干双源分离文献证据审查

**日期：** 2026-08-13

**作者：** Codex

**状态：** 文献审查；不作为天线定型结论

## 1. 审查问题

本次只回答以下问题，不根据理想仿真直接决定天线制作：

1. 是否有使用四阵元 `2×2` 方阵处理 GNSS 多径或多路信号的论文；
2. 论文究竟实现了测角、抑制，还是联合估计多条路径；
3. `2×2` 方阵能否依靠标准空间平滑恢复两个完全相干源；
4. 本项目的 dense correlator、空间-时延 GLRT/ML、协方差重构和置信度门控，哪些有文献依据，哪些仍是自研假设。

这里的“分离”必须至少估计两条路径各自的参数，例如方向、时延和复幅度。仅仅压低反射、提高 `C/N0` 或画出反射方向，不等同于持续输出两路伪距。

## 2. 结论先行

### 2.1 有方阵联合分离算法，但最直接依据是 SAGE/STAP，不是普通 MUSIC

Rougerie 等人在 2012 年明确采用四传感器、半波长间距的 `2×2` 方阵，并建立每条路径的联合参数：

$$
\boldsymbol\psi_l=[\gamma_l,\theta_l,\phi_l,\tau_l,\nu_l]^{\mathsf T},
$$

其中 $\gamma_l$ 是复幅度，$\theta_l,\phi_l$ 是俯仰角和方位角，$\tau_l$ 是码时延，$\nu_l$ 是多普勒。其 SAGE/STAP multicorrelator 联合模板可写成：

$$
\mathbf x_l(\boldsymbol\psi_l)=\widetilde\gamma_l
\left[\mathbf a(\theta_l,\phi_l)\otimes
\widetilde{\mathbf r}_C(\tau_l,\nu_l)\right].
$$

$\mathbf a$ 是方阵空间导向矢量，$\widetilde{\mathbf r}_C$ 是多抽头相关器在时延和频率上的响应。SAGE 交替减去其他路径，再估计当前路径的角度、时延、多普勒和幅度。这个模型与本项目“空间模板 × dense 相关核”的方向高度一致。

但论文目标仍是**多径抑制与直达径跟踪改善**；它证明联合估计路径参数可行，不等于已经证明本项目的停车场同码同钟双发射源能稳定输出两路伪距。

### 2.2 `2×2` 方阵配 MUSIC 有实测论文，但任务不同

Razgūnas 等人在 2023 年使用 `2×2` 方阵、同步 SDR、MUSIC 和波束形成，完成了直接信号/反射方向检测及多径空间滤波。它能支撑二维方向观测和实测反射检测，不能直接支撑两个完全相干 DAS 源总能形成两个稳定 MUSIC 峰，也没有证明亚码片双伪距持续跟踪。

### 2.3 四阵元 `2×2` 不满足经典二维空间平滑的通用保证

二维空间平滑把均匀矩形阵列划分为多个重叠矩形子阵，再平均子阵协方差。Chen 对 $K$ 个相干源的通用保证要求：

$$
M_x^{\mathrm{sub}},M_y^{\mathrm{sub}}\ge K+1,
\qquad L_x,L_y\ge K,
$$

总均匀矩形阵列至少为：

$$
2K\times2K.
$$

对 $K=2$，通用保证对应至少 `4×4` 阵列。在 `2×2` 内取 `1×2` 子阵时，两个信号占满二维空间，MUSIC 没有噪声子空间。因此“方阵可以做二维平滑”一般成立，但“四阵元 `2×2` 可用经典二维平滑可靠分离两个完全相干源”不成立。

## 3. 论文证据分级

| 方法 | 阵列与场景 | 论文实际做到什么 | 对本项目的证据等级 |
|---|---|---|---|
| SAGE/STAP multicorrelator | GNSS，`2×2` 方阵，半波长 | 联合估计路径角度、时延、多普勒、复幅度并接入跟踪环 | **直接方法依据** |
| SAGE 与阵列算法评测 | GNSS，`2×2` 阵列，软件和射频仿真 | 测试 `0.03--0.1 chip` 多径，比较 SAGE、LCMV、ESPRIT | **直接场景依据**，输出偏误差抑制 |
| MUSIC + 波束形成 | GNSS，实测 `2×2` 方阵 | 检测直达/反射方向并空间滤波 | **直接测角依据**，不是双伪距依据 |
| 二维空间平滑 + MPDR | GNSS，较大矩形阵列 | 解相关后抑制多径并改善伪距/定位 | **矩形阵依据**，不能缩成 `2×2` |
| 二维空间平滑理论 | 通用相干源，均匀矩形阵 | 给出子阵尺寸和数量的可辨识条件 | **直接理论依据**，说明 `2×2` 不够 |
| Toeplitz/矩阵重构 | GNSS 阵列，会议论文 | 结构化重构协方差后测角/抑制 | **相关方法依据**；未确认与本实现一致 |
| 本项目简化 GLRT/ML | 理想 `2×2` + 合成相关核 | 一源/二源比较，联合搜索方向和时延 | **SAGE/STAP 启发的原型**，不是复现 |
| 支撑约束重构 | 使用 GLRT 已估计的角度 | 为 MUSIC 显示构造秩 2 协方差 | **展示后处理**，无独立检出能力 |
| 四态置信度门控 | 合成数据阈值 | 拒绝低增益、病态或多解结果 | **工程假设**，需真实负对照标定 |

## 4. 现有算法的依据边界

本项目的共同模型：

$$
\mathbf q(\theta,\tau)=\mathbf a(\theta)\otimes\mathbf r(\tau),
$$

$$
\mathbf y_b=c_{0,b}\mathbf q(\theta_0,\tau_0)
+c_{1,b}\mathbf q(\theta_1,\tau_1)+\mathbf n_b,
$$

有 SAGE/STAP multicorrelator 的直接思想依据。dense correlator 是获得 $\mathbf r(\tau)$ 的工程实现。

但 `square_array_coherent_separation_lab.py` 没有实现完整 SAGE：没有逐路径 E/M 更新，没有联合估计多普勒、俯仰角和跟踪环状态；当前网格搜索 + 线性最小二乘属于 variable-projection / GLRT 简化原型。`RSS_H1/RSS_H2` 阈值与四态门控也未通过真实方阵数据标定。准确名称应为：

> **SAGE/STAP 联合空间-相关域模型启发的简化 GLRT/ML 原型。**

不能写成“论文已经验证了 GLRT、重构和门控组合”。

## 5. 对硬件选型的约束

文献允许保留 `2×2` 方阵为候选，因为它有 GNSS SAGE/STAP 与实测 MUSIC/波束形成研究。但在以下工作完成前，不应下达最终制作结论：

1. 复现 2012 SAGE/STAP 论文的方阵、多径时延和角度实验；
2. 同数据比较论文型 SAGE/STAP、现有简化 GLRT/ML 与 ULA+FBSS；
3. 使用真实 Phase A 相关核和实测阵列流形，而非只用理想模板；
4. 报告双源检出率、单源虚警率、时延/角度 RMSE 和 `UNRESOLVED` 比例；
5. 验证 `2×2` 停车场方向盲区，并与 ULA 前后模糊公平比较。

当前判断：

- **ULA + FBSS：** 解相干链条成熟，适合论文复现基线，但全方位有前后模糊；
- **`2×2` + SAGE/STAP：** 有直接 GNSS 联合估计依据，适合二维候选，但实现与验证更多；
- **`2×2` + 普通 MUSIC：** 可做测角/波束形成，不能单独承担相干双源分离；
- **`2×2` + 经典二维平滑：** 四阵元规模不满足两个相干源的通用条件。

## 6. 参考文献

1. [S. Rougerie et al., “A New Multipath Mitigation Method for GNSS Receivers Based on an Antenna Array,” 2012](https://doi.org/10.1155/2012/804732)。
2. [A. Konovaltsev et al., “Performance assessment of antenna array algorithms for multipath and interferers mitigation,” 2007](https://elib.dlr.de/48991/)。
3. [M. Razgūnas et al., “GNSS 2×2 antenna array with beamforming for multipath detection,” 2023](https://doi.org/10.1016/j.asr.2022.12.035)。
4. [N. Vagle et al., “Performance analysis of GNSS multipath mitigation using antenna arrays,” 2016](https://doi.org/10.1186/s41445-016-0004-6)。
5. [Y. M. Chen, “On spatial smoothing for two-dimensional direction-of-arrival estimation of coherent signals,” 1997](https://doi.org/10.1109/78.599939)。
6. [H. Wang and K. J. R. Liu, “Two-Dimensional Spatial Smoothing for Multipath Coherent Signal Identification and Separation,” 1995](http://hdl.handle.net/1903/5681)。
7. [Z. Zhang et al., “GNSS Multipath Mitigation Algorithm with Antenna Arrays Based on Matrix Reconstruction,” 2020](https://doi.org/10.1109/ICCT50939.2020.9295928)。需取得全文后再核对阵列几何和实验条件。

## 7. 审查意见

**2026-08-13，Codex：** 用户对“现有组合没有直接论文依据”的质疑成立。修正结论不是“方阵没有算法”，而是“方阵有 SAGE/STAP 和 MUSIC/波束形成论文，但项目当前 GLRT/重构/门控仍是待验证原型”。完成论文级复现前，暂停根据当前理想仿真下最终天线制作结论。
