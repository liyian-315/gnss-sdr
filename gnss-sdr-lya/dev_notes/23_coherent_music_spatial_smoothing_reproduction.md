# 相干 GNSS 信号的 MUSIC、空间平滑与停车场圆阵仿真

**日期：** 2026-08-12

**作者：** Codex

**分支：** `research/coherent-music-parking-array`

## 1. 研究问题

停车场内有两根相距 20 m 的 DAS 发射天线，发送同一颗卫星的同码、同频、同钟
GNSS 信号。接收机需要保留并分离两路，而不是把第二路当作干扰消除。

本报告只回答三个问题：

1. 普通 MUSIC 为什么会在高度相干 GNSS 信号上失效；
2. 空间平滑为什么能恢复相干信号的测角能力；
3. 在 20 m 双发射天线的停车场几何中，圆阵直接扫描、直接 MUSIC、圆阵改造空间
   平滑后使用 MUSIC 或 MVDR，分别有什么效果。

本次是窄带阵列处理仿真，不是完整 GNSS 射频波形仿真。它验证空间维度是否可辨，
尚未联合估计每路的码延迟和伪距。

## 2. 普通 MUSIC 为什么会失效

### 2.1 阵列信号模型

设阵列有 `M` 个阵元、空间中有 `K` 路信号：

\[
\mathbf{x}(t)=\mathbf{A}\mathbf{s}(t)+\mathbf{n}(t),
\qquad
\mathbf{A}=[\mathbf{a}(\theta_1),\ldots,\mathbf{a}(\theta_K)] .
\]

- \(\mathbf{x}(t)\)：某个时刻各阵元收到的复数 IQ 向量；
- \(\mathbf{a}(\theta_k)\)：方向 \(\theta_k\) 在阵列上产生的幅相模式，称为**导向
  矢量**；
- \(\mathbf{s}(t)\)：各路源信号；
- \(\mathbf{n}(t)\)：噪声。

阵列协方差矩阵为：

\[
\mathbf{R}_x=E[\mathbf{x}\mathbf{x}^{H}]
=\mathbf{A}\mathbf{R}_s\mathbf{A}^{H}+\sigma^2\mathbf{I} .
\]

上标 \(H\) 表示共轭转置，\(\mathbf{R}_s=E[\mathbf{s}\mathbf{s}^H]\) 是源信号
协方差矩阵。

### 2.2 “相干”造成秩亏

若两路源相互独立，\(\mathbf{R}_s\) 通常满秩。若两根 DAS 天线发送同一个波形，
第二路只是第一路的复数倍数：

\[
s_1(t)=\alpha s_0(t),
\qquad
\mathbf{R}_s=P_0
\begin{bmatrix}
1 & \alpha^*\\
\alpha & |\alpha|^2
\end{bmatrix},
\qquad \operatorname{rank}(\mathbf{R}_s)=1 .
\]

这叫做**相干源**。物理上有两路，统计上却只剩一个独立变化方向，即发生**秩亏**。

MUSIC 将 \(\mathbf{R}_x\) 特征分解成信号子空间 \(\mathbf{E}_s\) 与噪声子空间
\(\mathbf{E}_n\)，其伪谱为：

\[
P_{\mathrm{MUSIC}}(\theta)=
\frac{1}{\mathbf{a}^H(\theta)\mathbf{E}_n\mathbf{E}_n^H
\mathbf{a}(\theta)} .
\]

真实方向的导向矢量应与噪声子空间正交，因此分母接近零并形成尖峰。但两路完全相干
时，信号子空间只有一维，MUSIC 无法从一维子空间恢复两根不同的导向矢量。提高 SNR
或增加快拍，只会更精确地估计这个秩为 1 的矩阵，不能凭空恢复第二维。

因此，“论文中使用 MUSIC 成功”与“普通 MUSIC 对相干 GNSS 失效”并不矛盾。前者
通常满足以下至少一项：信号并非完全相干；已知卫星方向；先按码延迟分组；或先经过
空间平滑、波束空间变换、协方差重构等解相干步骤。

## 3. 空间平滑为什么有效

### 3.1 线阵的前后向空间平滑

对 `M` 阵元均匀线阵，取长度 `P` 的重叠子阵，共有 \(L=M-P+1\) 个。将每个子阵
的协方差相加：

