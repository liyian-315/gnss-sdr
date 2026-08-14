# 四阵元线阵北斗 B2a 波形与 FBSS 仿真报告

> 日期：2026-08-14
>
> 作者：Codex
>
> 状态：可复现实验台已完成；结论只覆盖四阵元 ULA，不作为最终天线定型结论。

## 1. 本轮要回答的问题

停车场两端相距 20 m 的 DAS 天线由同一个 GNSS 信号源功分后发射。接收端计划使用
四阵元均匀线阵（ULA），希望同时估计两路到达方向和两路码时延。本轮不再使用“两个
独立随机窄带信号”的过度简化模型，而是从北斗 B2a pilot 复基带波形开始，比较：

1. 原始协方差上的直接 MUSIC；
2. 前后向空间平滑（FBSS）后的 MUSIC；
3. 测角后进行空间分离，再用真实 B2a pilot 相关核拟合两路时延。

可运行脚本：

```text
python dev_notes/sim/ula_gnss_waveform_fbss_lab.py
```

所有常用入参集中在脚本顶部“用户可修改实验参数区”，不需要改算法函数。

## 2. 信号为什么这样生成

### 2.1 B2a pilot 主码与子码

北斗 B2a 的 data 与 pilot 主码周期均为 1 ms，码长 10230 chip，码率为
10.23 Mcps。每颗 PRN 的主码由两个 13 级线性反馈移位寄存器 G1、G2 的输出异或得到：

$$
c_p[n] = G_1[n] \oplus G_{2,p}[n], \qquad n=0,\ldots,10229.
$$

pilot 主码生成多项式为：

$$
\begin{aligned}
G_{1,p}(x)&=1+x^3+x^6+x^7+x^{13},\\
G_{2,p}(x)&=1+x+x^5+x^7+x^8+x^{12}+x^{13}.
\end{aligned}
$$

data 主码使用另一组多项式：

$$
\begin{aligned}
G_{1,d}(x)&=1+x+x^5+x^{11}+x^{13},\\
G_{2,d}(x)&=1+x^3+x^5+x^9+x^{11}+x^{12}+x^{13}.
\end{aligned}
$$

G1 初值全为 1，G2 初值随 PRN 变化；G1 在输出第 8190 chip 后复位。脚本支持
PRN 1 至 63 的主码，默认 PRN 11。PRN11 的头/尾 24 chip 分别通过 ICD 八进制
pilot `24752054`/`60410454` 与 data `24751346`/`12470110` 单元测试。

B2a pilot 还叠加一个 100 ms 子码。它由长度 1021 的 Legendre 序列构成截短 Weil 码：

$$
W_k(w)=L(k)\oplus L((k+w)\bmod 1021),
\qquad c_s[n]=W_{p-1+n}(w),\ n=0,\ldots,99.
$$

当前脚本按 ICD 表 5-4 实现 PRN 1 至 32 的 $(w,p)$，并在每个 1 ms 主码相关后
擦除已知子码。PRN11 子码头/尾 24 chip 也分别校验为 `36242432`、`16314440`。
data 分量使用固定子码 `00010` 和 200 sps 的 B-CNAV2 符号。原始复基带按正交形式

$$
s(t)=d(t)c_d(t)c_{s,d}(t)+j\,c_p(t)c_{s,p}(t)
$$

同时生成两分量；阵列处理只用 pilot 本地码做相关。配置的 `CN0_A_AT_REFERENCE_DB_HZ`
定义为 pilot 分量的 C/N0，data 默认与 pilot 等功率，因此总 B2a 功率比单分量高 3 dB。

### 2.2 同源功分双路如何建模

两端不是两个独立随机源。对第 $k$ 路、阵元 $m$，复基带模型为：

$$
x_m(t)=\sum_{k=0}^{1} A_k a_m(\theta_k)
s(t-\tau_k)e^{-j2\pi f_c\tau_k+j\phi_{k,\mathrm{hw}}}+n_m(t).
$$

其中：

