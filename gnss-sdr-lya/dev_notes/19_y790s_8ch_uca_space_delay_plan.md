# Y790s 八通道八阵元圆阵（UCA）空间-时延分离计划

**Date:** 2026-08-10
**Author:** Claude（研究架构与独立审查）
**Baseline:** `research/multipath-correlator-fit` @ `5271ccb8d`
**Branch:** `research/y790s-8ch-space-delay`
**取代关系:** 本文是 `16_static_four_antenna_space_time_plan.md`（四元 ULA 计划）的升级，不覆盖 16；16 保留为历史与方法论出处。

---

## 0. 证据等级标注约定（全文强制）

每条结论必须挂以下四级之一：

| 标签 | 含义 |
|---|---|
| **[B210实测]** | 已用 B210 真实采集数据证明 |
| **[纹理合成]** | 用 Phase A/B 实测纹理构造的 faithful synthetic 证明 |
| **[理想仿真]** | 理想阵列/理想核/共用生成-估计模型的仿真，仅证明代码接线与可辨识性论证 |
| **[Y790s未验证]** | 依赖 Y790s 硬件行为，尚无任何证据 |

**特别禁止**：`fit_space_delay_twosource.py --self-test` 的"0.1 chip 四元阵 RELIABLE"结果是 **[理想仿真]**，且是特别有利几何（0°/30° 在四元 λ/2 ULA 下 μ_spatial 恰为 0、生成器与估计器共核共导向律、真值恰在网格上，见 05 的 2026-08-04 评审）。**不得**将其描述为八阵元真实能力，也不得外推为"八元阵能到 0.1 chip"。

---

## 1. 现有工作摘要（本计划的复用底座）

以下全部保留、不重新发明：

1. **dense 复相关导出**（doc 11）**[B210实测]**：跟踪域逐历元密集复相关向量导出,二进制记录 + `.dat.json` 边车；主力抽头网格 `-1.5:0.1:1.5`（31 taps），30 s ≈ 29.8k 历元；配置 `dense_correlator_dump/taps_chips/decimation`；`extend_correlation_symbols=1` 纪律。
2. **Phase A 实测单源 R(τ) 核**（doc 11）**[B210实测]**：CSV 列 `tap_chips,coherent_re,coherent_im,mag_mean,mag_std`；形状特征从相干 |R| 取；L5 实测 FWHM≈1.09 chip；TRUSTWORTHY 分层验收（≥3 重复、n_blocks≥20、FWHM CV≤2%、asym std≤0.003）。
3. **A-only/B-only faithful 纹理**（doc 12/15）**[B210实测]**：真实单源逐历元复 dense 向量直接作为 path0/path1 纹理注入合成场景；clean 合成通过 ≠ 真实通过（吃过两次亏）。
4. **texture-aware GLRT**（doc 15）**[纹理合成]**：path0 纹理白化 + 存在性 GLRT；CN0≥45 dB-Hz 包线内 AUC≈1.0；不硬编码全局阈值，按 CN0 条件标定,包线外报 INSUFFICIENT。
5. **variable-projection ML**：几何参数非线性搜索、逐块复幅度线性 LS（`fit_two_path.py` / `fit_space_delay_twosource.py`）。
6. **四态置信** `RELIABLE / MARGINAL / UNRESOLVED / NO_SECOND_SOURCE` 及**不可靠时拒绝输出**原则。
7. **单源负对照**纪律：每类实验必配 path-absent 场景,虚警率与检出率同权重。
8. **静态单天线亚码片 = 欠定的墙**（doc 12）**[B210实测]**：path1 被 path0 残差压低约 30 dB,三种快照架构同样失败——这是本阵列路线存在的理由。
9. **空间-延迟骨架**（commit `7cab36dd7`）**[理想仿真]**：`μ_joint = μ_spatial × μ_temporal`（Kronecker 分解）、MMV 逐块 nuisance 幅度、A0 可辨识性 + A1 约束 GLRT 已实现并自测通过。

数据结构兼容性铁律：新八通道工作**只扩展**现有格式——dense 数组从 `(B, M, K)` 的 M=2/4 扩到 M=8；核 CSV、npz 键名（`dense/taps/meta_json`）、四态判定字段全部沿用。

---

## 2. doc16 四元 ULA → Y790s 八元 UCA：必须修改的部分

### 2.1 几何与坐标定义

- **UCA 几何**：8 阵元均匀圆阵。若沿圆周保持相邻阵元 ≈λ/2（L5 λ≈25.48 cm，λ/2≈12.74 cm），则周长≈1.019 m，**半径 R≈16.2 cm，孔径（直径）≈32.4 cm≈1.27λ**。半径为可调设计参数,由 G1 实测流形定稿。
- **坐标系**：阵列局部右手系,x 轴指向阵元 0,z 轴垂直阵面向上。阵元 m 位置
  `p_m = R·(cos φ_m, sin φ_m, 0)`，`φ_m = 2πm/8`，m=0..7。