\[
\mathbf{R}_{F}=\frac{1}{L}\sum_{\ell=0}^{L-1}
\mathbf{J}_{\ell}\mathbf{R}_x\mathbf{J}_{\ell}^{H} .
\]

\(\mathbf{J}_{\ell}\) 是截取第 \(\ell\) 个连续子阵的选择矩阵。再加入反向共轭子阵：

\[
\mathbf{R}_{FB}=\frac{1}{2}
\left(\mathbf{R}_{F}+\mathbf{\Pi}\mathbf{R}_{F}^{*}\mathbf{\Pi}\right),
\]

其中 \(\mathbf{\Pi}\) 是把阵元顺序倒过来的交换矩阵。这就是**前后向空间平滑**
（FBSS）。

直观解释是：同一组相干源在不同平移子阵上具有不同空间相位。把这些子阵协方差平均，
等于人为构造多组略有不同的观测，使原来粘在一起的一维统计结构恢复为多维。代价是：

- 有效孔径从 `M` 缩短为 `P`；
- 阵元数必须足够多；
- 依赖均匀线阵的平移不变/Vandermonde 结构。

空间平滑本身只生成修复后的协方差矩阵，并不直接输出角度。平滑后仍需 MUSIC、MVDR、
ESPRIT 等估计器。因此本报告将“非 MUSIC 的平滑方案”定义为 `FBSS + MVDR`，而不是
一个不存在的“仅空间平滑测角器”。

### 3.2 圆阵为什么不能直接切连续子阵

半径为 \(r\) 的均匀圆阵（UCA），第 `m` 个阵元角度为 \(\phi_m\)，远场方位角
\(\theta\) 的导向矢量为：

\[
a_m(\theta)=\exp\left[jkr\cos(\theta-\phi_m)\right],
\qquad k=\frac{2\pi}{\lambda} .
\]

相邻圆阵阵元不是线性平移关系，直接截取圆弧子阵并平均，不能得到线阵 FBSS 所需的
固定相位递推结构。

本仿真采用文献中的**相位模态/波束空间变换**。利用 Jacobi-Anger 展开：

\[
e^{jkr\cos(\theta-\phi)}=
\sum_{n=-\infty}^{\infty}j^nJ_n(kr)e^{jn\theta}e^{-jn\phi},
\]

对各阵元做离散圆周傅里叶变换，并除去 \(j^nJ_n(kr)\)：

\[
z_n(t)=\frac{1}{M j^nJ_n(kr)}
\sum_{m=0}^{M-1}x_m(t)e^{jn\phi_m}
\approx\sum_q c_q(t)e^{jn\theta_q} .
\]

- \(n\)：相位模态编号；
- \(J_n(\cdot)\)：第一类 Bessel 函数；
- \(e^{jn\theta}\)：转换后按 `n` 递推的 Vandermonde 结构。

转换后的模态序列可视为**虚拟均匀线阵**，再对它执行 FBSS。这就是本报告中的
`PM-FBSS`。ION 2014 的圆阵 GNSS 工作也明确采用 beamspace transformation 与
spatial smoothing 处理相干源。

## 4. 比较的四种方法

### 4.1 Bartlett 常规波束扫描

\[
P_B(\theta)=
\frac{\mathbf{a}^H(\theta)\mathbf{R}_x\mathbf{a}(\theta)}
{\left(\mathbf{a}^H(\theta)\mathbf{a}(\theta)\right)^2} .
\]

它不做特征子空间分解，分辨率较低，用作“不使用 MUSIC、也不解相干”的基线。

### 4.2 圆阵直接 MUSIC

直接对原始 UCA 协方差运行 MUSIC。它使用了 MUSIC，但没有修复相干秩亏，预期失败。

### 4.3 PM-FBSS-MVDR（不使用 MUSIC）

先做圆阵相位模态变换和 FBSS，再使用 MVDR/Capon：

\[
P_{\mathrm{MVDR}}(\theta)=
\frac{1}{\mathbf{a}^H(\theta)\mathbf{R}_{FB}^{-1}\mathbf{a}(\theta)} .
\]

MVDR 的含义是：保持候选方向单位增益，同时最小化其他方向输出功率。它不是 MUSIC，
但仍依赖平滑后的满秩协方差。

### 4.4 PM-FBSS-MUSIC

先用 PM-FBSS 恢复秩，再用 MUSIC 做超分辨角度搜索。这是本次圆阵的主要候选方案。