- $A_k$：传播损耗和两路发射功率形成的幅度；
- $a_m(\theta_k)$：第 $k$ 路在第 $m$ 个阵元上的空间相位；
- $\tau_k$：自由空间传播和馈线共同形成的时延；
- $\phi_{k,\mathrm{hw}}$：功放、连接器等未被线长解释的固定相位；
- $n_m(t)$：四通道独立复高斯热噪声。

有效路径长度为：

$$
L_k=\|\mathbf p_{\mathrm{rx}}-\mathbf p_{\mathrm{tx},k}\|
+\frac{L_{\mathrm{cable},k}}{v_f},
\qquad \tau_k=\frac{L_k}{c}.
$$

$v_f$ 是馈线速度因子。线长差不能只改变码时延而不改变载波相位，二者由同一个
$\tau_k$ 决定。理想同源同钟时，两路发射信号的相干系数为 1；可以额外配置差分相位
抖动，但默认关闭。

### 2.3 为什么当前固定点没有 20 m 时延差

默认发射坐标为 A `(-10,0)` m、B `(10,0)` m，接收机为 `(0,5)` m。接收机在
两端的垂直平分线上，因此

$$
r_A=r_B=\sqrt{10^2+5^2}\ \mathrm m,
\qquad \Delta r=r_B-r_A=0.
$$

两路等馈线时，真实时延差自然是 0；当前结果只有角度差并不是漏建模。如果把二维
接收机坐标放到 A 的位置 `(-10,0)`，则 $r_A=0$、$r_B=20$ m，二维模型给出
$\Delta r=20$ m。

“接收机在天线下方”在真实三维停车场里还包含垂直高度 $h$。若接收机正对 A、两端
水平间距为 $D=20$ m，则自由空间路差应为

$$
\Delta r=\sqrt{D^2+h^2}-h.
$$

因此只有 $h$ 相对 20 m 很小时才接近 20 m。例如 $h=3$ m 时路差约 17.22 m。
当前脚本是二维水平切片；在用实际停车场尺寸定型前，需要再把发射端和接收机高度
加入三维阵列流形，不能把二维的 20 m 直接当成现场真值。

### 2.4 C/N0 与 SNR 不是同一个量

手机 GNSS Logger 显示的 10、20、30、40 等数值通常是 dB-Hz，表示载波功率与噪声功率谱
密度之比 $C/N_0$，不是某个接收带宽内的普通 SNR。积分时间为 $T$ 时：

$$
\mathrm{SNR}_{T,\mathrm{dB}}
= (C/N_0)_{\mathrm{dBHz}} + 10\log_{10}T.
$$

因此 $C/N_0=30$ dB-Hz、$T=1$ ms 时，单个相关历元只有约 0 dB SNR。采样率为
$f_s=102.3$ MHz 时，原始单样点 SNR 约为：

$$
\mathrm{SNR}_{\mathrm{sample}}
=30-10\log_{10}(102.3\times10^6)\approx-50.1\ \mathrm{dB}.
$$

手机能捕获和定位，是因为它利用长时间积分、导航约束和多颗卫星。四阵元算法要从
同一 PRN 的两路完全相干信号中同时恢复两个角度和两个时延，任务明显更难。手机记录
只说明现实中可能出现的 C/N0 范围，不定义本仿真的固定工况，更不能单独决定阵列算法成败。

本实验把 C/N0 当作独立扫描轴，推荐覆盖 10 至 50 dB-Hz。它必须与两路功率比、相对
载波相位、角间隔、线长差、观察时长和通道误差交叉，而不是围绕某一个 C/N0 调参。

## 3. 阵列、MUSIC 与空间平滑

四阵元 ULA 使用 B2a 半波长间距：

$$
d=\frac{\lambda}{2}\approx12.74\ \mathrm{cm},
$$

总孔径约 38.2 cm。理想导向矢量为：

$$
\mathbf a(\theta)=
\left[1,e^{-j2\pi d u(\theta)/\lambda},
e^{-j4\pi d u(\theta)/\lambda},
e^{-j6\pi d u(\theta)/\lambda}\right]^T.
$$

$u(\theta)$ 是到达方向在阵列轴上的投影。