- **角度定义**：方位角 az ∈ [0°, 360°) 从 x 轴逆时针；俯仰角 el ∈ [-90°, 90°] 从阵面（xy 平面）向上为正。来波单位向量 `u = (cos el·cos az, cos el·sin az, sin el)`。
- **理想导向矢量**（仅作 A0 分析与仿真,实际估计必须用实测流形）：
  `a_m(az, el) = exp(+j·(2π/λ)·pᵀ_m·u) = exp(+j·(2π/λ)·R·cos el·cos(az − φ_m))`。
  注意 `p_m·u` 中 z 分量为 0 → **el 只通过 cos el 缩放有效半径进入模型**。

### 2.2 与四元 ULA 的方向模型区别

| 项 | 四元 λ/2 ULA（doc16） | 八元 UCA（本计划） |
|---|---|---|
| 角度参数 | 一维,只观测 sin θ | 二维 (az, el) |
| 方位覆盖 | ±60° 扇区,有前后镜像模糊 | **360° 无前后模糊**（这是室内 DAS 多天线布设最需要的性质） |
| 俯仰 | 完全盲 | 有 el 敏感度但弱且**存在 ±el 镜像模糊**（平面阵对阵面对称）；el→0 时敏感度→0 |
| 波束宽度 | 随 θ 偏离法线展宽 | 方位向近似各向同性 |
| 平移不变性 | 有（空间平滑可直接用） | **没有**（见 2.4） |
| 阵元互耦 | 链式,边缘阵元不同 | **循环对称**（circulant）,校准结构更规整,但邻元距离近、耦合绝对量不小 |

工程含义：室内 DAS 天线常在天花板（高 el），UCA 的 el 敏感度弱 + ±el 模糊意味着**方向输出主要交付 az,el 只报粗估 + 置信区间**；若后续 el 成为刚需,再评估加中心阵元或立体阵,不在本计划范围。

### 2.3 阵元位置如何进入 steering vector / 现有代码改动

现骨架 `steering(theta_deg, n_ant, spacing_wl)` 是 ULA 专用。升级为通用位置式：

```python
def steering_xyz(az_deg, el_deg, pos_wl):      # pos_wl: (M,3) 阵元坐标/波长
    u = unit_vector(az_deg, el_deg)            # (3,)
    return np.exp(1j * 2*np.pi * pos_wl @ u)   # (M,)
```

- `generate_space_delay_twosource.py` / `fit_space_delay_twosource.py` 的 `spacing_wl` 标量参数升级为 `array_xyz_m` (M,3) + `wavelength_m`,并写入 `meta_json`；ULA 作为位置矩阵的特例保持向后兼容。
- `build_q` 不变：`q(az, el, τ) = a(az, el) ⊗ r(τ)`,μ 分解不变。
- 真实估计时 `a(az, el)` 整体替换为 **G1 实测流形插值**,理想式只用于生成扰动仿真与 A0 预测。

### 2.4 为什么必须实测 array manifold

- 分离能力由 `μ_joint = μ_spatial × μ_temporal` 决定；亚码片下 μ_temporal≈0.95–1.0,全部判别力来自 μ_spatial。流形误差 ε（互耦、阵元方向图差异、电缆/通道相移、支架散射、安装误差）直接给 μ_spatial 造成 **~ε 量级的地板**：当两源理想空间相干度差异 < ε,判别是噪声。经验尺度：要在 μ_spatial≈0.9 的几何下工作,流形逐元素复误差需 ≲ 数个百分点（-30 dB 级）——理想公式在真实硬件上达不到,必须测。
- UCA 互耦是循环结构但绝对量不小（邻元 λ/2）；Y790s 八通道各自的 LNA/滤波器/走线相位差是**逐设备逐次开机**的属性,不进流形/校准就直接进 DOA 偏差。
- 这与 doc16"measured manifold"结论一致,只是从 5 点一维网格升级为 (az, el) 二维网格（见 G1）。

### 2.5 圆阵不能照搬 ULA 空间平滑

ULA 空间平滑依赖**平移不变性**（子阵与原阵同流形）。UCA 沿圆周取"子阵"得到的是旋转,不是平移,子阵流形不同,直接平滑无效。标准替代是**相位模式激励/beamspace（Davies 变换）**：把 8 元 UCA 变换到相位模式空间,得到近似 Vandermonde（虚拟 ULA）结构后再平滑。代价与限制：

- 最高可用模式阶 `h_max ≈ floor(2πR/λ) ≈ floor(1.27π) = 3`（R≈0.64λ 时 2πR/λ≈4.0,模式 ±4 与 8 元采样混叠且贝塞尔系数不稳,工程上取 |h|≤3）→ beamspace 维度 **7**；
- 变换基于**理想**贝塞尔系数,实测流形误差会造成模式泄漏——beamspace 精度上限受校准质量制约；
- 平滑再吃掉自由度：7 维虚拟 ULA 做前后向平滑解 L 个相干源,大约剩 7−L 的有效孔径。

结论：路线 P（论文复现）里 MUSIC 前必须走 beamspace+平滑,且这是它相对路线 R 的结构性劣势之一。

