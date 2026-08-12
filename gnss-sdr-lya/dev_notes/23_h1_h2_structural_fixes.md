# H1/H2 Continuous Refinement — 结构性修复报告（doc23）

**Date:** 2026-08-12
**Author:** Claude（研究架构与独立审查）
**Starting SHA:** `04a1a4c89`（被审算法 `7146fec14` + Codex 评审证据 commit）
**触发:** Codex 独立审查 `CONTINUOUS_REFINEMENT_REVIEW_BLOCK`（证据见 `sim/review_evidence_7146fec/`）
**证据等级:** 全部 **[理想仿真]**（生成器与估计器共核共导向律）;门限一律 `PROVISIONAL`(doc19 §14.2)。

---

## 1. 修复内容（对应 Codex 五项确认问题）

### F1 删除 H2 对 H1 tau 的锚定（`H2_H1_ANCHOR_BIAS_CONFIRMED`）

旧结构:H2 coarse 把 source0 的 tau 固定在 refined H1 tau,只全局搜 source1。
新结构:H2 coarse 是 **(az0,tau0,az1,tau1) 完全独立的双源搜索**——对模板库
(N=|az_grid|×|tau_grid|)一次性算出全部 i<j 模板对的闭式投影能量
`E_ij = (g_jj·S_ii + g_ii·S_jj − 2Re(g_ij·S_ij))/det`,向量化整库排序。
H1 结果只作 diagnostics + 一个**可选 multi-start 种子**(输出中 `h1_seeded`
标记),不约束任何一路的位置。tau 网格扩至 `[-0.75, +1.5]` chip。

### F2 有限、可审计 multi-start

coarse 上三角(i<j)天然完成 source-swap 去重;再按参数距离
(>1.5 网格步)贪心取 **top-K 独立候选,K=5**(写入输出 `n_starts`,含 H1 种子
共 6 起点);每个起点独立黄金分割坐标下降细化;取 refined residual 最低者;
每个 start 的 seed/refined/residual/status 全量保存在输出 `multi_start` 里。
未做大型全局优化器。

### F3 删除 delay-only collision 判据（`DELAY_ONLY_COLLISION_RULE_INVALID`）

`abs(tau1−tau0) < min_sep → UNRESOLVED` 已删除。退化只在**联合模板层面**判:
`mu_joint > 0.98`、联合设计条件数 `> 1e4`、第二源幅度显著性
(`amp_ratio < −30 dB`)。同时延+不同空间签名 = 合法 TWO_SOURCE;
同时延+同空间签名 → mu_joint→1 → UNRESOLVED。

### F4 三态语义修正

正式状态仅 `ONE_SOURCE / TWO_SOURCE / UNRESOLVED`:
- `improvement < detect_db(3, PROVISIONAL)` → ONE_SOURCE;
- `detect ≤ improvement < reliable_db(6, PROVISIONAL)` → **UNRESOLVED**
  (detail=`marginal_evidence`;旧 MARGINAL 仅存于 detail,**不再映射为 TWO_SOURCE**);
- `≥ reliable` 且联合可辨识合格 → TWO_SOURCE;
- mu_joint 过高/条件数恶化/弱幅度 → UNRESOLVED(detail 注明原因)。

### F5 MeasuredManifold 接口加固

新校验(13 项单测全过,`sim/test_measured_manifold_hardening.py`):
az 严格递增且唯一、有限值、response 形状/通道数检查、全零通道拒绝、
3-D response 禁止静默取 el=0(仅 E=1 且显式 `allow_single_elevation=True`)、
全圆网格显式加 wrap 节点(实测 0/360 缝隙 |Δa|=0.0009,连续)、扇区网格外
查询**报错而非静默钳位**。复数插值 = 逐通道 Re/Im 线性插值,文档注明限制:
相邻网格点相位步进大时会低估 |a|,实测网格须保证逐通道相位步 ≲30°;
归一化约定 = 以校准时定义的参考通道为基准(`calibration_id` 绑定),
加载器不做二次归一化。未实现 `a(θ,r)`(按 doc19 §14.5)。