两路完全相干时，源向量可写成 $\mathbf s(t)=\boldsymbol\alpha s(t)$，阵列协方差的
信号部分变成：

$$
\mathbf R_s
=\mathbf A\boldsymbol\alpha\boldsymbol\alpha^H\mathbf A^H,
$$

它最多秩 1。普通 MUSIC 假定两个源提供两个独立信号特征向量，因此在这里失效。

FBSS 将四阵元 ULA 划成两个相互平移的三阵元子阵，先做前向平均：

$$
\mathbf R_F=\frac{1}{2}\sum_{l=0}^{1}
\mathbf J_l\mathbf R\mathbf J_l^H,
$$

再与其共轭反向矩阵平均：

$$
\mathbf R_{FB}=\frac{1}{2}
\left(\mathbf R_F+\mathbf \Pi\mathbf R_F^*\mathbf \Pi\right).
$$

$\mathbf J_l$ 是第 $l$ 个子阵选择矩阵，$\mathbf\Pi$ 是反序矩阵。平移子阵给同一相干
源对引入不同空间相位，使平滑协方差有机会恢复第二个信号特征值。代价是有效孔径从
四阵元减为三阵元，角分辨率下降，而且 ULA 的 360 度前后镜像仍然存在。

## 4. 测角后如何估时延

脚本不是让 MUSIC 直接输出时延。处理顺序为：

1. 对每个 1 ms B2a pilot 主码周期生成多抽头复相关输出并擦除子码；
2. 用直接 MUSIC 或 FBSS-MUSIC 估计两个方向；
3. 将两个方向的导向矢量组成 $\widehat{\mathbf A}$；
4. 用伪逆做空间分离：

$$
\widehat{\mathbf z}(\tau,t)
=\widehat{\mathbf A}^{\dagger}\mathbf y(\tau,t);
$$

5. 用公共 Prompt 相位旋转每个历元，再相干平均；
6. 以同一 PRN、同一采样率生成的 B2a 相关核 $R_c(\tau)$ 做**复数**最小二乘时移拟合：

$$
(\widehat\tau,\widehat\alpha,\widehat\beta)
=\arg\min_{\tau,\alpha,\beta\in\mathbb C}
\left\|\mathbf z-\alpha\mathbf R_c(\tau)-\beta\mathbf 1\right\|_2^2.
$$

这里 $\mathbf z$ 保留 I/Q 相位，$\alpha$ 同时估计路径幅度与相位；只有绘图时才画
$|\mathbf z|$。这避免了先取绝对值造成的相位信息不可逆丢失。

解混矩阵当前明确使用理想阵列流形：

$$
\widehat{\mathbf z}=\mathbf A_{\mathrm{ideal}}^{\dagger}\mathbf y.
$$

仿真数据则可以通过 `CHANNEL_GAIN_ERROR_DB_RMS` 和
`CHANNEL_PHASE_ERROR_DEG_RMS` 乘上未知通道响应。也就是说，误差打开后，数据来自
“失配阵列”，算法仍按理想阵列解混。这不是实现疏漏，而是校准误差压力测试：误差
增大后测角和时延估计失败是预期结果。后续如果要区分算法上限和校准上限，可以再加
“使用实测/真值流形”的 oracle 对照，但正式结果不能用 oracle 代替现场校准。

如果只出现一个局部角峰，脚本返回 `UNRESOLVED_ONE_PEAK`，不会从一个宽峰旁边硬挑
第二个网格点。

## 5. 可修改参数