### 2.6 同码高度相干信号对 MUSIC 的影响

DAS 各天线转发**同一颗星同一 PRN**,narrowband 快拍协方差里各源复包络完全相干（相关系数 |ρ|≈1）→ 信号子空间秩塌缩为 1,标准 MUSIC 谱只出一个峰或系统性偏峰。必须先去相干（beamspace 平滑,或跨 Doppler/延迟维的伪快拍构造）,每一步都损失孔径与 DOF。这正是 doc16"MUSIC 是 comparator 不是主算法"的原因,八元 UCA 下依然成立。

---

## 3. 路线 P：论文复现基线（comparator）

```
8ch IQ → calibration → common-reference carrier/code wipeoff → covariance
       → coherent-source handling(beamspace+平滑) → MUSIC/等价DOA
       → MVDR beamforming → 每波束×本地PRN相关 → per-beam delay estimation
```

分步说明与出处：

1. **calibration**：注入共源标定复传函 `G_m(f)`（doc15/16 已有双通道版方法,扩到 8）。〔已有思想:标准阵列校准〕
2. **common-reference wipeoff**：见 §6,与路线 R 共享同一模块。〔论文常规,GNSS 阵列文献均如此〕
3. **covariance**：wipeoff 后按短块估 8×8 样本协方差（post-correlation 域,用 dense tap 向量或 prompt 快拍）。
4. **coherent-source handling**：Davies beamspace(|h|≤3) + 前后向平滑（§2.5）。〔已有思想:Mathews&Zoltowski UCA-RB-MUSIC 一脉〕
5. **DOA**：beamspace MUSIC；源数用 MDL/AIC + 平滑后特征值间隙,**同码场景下源数估计本身不可靠,输出须带告警**。
6. **MVDR**：对每个 DOA 峰做 MVDR 权,形成波束。〔已有思想〕
7. **per-beam 相关 + delay**：每波束输出与本地 PRN 密集相关,单径拟合（复用 `fit_two_path.py` 单源模式）出各波束延迟。〔已有思想:Rougerie/Konovaltsev 等,doc16 参考文献〕

**角色定位**：P 全程是论文已有思想的组装,不含我们的增强。它的价值是 (a) 学术对照基线,(b) 交叉检验 R 的 DOA 输出,(c) 审稿人问"为什么不用 MUSIC"时的实证回答。**P 不承诺亚码片延迟分离**——波束分离后每波束仍是单天线延迟估计,两源角距小于波束宽度(约 40–50°@8元UCA)时 P 直接失效。

## 4. 路线 R：本项目主算法

```
8ch IQ → calibration → 8×K complex dense correlator（共参考,§6）
       → measured spatial manifold(G1) → measured Phase-A temporal kernel
       → H1/H2/H3/H4 模型选择(GLRT/BIC/evidence) → variable-projection ML
       → optional MSBL/SAGE refinement → path association → confidence state
```

观测模型（`fit_space_delay_twosource.py` 的直接推广,L 源）：

```
y[b,m,k] = Σ_{l=0..L-1} c_l[b] · â_m(az_l, el_l) · R(τ_k − τ_l) + n[b,m,k]
â = 实测流形插值,R = Phase A 实测核,c_l[b] = 逐块复 nuisance（MMV）
```

- **H1..H4 模型选择**：现骨架 H1/H2 的 `improvement_db` 门限法推广到嵌套序列 H1⊂H2⊂H3⊂H4；每升一阶需 GLRT 改善过 CN0 条件化门限 **且** BIC/evidence 净改善（惩罚 3 个几何参数 + B 个复幅度/源）；新源与已有任一源的成对 μ_joint > mu_max 时该阶直接 UNRESOLVED,不硬加源。
- **varpro ML**：外层几何 (az, el, τ) 逐源坐标下降 + 局部细化,内层逐块幅度线性 LS（现有 `_residual` 直接复用,设计矩阵 (M·K)×L=248×L,B 块批量 pinv）。
- **MSBL/SAGE**：只作 H3/H4 的粗初始化与局部精修,在 H2 真实门（G3）通过之前不投入。
- **path association**：跨历元块把 (az, el, τ, power) 关联成路径轨迹,复用 Track B 的一致性思想（延迟连续性 + 幅度平滑 + 支撑共享）。
- **confidence state**：沿用四态 + INSUFFICIENT（低于验证包线,doc15 决策）；per-path 输出 (az, el, τ, power, 置信椭圆, state)。

**已有思想 vs 我们的增强**：

| 环节 | 归属 |
|---|---|
| 空时联合模型 a⊗r、varpro、SAGE/MSBL、GLRT/BIC | 论文已有（doc16 参考文献、doc09） |
| **实测 Phase-A 温度核**取代理想 R(τ) | 我们的增强 [B210实测] |
| **实测流形 + 校准 ID 进模型**而非理想导向律 | 论文有先例但作为硬门禁+数据格式是我们的工程增强 |
| **faithful 纹理正负对照**驱动的验收 | 我们的增强 [纹理合成] |
| **texture-aware 白化 GLRT** | 我们的增强（doc15） |
| **μ_joint = μ_spatial×μ_temporal 的 A0 预判 + UNRESOLVED 拒绝输出** | 分解是数学常识,把它做成先于优化器的门禁与诚实拒绝是我们的方法论 |
| MMV 逐块 nuisance 防钟漂冒充分离机制 | 我们的增强（doc16/骨架） |