另修一处**新发现的实现 bug**(修复过程中引入检测):coarse 投影能量交叉项
误写为 `Re(G·conj(S))`,正确为 `Re(G·S)`——μ≈0 时无影响,高相干对能量被
高估导致 coarse 选中退化对。已修复并由全部下游结果验证。

---

## 2. 验收结果

复现:
```
python dev_notes/sim/fit_space_delay_h1h2.py --self-test
python dev_notes/sim/test_measured_manifold_hardening.py
python dev_notes/sim/run_h1h2_protection_matrix.py --output <csv>
python dev_notes/sim/calibrate_h0_glrt.py --n-trials 500 [--manifold-error 0.05]
```
证据文件:`sim/h1h2_fix_evidence/`(matrix CSV + 2×H0 JSON);
pre-fix 基线:Codex `sim/review_evidence_7146fec/`。

### 2.1 锚定压力场景前后对比（27 runs post,3 taus×3 Δaz×3 seeds,等功率）

| 量 | pre-fix(reviewed_anchor) | post-fix |
|---|---|---|
| delay MAE | **0.0967 chip** | **0.0014 chip** |
| delay max err | 0.3006 chip(−0.5/+0.5, Δaz=10°) | 0.0035 chip |
| 全部状态 | — | 27/27 TWO_SOURCE |

三个指定 taus 组合(−0.25/+0.25、−0.5/+0.5、−0.18/+0.32)全部恢复,
multi-start residual spread 最高 19 dB(说明单起点确有局部极小风险,
multi-start 有效;Δaz=30° 时 H1 种子起点偶为最优——作为种子合法)。

### 2.2 基准 A:0.5 chip / 30° / −6 dB（off-grid τ0=0.07,5 seeds）

| | pre-fix | post-fix |
|---|---|---|
| delta_tau 估计 | 0.396–0.452(MAE 0.082,即"0.418 问题") | 0.4975–0.5008(**MAE 0.0016,max 0.0025**) |
| 状态 | 5/5 TWO_SOURCE(但有偏) | 5/5 TWO_SOURCE |

偏差改善 ~50 倍,锚定偏置消除。

### 2.3 零延迟/大角度（Δτ=0,Δaz∈{60,90,120,180}°,0/−6 dB,3 seeds）

pre-fix:24/32 UNRESOLVED(collision)、8 ONE_SOURCE——collision 规则误杀。
post-fix:
- **60/90/120°:18/18 TWO_SOURCE**,dtau_est ≤0.005 chip,|Δaz| 误差 ≤0.36°,
  improvement 13.2–21.6 dB,mu_joint 0.0002–0.61;
- **180°:6/6 ONE_SOURCE(improvement≈0.05 dB)**——λ/2 ULA 的 ±90° endfire
  导向矢量数学上恒等(空间签名相同),物理不可辨,**预期行为而非缺陷**;
  真实 4 阵元 XYZ 到手后须用 T2/T3 重算此类退化方位。
(注:等功率零延迟下 Δaz 符号偶有翻转,源排序在 τ 相等时按 az,属标签
歧义,|Δaz| 正确。)

### 2.4 主保护矩阵（Δτ{0,0.25,0.5,1}×Δaz{60,40,30,20,10}×{0,−6 dB}×3 seeds=120 runs）

**120/120 TWO_SOURCE**;delta_tau 最大绝对误差 **0.0062 chip**(Δτ=0,
Δaz=10°,−6 dB);improvement 最低 10.3 dB(同几何)。矩阵 CSV 含
state/improvement/估计值/mu_joint/cond/H1、H2 residual/multi-start
winner+spread/optimizer status 全列。