## 5. 仿真设置

### 5.1 论文参数复现

- 10 阵元、半波长间距 ULA；
- 3 个重叠的 8 阵元子阵；
- 四个完全相干方向：\(30^\circ,-60^\circ,-30^\circ,5^\circ\)；
- 原始协方差信号秩为 1，FBSS 后恢复为 4；
- FBSS-MUSIC 恢复四个真值角度。

两源 Monte Carlo 中，4 阵元 ULA、全相干、第二源为 -6 dB：普通 MUSIC 在
SNR `-5/0/5/10/15 dB` 下成功率为 `0/1/4/1/2%`，FBSS-MUSIC 为
`41/86/100/100/100%`。这验证了“失效来自相干秩亏，而不只是噪声”。

### 5.2 停车场圆阵场景

- 发射天线：`(-10,0)m` 与 `(10,0)m`，间距 20 m；
- 接收点：两天线正中、正中偏移 5 m、两天线外侧、紧邻一侧、远侧；
- L5 圆阵相邻阵元间距：\(0.5\lambda\)，\(\lambda\approx0.255\,m\)；
- 阵元数：4、6、8；
- 两源完全相干，第二源功率 -6 dB；
- 阵列 SNR 15 dB，2048 快拍；
- 每个条件随机相对载波相位 40 次；
- 两个 DOA 均在真值 ±5° 内才算成功；若两源方位相同，则定义为几何不可分，不能
  记成成功。

## 6. 圆阵仿真结果

### 6.1 四阵元圆阵

四阵元在当前 PM-FBSS 实现中只能可靠保留 \(n=-1,0,1\) 三个模态。若还要用两个
平移子阵解相干，平滑后没有足够维度同时容纳“两维信号子空间 + 至少一维噪声子空间”。
因此 `PM-FBSS-MUSIC/MVDR` 标记为 `N/A`，不是把算法强行跑出数字。

直接 Bartlett 与直接 MUSIC 在真正双方向位置的成功率基本为 `0–5%`。这说明四阵元
圆阵虽然几何上没有线阵的整条前后模糊，但仅靠原始协方差仍解决不了同码相干双源。

注意：这是“本相位模态-FBSS链路的维数结论”，不是证明所有四阵元圆阵算法都不可能。
四阵元仍可用于 2×2 平面阵列的联合空间-时延最大似然验证，但不能把线阵 FBSS 直接
移植后期待稳定分离。

### 6.2 六阵元和八阵元

下表为 40 次随机相位的成功率：

| 阵元 | 接收位置 | 方位差 | Bartlett | 直接 MUSIC | PM-FBSS-MVDR | PM-FBSS-MUSIC |
|---:|---|---:|---:|---:|---:|---:|
| 6 | 两天线正中 | 180° | 62% | 15% | 100% | 100% |
| 6 | 正中偏移 5 m | 126.9° | 0% | 7% | 10% | 10% |
| 6 | 紧邻左侧天线 | 76.0° | 0% | 5% | 0% | 0% |
| 6 | 远侧 | 53.1° | 0% | 3% | 0% | 0% |
| 8 | 两天线正中 | 180° | 57% | 45% | 100% | 100% |
| 8 | 正中偏移 5 m | 126.9° | 62% | 50% | 100% | 100% |
| 8 | 紧邻左侧天线 | 76.0° | 0% | 7% | 15% | 2.5% |
| 8 | 远侧 | 53.1° | 42% | 25% | 0% | 2.5% |

“两发射天线外侧且共线”时，两路方位差为 0°，所有方法均按 0% 记录。此时无论圆阵
还是线阵，两路具有相同空间导向矢量：

\[
\mathbf{a}(\theta_0)=\mathbf{a}(\theta_1),
\]

空间域没有信息可用，只能依靠码延迟、运动、不同频率或先验几何等其他维度。

### 6.3 怎样理解结果

1. **直接 MUSIC 失败是预期结果。** 原始协方差秩为 1，偶尔命中来自噪声、固定
   相位和峰形的偶然组合，不能当稳定能力。
2. **空间平滑后，MUSIC 与 MVDR 都能受益。** 八阵元在两发射天线之间达到 100%，
   证明“解相干预处理”才是关键，不是 MUSIC 这个名字本身。