---

## 5. 2/3/4 源可辨识性审查

参数记账（B 块、M=8、K=31）：数据 8·31·B 复数;L 源未知数 = 3L 几何 + L·B 复幅度。**计数从不是瓶颈,条件数才是**。以下全部为分析预测,标签 **[理想仿真]**/推理,Y790s 实测前不升级。

共同的退化因子（对所有 L 生效）：
- 同码相干：路线 R 的 ML 天然处理相干,但代价是 μ 高时 Fisher 信息塌缩;路线 P 需去相干,DOF 掉到 7 维 beamspace 再减平滑。
- 流形误差 ε：给 μ_spatial 判别加 ~ε 地板;通道相位漂移等效于时变 ε。
- 角度接近：8 元 UCA 方位向自然波束宽 ~40–50°;ML 可超分辨,但 Δaz≲15–20° 时 μ_spatial 升高、CRLB 陡增。
- 时延接近：Δτ<0.5 chip 时 μ_temporal≳0.95,判别几乎全压在空间轴。
- 功率差：-10 dB 弱源的有效 CN0 掉 10 dB;doc15 已证 CN0<~42–45 dB-Hz 纹理 GLRT 失效。
- 空间平滑/beamspace：路线 P 专属损失（§2.5）。
- 互耦与通道相位误差：进 ε;循环对称使互耦可低参数建模,但必须实测。

### 8 元、2 源

- **理论**：M=8 ≫ L=2,即便 μ_temporal≈1,只要 Δaz 使 μ_spatial ≲0.9、ε 足够小,联合模型强可辨识;beamspace-MUSIC 路线也够(7−平滑≥2)。
- **工程推荐**：**主目标,可承诺**。条件包线：Δaz ≥ 30°（UCA 全方位任意绝对朝向,须 G1 后用实测流形复核 μ_spatial(Δaz) 曲线,不复用四元 ULA 0/30° 的巧合正交）,Δτ ∈ [0, 1] chip 任意（含 0）,功率比 ≥ -10 dB,CN0 ≥ 45 dB-Hz,校准当次有效。0.5 chip 亚码片分离在此包线内是**现实的 G3 目标**。Δaz < 15° 预期 UNRESOLVED,照实报。

### 8 元、3 源

- **理论**：DOF 充足;三源成对 μ 矩阵中最坏的一对决定条件数;ML 搜索空间 9 维几何,varpro+坐标下降可行。
- **工程推荐**：**有条件可行,G5 前不承诺**。要求三源成对 Δaz ≥ ~40°、成对 μ_joint ≤ ~0.9、功率两两差 ≤ 10 dB、CN0 ≥ 48 dB-Hz(弱源余量)。风险集中在模型阶选择：H2 vs H3 的 GLRT 改善量在第三源弱/近时与 path0 纹理残差同量级(doc12 的 30 dB 墙教训在高阶复现)。验收必须含"真 2 源被 H3 误报为 3 源"的负对照。路线 P 在 3 相干源下 beamspace 平滑后已很勉强,只作旁证。

### 8 元、4 源

- **理论**：仍 M>L,理想条件下可辨识;但四源成对 μ 全部良好的几何在室内 DAS 布设中概率低,12 维几何搜索 + 4B 幅度的 evidence 比较对纹理误差极敏感。
- **工程推荐**：**v1 不承诺分离**。只承诺:检测"≥3 源"并对第 4 源输出 MARGINAL/UNRESOLVED 及粗 (az, τ);把 4 源可靠分离列为 G5 之后的研究问题。理由:流形误差地板 + 同码相干下,第 4 个（通常最弱的）源的 GLRT 改善预计常态落入门限灰区;硬输出违反"不可靠时拒绝输出"的项目铁律。

**结论一句话**：理论可行上限 = 4 源;工程承诺上限 = **2 源(主目标)**,3 源为有条件扩展目标,4 源仅检测不承诺分离。

---

## 6. 共同参考处理（禁止独立 PLL 拼相关）

**禁止**：8 通道各自 acquisition/tracking/PLL → 各自 NCO 相位 → 拼 8 路复相关。各通道 PLL 会把阵元间空间相位差吸收进各自载波相位估计,拼出来的"阵列相位"是 8 个环路的噪声,空间信息被消掉。doc16 已在 4 通道版本禁止,8 通道同样。

**主设计（离线优先,与现骨架/dense 导出兼容）**：