### 2.5 H0 negative-control（连续随机 az/τ,500 ideal + 500 5% 流形失配）

| 条件 | q50 | q90 | q95 | q99 | max | TWO_SOURCE 虚警 | UNRESOLVED |
|---|---|---|---|---|---|---|---|
| ideal(500) | 0.042 | 0.051 | 0.054 | 0.059 | **0.064 dB** | **0/500** | 0 |
| 5% manifold err(500) | 0.381 | 0.975 | 1.228 | 1.763 | **2.545 dB** | **0/500** | 0 |

对比 pre-fix(Codex 500+500):ideal max 0.077、5% max 2.571——
**multi-start 没有抬高 H0 尾部**(反而略降,因去掉了退化对的能量高估);
off-grid splitting 虚警保持消失;1000 试验 0 例达到 3 dB detect 门限。
数值仍为 **simulation-derived provisional**,不作最终实验门限。

## 3. 九项验收问答

1. **H2 H1-anchor bias 是否完全删除?** 是。coarse 为独立四参数搜索,H1 仅
   diagnostics+可选种子(输出可审计);压力场景 MAE 0.097→0.0014 chip。
2. **三个 anchor-pressure cases 的 delay MAE 是否改善?** 是,~70×
   (0.0967→0.0014),max 0.30→0.0035。
3. **zero-delay/large-angle 是否正确 TWO_SOURCE?** 是,60/90/120° 18/18;
   180° 为 ULA 几何性空间退化,正确拒报(非缺陷)。
4. **off-grid H0 false alarm 是否仍接近 0?** 是,1000/1000 无 TWO_SOURCE
   虚警,ideal max 0.064 dB ≪ 3 dB。
5. **multi-start 是否明显改善局部极小?** 是,start 间 residual spread 实测
   最高 19 dB;winner 分布(含 H1 种子偶胜)证明单起点不充分;且未付出
   H0 尾部代价。
6. **0.5/30/−6 的 delta_tau bias 是否改善?** 是,MAE 0.082→0.0016 chip
   (0.418 问题消除)。
7. **MARGINAL 是否改为正式 UNRESOLVED?** 是,3–6 dB 区间 → UNRESOLVED
   (detail=marginal_evidence),不再出现在正式 TWO_SOURCE。
8. **MeasuredManifold 安全接口是否完成?** 是,13 项加固单测全过,含 360°
   wrap 连续性与禁止静默钳位/静默 el 切片。
9. **是否允许进入 measured-kernel / faithful-texture?** **允许**——结构性
   阻塞项全部清除;下一阶段(须另行下达)应以实测 Phase-A 核 + faithful
   纹理重跑本报告 2.1–2.5 全套,并按 doc19 §14.2 走真实单源门限标定。

## 4. 限制（verdict 的 WITH_LIMITATIONS 部分）

- 全部证据仍为 **[理想仿真]**:共核、共导向律、加性高斯噪声;faithful
  纹理与实测核未进入本轮(按指令排除)。
- H0 标定用的 coarse 网格(az 步 10°/τ 步 0.1)比双源矩阵(5°/0.05)粗,
  为运行时间取舍;真实标定时须用与实验一致的网格重跑。
- 180° 类空间退化方位依赖阵列几何,4 阵元实际 XYZ 到手前不可外推。
- `PROVISIONAL` 门限(3/6 dB、mu_max=0.98、cond_max=1e4、amp_floor −30 dB)
  未被本轮任何数据"确认",只被"未推翻"。

## 5. Verdict

```
H1H2_STRUCTURAL_FIX_PASS_WITH_LIMITATIONS
```

五项结构性问题全部修复并经保护矩阵+H0 复验;限制仅为证据等级与
provisional 门限的固有范围,不构成结构性阻塞。未实现(按指令):
MUSIC / MVDR / spatial smoothing / CAF / SAGE / H3-H4 / Y790s SDK /
parking-garage processing。不自行进入下一阶段。