3. **简单 PM-FBSS 还不具备全方位稳健性。** 侧方位置即使空间相干度不高，仍出现
   明显失败。原因是有限阵元、Bessel 模态截断和模态混叠使理想虚拟线阵模型与真实
   UCA 流形不完全一致；不是单纯把阈值调松就能解决。
4. **非 MUSIC 方案没有自动更稳。** PM-FBSS-MVDR 在正中区域与 MUSIC 同样达到
   100%，但侧方也会失败。空间平滑修复秩，不会修复错误的圆阵流形模型。

一次额外诊断显示，使用同样的五模态变换时，12 阵元理想圆阵在这些代表位置可将峰值
误差压到约 0–2°；但该结果尚未纳入完整 Monte Carlo，也未加入通道幅相误差、互耦和
近场效应，不能直接冻结为“12 阵元规格”。

## 7. 对停车场阵列制作的判断

### 7.1 当前可以确定的

- 四通道是值得做的最低硬件原型，但优先形态应是 `2×2` 平面阵，不建议把四阵元
  圆阵 + PM-FBSS 当最终方案。
- 若明确采用圆阵相位模态 + 空间平滑，阵元数应从 8 起做算法验证；六阵元余量偏小。
- 圆阵相邻弦长可先取 \(0.5\lambda\)。GPS L5 上约为 12.7 cm；八阵元圆阵半径约
  16.7 cm、直径约 33.3 cm。
- 四路必须共采样时钟、共本振、同时启动、固定增益，并校准每路的复增益和群时延。

### 7.2 当前不能确定的

- 不能仅凭理想远场仿真决定 4/6/8/12 阵元最终数量；
- 不能声称圆阵在整个停车场都能分离两路；
- 不能用本 DOA 仿真替代最终的每路延迟、伪距、\(C/N_0\) 跟踪验证；
- 不能忽略发射天线与接收阵列距离较近时的球面波、天线互耦和停车场反射。

## 8. 下一步最小闭环

1. 在仿真中加入四通道幅相误差、群时延误差和校准残差，比较 `2×2` 平面阵与 8 阵元
   UCA；
2. 用精确球面距离替代远场平面波，对靠近发射天线的位置做近场验证；
3. 将空间估计与现有 dense correlator 联合，输出每个方向对应的延迟和幅度，而不只
   输出角度；
4. 硬件 Gate 0：同一信号经功分器送入全部通道，测量 20 MHz 内的复数通道响应；
5. 只有实测阵列流形校准通过后，再做双发射天线 OTA 分离。

## 9. 运行方式与产物

```bash
python -m unittest -v dev_notes/sim/test_coherent_music_parking.py
python -u dev_notes/sim/simulate_coherent_music_parking.py --output-dir dev_notes/sim/results/coherent_music_parking
```

主要产物：

- `summary.json`：全部数值结果；
- `parking_uca_method_comparison.csv`：圆阵各位置、阵元数和方法成功率；
- `parking_uca_method_spectra.png`：代表位置空间谱；
- `parking_uca_method_success.png`：成功率热图；
- `paper_music_vs_fbss.png`：文献参数复现；
- `music_correlation_monte_carlo.png`：相关系数/SNR Monte Carlo。

## 10. 参考文献

1. [X. Wang et al., “Off-Grid High Resolution DOA Estimation for GNSS Circular
   Array Receivers,” ION GNSS+ 2014](https://www.ion.org/publications/abstract.cfm?articleID=12253)。
   文中对 UCA 相干源使用 beamspace transformation 与 spatial smoothing。
2. [M. Wax and J. Sheinvald, “Direction Finding of Coherent Signals via Spatial
   Smoothing for Uniform Circular Arrays,” IEEE Transactions on Antennas and
   Propagation, 42(5), 1994](https://doi.org/10.1109/8.299559)。
3. [S. U. Pillai and B. H. Kwon, “Forward/Backward Spatial Smoothing Techniques
   for Coherent Signal Identification,” IEEE Transactions on ASSP, 37(1),
   1989](https://doi.org/10.1109/29.17496)。
4. [T. J. Shan, M. Wax and T. Kailath, “On Spatial Smoothing for Direction-of-
   Arrival Estimation of Coherent Signals,” IEEE Transactions on ASSP, 33(4),
   1985](https://doi.org/10.1109/TASSP.1985.1164649)。

-- Codex (GPT-5), 2026-08-12