1. 一次同步采集 8 路原始 IQ（共钟共触发,G0 保证）;
2. 在**参考通道 ch0** 上做标准 acquisition + tracking（现有 GNSS-SDR 链路不动）;
3. 把 ch0 的码相位/载波 NCO 假设（dense dump 记录里已含 `rem_code_phase_chips/carrier_phase_step_rad` 等全部重建字段,doc11 格式）**开环施加**到全部 8 路原始流,各路只做混频+相关,不闭环;
4. 每历元产出 `8×K` 复 dense 向量（K=31,网格沿用 `-1.5:0.1:1.5`）;
5. 施加实测频域校准 `G_m(f)`（G0 产物）;
6. 不取模,按短块进 MMV 模型（逐块复幅度吸收残余共模相位/钟漂）;
7. 一源~四源模型比较（§4）。

为什么保留空间相位：所有通道用**同一个**本地载波/码复本,阵元 m 相对 ch0 的到达相位差 `exp(j·2π/λ·(p_m−p_0)·u)` 原封不动落在该通道相关值的复相位上;逐块 nuisance 幅度只吸收全阵共模项,不吸收阵元间差分项。

**可选增强（须论证不消空间相位后才可用）**：
- **波束参考跟踪**：用固定权（如全 1 和波束）合成参考流做跟踪,SNR 高 ~9 dB、弱信号下环路更稳。共模 NCO 仍唯一、开环施加到各原始通道,阵元间差分相位不受影响——**不消空间相位**,G6 实时链路的推荐参考源。
- 禁止的变体依然禁止：任何"先各通道独立锁相再对齐"的方案不予评审。

---

## 7. Gate 0–6

通用规则：每个 Gate 产物入 `~/lya/gnss_data/{raw,logs,outputs,analysis}`（doc10 规范）,带 §8 metadata;正对照/负对照缺一不发 PASS;MARGINAL = 限期复测一次,再不过按 STOP 处理;所有 PASS 判定写入 05 决策日志。

### G0 Y790s 八通道电子同步 [Y790s未验证]

- **输入**：Y790s + 单强源经 8 路功分器有线注入全部 RX。
- **操作**：5 s RAM-disk 冒烟 → 30 s 采集;重启、重调谐、跨天各 ≥3 次;记录 `G_m(f)`（8 路宽带复传函,以 ch0 为基准）;监控 overflow/丢样;20 Msps×8ch×sc16 ≈ **640 MB/s**,吞吐先行验证。
- **正对照**：功分器有线注入（8 路同信号,理论相位差=电缆差,静态）。
- **负对照**：断开一路天线口,该通道须报无信号而非复制邻路（查串扰/软件bug）。
- **输出**：`raw` 8ch 文件 + sidecar;`calib_<ID>.npz`（`G_m(f)` + 时间戳 + 温度备注）;同步报告。
- **指标**：样点数一致性;历元对齐确定性(重启后 ch 间样点偏移=0 或恒定可查);30 s 内 ch 间相位漂移;重启后 `G_m(f)` 复现性;overflow 计数。
- **PASS**：0 overflow;run 内任意通道对相位漂移 < 5°(RMS);重启后 |ΔG| < 0.5 dB / 5°;时延对齐确定。
- **MARGINAL**：漂移 5–15° 或重启复现 5–15°——记录漂移模型,评估能否 run 内标定跟踪。
- **STOP/REDESIGN**：漂移 >15° 或重启不可复现或跨 tile 样点对齐不确定 → 与厂家对质(§10),不满足则换硬件。**G0 不过,后面全部冻结。**

### G1 单源实测圆阵流形 [Y790s未验证]

- **输入**：G0 PASS 的整套装置 + 8 元 UCA 支架 + 单模拟器 A-only OTA,受控/低反射环境。
- **操作**：转台或移动源覆盖 az 网格 **0:30:330°**(12 点) × el {低,中}两档,每点 ≥3 次 30 s;每点存 8×K 复模板、协方差、校准 ID、几何照片/量测;插值误差评估决定是否加密到 15°。
- **正对照**：任一网格点重复 3 次,模板复一致性;理想导向律作形状 sanity（只比趋势不作真值）。
- **负对照**：同一角度换极化/换天线个体,验证差异被流形吸收还是超限。
- **输出**：`manifold_<ID>.npz`（§8 格式）+ 流形质量报告（逐点 SNR、重复性、与理想式偏差 ε 图、μ_spatial(Δaz) 实测曲线）。
- **指标**：逐点重复复误差 ε_rep;插值误差 ε_int;实测 μ_spatial(Δaz=30°) 值。
- **PASS**：ε_rep < 5%(向量范数比);ε_int < 8%;μ_spatial(30°) ≤ 0.9(否则 G3 的 30° 包线要改)。
- **MARGINAL**：ε 5–10% → 加密网格/改支架再测。
- **STOP/REDESIGN**：ε > 10% 或跨日不可复现 → 互耦建模/机械重设计,不得带病进 G2。

### G2 两源 0-delay 空间分离 [Y790s未验证]