| 参数 | 含义 |
|---|---|
| `B2A_PRN` | 北斗 B2a pilot PRN；主码支持 1 至 63，子码支持 1 至 32 |
| `INCLUDE_B2A_DATA_COMPONENT` | 是否在原始 IQ 中加入与 pilot 正交、等功率的 B-CNAV2 data 分量 |
| `SAMPLE_RATE_HZ` | 原始 IQ 采样率，默认 102.3 MHz（10 sample/chip） |
| `CODE_PERIODS` | 仿真时长，单位 1 ms，默认 100 |
| `TX_A/B_X/Y_M` | 两端发射天线坐标 |
| `RECEIVER_X/Y_M` | 固定接收机坐标 |
| `TX_A/B_POWER_DB` | 两路相对发射功率 |
| `CABLE_A/B_LENGTH_M` | 两路馈线长度 |
| `CABLE_VELOCITY_FACTOR` | 馈线速度因子 |
| `TX_B_EXTRA_PHASE_DEG` | 未由线长解释的固定硬件相位 |
| `CN0_A_AT_REFERENCE_DB_HZ` | A 路在参考距离处的 C/N0 |
| `REFERENCE_DISTANCE_M` | C/N0 标定参考距离 |
| `PATH_LOSS_EXPONENT` | 室内路径损耗指数 |
| `ENABLE_CW_INTERFERENCE` | 是否加入窄带连续波干扰 |
| `ENABLE_WIDEBAND_INTERFERENCE` | 是否抬高宽带噪声底 |
| `CHANNEL_GAIN/PHASE_ERROR_*` | 四通道未校准幅相误差 |
| `ULA_AXIS_DEG` | 线阵安装方向 |
| `KNOWN_HALF_PLANE` | 固定点是否使用已知半平面先验 |
| `CORRELATOR_TAP_*` | 相关抽头范围和间隔 |
| `EXPERIMENT_MODE` | `fixed`、`random` 或 `both` |
| `RANDOM_CENTER_MODE` | 随机圆域中心：中点、A 或 B |
| `RANDOM_RADIUS_M` | 随机圆域半径 |
| `RANDOM_RECEIVER_COUNT` | 随机接收点数量，即用户所说的 `rev_n` |

## 6. 2026-08-14 仿真结果

### 6.1 算法结构测试

无噪声、两路严格相干的单元测试中：

- 原始四阵元协方差只有一个有效信号特征值；
- 三阵元 FBSS 协方差恢复两个有效信号特征值；
- 两个角峰误差均小于 1 度。

这证明 FBSS 代码实现与经典相干源解秩机制一致。

### 6.2 固定接收机，一个 29 dB-Hz B2a 示例点

几何为 A `(-10,0)` m、B `(10,0)` m、接收机 `(0,5)` m，两路等功率、等馈线，
实际两路 C/N0 均约 29.03 dB-Hz：

| 方法 | 角度结果 | 时延结果 | 判定 |
|---|---:|---:|---|
| 直接 MUSIC | 两角 RMSE 32.99 度 | 相对时延误差 -1.17 m | `WRONG_SOLUTION` |
| FBSS-MUSIC | 两角 RMSE 22.30 度 | 相对时延误差 1.17 m | `WRONG_SOLUTION` |

这次 B2a 固定点实跑确认波形、子码擦除、MUSIC/FBSS 和复相关时延拟合链路都能执行。
但默认等距、等功率且 29 dB-Hz 的相干双源仍未通过角度门限；这不构成硬件选型结论。
后续相位/CN0/随机位置统计必须用 B2a 新版本重新生成，旧 GPS L1 数值不再引用。

### 6.3 C/N0 与相位扫描状态

脚本仍提供 C/N0、相对载波相位和随机位置扫描，但 2026-08-14 以前生成的表格属于
GPS L1 C/A 版本。B2a 的码率、波长、阵列孔径和 100 ms 观察长度均已改变，因此旧表
不能机械沿用。重新运行后，必须把每档 Monte Carlo 次数提高到至少 50，才可报告
检测率；默认 3 次仍只用于代码冒烟和趋势检查。

### 6.4 随机圆域状态

随机圆域功能已保留，但需要在 B2a 版本下重新形成统计。读取结果时还要区分：角度
不可分、时延不可分、前后镜像、一路 C/N0 过低和理想流形失配，不能把它们合并成
一个没有诊断意义的“失败率”。

## 7. 图和数据怎么看

输出目录：`dev_notes/sim/results/ula_gnss_waveform_fbss/`。

- `固定接收机MUSIC_FBSS与双路时延.png`：左为停车场几何，中为两个空间谱，右为
  测角后分离出的相关峰。真值虚线处各有一个尖峰才算角度分开；只有一个峰表示未分开。