- **输入**：两模拟器同 PRN、**延迟差 0 chip**、不同方向(首选实测 μ_spatial 最低的一对角),等功率与 -6 dB 两档,CN0≈52。
- **操作**：每条件 ≥5 次 30 s;跑 H1 vs H2(空间轴唯一判别力);沿用现有 `fit` 四态输出。
- **正对照**：Δaz 取最优角对(μ_spatial 最低)。
- **负对照**：①单源(A-only) ≥5 次——H2 检出率即虚警率;②两源**同方向**(同一喇叭/相邻角)——必须 UNRESOLVED。
- **输出**：`block` 格式数据 + 判定 CSV(state, improvement_db, μ 三件套, cond)。
- **指标**：P_D、P_FA、az 误差、UNRESOLVED 正确率。
- **PASS**：P_D ≥ 90%(Δaz≥30° 档)、P_FA ≤ 5%、同方向负对照 100% 不出 RELIABLE。
- **MARGINAL**：P_D 70–90% → 查校准时效/流形插值,复测一轮。
- **STOP/REDESIGN**：P_D < 70% 或 P_FA > 10% → 空间轴本身不成立,回 G0/G1 找根因;**禁止**跳过 G2 直接做 0.5 chip(doc16 原则)。

### G3 两源 0.5-chip 空间-时延联合分离（核心研究目标） [Y790s未验证]

- **输入**：两模拟器,Δτ ∈ {0, 0.5, 1.0} chip × Δaz ∈ {0, 10, 30, 60°},功率 -6 dB,CN0≈52(继承 doc16 最小筛查设计),每条件 3 次 + 单源对照。
- **操作**：路线 R 全链路(实测核+实测流形+H1/H2 GLRT+varpro);路线 P 平行跑作对照;先用 faithful 纹理 + 流形扰动仿真预演全部条件(见 §9 Codex 任务),实测只验证仿真预测。
- **正对照**：Δτ=0.5, Δaz=60°(最有利)。
- **负对照**：①单源;②Δaz=0(纯时延,应回落到单天线的墙:UNRESOLVED/NO_SECOND);③faithful 纹理阴性集。
- **输出**：判定 CSV + delay/az 误差表 + 与仿真预测对照报告。
- **指标**：doc16 验收沿用——P_D ≥ 90%,P_FA ≤ 5%,**delay RMSE ≤ 0.1 chip**,amp 比误差,az 误差,UNRESOLVED 正确率;附加 doc15 纪律:延迟接近真值 ≠ 成功,须幅度+残差改善+条件数同过。
- **PASS**：Δaz ≥ 30° 档全指标达标 → **对外可宣称"2 源 0.5 chip 亚码片分离 [Y790s实测]"**。
- **MARGINAL**：仅 60° 档达标 → 包线照实收窄,不改指标凑数。
- **STOP/REDESIGN**：30/60° 都不过而 G2 曾过 → 时延轴引入的纹理失配是根因,回纹理感知 GLRT 扩展,不加新优化器。

### G4 angle-delay separability map [Y790s未验证]

- **输入**：G3 PASS 后,围绕过渡带扩展:Δτ {0.3, 0.5, 0.75, 1.0} × Δaz {5, 10, 20, 30, 60°} × 功率 {0, -3, -6, -10 dB} × CN0 {45, 52, 57}。
- **操作**：自适应采样(重复次数堆在 RELIABLE/UNRESOLVED 边界),多 PRN、多日、重启重校;绝对阵列朝向至少 2 种(验 UCA 各向同性)。
- **正/负对照**：每 session 首尾各一次单源标定 run。
- **输出**：`separability_map.csv` + 等值线图(P_D、RMSE、UNRESOLVED 率 over (Δτ, Δaz))——这是交付给应用侧的**能力包线文件**。
- **指标**：边界重复性(跨日边界移动 < 一个网格步)。
- **PASS**：地图闭合且跨日稳定。MARGINAL：个别格点跨日翻转 → 加采样。STOP：边界随 session 漂移 → 校准时效问题,回 G0 漂移模型。

### G5 三源/四源扩展 [Y790s未验证]

- **输入**：三台(后四台)模拟器或双源+DAS 实物;几何按 §5 的 3 源包线设计。
- **操作**：H1..H4 模型阶选择全链路;先 faithful+流形扰动仿真预演。
- **正对照**：3 源大角距大延迟差(全部成对 μ_joint < 0.85)。
- **负对照**：①真 2 源跑 H3——过检率即模型阶虚警;②单源跑 H2..H4。
- **输出**：模型阶混淆矩阵 + 3 源参数误差表。
- **指标**：阶选择正确率、per-path 误差、4 源检测(不分离)的告警正确性。
- **PASS**：3 源包线内阶正确率 ≥ 85%、过阶虚警 ≤ 5%。MARGINAL：仅最有利几何过 → 3 源降级为"演示级"。STOP：H3 系统性把纹理残差当第三源 → 冻结 3/4 源承诺,只交付 2 源 + 检测。

### G6 GNSS-SDR 实时/准实时集成 [Y790s未验证]

- **输入**：全部离线 Gate 通过的算法冻结版。
- **操作**：Y790s 8ch signal source 块接入;参考通道(或和波束)实时跟踪;8 路开环 dense 相关实时导出;空时估计器先跑准实时(块延迟秒级),再评估实时;复用 doc07 的 observables/monitor 工程。
- **正对照**：同一段 RF 录制离线 vs 在线结果一致(逐历元比对)。
- **负对照**：单源实时长跑虚警率。
- **输出**：实时 per-path (az, el, τ, power, state) 流 + 资源占用报告。
- **指标**：在线=离线一致性;丢样率;端到端延迟;24 h 稳定性。
- **PASS**：一致性 100%(容浮点差),0 overflow(吸取 L5 实时 overflow 教训:先查消费停顿再怪算力)。STOP：算力不够 → 降 K/降块率,不牺牲判定纪律。

---

## 8. 数据规范（8 通道统一接口）

所有 npz 均含 `meta_json`(JSON 字符串),沿用现骨架键风格。**必填 metadata 字段**（所有层级共用）：

```json
{
  "device": "Y790s-SNxxxx", "firmware": "...", "sdk_version": "...",
  "sample_rate_sps": 20000000, "center_freq_hz": 1176450000,
  "gain_db": [g0,...,g7], "antenna_mapping": ["RX0:elem0",...],
  "calibration_id": "calib_20260810a", "array_xyz_m": [[x,y,z]x8],
  "wavelength_m": 0.2548, "array_orientation_note": "...",
  "simulator": {"units": 2, "shared_10mhz": true, "settings": "..."},
  "prn": 28, "signal": "L5I",
  "truth": {"az_deg": [...], "el_deg": [...], "delay_chips": [...],
             "power_db": [...]} ,
  "capture_utc": "...", "operator": "...", "evidence_level": "Y790s|B210|faithful|ideal"
}
```

层级格式：

1. **raw**：`<prefix>_8ch.dat` 交织 sc16,布局 `[sample][channel]`(channel-interleaved,若 SDK 给平面布局则 sidecar 注明 `layout: planar`);sidecar `<prefix>_8ch.json` 含上表 + `layout/scale/start_sample_time`。
2. **post-correlation dense**：npz 键 `dense`(complex64, **[epoch, channel, tap]** = (E, 8, 31))、`taps`(chips)、`epoch_meta`(sample_counter/tow_ms/cn0 per epoch,继承 doc11 记录头字段)、`meta_json`。单通道旧格式 (E, K) 视为 M=1 特例,读取器统一。
3. **block**：npz 键 `dense_blocks` **[block, epoch_in_block, channel, tap]**、`block_len_epochs`、`taps`、`meta_json`。估计器输入 = 沿 epoch 轴相干平均后的 `(B, M, K)`——与现 `fit_space_delay_twosource.py` 形状**完全一致**,零改动接入。
4. **manifold**：npz 键 `az_deg`(A,), `el_deg`(Ev,), `response`(complex64, **[az, el, channel]**), `response_cov`, `n_runs`, `meta_json`(含 calibration_id 绑定)。插值器输出 `a(az,el)` (8,) 复向量。
5. **kernel**：不变——Phase A CSV `tap_chips,coherent_re,coherent_im,mag_mean,mag_std`。
6. **calibration**：npz 键 `freq_hz`, `G`(complex, [channel, freq]), `ref_channel=0`, `meta_json`。

命名：`<yyyymmdd>_<gate>_<prn>_<condition>_<runN>` 前缀贯穿 raw/dense/block/判定 CSV,靠 `calibration_id` 与 `manifold_id` 外键关联。

---

## 9. Codex 下一阶段开发任务（不动核心 C++）

优先级排序,全部在 `dev_notes/sim/` 层,硬件到货前即可做：

1. **T1 阵列模型通用化**：`steering_xyz`(任意 (M,3) 位置 + az/el)替换 ULA 专用 `steering`;`generate/fit_space_delay_twosource.py` 参数 `--array-xyz`/`--uca-radius-m`;`meta_json` 加 `array_xyz_m/wavelength_m`;ULA 回归自测保持通过。
2. **T2 UCA A0 可辨识性图**：8 元 UCA 理想流形下扫 μ_spatial(Δaz, 绝对朝向, el) 与 cond,输出等值线;明确标注 [理想仿真];复核"30° 包线"在 UCA 下的真实 μ 值(替换四元 ULA 0/30° 巧合正交的结论)。
3. **T3 流形扰动 + faithful 纹理合成**：在 T1 生成器上加 (a) 逐元素复流形误差 ε(可设 3/5/10%)、(b) 通道相位漂移过程、(c) path0 用真实 A-only 纹理(复用 doc12/15 管线)——产出 G2/G3 的仿真预演包线。**这是把 [理想仿真] 升级到 [纹理合成] 的关键任务。**
4. **T4 H1..H4 模型阶选择**：`fit` 推广到 L∈{1..4},嵌套 GLRT+BIC,成对 μ 门禁,负对照(真2源过H3)脚本化。
5. **T5 τ0 精修**：去掉骨架 `tau0=0` 硬编码,path0 延迟对齐/局部细化(05 评审遗留项);被拒 H 阶的参数输出 N/A。
6. **T6 数据规范落地**：§8 各层读写器 + 校验器(schema check),旧单通道数据自动升格 M=1。
7. **T7 路线 P comparator**：beamspace(Davies |h|≤3)+平滑+MUSIC+MVDR+per-beam 延迟,仅仿真验证,作 G3 对照工具。
8. **T8 GLRT 阈值标定协议**：3/6 dB 与 mu_max=0.98 是临时值(05 评审),写标定脚本:用 T3 的单源+扰动集按 CN0 分档拟合门限,输出门限表而非常数。