- `固定点CN0扫描.png`：角 RMSE 随实际 C/N0 的变化。
- `固定点相对载波相位敏感性.png`：同源双路固定相位对 FBSS 的影响。
- `随机圆域MUSIC与FBSS成功位置.png`：不同接收位置的严格成功/失败分布。
- 对应 CSV/JSON 保存每个点的真值、估计值和状态，可继续做统计而无需看图猜结论。

## 8. 对四阵元 ULA 制作的当前判断

本轮结果支持制作 ULA 作为**论文复现基线和受控半平面验证阵列**，但不支持把它直接
定为停车场全方位最终天线。原因如下：

1. FBSS 有成熟论文依据，且结构测试确实恢复相干双源秩；
2. 四阵元 B2a 半波长 ULA 总长约 38.2 cm，硬件可实现；
3. 但 360 度前后镜像是几何硬伤，不是提高 C/N0 能修复的；
4. 在本次约 29 dB-Hz 示例和不利相位下，四阵元 ULA 经常只输出一个峰；该现象需在
   完整 C/N0 × 相位 × 功率比矩阵中统计，不能外推成单一门限；
5. 两端相距 20 m 时，接收机离开中点会迅速形成强弱路功率差；
6. 真实天线互耦、通道群时延和幅相误差尚未加入实测流形，实际只会比理想模型更难。

因此，制作前的正确决策不是“ULA 已经胜出”，而是：先把 ULA 当成熟 FBSS 基线；再与
`2×2` 方阵 SAGE/STAP 在同一真实相关核、同一通道误差和同一停车场位置集上比较。

## 9. 设备到位前还应补的因素

本脚本已提供但默认关闭：CW 干扰、宽带干扰、差分相位抖动、四通道固定幅相误差。
仍需在后续 faithful synthetic 或实测中补齐：

1. B210/N310 四通道同步采样与频率相关群时延；
2. 天线方向图、互耦和地面/顶棚反射形成的实测阵列流形；
3. 前端带通滤波、ADC 量化和 AGC/固定增益差异；
4. 两端 DAS 功放的真实相位稳定度和群时延；
5. 真实停车场接收位置分布，不只使用均匀圆域；
6. 单源负对照、两源功率比阶梯、角间隔阶梯和延迟阶梯；
7. 多于两路时的模型阶数与可信度门控。

## 10. 本轮结论

这次仿真的价值不是证明“四阵元 ULA 一定能分开”，而是把问题拆清楚：

- 真实 B2a pilot 主码/子码和 C/N0 噪声模型确认 C/N0 必须作为实验维度扫描，不能用手机某次读数
  代替阵列分离门限；
- 直接 MUSIC 对完全相干双源确实失效；
- FBSS 在结构上能恢复秩，并在较高 C/N0、多数相位下明显改善；
- ULA 的前后镜像、相位病态区和强弱路差仍使全停车场覆盖不可靠；
- 测角后估时延可行，但只有测角可信时才允许输出两路时延。

当前最诚实的硬件结论：四阵元 ULA 值得制作一个验证样机，但最终停车场阵列几何仍需
等待 ULA+FBSS 与 `2×2` SAGE/STAP 的 faithful synthetic 公平比较和四通道校准门禁。

## 参考

1. 中国卫星导航系统管理办公室，[《北斗卫星导航系统空间信号接口控制文件：公开服务信号 B2a（1.0 版）》](https://www.beidou.gov.cn/zt/xwfbh/wznfbh/gdxw3/201712/P020171226743636973282.pdf)，2017。
2. S. U. Pillai and B. H. Kwon, “Forward/backward spatial smoothing techniques for coherent signal identification,” IEEE TASSP, 1989, DOI: `10.1109/29.17496`。
3. N. Vagle et al., “Performance analysis of GNSS multipath mitigation using antenna arrays,” Journal of Global Positioning Systems, 2016, DOI: `10.1186/s41445-016-0004-6`。
4. 项目文档 `23_停车场四阵元线阵圆阵方阵对比与选型.md`。
5. 项目文档 `25_方阵SAGE_STAP与线阵FBSS公平复现报告.md`。