## 10. Y790s 厂家必须确认的接口清单（G0 前置,一项不落）

| # | 项 | 必须确认的具体问题 | 不满足的后果 |
|---|---|---|---|
| 1 | 8RX 同步流 | 8 通道能否**单命令同起**、同一采样时刻;最大聚合速率下(8ch×20 Msps sc16=640 MB/s)接口(万兆/PCIe/USB?)是否撑得住 | G0 吞吐直接失败 |
| 2 | 跨 tile 同步(MTS 等效) | 多 ADC/tile 架构下是否有 Multi-Tile Sync;每次上电后 tile 间样点偏移是否**确定**或可读出 | 通道间时延随机 → 流形每次作废 |
| 3 | deterministic latency | 重启/重调谐后通道间时延与相位是否可复现;若不可复现,是否提供内部校准信号回环 | 每次开机都要全套 OTA 重校 |
| 4 | 同步 NCO reset | 8 路 DDC NCO 能否同相位复位/同步调谐 | 阵元间随机相位偏置,只能靠外部校准吸收 |
| 5 | 硬件触发 | 外触发/PPS 触发采集,触发到首样点延迟确定性 | 与模拟器时刻对不上,真值延迟失效 |
| 6 | timestamp | 样点级时间戳;8 通道时间戳是否同源 | 历元对齐靠猜 |
| 7 | overflow 上报 | 每通道 overflow/丢样是否上报且**定位到样点** | 静默丢样毁掉相位连续性(L5 实时教训) |
| 8 | SDK 数据布局 | 交织/平面、位宽、缩放、字节序;是否零拷贝取流 | 记录器返工 |
| 9 | GNU Radio/C++ 接口 | 有无 gr-source 块或 C/C++ API;能否被 GNSS-SDR signal source 适配;Linux 驱动依赖 | G6 集成路线不成立 |
| 10 | 参考钟 | 外部 10 MHz 输入;8 通道是否共 LO(共 LO 则相位漂移只剩走线/温度项) | 不共 LO → 回到双 B210 的漂移地狱 |
| 11 | 增益相位耦合 | 改增益是否改相位(AGC 必须可关) | run 中 AGC 动作 = 流形时变 |

**硬件风险表**：

| 风险 | 等级 | 缓解 |
|---|---|---|
| Y790s 相位同步指标为纸面值 | 高 | G0 独立复测,厂家演示不作数 |
| 640 MB/s 持续写盘 | 高 | RAM-disk 冒烟 + NVMe 预算;不行则降 10 Msps(L5 下限告警,doc11) |
| 互耦/支架散射超流形预算 | 中 | G1 的 ε 门禁;必要时加大阵元间距/吸波 |
| 校准时效(温漂) | 中 | G0 漂移模型;session 首尾标定 run |
| 模拟器与 Y790s 无共同 10 MHz | 中 | doc15 教训:A/B 前后各录单源基线,否则不宣称米级绝对真值 |
| el 维弱观测被误当强能力交付 | 中 | 输出规范里 el 恒带宽置信区间,文档明示 ±el 模糊 |

## 11. 必须由用户本人执行的实验（AI 不可代替）

1. Y790s 采购前与厂家逐项过 §10 清单并拿到书面答复;
2. G0 全部实机操作(接线、功分、重启/重调谐序列、吞吐测试);
3. UCA 支架加工/装配与几何量测(半径、平面度、阵元朝向拍照存档);
4. G1 转台/角度网格 OTA 采集(受控环境协调);
5. 双(多)模拟器场景配置(功率、补偿距离、共 10 MHz 接法)与每次采集的单源基线;
6. NUC/主机侧按 git-sync 流程拉代码、conda 环境编译(两机路线纪律,勿混二进制);
7. 所有 Gate 的 PASS/STOP 决策签字——AI 给判定建议,go/no-go 是用户的。

---

## 12. 与历史文档的关系

- doc16 的方法论(共参考、实测流形、MMV、四态、stop rules)全部继承;其 ULA 几何、5 点角网格、四通道硬件章节被本文件 §2/§7-G1 取代。
- doc12 的"静态单天线欠定墙"是本路线的动机,不因阵列成功与否改写。
- doc15 的纹理 GLRT/CN0≥45 包线直接作为 G3 的时延轴判定组件。
- 现有 0.1 chip 自测结果的证据等级与适用范围以 05 的 2026-08-04 评审为准,本文 §0 重申。
