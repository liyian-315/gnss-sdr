# 05 · 踩坑与决策日志（按日期追加）

> **追加式**日志：新条目加到最上面（倒序，最新在前）。记录三类东西：
> - 🧭 **决策**（Decision）：为什么这么做，考虑过哪些方案。
> - 🕳️ **坑**（Pitfall）：遇到的问题、原因、解法/绕法。
> - ❓ **疑问**（Open Question）：暂未解决、需后续确认的点。
>
> 维护提示：**只往这里追加**，不改历史条目；避免每次都要重读全部文档，省 token。

---

## 2026-08-03

### 🧭 决策：转"静态四天线空间-时延"路线（`16`）——是既有工作的**扩展**，不是重写

**赞成 Codex 的 pivot（暂停匀速运动，开静态阵列线）**。理由：① 空间(角度)是单静态天线缺的**新可辨识维**，且**天然匹配 DAS**——多室分天线本就空间分离、从不同方向到达；② **静态**，无运动/轨迹真值的工程负担；③ 方法是**实测模板约束 GLRT/ML，不是盲 MUSIC**（同码同钟=相干源，普通协方差 MUSIC 秩亏）；④ **可辨识性优先**：先用模板算 μ 相干度+条件数/CRLB **预测**哪些几何本就不可分，再上优化器。

**关键物理（一句话）**：可分性由联合模板相干度 `μ = |q0ᴴq1| = μ_spatial · μ_temporal` 决定（因 q(θ,τ)=a(θ)⊗r(τ) 是 Kron 积→相干度**可分解**）。**阵列把亚码片下很高的时延相干度 μ_temporal 乘上一个<1的空间相干度 μ_spatial**→把不可分的对变可分——**当方向不同时**；μ→1(同向)则无论优化器都判**不可分**。

**我的两点补充（写进 `16` 的降险）**：
1. **先做单 B210 双相干通道首证，再上四通道双 B210**。单台 B210 的两路 RX 共享 LO/时钟→**天生相干**，校准只是一个稳定固定偏移；这把**头号风险(跨设备载波初相——共 10MHz/PPS 并不能定死 RF 相位)**从首次端到端验证里彻底拿掉。先在 2 相干通道上跑通空间-时延拟合，再扩到 4 通道要角度分辨力。
2. **优先原生四通道接收机(N310)**，两台 B210 只作条件性原型；**Gate 0(校准稳定性)是真 go/no-go**，不是走过场。

**回答用户三问（存档）**：
- **算法要大改吗？不大改，是扩展**。共享核**全部复用**：dense 复相关导出、Phase A 实测核 R(τ)、一/二源约束 GLRT-ML(varpro：幅度线性、延迟/角度非线性)、纹理感知似然、四态置信(RELIABLE/MARGINAL/UNRESOLVED/NO_SECOND_SOURCE)。**新增**：空间模板维 `a(θ)⊗r(τ)` + 四通道前端(同步采集 + 共参考"ch0跟踪应用到四路" + 复宽带校准 G_m(f))。运动的 Doppler 轴拟合器与此角度轴拟合器**是同一估计器的不同第二维**。
- **还用采数据吗？** 老单通道电缆数据**空间信息为零**(功分器给四路同一信号)→**空间验证必须采新的多通道 OTA 数据**。但老数据**不废**：是 R(τ) 核 + **单天线对照基线**(阵列必须统计上跑赢它)。顺序=先在**四通道合成**上开发算法+可辨识性报告(无硬件)→过 Gate 0 校准→再采 OTA。
- **部署前提(待确认)**：接收端是否允许小阵列(L5 λ/2=12.7cm，可上设备/UAV)——若允许，则空间路线**既验证物理又贴合部署**。

**已交付可演示的骨架代码(合成、无需硬件)**：
- `dev_notes/sim/generate_space_delay_twosource.py`：N 元 ULA 双源场景，逐块随机相位(模拟两台独立钟)，写 npz。
- `dev_notes/sim/fit_space_delay_twosource.py`：A0 μ 分解(时延×空间→联合)+ 条件数；A1 一/二源约束 GLRT-ML(逐块线性幅度)+ 四态判定；`--self-test`。
- 冒烟结果：`0.5 chip/30°→RELIABLE 14.7m`；**`0.1 chip(2.9m)/30°`：单天线→NO_SECOND_SOURCE(漏检)，4 元阵列→RELIABLE(恢复2.9m)**=空间分集撬开亚分辨延迟；同向→诚实拒判；单源→NO_SECOND_SOURCE。⚠️用的是**合成理想核**，真实 path0 纹理 + 实测阵列流形是下一步(勿把合成通过当真实通过——这坑已吃过两次)。

**最大风险(来自 `16`)**：四通道相位校准、相干源模型失配、受控空间几何(OTA)。阵列只在两源方向差足够大时有效——**是条件图，不是普适**；同向/差校准→正确输出 UNRESOLVED。

-- Claude (Opus 4.8), 2026-08-03

---

## 2026-07-29

### 🧭 决策：Phase B 转"双模式"——静态快照=诚实的墙，运动=最低目标的真正归宿（但尚未 cross-PRN 稳健）

**范式判定（三次同样的失败 → 换范式，不是换算法）**：静态双模拟器快照下，1-D 漂移拟合 / 交替残差带 / 2-D delay-Doppler 三种不同架构在近距(≤1 码片)全部同样失败——都被 path0 残差拽到最小延迟(4.4 m / 0.15 chip)。诊断(`12`)量化了根因：真实 path0 在 delay-Doppler 面上是**横向 Doppler 条带(非单一 ridge)**，path1 埋在其下约 30 dB；单核逐历元扣除能抬约 30 dB 但**留多个竞争候选**，不唯一。**faithful path0 synthetic(用真实 A-only 纹理)复现了真实失败，而 clean synthetic 成功**——证明早期合成过于乐观。结论：**同码同钟静态亚码片分离是欠定问题**，扣 path0 的技巧造不出缺失的分集。

**运动是缺失的分集(=合成孔径)**：真实部署 = 多天线固定 + **接收机运动** → 每径几何相关的时变 Doppler/延迟轨迹。Track B(`13`/`14`)在**真实 PRN28 纹理**上把 0.37–0.55 chip(11–16 m，含最低目标 0.5 chip)恢复到亚米级，静态对照正确判 UNRELIABLE，真负例(path1 缺席)正确拒绝。**这是第一个真正撬动亚码片的结果。**

**⚠️ 但 `15` 交叉纹理基准把话说回来(必须诚实)**：PRN28 是有利个例、**不代表全体**。23 参考跨纹理：EKF 运动 −6 dB 仅 **8/19** RELIABLE、DP 14/19；等功率/180° 更低。**真实 path0 逐历元纹理仍是运动模式下的主障碍**(Phase-A 指纹门通过 ≠ 纹理对双源跟踪友好)。真正稳健的是 **EKF 的负控行为**(静态/缺席全拒)；DP 会误收 4 个静态对照 → **DP 必须加运动/分集门**。CN0 非唯一解释变量(同 PRN 同功率 run 间纹理变化即改判)。

**决策**：采纳**双模式**——① **静态模式**：只报诚实的可分离下限 + 不确定度(墙在亚码片)；② **运动模式**：面向亚码片最低目标，**已证可行、尚未 cross-PRN 稳健**。下一算法杠杆是**纹理感知的接收/初始化 + 失配感知的 EKF 协方差 + 多假设一致性**，**不是**再调阈值、也不是再来一个快照算法。纪律(来自 `15` 静态审计)：**延迟接近注入值 ≠ 成功**——幅度、残差改善、条件数、采集质量必须同时过关。

**下一步优先级**：truth-free 置信(轨迹最优–次优边距 + 运动/几何一致性，无需真值，供真实数据虚警控制) → 纹理质量分(A-only 残差图) → 运动包络扫描(几何/速度/CN0/曲线轨迹) → faithful path1 纹理 → **真实运动 B210 采集(带测量轨迹真值)**。最大未测风险：**真实运动下跟踪环对"运动复合信号"的动态反应**(合成里 path0 是静态场景纹理，未含环路对双动源的响应)。

-- Claude (Opus 4.8), 2026-07-29

---

## 2026-07-31

### Codex decision: trajectory-only truth-free confidence is diagnostic, not a real-data gate

Claude's motion-span, Doppler-span, physics-link, and best-vs-second confidence
features were rerun on all 23 cross-reference textures. They rejected every
static and path-absent control, but also rejected nearly every correct moving
track. After correcting the alternative-path definition, the best threshold
combination at false-positive rate <=5% recovered only 3/18 correct moving
tracks (16.7% recall). The trajectory margin was larger for negatives than for
correct tracks on median.

Decision: preserve the instrumentation, but do not calibrate another global
threshold on these features. A false path0-residual trajectory can be smooth,
show delay/Doppler span, and obey the local kinematic relation. Next work must
make the observation model texture-aware: path0 residual likelihood,
multi-block candidate consensus, and mismatch-aware EKF covariance. Evidence
and artifact paths are recorded in `15_trackb_cross_reference_benchmark.md`.

-- Codex, 2026-07-31

---

## 2026-07-21

### ✅ 里程碑：现场 L5 链路彻底打通（第三台机 i9-NUC11）+ 三条硬经验

**三台机筛选**：NUC7(双核) 连实时 10Msps 都撑不住 → RK3588(8核 apt,能编但弱) → **NUC11 i9-11900KB(16核/30G/NVMe) 选定为捕获主力**（GitHub 克隆 feature 分支、apt 装依赖、137s 编完；见 `06`/机器清单）。

**L5 现场首次稳锁**：B210(serial 31502C6) 馈线接 **RF B TX/RX**（`--subdev A:B --ant TX/RX`）、直连模拟器，`gain 65`、10Msps，离线处理 → **PRN21 零掉锁 + 二级码锁 + 解出 NAV 电文，CN0 69 dBHz**。也顺带证明 31502C6 没坏（早先只有噪声是别的原因，见下）。

**三条硬经验（都踩过、都验证）**：
- **overflow 主因是"实时算力 / 远程桌面抓屏抢占"，不是采样率本身**。双核 NUC7 + 向日葵撑不住实时 10Msps；i9 **录 30Msps 零 overflow（ToDesk 开着无感），50 也干净，40/56 仅启动瞬间 1 次**。→ **弱机器现场策略：只"录文件"(`record_b210.py` 到 `/dev/shm`)，离线再处理**，彻底绕开实时+远程桌面。L5 录制推荐 **25-30Msps**（覆盖 20.46MHz、零 overflow）。
- **别只看幅度判断"有没有信号"**：GNSS 埋在噪底下，幅度看着像噪声(0.003) 也可能有信号，**必须跑捕获**（相关增益~43dB）才看得出来。我一度用幅度误判"无信号"，是录 15s+跑捕获才发现 PRN21 在。
- **B210 增益决定 ADC 填充度 → 有效 CN0**：同一强信号，gain 40/50 时信号在 ADC 里占比极小 → 量化噪声主导 → 假性 marginal（掉锁/无电文）；**gain 65 填满 ADC → CN0 直接 69 → 铁锁**。弱信号先别急着加 sim 功率，先把 B210 gain 提够（注意别削顶：看 `sat_frac`、幅度别近 1.0）。

**🧭 模拟器 L1/L5 在不同 RF 口**：RpsNetCtrl 里 L1CA→射频 CH0、L5→射频 CH1，是两个物理口。馈线要接**对应频段的活口**（测 L5 接 RF CH1，或接正在辐射给手机的那个口），否则采到的是空口噪声——这解释了早期"L1 通 L5 死"的一部分。

**新增工具**：`sim/acq_health.py`（聚合判定 CLEAN/MARGINAL/NOISE，比 `check_acq` 可靠：门限余量+峰噪比+码相位稳定度）、`sim/multipath_consistency.py`（第二峰时间一致性）、`08_field_triage_runbook.md`（现场门禁式排查流程）。

---

## 2026-07-20

### ✅ 里程碑：RK3588/Debian11 开发板 apt 路线编译通过（第二套构建环境，区别于 NUC conda）

**背景**：新增一台 **ATK-DLRK3588** 开发板（Rockchip RK3588，aarch64，8核/15G/14G根分区，Debian 11 bullseye，ustc 镜像源），目标让它也能编译本仓库 gnss-sdr（后续接 USRP 现场测试）。SSH `linaro@192.168.137.66`。

**关键结论：这台走 apt 系统包路线，不用 conda**（与 NUC 相反）。Debian 11 自带 **GNU Radio 3.8.2**（不是 NUC 那个 FFT 坏掉的 3.7.11），可直接用；UHD 3.15 也在 apt 里，USRP 支持现成。

**依赖（一条 apt，98 包，约 0.7G，全 bullseye 官方版）**：
```bash
sudo apt-get install -y build-essential cmake git pkg-config \
  gnuradio-dev libboost-all-dev libarmadillo-dev \
  libgflags-dev libgoogle-glog-dev libmatio-dev libpugixml-dev \
  libprotobuf-dev protobuf-compiler libblas-dev liblapack-dev \
  libgtest-dev python3-mako libpcap-dev libspdlog-dev libfmt-dev \
  libuhd-dev uhd-host libssl-dev
```

**构建**（源码根是 `gnss-sdr-lya/` 子目录，见坑④）：
```bash
cd ~/lya/gnss-sdr/gnss-sdr-lya
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF
cmake --build build -j8      # RK3588 8核约 7.8 分钟(469s)，内存峰值<3G
```
产物 `build/src/main/gnss-sdr`（v0.0.21，11MB，属主 linaro），`--version` 正常。磁盘装完+编完仍剩 7.2G。

**踩的 4 个坑（都已解，下次上新板照查）**：
- 坑①**clone 是 root 属主**（当初 sudo git clone）→ 用 linaro 编译写不进 + git 因 dubious ownership 静默失败（`git branch` 空白）。解：`sudo chown -R linaro:linaro ~/lya/gnss-sdr`。⚠️**别用 sudo 编译**，否则 build 又变 root。
- 坑②**clone 停在空的 main 分支**：`main` 只有 1 提交（Initial commit）+ `.gitignore`（`git ls-files`=1），真代码在 `origin/feature/*`。解：`git checkout feature/l5-dual-path-tracking`（检出后 5503 文件）。
- 坑③**缺加密库**：cmake 报 `OpenSSL or GnuTLS required`。解：`apt install libssl-dev`。**坑中坑**：补装后必须 `rm -rf build` 再 configure——否则旧 cache 残留 `GNUTLS_INCLUDE_DIR-NOTFOUND` 注入 include 路径，generate 阶段报错。
- 坑④**源码根在子目录**：clone 根 `~/lya/gnss-sdr` 只有 `gnss-sdr-lya/`、`gnss-sdr-xinghe/` 两个副本，CMakeLists.txt 在 `gnss-sdr-lya/` 里，不在 clone 根。

**对照 NUC**：NUC 系统 GNU Radio 3.7.11 FFT 坏 → 必须 conda 3.10 + `build-conda/`；RK3588 Debian11 的 3.8.2 是好的 → apt 直接编、`build/`。两套环境并存，跑测试时注意用对应机器的二进制。

---

## 2026-07-18

### 🕳️ 3D 谱面确认：根本没干净捕获 → 排查重心前移到 RF/链路（附 `08` runbook）

**决定性证据**：用户 3D 谱面截图 `peak @ 1842.4 chip, 1250 Hz, grid=(40,10000), has2=1 ratio=4.1dB`——
整个相关面是**一片噪声草皮，没有一根尖峰立在噪底之上**；`ratio=4.1dB` 说明"主峰"只比"第二峰"高 2.6×，两者都是噪声草叶。
**佐证**：用户报告现场 `50/100/200m` 补偿结果**完全无差别**——有真信号+多径时改延迟结果必变，结果不变 = 纯噪声、没锁上信号。

**结论修正（重要）**：当前**根本没干净捕获目标星**，多径分析全是空中楼阁。这正是 `06 §2E.5` 早已写的
"3D 图没有清晰尖峰 → 先查频点/限带/overflow/模拟器/天线，**不要先怀疑多径算法**"。
排查重心从"多径算法"**前移到"先拿到一次干净的单星捕获"**。

**交付（可直接照做，无需环境即可先读）**：
- 新增 `dev_notes/08_field_triage_runbook.md`：按**门禁**逐步走——Step1 单模拟器干净捕获（最关键的门）→ Step2 单路假警基线标定门限 → Step3 **导线注入已知延迟（黄金标准，验证算法本身）** → Step4 OTA 几何自检 → Step5 距离阶梯+时间一致性 → Step6 转场。每步有[命令]+[✅通过标准]+[❌不过怎么办]。
- 新增 `dev_notes/sim/acq_health.py`：聚合判定捕获是否干净（`margin_db`/`peak2floor_db`/主峰码相位 std → CLEAN/MARGINAL/NOISE），比单看 `positive_acq` 可靠。
- 新增 `dev_notes/sim/multipath_consistency.py`：读 `summary.tsv`，对 `delta_chip` 聚类找最大一致簇 → CONSISTENT/SCATTERED，直接否掉噪声游走。
- ⚠️ 两个新脚本**无环境未实跑**，首次用请先在一份真 dump 上冒烟。

**关键新增判据**：① `acq_health` 的**主峰码相位跨 dump std**——真信号稳定(<1chip)、噪声乱跳；② `multipath_consistency` 的**Δ 一致簇**——真反射时间上稳定、噪声散布全窗。这两条是把"噪声 argmax"和"真峰"分开的核心。

### 🧭 真实环境第二峰噪声化：根因诊断 + 排查/算法改进路线（承接 07-17「现场50m失效」条目）

**看图得到的更强结论**（`gps_l5_prn18_twosim_350_-350m_30s_part01`，194 dump，1 chip=29.3m）：
- `Δ延迟` 在**整个 ±90 chip 搜索窗里随机游走**（图中 -89~+84 chip、-2600~+2458m），不聚集在任何值 → 报出的"第二峰"是**噪声最大点**，不是反射。
- `valid_positive_has2=0`：194 份里**没有一份**同时 `positive_acq=1 && has2=1` → 当前无一条可信多径检出。
- dump 文件名是 **`sat_23` 而非 PRN18** → 可能是弱信号下的**互相关假峰**或搜到别的真星；**目标 PRN 没干净捕获前，第二峰无意义**。

**算法层根因**（读 `pcps_acquisition.cc:556 find_second_peak`）：该函数在主峰同多普勒 bin、`±multipath_max_delay_chips` 环带内（排除 ±1 chip）取**全局最大点**做第二峰，门限仅 `test_statistics2 > multipath_threshold_fraction×threshold`。三个放大器叠加导致噪声化：
1. **窗太宽**：默认窗到 90 chip（±2637m），比感兴趣信号宽约 7×，环带内噪声最大点几乎必然是噪声尖峰，逐 dump 乱跳。
2. **信号弱**：CN0 35-40 → 主峰勉强过门限 → `fraction×threshold` 门贴着噪底 → 噪声轻松过门。
3. **无时间一致性 & 等功率翻转**：逐 dump 独立判定，无持久性约束；两路等功率使主/次峰翻转，Δ 正负乱变。
> 结论修正：这**不只是"50m太近"**——即便 350m（12chip）分离，在此宽窗+弱信号下也会被噪声淹没。近距是硬墙，但当前检测器在远距下同样不鲁棒。

**排查/改进路线（按优先级，低成本先做）**：
- **Phase 0 · 先确认"看的是不是真信号"（不改代码，最高优先）**：① 锁 PRN——查 conf 固定/扫池、确认模拟器发 PRN18、分析脚本只吃目标 PRN 的 dump，排除 `sat_23` 互相关假峰；② 用 `plot_acq_3d.py` 肉眼看 best dump 谱峰面是"单峰+噪底"还是"稳定双峰"，别信 has2 flag；③ 几何自检——站两天线中间时两路程差可能≈0，用几何算清 expected Δ，别拿物理50m当预期；④ 同步自检——两模拟器共 10MHz/1PPS 否则码相位漂；⑤ **单路基线假警标定**——只开一台模拟器录一段跑同分析，理想 has2≈0，若单路也满屏 has2=1 说明当前窗/门就是假警机。
- **Phase 1 · 收紧捕获域检测器（低成本）**：① `multipath_max_delay_chips` 按 expected Δ 收窄（预期6.8chip就设±10，别用90）；② 加大 `max_dwells` 非相干积分压噪底；③ 用单路基线把 `multipath_threshold_fraction` 标到单路 has2=0；④ **加时间一致性/持久性判据（核心）**——要求第二峰在 N 份连续 dump 落在同一 Δ±1chip 才算 has2=1；**先在 `analyze_multipath.py`/summary.tsv 后处理里做（免重编）验证**，有效再下沉 C++。此条可直接否掉图里的随机游走。
- **Phase 2 · 近距(<~2chip)转跟踪域（架构B=`04`的Stage2）**：50m=1.7chip、10Msps 下码相位分辨≈1sample/chip，捕获域到底；即便 Phase1 全做对也分不开。出路：`dll_pll_veml_tracking` 加密相关器抽头重建相关函数→MEDLL/double-delta 估计直射+反射(时延,幅度)。先决：通读 tracking。
- **Phase 3 · 验证方法学（找分离下限）**：距离阶梯 1000→700→350→200→100→50m，每级要求目标PRN正确+有效样本聚集+3D稳定双峰+Δ方差小；记录"哪级开始发散"= 捕获域分离下限 = 架构A↔B 交接点（本项目关键实验结论）。

**下一步落点**：Phase 0 由用户在测试机做（现场因素只能现场排除）；Phase 1 的后处理一致性判据 + 收窗我可以先在分析脚本里实现，不需重编，能立刻在已录 dump 上验证是否把噪声游走压掉。

---

## 2026-07-17

### ⚠️ 当前痛点：现场 L5 近距多径分离失效（约 50m 场景不稳定）

**现象**

- 现场用两边天线分别发送 L5，接收端站在中间，目标是验证约 `50m` 量级的两路伪距差。
- 第一阶段离线捕获分析输出没有稳定聚集到 `50m` 附近。
- 截图中出现 `sat_23` dump，而测试预期曾围绕 PRN18；同时 `Δ米` 大范围跳变，例如几百米到几千米。
- 统计里有效 `positive_acq=1 && has_second_peak=1` 的样本数很少，best 结果不能代表稳定多径识别。

**当前判断**

- 这不是“L5 一定不能分 50m”的结论，而是：**当前第一阶段 acquisition Top-2 方法在现场 50m 量级下尚未形成可靠识别**。
- GPS L5 1 chip 约 `29.3m`，`50m` 只有约 `1.7 chips`；在 `10 Msps` 采样率下接近 `1 sample ≈ 1 chip`，捕获域码相位分辨率已经逼近方法下限。
- 当前算法更适合 `200m/350m/700m/1000m/2000m` 这类远距分离；`50m` 属于近距多径，需要 tracking 域多相关器/窄相关/插值或 MEDLL 类估计。

**需要优先排除的现场因素**

- PRN 是否一致：配置、模拟器、分析脚本必须锁定同一目标 PRN；如果预期 PRN18 却分析出 `sat_23`，不能当作有效 50m 测试。
- 两台模拟器是否共时钟/共 1PPS：若不同步，所谓 50m 相对补偿会被初相、时钟漂移和启动时序污染。
- 几何含义是否一致：两根发射天线物理相距 50m，不等于接收机看到的两路传播距离差一定是 50m；站在中间时，两边传播距离差可能接近 0。
- 有效样本数是否足够：必须看 `positive_acq=1 && has_second_peak=1` 的数量和 `abs(delta_m)` 是否聚集，单个 best dump 不能作为结论。

**下一步验证边界**

- 建议按距离阶梯重测：`1000m -> 700m -> 350m -> 200m -> 100m -> 50m`。
- 每一级都要求目标 PRN 正确、有效样本足够、`delta_m` 聚集、3D 谱峰有稳定双峰。
- 如果 `200m` 稳定、`100m/50m` 开始发散，则可确认当前 acquisition 分离已到边界，应转入 Stage 2 tracking 域近距多径估计。

### ✅ 长时间实时输出实现：monitor-only 配置 + UDP 两径配对脚本

**实现**

- 新增 `dev_notes/sim/watch_dualpath_monitor.py`：
  - 监听 GNSS-SDR `Monitor` UDP protobuf。
  - 不依赖 `protoc`、`gnss_synchro_pb2.py` 或 Python protobuf 包，直接解析所需字段。
  - 在内存中保存每个 `(system, signal, prn, signal_path)` 的最近状态。
  - 当同一 PRN 的 path0/path1 都在 `--stale-sec` 时间窗内出现时，输出 `primary/second` 伪距、C/N0、Doppler 和 `delta_m`。
- 扩展 `dev_notes/sim/make_l5_dualpath_conf.py`：
  - 新增 `--source uhd`，可直接生成 B210 实时配置。
  - 新增 `--enable-monitor`，生成配置时关闭 `Acquisition_L5.dump`、`Tracking_L5.dump`、`Observables.dump`，打开 `Monitor.enable_monitor=true`。
  - 支持 `--monitor-decimation` 控制 UDP 输出频率，减少主链路负担。
- 优化 `src/core/monitor/gnss_synchro_monitor.cc`：
  - 旧逻辑只在触发 UDP 发送时 consume monitor 输入。
  - 新逻辑每次 `general_work()` 都 consume 输入，只按 `decimation_factor` 抽样发送 UDP。
  - 目的：Monitor 作为旁路输出时不能因降采样而积压，避免反向拖慢主 flowgraph。

**关键判断**

- `gnss_synchro_monitor` 每个 UDP 包通常只发送一个通道的 `Gnss_Synchro`，不能假设 path0/path1 会在同一包里。
- 因此接收端必须跨包维护最近状态再配对，否则会出现“收得到包但没有成对输出”的假故障。

**自测**

- 生成 `--source uhd --prns 18,20 --enable-monitor` 配置，确认：
  - `UHD_Signal_Source`
  - `Acquisition_L5.dump=false`
  - `Tracking_L5.dump=false`
  - `Observables.dump=false`
  - `Monitor.enable_monitor=true`
  - PRN18/20 均有 path0/path1。
- 构造两个最小 protobuf UDP payload，分别模拟 path0/path1，确认 `watch_dualpath_monitor.py` 能跨包配对并输出 `delta_m=350.0`。
- Python 脚本语法检查通过；C++ 改动需要在 Ubuntu/conda `build-conda` 中完整编译验证。

### 🧭 长时间实时测试避免 overflow：不要 dump，走 monitor 或内存打印

**背景**：当前测试版为了排查方便会写采样文件、acquisition dump、observables dump。L5 `10 Msps` 长时间运行时，磁盘 I/O 是 overflow 的重要诱因；用户需要后续持续打印当前伪距和载噪比，不需要大量中间结果文件。

**读码确认**

- `serdes_gnss_synchro.h` protobuf 已包含 `signal_path`、`cn0_db_hz`、`pseudorange_m`、`prn`、`channel_id`。
- `gnss_flowgraph.cc` 已支持把 observables 输出接到 `Monitor`。
- 因此不必为了实时显示再写 `.dat/.mat`。

**方案**

- 优先方案：开启 `Monitor.enable_monitor=true`，关闭所有 dump，写一个轻量 UDP protobuf 接收脚本，按 PRN 聚合 path0/path1 后持续打印 `primary/second` 伪距、C/N0 和 `delta_m`。
- 备用方案：如果 Python protobuf 接收部署麻烦，就在 `hybrid_observables_gs` 内加低频 stdout/CSV 打印，不经磁盘中间文件。

**结论**

- 后续实时测试不要依赖 `Observables.dump=true`。
- dump 只保留给短时离线诊断和画谱峰图。

### 🧭 Stage 2 第三步：输出格式稳定化为 CSV/JSONL

**背景**：表格输出适合人工看，但后续要持续测试、统计伪距差、接入实时打印或上层分析，需要稳定字段名和机器可读格式。

**实现**

- `read_observables_dump.py` 新增 `--format-out table|csv|jsonl`，默认仍是原来的人工表格。
- 新增 `--out` 指定输出文件；不指定时输出到 stdout。
- CSV/JSONL 固定字段：
  `epoch, channel, system, signal, prn, signal_path, role, rx_time_s, tow_s, pseudorange_m, doppler_hz, carrier_cycles, cn0_db_hz, valid`。
- 兼容旧 7 列 dump 和新 9 列 extended dump；旧 dump 没有 C/N0，CSV 为空，JSONL 为 `null`。

**自测**

- 构造 2 通道 extended dump，验证 table/csv/jsonl 都能输出 `primary/second`。
- 构造 legacy dump，验证 auto 格式不会误判成 extended，且 JSONL 不因 `NaN` 失败。

### 🧭 Stage 2 第二步：多颗卫星通用化采用“显式 PRN 列表生成配置”

**背景**：固定 `l5_dualpath_prn18.conf` 只能验证一颗卫星两条径。测试阶段需要扩展到两颗、三颗或更多 PRN，并保持每颗 PRN 的主峰/第二峰通道成对可读。

**决策**

- 新增 `dev_notes/sim/make_l5_dualpath_conf.py`，输入 `--prns 18,20,21` 后生成 `2*N` 个通道。
- 每颗 PRN 固定成对分配：偶数通道 `Signal_Path=0`，奇数通道 `Signal_Path=1`。
- 保留 `Channels_L5.signal_paths=2`，让底层 `Signal_Path==1` 继续走第二峰交给 tracking 的已有逻辑。
- 测试阶段不用“完全自动扫 PRN 池”作为主路径，因为自动扫会从 PRN 列表头开始，现场单星/少星测试时不够可控。

**自测**

- 用脚本生成 PRN18/20/21 的 6 通道配置，确认 `Channels_L5.count=6`，且每颗 PRN 都有 path0/path1。
- 后续服务器实测时，读取 observables dump 需要 `--channels` 等于生成配置里的通道数。

### 🧭 Stage 2 第一步：先做 L5 最小双跟踪原型，不立即重写 Channel

**背景**：第一阶段测试已经验证 L5 更适合做远距多径捕获分离。下一阶段目标是让接收机同时跟踪最强峰和第二峰，并输出两条径的伪距、载噪比等信息。

**读码确认**

- `Gnss_Synchro::Signal_Path` 已存在，`0` 表示最强峰，`1` 表示第二峰。
- `pcps_acquisition.cc` 已有逻辑：当 `Signal_Path==1` 或 `acquire_second_path=true` 时，捕获层会搜索第二峰，并把第二峰的码相位/多普勒交给 tracking。
- `rtklib_pvt_gs.cc` 已过滤 `Signal_Path==0`，第二径不会直接进入 PVT。
- 原 observables dump 实际只写 7 个 double，没有 `Signal_Path` 和 `CN0_dB_hz`，因此无法直接从 dump 标明主峰/第二峰并查看载噪比。

**决策**

- 第一版不重写 `Channel` 拓扑，不做“一个 Channel 内挂两个 tracking block”的大改。
- 先用两个固定通道跟同一颗 L5 PRN：`Channel0.signal_path=0`、`Channel1.signal_path=1`。
- 新增 `Observables.dump_extended=true`，只在开启时把 dump 扩展为 9 列，追加 `Signal_Path` 和 `CN0_dB_hz`；默认关闭，保持旧 dump 兼容。
- 新增 `dev_notes/sim/l5_dualpath_prn18.conf` 作为 Stage 2 最小双跟踪验证配置。
- 更新 `read_observables_dump.py`，用 `primary/second` 标签和 `--pairs` 输出 `second-primary` 伪距差。

**边界**

- 当前是固定 PRN18 的文件源原型，目标是先验证两条 tracking 链路能持续输出。
- 尚未升级到所有可见卫星自动每星两径输出。
- 第二径仍只用于分析，不参与 PVT 校正。

### 🧭 `--expected-delay-m` 只作画图提示，伪距差必须客观统计

**背景**：用户指出 `--expected-delay-m 700` 会筛选接近已知答案的结果，不能作为真实伪距差测量依据。

**决策**

- `--expected-delay-m` 只保留为 plot hint：方便已知模拟器设置时快速找到接近预期的候选图。
- 正式伪距差不使用 expected 参数，而是从所有 `positive_acq=1 && has_second_peak=1` 的有效 dump 中计算 `abs(Δm)`。
- `run_b210_offline_multipath_test.sh` 新增客观汇总：
  - `/tmp/<tag>_summary.tsv`
  - `/tmp/<tag>_summary.log`
- 结论优先看 `objective_abs_delta_m_median/mean/std`；若有效 dump 数量太少，应继续采样或提升链路稳定性。

### 🕳️ GPS L5 PRN18 2000m 测试误差大：第二峰搜索窗不足

**现象**：用户将模拟器补偿改为 `+2000m`，运行：

```bash
bash dev_notes/sim/run_b210_offline_multipath_test.sh \
  --signal l5 --prn 18 --tag gps_l5_prn18_twosim_2000m_30s \
  --secs 30 --chunk-secs 10 --gain 76 --ant RX2 --device-args serial=30F4100
```

**结果摘要**

- 分成 3 段 10 秒录样；每段录样只有 1 次 overflow，不是主要问题。
- 三段 best dump 都 `positive_acq=1`，主捕获通过。
- 但三段 best dump 都 `has_second_peak=0`，第二峰未通过多径判定。
- 总 best 给出 `Δ≈-59.3 chips ≈ -1739m`，距离目标 `2000m` 偏差约 `261m`。

**原因**

- L5 1 chip 约 `29.3m`，`2000m` 约 `68.2 chips`。
- 当时 `Acquisition_L5.multipath_max_delay_chips=60`，只覆盖约 `1758m`。
- 目标第二峰超出了搜索窗，算法只能在窗边或其他峰上找到候选，因此出现 `positive_acq=1` 但 `has_second_peak=0`，此时 `Δm` 不能当有效 2000m 检出。

**修复**

- 将 `dev_notes/sim/l5_offline_prn1.conf` 的 `Acquisition_L5.multipath_max_delay_chips` 从 `60` 改为 `90`，覆盖到约 `2637m`。
- `run_b210_offline_multipath_test.sh` 增加 `--max-delay-chips`，可在命令行临时覆盖搜索窗。
- 建议 2000m 测试命令增加：
  `--expected-delay-m 2000 --max-delay-chips 90`

### 🕳️ L5 100s 连续录样大量 overflow：改为脚本自动分段录制

**现象**：用户将测试脚本里的录制时长手工改为 `100s` 后，L5 录样出现大量 USRP overflow。

**证据**

- 100 秒 L5 配置为 `10 Msps × complex64`，录样量为 `1,000,000,000` samples，单文件约 `7.5GB`。
- `/tmp/gps_l5_prn18_twosim_1000m_record.log` 中出现约 `135` 行 `overflows occurred`。
- 日志末尾多次出现每 `0.75s` 左右 `20~39` 次 overflow，属于持续性丢样，不是开头偶发一次。
- 当时服务器负载曾到 `load average: 4.45, 17.58, 10.42`，SSH 一度 banner exchange 超时，说明系统处在明显 IO/调度压力下。

**判断**

- 这不是模拟器信号或捕获算法问题，而是长时间大文件连续写盘导致 GNU Radio/USRP 缓冲不能持续消费。
- L5 `10 Msps` 下写盘速率约 `80 MB/s`，100 秒连续落盘会形成约 `8GB` 单文件；磁盘 flush 或系统调度抖动会直接反映为 USRP overflow。

**修复**

- 修改 `dev_notes/sim/run_b210_offline_multipath_test.sh`：新增 `--chunk-secs`，默认 `30`。
- 当 `--secs` 大于 `--chunk-secs` 时自动切段，例如 `--secs 100` 变成 `30+30+30+10`。
- 每段按“录样 -> `sync` 落盘 -> 离线跑 GNSS-SDR -> 分析 `.mat` -> 画图”的顺序执行，避免前一段大文件后台写回叠到下一段 B210 采样期间；脚本最后从所有片段的 best dump 中再挑总 best。
- `06 §1A` 增加可复制的 `--secs 100` 用法，并明确不要手工 `sed` 改脚本。
- `record_b210.py` 增加 UHD 打开重试，避免 B210 刚释放/USB 短暂重枚举时直接因 `No devices found` 失败；测试脚本增加 `--device-args serial=30F4100` 透传，当前测试机可固定到这台 B210。

### 🕳️ GPS L5 PRN18 `max_dwells=10` 配置固化后复测：当前现场未过主捕获门限

**背景**：根据上一轮 PRN18 手工临时配置成功结果，将 `dev_notes/sim/l5_offline_prn1.conf` 中 `Acquisition_L5.max_dwells` 从 `2` 改为 `10`，提交到 Git 后由服务器从 `origin/feature/multipath` 精确检出配置再测试。

**配置确认**

- `Channel0.satellite=18`
- `Acquisition_L5.pfa=0.001`
- `Acquisition_L5.max_dwells=10`

**复测结果**

| 录样 | overflow | 录样幅度 | dump数 | positive | 最高 test/threshold | 1000m 附近候选 |
|------|----------|----------|--------|----------|---------------------|----------------|
| `/tmp/gps_l5_prn18_twosim_1000m_dwell10_r2.dat` | 1 次 | `rms≈0.01994`, `max_abs≈0.087` | 193 | 0 | `86.39 / 116.00` | 44 个 has2 候选在 `800-1200m` |
| `/tmp/gps_l5_prn18_twosim_1000m_dwell10_r3.dat` | 1 次 | `rms≈0.02002`, `max_abs≈0.181` | 194 | 0 | `107.46 / 116.00` | 55 个 has2 候选在 `800-1200m` |

**判断**

- 配置已经正确变为 `max_dwells=10`，但当前两次新录样均 `positive_acq=0`，不能判定为正式捕获成功。
- r3 中存在多个接近目标补偿的候选，例如 `989m`、`1019m`，说明 1000m 量级的第二峰结构仍在谱面里出现；但主捕获统计量没有过门限，所以这些只能作为调参线索，不能作为有效多径检出结果。
- 与上一轮同为 PRN18、`max_dwells=10` 但 `test=120.94 > threshold=116.00` 的成功结果相比，本轮当前现场链路强度/稳定性变差；优先检查模拟器是否仍保持两路 L5 PRN18、两路 `-40 dBm`、补偿 `+1000m`，以及 B210 录制时的 overflow。
- 如果要继续提高通过率，可先尝试短期诊断参数 `pfa=0.01` 或提高接收/发射链路稳定性；正式结论仍以 `pfa=0.001` 过门限为准。

### ✅ GPS L5 PRN18 双模拟器 1000m 测试：`max_dwells=10` 检出目标第二峰

**背景**：PRN20 多次未过主捕获门限后，用户将模拟器和测试配置改为 `PRN18`，现场条件保持为两台模拟器同时发射，一路 0m，一路 `+1000m` 补偿；两路单星功率 64，发射功率均 `-40 dBm`。

**录样条件**

- GPS L5I PRN18，中心频率 `1176.45 MHz`。
- B210 RX2，`gain=76 dB`，`rate=10 Msps`，录样 10 秒。
- 录样文件：`/tmp/gps_l5_prn18_twosim_1000m.dat`。
- 录制日志无 USRP overflow。
- 录样幅度：`rms≈0.02002`，`max_abs≈0.0855`，无削顶。

**离线捕获结果**

| 配置 | dump数 | positive | positive+has2 | test | threshold | 第二峰距离 | 结论 |
|------|--------|----------|---------------|------|-----------|------------|------|
| `pfa=0.001, max_dwells=2` | 43 | 1 | 1 | 61.08 | 56.27 | `abs(Δ)≈300m` | 能捕获 PRN18，但第二峰不是目标 1000m |
| `pfa=0.001, max_dwells=10` | 1 | 1 | 1 | 120.94 | 116.00 | `abs(Δ)≈1019m` | 检出与 `+1000m` 补偿匹配的第二峰 |

**判断**

- PRN18 L5 链路已能被 GNSS-SDR 捕获，说明前面 PRN20 失败不应再简单归因于脚本或 B210 录制流程。
- `max_dwells=2` 虽然过了主捕获门限，但第二峰落在约 `300m`，不稳定；`max_dwells=10` 后第二峰为 `-34.8 chips ≈ -1019m`，与模拟器 `+1000m` 补偿量级一致。
- `Δ` 为负表示当前峰强度排序下，第二峰相对主峰在码相位上的方向；判断补偿距离时看 `abs(Δ)`。
- L5 的 10 Msps 下每码片约 `29.3m`，`1000m` 约 `34.1 chips`，本次 `34.8 chips` 属于合理范围。
- 图已保存：
  - `dev_notes/sim/gps_l5_prn18_twosim_1000m_dwell10.png`
  - `dev_notes/sim/gps_l5_prn18_twosim_1000m_dwell10_3d.png`
- 后续若继续做 L5 双径测试，建议将诊断配置优先使用 `Acquisition_L5.max_dwells=10`，再根据耗时和稳定性回调到更小值。

### 🕳️ GPS L5 PRN20 双模拟器 1000m 测试：未通过主捕获门限

**背景**：用户将 L5 测试配置改为 `PRN20` 并提交 Git，现场两路信号均为单星功率 64、发射功率 `-40 dBm`；一路无补偿，一路 `+1000m` 补偿。按要求通过 SSH 登录测试机测试，不直接在服务器编辑源码。

**远端同步方式**

- 远端仓库存在大量 `build/` 和历史输出文件脏状态，不能直接清理。
- 使用 `git fetch origin feature/multipath` 获取 GitHub 最新内容。
- 只从 `origin/feature/multipath` 精确检出测试相关文件，避免碰服务器脏工作区：
  - `dev_notes/sim/l5_offline_prn1.conf`
  - `dev_notes/06_b210_multipath_test_usage.md`
  - `dev_notes/sim/record_b210.py`
  - `dev_notes/sim/analyze_multipath.py`
  - `dev_notes/sim/plot_acq_grid.py`
  - `dev_notes/sim/plot_acq_3d.py`

**测试条件**

- GPS L5I PRN20，两台模拟器同时发射：一路 0m，一路 `+1000m`。
- 两路单星功率 64，发射功率均 `-40 dBm`。
- B210 RX2，`gain=76 dB`，`freq=1176.45 MHz`，`rate=10 Msps`。
- 录样文件：`/tmp/gps_l5_prn20_twosim_1000m.dat`，10 秒，`100000000` complex64 samples，800 MB。
- 录制过程中出现数次 USRP overflow。
- 录样幅度：`rms≈0.0204`，`max_abs≈0.094`，无削顶。

**离线捕获结果**

| 配置 | dump数 | positive | positive+has2 | 最高 test | threshold | 结论 |
|------|--------|----------|---------------|-----------|-----------|------|
| `pfa=0.001, max_dwells=2` | 226 | 0 | 0 | 46.60 | 56.27 | 未捕获 |
| `pfa=0.01, max_dwells=2` | 215 | 0 | 0 | 42.3 | 51.1 | 放宽门限仍未捕获 |
| `pfa=0.001, max_dwells=10` | 186 | 0 | 0 | 79.1 | 116.0 | 非相干积分增强后仍未过门限 |

**判断**

- 这次不能判定为 L5 PRN20 多径捕获成功。虽然部分 dump 的相对峰给出 `Δ≈1000m` 附近的数字，但所有 dump 都 `positive_acq=0`，这些第二峰不能作为有效多径证据。
- 主要问题优先怀疑 L5 链路强度/配置，而不是第二峰算法：
  - L5 录样整体电平偏弱；
  - 10 Msps 录制有 overflow；
  - 需要确认模拟器确实发 GPS L5I PRN20，而不是 L5Q/其他 PRN/其他频点；
  - 需要确认当前接收天线在 1176.45 MHz L5 频段有效。
- 下一步建议先单独打开每台 L5 模拟器分别测试 PRN20 是否 `positive=1`；单路过捕获后，再做双源 1000m。

**补充复测（用户重新录样，2026-07-17）**

- 用户重新执行：
  `record_b210.py --secs 10 --gain 76 --ant RX2 --freq 1176450000 --rate 10000000 -o /tmp/gps_l5_prn20_twosim_1000m.dat`
- 这次录制日志中没有看到 USRP overflow。
- 录样幅度：`rms≈0.02005`，`max_abs≈0.0965`，无削顶。
- 正式 `pfa=0.001, max_dwells=2`：
  - `dump_count=225`
  - `positive=0`
  - `positive_has2=0`
  - 最高 `test=43.21 < threshold=56.27`
- 诊断 `pfa=0.01`：
  - `positive=0`
  - 最高 `test=47.17 < threshold=51.10`
- 判断：重录后排除了 overflow 干扰，但 PRN20 L5 仍未过主捕获门限；问题更像是 L5 信号强度/PRN/信号分量/天线频段配置，而不是录制溢出。

**补充复测 r2（模拟器确认改为 L5 后再次录样，2026-07-17）**

- 用户确认前两次模拟器误配成 L1，已改为 L5；要求再测一次。
- 录样：`/tmp/gps_l5_prn20_twosim_1000m_l5fix_r2.dat`，10 秒，10 Msps，B210 RX2，`gain=76`。
- 录制日志无 overflow。
- 录样幅度：`rms≈0.01995`，`max_abs≈0.0858`，无削顶。
- 正式 `pfa=0.001, max_dwells=2`：
  - `dump_count=229`
  - `positive=0`
  - `positive_has2=0`
  - 最高 `test=43.86 < threshold=56.27`
- 诊断 `pfa=0.01`：
  - `positive=0`
  - 最高 `test=45.02 < threshold=51.10`
- 判断：模拟器改为 L5 后仍未过 PRN20 主捕获门限。当前证据仍指向 L5 链路过弱、天线/频段匹配不足，或模拟器实际发射分量/PRN与 GNSS-SDR 的 GPS L5I 配置不完全一致；不能把任何第二峰候选当作有效 1000m 多径。

### 🧭 运行手册改名，并记录 PRN/多卫星操作方法

**背景**：用户开始准备 GPS L5 多径捕获分离测试，指出原文件名 `06_b1c_b210_two_path_usage.md` 已不适合，因为现在不只是 B1C/B1I 测试。

**操作**

- 将 `dev_notes/06_b1c_b210_two_path_usage.md` 重命名为 `dev_notes/06_b210_multipath_test_usage.md`。
- 更新 `dev_notes/README.md` 的文档地图，明确 06 是 B210 多径测试总手册，覆盖 B1I/L5I 的录制、离线分析、画图、调参、排错。
- 在 06 中新增 `2E. 如何指定 PRN，以及如何锁多颗卫星`：
  - 单颗卫星改 `Channel0.satellite=<PRN>`。
  - 多颗卫星改 `Channels_<signal>.count=N`，并写 `Channel0.satellite`、`Channel1.satellite` 等。
  - 离线捕获分析用通配符匹配多份 `.mat`。
  - 每颗卫星两条径持续跟踪时，通道数要按 `卫星数 × 2` 配，并需要对应信号支持 `signal_paths=2`。

**判断**

- L5 目前新增的是离线捕获谱验证配置，适合做 `positive/has2/Δm` 判断和 2D/3D 谱峰图。
- L5 若要像 B1I 一样“每颗卫星两条径持续跟踪”，后续还要补 L5 的双路径实时/跟踪配置并实测 flowgraph。

## 2026-07-16

### ✅ 1000m 双源等功率复测：检出远距第二峰，量化到约 1049m

**背景**：用户将补偿改为 `+1000m`，两路功率均为 `-40 dBm`，要求再测一次；并询问若与 `+1030m` 一样都接近 970m，应分析原因。

**测试条件**

- BDS B1I PRN9，双模拟器同时发射：一路 0m，一路 `+1000m`。
- 两路发射功率均为 `-40 dBm`。
- B210 RX2，无源接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 离线配置固定 `Acquisition_B1.pfa=0.001`。
- 采样文件：`/tmp/b1i_twosim_1000m_equal_power_r5.dat`。

**结果**

| positive | test_stat | threshold | has2 | Δchips | Δm | ratio |
|----------|-----------|-----------|------|--------|----|-------|
| 1 | 113.04 | 54.22 | 1 | -7.2 | -1049 m | 1.8 dB |

**判断**

- 主捕获和第二峰判定均通过，捕获域检出远距双峰。
- `+1000m` 理论约 `6.82 chips`；实测 `abs(Δ)=7.2 chips ≈ 1049m`，量级匹配。
- 这次没有和 `+1030m` 一起落在 `970m`，而是落到相邻的量化/插值台阶。当前算法的第二峰位置来自 acquisition dump 的采样点峰值，4 Msps 下 B1I 每 chip 约 `1.955 samples`，整数采样点差会造成约 `0.51 chip ≈ 75m` 的台阶；再叠加等功率双峰干涉、噪声和二次峰插值不足，`970m` 与 `1050m` 这种几十米级跳动是合理的。
- 图已保存到 `dev_notes/sim/bds_b1i_twosim_1000m_equal_power_r5_pfa001_3d.png`。

### ✅ 1030m 双源等功率复测：捕获域稳定检出远距第二峰

**背景**：用户将补偿改回 `+1030m`，两路功率均为 `-40 dBm`，要求再做一次测试。

**测试条件**

- BDS B1I PRN9，双模拟器同时发射：一路 0m，一路 `+1030m`。
- 两路发射功率均为 `-40 dBm`。
- B210 RX2，无源接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 离线配置固定 `Acquisition_B1.pfa=0.001`。
- 采样文件：`/tmp/b1i_twosim_1030m_equal_power_r4.dat`。

**结果**

| positive | test_stat | threshold | has2 | Δchips | Δm | ratio |
|----------|-----------|-----------|------|--------|----|-------|
| 1 | 80.79 | 54.22 | 1 | -6.6 | -974 m | 4.9 dB |

**判断**

- 主捕获和第二峰判定均通过，捕获域检出远距双峰。
- `+1030m` 对 B1I 约 `7.0 chips`；实测 `abs(Δ)=6.6 chips ≈ 974m`，量级匹配。
- `Δ` 为负仍是等功率双源下主/次峰按强度排序造成的翻转；看距离差时应取 `abs(Δ)`。
- 图已保存到 `dev_notes/sim/bds_b1i_twosim_1030m_equal_power_r4_pfa001_3d.png`。

### ✅ 200m 双源等功率测试：捕获域检出第二峰

**背景**：上一轮 `+200m` 补偿路发射功率为 `-50 dBm` 时未检出第二峰；用户将补偿一路调回 `-40 dBm`，要求再测一次。

**测试条件**

- BDS B1I PRN9，双模拟器同时发射：一路 0m，一路 `+200m`。
- 补偿一路发射功率调回 `-40 dBm`；现场按等功率双源处理。
- B210 RX2，无源接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 离线配置固定 `Acquisition_B1.pfa=0.001`。
- 采样文件：`/tmp/b1i_twosim_200m_equal_power.dat`。

**结果**

| positive | test_stat | threshold | has2 | Δchips | Δm | ratio |
|----------|-----------|-----------|------|--------|----|-------|
| 1 | 102.45 | 54.22 | 1 | 1.5 | 225 m | 3.8 dB |

**判断**

- 主捕获通过且第二峰通过判定，当前捕获域能检出接近 `200m` 的双峰。
- `200m` 对 B1I 约 `1.36 chips`；实测 `1.5 chips ≈ 225m`，量级匹配。
- 与上一轮 `+200m/-50 dBm` 对比，第二径功率降低约 10 dB 时未过判定；等功率时能检出，说明此距离已接近捕获域可分辨边界，功率比对结果影响很大。
- 图已保存到 `dev_notes/sim/bds_b1i_twosim_200m_equal_power_pfa001_3d.png`。

### 🧭 200m 双源测试：主捕获强，但捕获域第二峰未过判定

**背景**：用户把补偿改为 `+200m`，发射功率设为 `-50 dBm`，要求再测一次。

**测试条件**

- BDS B1I PRN9，双模拟器同时发射：一路 0m，一路 `+200m`。
- 用户说明发射功率为 `-50 dBm`；若只改了补偿模拟器，则未补偿一路沿用现场当前设置。
- B210 RX2，无源接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 离线配置固定 `Acquisition_B1.pfa=0.001`。
- 采样文件：`/tmp/b1i_twosim_200m_passive_ant.dat`。

**结果**

| positive | test_stat | threshold | has2 | Δchips | Δm | ratio |
|----------|-----------|-----------|------|--------|----|-------|
| 1 | 113.74 | 54.22 | 0 | -7.2 | -1049 m | 11.8 dB |

**判断**

- 主捕获很强，`positive_acq=1` 且余量明显。
- `has2=0`，所以捕获域没有有效检出第二径；表里的 `-1049m` 是未通过第二峰判定的相对峰，不能当作 `200m` 多径结果。
- `200m` 对 B1I 约 `1.36 chips`，刚过当前捕获域可分边界，但补偿路若比主路低 `10 dB`，第二峰会很容易低于多径判定门限。
- 若要在捕获域继续验证 `200m`，建议把补偿路功率提高到接近主路，或临时降低 `multipath_threshold_fraction` 做灵敏度扫描；正式近距多径仍应进入跟踪域方案。
- 图已保存到 `dev_notes/sim/bds_b1i_twosim_200m_passive_ant_pfa001_3d.png`。

### 🧭 70m 近距双源测试：主捕获通过，捕获域未检出第二峰

**背景**：用户把补偿改为 `+70m`；未补偿模拟器发射功率保持 `-40 dBm`，加补偿模拟器发射功率改为 `-50 dBm`，要求再测一次。

**测试条件**

- BDS B1I PRN9，双模拟器同时发射：一路 0m，一路 `+70m`。
- 0m 模拟器发射功率 `-40 dBm`，`+70m` 模拟器发射功率 `-50 dBm`。
- B210 RX2，无源接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 离线配置固定 `Acquisition_B1.pfa=0.001`。
- 采样文件：`/tmp/b1i_twosim_70m_passive_ant.dat`。

**结果**

| positive | test_stat | threshold | has2 | Δchips | Δm | ratio |
|----------|-----------|-----------|------|--------|----|-------|
| 1 | 73.78 | 54.22 | 0 | -1.5 | -225 m | 10.8 dB |

**判断**

- 主捕获通过，说明当前链路仍能收到 PRN9。
- `+70m` 对 B1I 约等于 `0.48 chip`，小于当前捕获域第二峰算法的 `±1 chip` 主峰排除区，理论上就不适合用 PCPS 捕获谱分成两个独立峰。
- `has2=0` 符合预期；脚本显示的 `-225m` 只是未通过第二峰判定的相对峰，不能作为真实 70m 多径证据。
- 70m 这类近距多径应进入跟踪域多相关器/峰形拟合方案，而不是继续依赖捕获域 Top-2 峰。
- 图已保存到 `dev_notes/sim/bds_b1i_twosim_70m_passive_ant_pfa001_3d.png`。

### 🕳️ 换无源天线后 0m + 1030m 双模拟器测试：主捕获通过，但 1030m 第二径未稳定出现

**背景**：用户更换一根无源天线，两台模拟器同功率发射；一台无补偿，一台 `+1030m` 补偿，发射功率 `-40 dBm`。

**测试条件**

- BDS B1I PRN9，双模拟器同时发射：一路 0m，一路 `+1030m`。
- B210 RX2，无源接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 离线配置固定 `Acquisition_B1.pfa=0.001`。
- 采样文件：
  - r1: `/tmp/b1i_twosim_1030m_passive_ant.dat`
  - r2: `/tmp/b1i_twosim_1030m_passive_ant_r2.dat`

**结果**

| 轮次 | positive | test_stat | threshold | has2 | Δchips | Δm | ratio | 备注 |
|------|----------|-----------|-----------|------|--------|----|-------|------|
| r1 | 1 | 103.01 | 54.22 | 1 | 3.6 | 525 m | 8.4 dB | 主捕获有效，但第二峰不是预期 `1030m` |
| r2 | 1 | 93.66 | 54.22 | 0 | - | - | 14.6 dB | 主捕获有效，第二峰未过多径判定 |
| r3 | 1 | 79.84 | 54.22 | 1 | -6.6 | -974 m | 0.2 dB | 两峰几乎等强；距离量级接近 `1030m`，但主/次排序反了 |

**判断**

- 换无源天线后，主捕获质量明显恢复：两轮 `positive_acq=1`，说明 B210/RX2/PRN9 基本链路是通的。
- `+1030m` 第二径仍不算稳定：r1 找到约 `525m` 的相对峰，r2 则 `has2=0`，r3 找到约 `974m` 的双峰且两峰几乎等强。
- r3 的 `Δ` 为负，是因为捕获算法按强度选主峰；两峰等强时，补偿/未补偿哪条被选为主峰会翻转。判断距离时应看 `abs(Δ)`。
- 当前可以说 r3 复现了接近 `1030m` 的双峰，但还需要连续重复统计稳定性。下一步更适合单独打开两台模拟器分别复测，确认 `0m` 和 `+1030m` 两路单独发射时的码相位差，再重新双源。
- r1/r3 的图分别保存到 `dev_notes/sim/bds_b1i_twosim_1030m_passive_ant_pfa001_3d.png` 和 `dev_notes/sim/bds_b1i_twosim_1030m_passive_ant_r3_pfa001_3d.png`。

### 🕳️ 双模拟器 0m + 1030m 同功率测试未通过严格捕获

**背景**：用户把两台模拟器设为同功率，一台无补偿，一台 `+1030m` 补偿，要求开始多径捕获识别测试。

**测试条件**

- 两台模拟器同时发 BDS B1I PRN9：一路 0m，一路 `+1030m`。
- B210 RX2，新 USRP 接收天线，`gain=76 dB`，`freq=1561.098 MHz`，`rate=4 Msps`。
- 使用 conda 版 GNSS-SDR：`./build-conda/src/main/gnss-sdr`。
- 离线配置临时文件固定 `Acquisition_B1.pfa=0.001`，输入为 `/tmp/b1i_twosim_1030m.dat` / `/tmp/b1i_twosim_1030m_r2.dat`。

**结果**

| 轮次 | pfa | positive | test_stat | threshold | has2 | Δchips | Δm | 备注 |
|------|-----|----------|-----------|-----------|------|--------|----|------|
| r1 | 0.001 | 0 | 29.07 | 54.22 | 1 | -3.6 | -525 m | 未过捕获门限，第二峰不可作为有效 1030m 证据 |
| r2 | 0.001 | 0 | 43.44 | 54.22 | 1 | -8.7 | -1274 m | 重复采集仍未过门限，第二峰位置不稳定 |
| r2 | 0.01 | 0 | 43.44 | 49.03 | 1 | -8.7 | -1274 m | 放宽门限后仍未通过捕获 |

**判断**

- 当前 `1030m` 同功率测试没有复现 `1000m` 那次的干净双峰；严格判据应以 `positive_acq=1 && has2=1 && Δ≈7.0 chips` 为准，本次不满足。
- `analyze_multipath.py` 会显示 `has2=1`，但如果 `positive_acq=0`，该第二峰只是未通过捕获门限的谱面相对峰，不能当成有效多径识别。
- 下一步应先检查两台模拟器是否仍为 PRN9/B1I、功率/天线链路是否和 `1000m` 成功测试完全一致；必要时单独打开每台模拟器复测 `positive_acq`，再做双源。

### ✅ 双模拟器 0m + 1000m 多径捕获识别成功

**背景**：用户同时打开两台模拟器：一台无补偿，一台 `+1000m` 补偿；要求开始做多径捕获识别测试。

**测试条件**

- OTA 天线收发，新 USRP 接收天线。
- 两台模拟器同时发 BDS B1I PRN9：一路 0m，一路 `+1000m`。
- B1I `1561.098 MHz`，RX2，USRP `gain=76 dB`，4 Msps。
- 录样 10 秒：`/tmp/b1i_twosim_1000m.dat`。
- 录样电平：`rms=0.0380376`，`max_abs=0.159412`，`clip_frac=0`。

**离线捕获结果**

| pfa | threshold | test_stat | positive | has2 | Δchips | Δm | ratio |
|-----|-----------|-----------|----------|------|--------|----|-------|
| 0.001 | 54.22 | 108.19 | 1 | 1 | 6.65 | 974.3 m | 7.8 dB |
| 0.01 | 49.03 | 51.58 | 1 | 0 | 9.72 | 1424.0 m | 6.5 dB |

**关键结论**

- 默认严格门限 `pfa=0.001` 下已经 `positive=1`，并且多径检测 `has2=1`。
- 检出的第二径延迟 `Δ≈6.65 chips ≈ 974 m`，非常接近模拟器设置的 `1000m`。
- 2D/3D 谱峰图已生成：
  - `bds_b1i_acq_C_B1_ch_0_1_sat_9.png`
  - `bds_b1i_acq_C_B1_ch_0_1_sat_9_3d.png`
- 这是目前最关键的成功证据：捕获域第二峰检测能在真实 B210 OTA 双模拟器场景下识别约 1000m 多径。

**注意**

- `pfa=0.01` 那轮虽然 `positive=1`，但 `has2=0`，且统计量/峰值结果不同；多径判据以后优先采用 `pfa=0.001` 这轮结果。
- 两台模拟器的同步方式仍需关注。当前一次测试已能看到目标延迟峰；若要做稳定性/论文图，应重复录多段，统计 Δchips 是否稳定在 6.8 附近。

### ✅ 只开 +1000m 补偿模拟器：单路接收正常，默认门限可捕获

**背景**：用户关闭未补偿模拟器，只打开另一台已加 `+1000m` 补偿的模拟器，要求测试这台模拟器本身接收是否正常。

**测试条件**

- OTA 天线收发，新 USRP 接收天线。
- 只开 `+1000m` 补偿的模拟器；未补偿模拟器关闭。
- B1I `1561.098 MHz`，RX2，USRP `gain=76 dB`，4 Msps。
- 录样 10 秒：`/tmp/b1i_sim2_1000m.dat`。
- 录样电平：`rms=0.0378924`，`max_abs=0.153094`，`clip_frac=0`。

**离线捕获**

| pfa | threshold | test_stat | positive | doppler | delay | has2 |
|-----|-----------|-----------|----------|---------|-------|------|
| 0.001 | 54.22 | 92.41 | 1 | 250 | 2212 | 0 |
| 0.01 | 49.03 | 92.41 | 1 | 250 | 2212 | 0 |
| 0.05 | 45.32 | 92.41 | 1 | 250 | 2212 | 0 |

**实时 45 秒**

- `overflow=0`
- `loss=0`
- `tracking=1`
- `DNAV=2`
- `CN0≈47 dB-Hz`

**判断**

- 这台 `+1000m` 补偿模拟器单独工作正常，B210/GNSS-SDR 默认严格门限 `pfa=0.001` 可稳定捕获并跟踪。
- `has2=0` 是预期：只开这一台时，它只是单一路径整体延迟，不会形成主峰+第二峰。
- 后续要验证双峰，需同时打开未补偿模拟器和 `+1000m` 补偿模拟器，并保证两路时间/频率同步、功率相近。

### 🧪 新接收天线 + 发射天线远 2m：仍可捕获，但裕量下降

**背景**：用户将发射天线拿远约 2m，要求在同等功率下复测。

**测试条件**

- OTA 天线收发，新 USRP 接收天线。
- B1I `1561.098 MHz`，RX2，USRP `gain=76 dB`，4 Msps。
- 录样 10 秒：`/tmp/b1i_ant2_far2m.dat`。
- 录样电平：`rms=0.0455753`，`max_abs=0.196039`，`clip_frac=0`。
- 对比近距离新天线：`rms=0.0482272`，略降；无削顶。

**离线捕获**

| pfa | threshold | best test_stat | positive | doppler | delay | has2 |
|-----|-----------|----------------|----------|---------|-------|------|
| 0.001 | 54.22 | 60.40 | 1 | 0 | 2933 | 0 |
| 0.01 | 49.03 | 53.80 | 1 | 500 | 291 | 0 |
| 0.05 | 45.32 | 48.25 | 1 | 250 | 291 | 0 |

**判断**

- 发射天线远 2m 后，默认严格门限 `pfa=0.001` 仍能 `positive=1`。
- 捕获裕量明显小于近距离新天线（`test≈60` vs `115`），但仍可作为 OTA 单路径基线。
- `has2=0` 符合无补偿单路径预期。
- 下一步加 1000m 第二径时，建议保持这根接收天线，并尽量让第二径功率不要比主径低太多；否则第二峰可能又落到门限附近。

### ✅ 更换 USRP 接收天线后 OTA 单路径通过捕获门限

**背景**：用户在同等模拟器功率条件下，只更换连接 USRP 的接收天线，要求重新测试。

**测试条件**

- OTA 天线收发，同等发射功率。
- B1I `1561.098 MHz`，RX2，USRP `gain=76 dB`，4 Msps。
- 录样 10 秒：`/tmp/b1i_ant2_samepower.dat`。
- 录样电平：`rms=0.0482272`，`max_abs=0.186508`，`clip_frac=0`。
- 对比旧天线 OTA：`rms≈0.0129`，新天线约提升 3.7 倍幅度（约 11.5 dB 功率）。

**离线捕获**

| pfa | threshold | test_stat | positive | doppler | delay | has2 |
|-----|-----------|-----------|----------|---------|-------|------|
| 0.001 | 54.22 | 115.49 | 1 | 1000 | 1741 | 0 |
| 0.01 | 49.03 | 115.49 | 1 | 1000 | 1741 | 0 |
| 0.05 | 45.32 | 115.49 / 273.76 | 1 | 1000 / 0 | 1741 / 3747 | 0 |

**判断**

- 新接收天线让 OTA 单路径稳定过默认严格门限：`pfa=0.001` 下 `positive=1`。
- `has2=0` 符合当前无补偿单路径预期。
- 这证明前面 OTA 失败主要是接收天线/RF 链路问题，不是 GNSS-SDR 捕获算法或模拟器必然不可用。
- 下一步可以在这根天线/同等功率作为基线，加入 `+1000m` 第二径；正式多径验证建议先用 `pfa=0.001` 或 `0.01`，不要用 `0.05`，避免假峰。

### ✅ 馈线直连复测：默认 pfa=0.001 强捕获，单径 has2=0

**背景**：用户将链路切回馈线直连，要求重新测试。

**测试条件**

- B1I `1561.098 MHz`，RX2，USRP `gain=70 dB`，4 Msps。
- 录样 10 秒：`/tmp/b1i_direct_retest.dat`。
- 录样电平：`rms=0.173022`，`max_abs=0.304678`，`clip_frac=0`，电平健康且未削顶。

**离线捕获**

| pfa | threshold | test_stat | positive | doppler | delay | has2 |
|-----|-----------|-----------|----------|---------|-------|------|
| 0.001 | 54.22 | 1832.20 | 1 | 750 | 1090 | 0 |
| 0.01 | 49.03 | 1832.20 | 1 | 750 | 1090 | 0 |
| 0.05 | 45.32 | 1832.20 | 1 | 750 | 1090 | 0 |

**实时 45 秒**

- `overflow=0`
- `tracking=2`
- `loss=1`
- `bit_sync=0`
- `DNAV=0`

**判断**

- 馈线直连下，B210/GNSS-SDR 捕获完全正常；默认严格门限 `pfa=0.001` 就强烈过门限。
- `has2=0` 是预期：直连单径非常干净，没有显著第二峰。
- 与 OTA 天线场景的 `test_stat≈37~45` 相比，直连 `test_stat≈1832`，说明 OTA 问题主要是 RF/天线链路强度不足，不是 GNSS-SDR 捕获算法或 `pfa` 设置问题。
- 实时 45 秒仍出现 1 次 loss/reacquire，但无 overflow；后续若要验证长时间稳定性，应单独延长直连实时测试并看 tracking 环路参数/模拟器时间连续性。

### 🧪 OTA 单星幅度 64 / 发射 -40 dBm 复测：未复现 positive=1

**背景**：用户要求把单星功率幅度设回 64，B1 发射功率保持 `-40 dBm`，再次测试 `positive` 是否为 1。

**测试条件**

- 录样：B1I `1561.098 MHz`，RX2，`gain=76 dB`，4 Msps，10 秒。
- 录样文件：`/tmp/b1i_power_m40_amp64_repeat.dat`。
- 录样电平：`rms=0.0128982`，`max_abs=0.0529443`，`clip_frac=0`。

**pfa 扫描结果**

| pfa | threshold | best test_stat | positive | tracking |
|-----|-----------|----------------|----------|----------|
| 0.001 | 54.22 | 37.28 | 0 | 0 |
| 0.01 | 49.03 | 38.54 | 0 | 0 |
| 0.05 | 45.32 | 39.23 | 0 | 0 |

**判断**

- 这次没有复现上一轮“幅度 64 / -40 dBm / pfa=0.05 下 positive=1”的压线结果。
- 输入 RMS 仍约 `0.0129`，与幅度 70、-40 dBm 几乎一样，说明当前 OTA 到 B210 的接收功率没有明显变化。
- 多次测试的 best test_stat 在 37~45 附近波动，峰位/Doppler 不稳定，说明仍处在噪声/弱信号边缘区；偶发 `positive=1` 不应作为可靠捕获基线。
- 要做稳定单路径/多径验证，仍需要增强 RF 链路，让 `pfa=0.01` 或更严格的 `0.001` 稳定过门限。

### 🧪 OTA 单星幅度 70 / 发射 -40 dBm 复测：未捕获，输入电平几乎未提升

**背景**：用户将单星功率幅度从 64 调到 70，B1 发射功率保持 `-40 dBm`，要求再次测试 `positive` 是否为 1。

**测试条件**

- 录样：B1I `1561.098 MHz`，RX2，`gain=76 dB`，4 Msps，10 秒。
- 录样文件：`/tmp/b1i_power_m40_amp70.dat`。
- 录样电平：`rms=0.0128935`，`max_abs=0.0555601`，`clip_frac=0`。
- 对比上一轮“幅度 64 / 发射 -40 dBm”：`rms=0.0128845`，几乎没有变化。

**pfa 扫描结果**

| pfa | threshold | best test_stat | positive | tracking |
|-----|-----------|----------------|----------|----------|
| 0.001 | 54.22 | 44.75 | 0 | 0 |
| 0.01 | 49.03 | 43.08 | 0 | 0 |
| 0.05 | 45.32 | 43.02 | 0 | 0 |

**判断**

- 这轮没有捕获；即使 `pfa=0.05`，`positive` 仍为 0。
- 与上一轮相比，B210 输入 RMS 几乎不变，说明模拟器界面的“单星功率幅度 64 -> 70”没有明显转化为 B210 接收端功率提升，或者该字段不是当前 RF 输出的主控制量。
- 当前更有效的调参方向应是继续调全局/B1 RF 发射功率、打开/确认 PA、缩短天线距离或改用可控合路器，而不是只调单星功率幅度。

### 🧪 OTA 单星功率 -40 dBm 复测：pfa=0.05 时 positive=1，仍属压线捕获

**背景**：用户将单星功率幅度保持 64，B1 发射功率调到 `-40 dBm`，要求重新测试 `positive` 是否为 1。

**测试条件**

- 测试机：`nano@192.168.112.175`。
- 录样：B1I `1561.098 MHz`，RX2，`gain=76 dB`，4 Msps，10 秒。
- 录样文件：`/tmp/b1i_power_m40.dat`。
- 录样电平：`rms=0.0128845`，`max_abs=0.0549261`，`clip_frac=0`，无削顶。
- 离线 File 源：`/tmp/b1i_prn9.dat`，固定 PRN9。

**pfa 扫描结果**

| pfa | threshold | best test_stat | positive | tracking |
|-----|-----------|----------------|----------|----------|
| 0.001 | 54.22 | 45.75 | 0 | 0 |
| 0.01 | 49.03 | 45.75 | 0 | 0 |
| 0.05 | 45.32 | 45.75 | 1 | 1 |

**判断**

- `-40 dBm` 比上一轮 OTA 明显更接近捕获门限；最佳统计量到了 `45.75`。
- 默认 `pfa=0.001` 和温和诊断档 `pfa=0.01` 仍没有捕获。
- 激进诊断档 `pfa=0.05` 时 `positive=1`，但只比门限高 `0.43`，属于压线捕获；此时 `has2=1` 也不能直接当多径证据，可能是弱信号/低门限下的假第二峰。
- 下一步如果要稳定单路径，优先把发射功率再提高一点，或改善天线链路，让 `pfa=0.01` 甚至 `0.001` 下也能 `positive=1`。

**建议**

- 若只是为了验证“当前能不能勉强捕获”，可临时用 `Acquisition_B1.pfa=0.05`。
- 若要作为多径检测基线，不建议用 `pfa=0.05`；应继续增强 RF 链路，目标是 `pfa=0.01` 下明显过门限。

### 🧪 降低捕获门限试验：pfa 提到 0.1 仍未稳定捕获，主要矛盾仍是 OTA 信号强度

**背景**：用户要求“尝试把捕获门限降低”。代码确认 `Acquisition_B1.pfa > 0` 时，PCPS 捕获门限由 `compute_threshold(pfa, ...)` 计算；增大 `pfa` 会降低门限。

**远端测试**

使用 2026-07-16 OTA 录样 `/tmp/b1i_ant_RX2_76.dat`，固定 PRN9，离线 File 源跑 `b1i_offline_prn9.conf`，只改 `Acquisition_B1.pfa`。

| pfa | threshold | best test_stat | positive |
|-----|-----------|----------------|----------|
| 0.001 | 54.22 | 37.55 | 0 |
| 0.005 | 50.60 | 43.26 | 0 |
| 0.01 | 49.03 | 37.73 | 0 |
| 0.02 | 47.44 | 38.61 | 0 |
| 0.05 | 45.32 | 36.19 | 0 |
| 0.1 | 43.66 | 36.63 | 0 |

**判断**

- 温和降门限（`pfa=0.01`）仍捕不到。
- 即使激进到 `pfa=0.1`，也没有稳定 `positive=1`；不同 dump 的最佳 Doppler/码相位还在乱跳，说明仍像噪声峰，不像稳定 PRN9 相关峰。
- 因此当前 OTA 单路径问题不能靠继续降门限解决；主矛盾仍是 B210 侧有效信号强度/天线链路不足。

**本轮配置调整**

- 将 `dev_notes/sim/b1i_offline_prn9.conf` 的 `Acquisition_B1.pfa` 从 `0.001` 调到 `0.01`，作为 OTA 弱信号诊断档。
- 不建议把默认验证配置长期设到 `0.05/0.1`，假捕获风险太高；若必须临时扫门限，扫完要用 2D/3D 谱峰确认峰是否稳定。

### 🧪 Codex SSH 实测：天线收发、无补偿单路径 PRN9 目前未达到 B210 捕获门限

**背景**：用户将 USRP 改为天线接收、模拟器改为天线发送；手机可以看到 9 号卫星；当前没有 1000m 补偿，功率与直连时一致。要求 Codex 通过 SSH 登录测试机复测单路径是否正常。

**测试机状态**

- SSH：`nano@192.168.112.175`。
- 项目目录：`~/lya/gnss-sdr/gnss-sdr-lya`。
- 运行环境：`conda activate gnsssdr` + `build-conda/src/main/gnss-sdr`。
- 测试前无残留 `gnss-sdr` 进程；B210 可识别，serial `30F4100`。
- Firefox 当时仍占用较高 CPU，测试前已关闭，避免污染实时 SDR。

**录样电平扫描（B1I@1561.098 MHz，4 Msps，2 秒）**

| 端口 | 增益 | RMS | max_abs | clip_frac |
|------|------|-----|---------|-----------|
| RX2 | 70 dB | 0.00669 | 0.0409 | 0 |
| RX2 | 76 dB | 0.01292 | 0.0514 | 0 |
| TX/RX | 70 dB | 0.00669 | 0.0346 | 0 |
| TX/RX | 76 dB | 0.01292 | 0.0534 | 0 |

结论：没有削顶/饱和；但 OTA 信号进 B210 后明显比直连弱很多。RX2 与 TX/RX 两口电平近似，未发现“只因接错口导致完全无信号”的证据。

**实时锁定测试**

- 临时配置：`/tmp/b1i_ant_prn9.conf`，只盯 BDS B1I PRN9，单通道，`gain=70`，`antenna=RX2`，`Acquisition_B1.dump=false`。
- 运行 45 秒结果：`overflow=0`、`loss=0`、`tracking=0`、`bit_sync=0`、`DNAV=0`。
- 解释：这次不是 overflow，也不是失锁；而是没有捕获/跟踪到 PRN9。

**离线捕获验证**

用同一批 OTA 录样走 `b1i_offline_prn9.conf` 生成 acquisition dump：

- RX2 / gain 76：最高 `test_stat=36.31`，`threshold=54.22`，`positive=0`。
- TX/RX / gain 76：最高 `test_stat=39.96`，`threshold=54.22`，`positive=0`。

结论：离线无实时压力也未捕获，说明当前 OTA 单路径信号对 B210/GNSS-SDR 来说仍低于捕获门限。手机能看到 PRN9 不等价于 B210 这一路有足够 C/N0；手机接收机、天线、增益链和算法门限都不同。

**下一步**

1. 先不要上第二台模拟器/1000m 补偿；必须先让 OTA 单路径 PRN9 离线 `positive=1`。
2. 增强单路径链路：提高模拟器输出功率、打开功放/PA、缩短模拟器发射天线到 B210 接收天线距离、换/确认 B1I 频段可用接收天线。
3. 每次改 RF 条件后先录 2~10 秒，检查 `clip_frac=0`，再跑 `b1i_offline_prn9.conf` 看 `test_stat > threshold`。
4. 只有单路径 OTA 能稳定捕获后，再配置第二径 `+1000m`、相对功率差不超过约 6 dB，并继续用离线 dump 验证 `has2=1`。

## 2026-07-15

### ✅ 真相落地：实时"失锁/overflow/无定位"是环境三连，与改造代码无关（Claude via SSH 实测）

**背景**：排查用户长期困扰的"直连馈线仍 loss of track、overflow 没解决、看不到 .mat"。SSH 直连测试机 `nano@192.168.112.175`（NUC7i7BNH，i7-7567U **2核4线程**，Ubuntu18.04，B210 走 USB3）实测定位根因。

**三个真因（按影响排序）**：
1. **12 个挂起的 gnss-sdr 叠罗汉**：用户用 Ctrl+Z（挂起）而非 Ctrl+C（终止）反复起停，累积 12 个 `T`(stopped) 进程（2.5~22.5h），同属一个 bash、无 cron。占着 B210 句柄+内存。→ `pkill -9 -x gnss-sdr` 清空（停止态进程对 SIGTERM 不响应，必须 -9）。
2. **Firefox 吃 ~95% CPU**（`Isolated Web`58%+`firefox`37%，load 2.7/4核）。实时跑必须关。
3. **增益太低→欠量化**：直连+`功放关`+B1I 功率 -40（模拟器注释"单星比设置低 24~25dB"）→ 输入极弱。clipping 实测：gain45 rms=0.0008（~1个ADC格），gain 0→45 几乎不变（=固定量化地板、真射频输入≈0），gain76 才 rms=0.021。**饱和被实测排除（全程 0 削顶）。** 应开到 ~70。

**验证（清空+关扰+gain70，单星PRN9，45s）**：**零失锁、零 overflow**，解出历书/电离层，CN0=82~83dB-Hz（模拟器无噪特征）。随后录 10s@gain70 rms=0.16（健康无削顶）。

**决策/规范**：
- 实时 B1I 用 `SignalSource.gain≈65~70`（此弱信号模拟器）；若开功放/加大模拟器功率，需回调增益防饱和。
- **一次只跑一个实例；停止用 Ctrl+C 不用 Ctrl+Z；跑前关 Firefox。**
- 之前在"12进程+Firefox"脏状态下产的 overflow/失锁日志（`run.log`/`b1i_run.log` 等）**不作数**。
- `run.log` 那次 GPS L1 churn 是裸 `gnss-sdr`(=`/usr/local/bin`，4-26 原版)在脏状态下跑的，不能当"原版也坏"的证据。

**模拟器实况（用户截图）**：只发 **1 颗 BDS PRN9**（B1I），带 PR1/PR2、DPL1/DPL2 两条径参数，接收点北京。→ **单星，数学上无法定位（需≥4星），0字节 PVT/geojson 是预期，不是 bug。**

### ❓ 多径第二径：离线捕获目前只见单峰，需模拟器给"可分辨两径"场景

录10s@gain70 → `b1i_offline_prn9.conf`（File源+acq dump）→ `bds_b1i_acq_C_B1_ch_0_1_sat_9.mat`：
- `check_acq`：positive=1，**test_stat=3095.9 ≫ threshold=54.2** → 真捕获（强、干净）。
- `analyze_multipath`：**has2=0**。主峰 chip=1925.8，最强旁候选 1934.5（Δ8.7chip/1274m）但**比主峰低 27.3dB** → 正确判为旁瓣/噪声，没当第二径。

**判断**：接收端第二峰检测器工作正常（强单峰、无显著多径就如实报 has2=0）。当前模拟器场景**没在 B1I 上给出可分辨且够强的第二径**，可能：①第二径太弱（-27dB）；②两径过近（<1chip/近距多径）→ 捕获本就分不开，属 Stage-2 跟踪域多相关器；③PR1/PR2 的第二分量没真正在 B1I 辐射。

**下一步（用户在模拟器侧配）**：第二径设**可分辨延迟(~1000m≈6.8chip)+ 与直射功率相近(≤~6dB)+ 确认在 B1I 辐射** → 再离线看，应出 has2=1。近距多径(<1chip)留 Stage-2。

### 🧭 直连馈线仍 loss/overflow：噪声不是唯一变量，先排饱和和实时负载

**用户补充**：模拟器馈线已经直接连到 B210 `RX2`，理论上没有空间噪声，载噪比也较强。

**判断**

- 直连馈线能排除天线环境、多径和大部分外界干扰，但不能排除：
  1. **USRP overflow**：这是主机/USB/调度/处理链吞吐问题，和 RF 噪声无关；一旦 overflow，样点被丢，跟踪会失锁。
  2. **前端/ADC 饱和**：直连模拟器如果输出电平偏高，再叠加 `SignalSource.gain=50`，可能让 B210 前端过载；CN0 看起来强，但环路会不稳。
  3. **配置负载仍过高**：即使 RF 很干净，多通道双路径 + observables/PVT 输出仍可能压垮实时处理。
- 日志里仍有 `O/overflow` 和频繁 `Loss of lock`，因此目前不能把问题归因到“噪声太大”。先让单星双路径稳定连续锁定，再谈多星/多径效果。

**本轮配置调整**

- `SignalSource.gain: 50 -> 30`：直连馈线先降增益，避免过载；如果 CN0 明显偏低再逐步加。
- `Channels_B1.count: 4 -> 2`：先只跑 1 颗星两条径，确认无 overflow/loss；稳定后再加回 4/8/12。

**建议观察**

```bash
grep -c "overflows occurred" run.log
grep -c "Loss of lock" run.log
grep "CN0=" run.log | tail -20
python3 dev_notes/sim/read_observables_dump.py bds_b1i_observables.dat --channels 2 --tail 50
```

若 `count=2/gain=30` 仍 loss，继续把 `SignalSource.gain` 试到 `20/10/0` 或加外部衰减器；若 overflow 仍在，则先临时 `Observables.dump=false` 做纯稳定性测试。

### 🕳️ 实时运行没有 acq `.mat` 是预期现象；持续 loss of lock 会导致有效伪距不足

**现象**：用户运行 `my_bds_b1i_twopath.conf` 后目录里有 `bds_b1i_observables.dat`、`bds_b1i_tracking_ch_*.dat/.mat`、PVT/RINEX 文件，但执行：

```bash
python3 dev_notes/sim/analyze_multipath.py --pattern "bds_b1i_acq_*_sat_*.mat" --code-length 2046
```

提示匹配 dump 为 0。终端同时仍有 `usrp_source ... overflows occurred` 和频繁 `Loss of lock`。

**判断**

1. 当前实时配置为了避免 I/O 加重 overflow，设置了 `Acquisition_B1.dump=false`，所以不会生成 `bds_b1i_acq_*.mat`。`analyze_multipath.py` 只读 acquisition dump，因此实时跑后找不到 `.mat` 是预期现象。
2. 若目录里仍有很多 `bds_b1i_tracking_ch_*.mat/.dat` 或 PVT 历史文件，可能是旧配置/旧运行残留；每次测试前建议新建空目录或先清理 `bds_b1i_*`、`GSDR*`、`pvt.dat*`，否则容易把新旧结果混在一起。
3. 持续 `Loss of lock` 会导致 `Flag_valid_word` / `Flag_valid_pseudorange` 不稳定，observables 里即使有伪距字段，也可能多数 epoch 无效；PVT/NMEA 更需要连续锁定和足够卫星，不能只靠短暂 Tracking started。
4. 直连馈线并不等于没有问题：可能仍有 host overflow，也可能因为信号太强导致前端/ADC 饱和。若直连模拟器/馈线，优先降低 `SignalSource.gain` 或加衰减器，并继续压 overflow。

**操作建议**

- 实时看伪距：用 `read_observables_dump.py` 读 `bds_b1i_observables.dat`，不要用 `analyze_multipath.py`。
- 画 2D/3D acquisition 谱峰：走离线文件源配置 `b1i_offline_prn9.conf`，其中 `Acquisition_B1.dump=true`，不会受实时 I/O 约束。
- 若仍频繁 loss of lock：先把实时配置进一步降载，临时 `Observables.dump=false`、`Channels_B1.count=2`；直连时尝试 `SignalSource.gain=20~35`。

### ❓ 伪距不会默认打印到终端：先读 observables dump

**现象**：用户直连馈线到 B210 RX2，运行 `my_bds_b1i_twopath.conf` 后终端能看到：

- `New BEIDOU B1I DNAV Iono message received...`
- `Beidou B1I ... bit synchronization locked...`
- 多个 PRN Tracking started
- 但仍有 `usrp_source ... overflows occurred`、`O`、以及多次 `Loss of lock`

用户疑问：按理直连没有噪声，为什么没看到伪距输出，伪距计算是否需要很久。

**判断**

1. GNSS-SDR 默认终端主要打印捕获/跟踪/电文/PVT 状态，不会把每个通道的 `Pseudorange_m` 当文本持续刷屏。
2. 当前 `Observables.dump=true` 时，伪距写在 `bds_b1i_observables.dat` 二进制文件中。代码里的 Hybrid_Observables dump 每通道每历元写 7 个 double：`RX_time`、`TOW_s`、`Doppler_Hz`、`Carrier_phase_cycles`、`Pseudorange_m`、`PRN`、`valid`。
3. 直连馈线只能减少空间噪声/多径，不会解决 host 处理不过来的 USRP overflow；overflow 是丢样点，仍会导致 loss of lock 和伪距无效。
4. 直连还可能因为信号太强导致前端/ADC 饱和；如果频繁 lock/loss，需降低 `SignalSource.gain` 或加衰减器。
5. 终端看到 iono/bit sync 说明电文链路开始工作，但 PVT/稳定伪距仍依赖连续锁定、有效 TOW/word、足够卫星和无 overflow。日志里仍频繁 loss of lock，因此不能期待马上稳定输出最终定位。

**本轮新增**

- `dev_notes/sim/read_observables_dump.py`：读取 `bds_b1i_observables.dat`，按 epoch/channel 打印有效 `pseudorange_m`。
- `06` 增加查看伪距命令：

```bash
python3 dev_notes/sim/read_observables_dump.py bds_b1i_observables.dat --channels 4 --tail 20
```

### 🕳️ 实时全星双路径仍 overflow：默认运行配置降为保守档

**现象**：用户每次运行：

```bash
./build-conda/src/main/gnss-sdr \
  --config_file=dev_notes/sim/my_bds_b1i_twopath.conf 2>&1 | tee run.log
```

都会出现 USRP overflow。

**判断**：当前已经不是 GNU Radio FFT 损坏问题，而是实时处理负载超过测试机稳定吞吐。原配置虽然关了 acquisition dump，但仍有：

- `Channels_B1.count=12`：双路径下最多 6 颗星，每颗两条径。
- `Channels.in_acquisition=4`：最多 4 路捕获并发跑 PCPS FFT。
- `doppler_step=250` + `max_dwells=2`：捕获计算量较大。
- `Tracking_B1.dump=true`、`PVT.dump=true`、`Monitor.enable_monitor=true`：持续输出叠加 I/O/调度压力。

这些叠在 B210 实时流上，会导致采样消费不及时；一旦 overflow，后续主峰/第二峰/伪距判断都不可信。

**本轮处理：把 `my_bds_b1i_twopath.conf` 改成实时保守档**

- 加 `SignalSource.IF_bandwidth_hz=2000000`，显式设置 B210 RF 带宽。
- `Channels_B1.count: 12 -> 4`，先最多 2 颗星各两条径。
- `Channels.in_acquisition: 4 -> 1`，实时只跑一路捕获。
- `Acquisition_B1.doppler_step: 250 -> 500`，减少 Doppler bins。
- `Acquisition_B1.max_dwells: 2 -> 1`，先保实时吞吐。
- `Tracking_B1.dump: true -> false`，避免连续 tracking dump。
- `PVT.dump: true -> false`，减少 I/O。
- `Monitor.enable_monitor: true -> false`，减少实时旁路负载。
- 暂时保留 `Observables.dump=true`，因为它是当前“两条径伪距输出”的主要证据；如果仍 overflow，再临时关它做纯稳定性测试。

**后续调参顺序**

1. 先用保守档跑 30~60 秒，确认没有 `overflow`。
2. 若仍 overflow：先把 `Observables.dump=false`，再把 `Channels_B1.count=2`。
3. 若不 overflow：逐步恢复 `Channels_B1.count=6/8/12`，每次只改一个旋钮；不要一口气恢复全量。
4. 多径谱峰/3D 图验证继续走“录制干净数据 -> File 源离线 dump”路线，不在实时配置里开 acquisition dump。

### ✅ 补全检查：Claude 新增 3D 捕获谱峰绘图脚本已可用

**背景**：用户让 Claude 根据提示新增 3D 谱峰图脚本；Claude 输出中出现 429，中断风险不明，因此本轮检查脚本是否完整。

**检查结论**

- `dev_notes/sim/plot_acq_3d.py` 文件存在，主流程不是半截：能读 HDF5 `.mat` 的 `acq_grid`，绘制 Doppler × 码相位 × 相关值的 3D 曲面，并保存 PNG。
- 但原版偏“刚写完可跑”，缺少实测保护：glob 无匹配会 `IndexError`，输出默认落当前目录，路径分隔只按 `/`，没有显式标注第二径。

**本轮补全**

1. 增加无匹配文件、缺 `acq_grid`、`acq_grid` 非二维的错误提示。
2. 改用 `pathlib.Path` 生成输出路径，默认保存到输入 `.mat` 同目录，文件名为 `<stem>_3d.png`。
3. 增加 `--max-code-points` 控制码相位方向降采样，避免大矩阵 3D 渲染过慢。
4. 增加 `--elev` / `--azim` 调整视角。
5. 在 3D 图中用红色 `x` 标主峰；如果 dump 里 `has_second_peak=1` 且有 `acq_delay_samples_2`，用白色点标第二径。
6. 输出打印主峰码相位、Doppler、grid shape、samples/chip、has2。

**验证**

- `python -m py_compile dev_notes/sim/plot_acq_3d.py plot_acq_grid.py analyze_multipath.py` 通过。
- 在临时目录构造合成双峰 HDF5：`acq_grid=(41,8000)`，主峰与第二峰相距约 27 samples，`has_second_peak=1`；运行 `plot_acq_3d.py` 成功生成 PNG（约 207 KB），输出主峰 `511.5 chip, 0 Hz`。

**关于用户的 1000m 双径模拟设计**

- 1000m 对 B1I 约为 `1000 / 146.6 ≈ 6.8 chips`，在 4 Msps 下约 `13.6 samples`，大于捕获码相位采样间隔，理论上属于可在捕获相关面分开的远距双峰。
- 两路等功率有利于“看到两个峰”，但会让“哪条是直射”变得不唯一；这是后续 LOS 判别问题，不是谱峰分辨问题。
- 如果 3D 图上连单个尖峰都没有，应优先怀疑录制/限带/overflow/信号源，而不是 1000m 设计本身不可分辨。

### 🧭 Codex 跟进：SDR 已跑通，当前进入测试优化/效果验证阶段

**本轮已读**：`dev_notes/README.md`、`05_pitfalls_and_decisions_log.md`、`06_b1c_b210_two_path_usage.md`、`dev_notes/sim/my_bds_b1i_twopath.conf`、`b1i_sim_prn9.conf`、`record_b210.py`、`check_acq.py`。

**当前进度判断**

- 环境问题已过：系统 GNU Radio 3.7 FFT 坏的问题已通过 conda GR3.10 + `build-conda/` 绕开；B210 实收 B1I 已能 Tracking，阶段从“跑起来”进入“测试优化”。
- 当前效果不理想的首要嫌疑不是 B1I/B1C 代码链路，而是测试数据质量和验证方式：
  1. 实时 USRP 跑复杂捕获/跟踪时容易 overflow，样点一旦丢失，主峰/第二峰都会随机跳，多径判断失真。
  2. 只发单颗 PRN9 做模拟器验证时，其它 PRN 容易出现互相关/噪声假捕获，所以应先固定 PRN9 两通道验证机制，再扩到所有星。
  3. 真实天空干净信号未必有明显第二径，不能用“没有 MULTIPATH 日志”直接判定算法无效；需要模拟器可控延迟径或离线 dump 相关面确认。

**建议优化路线**

1. 先用 `record_b210.py` 录一段干净 B1I 原始采样，确认录制时没有 overflow。
2. 用 File 源离线处理这段数据，离线时再打开 acquisition dump，避免实时 I/O 把采样打坏。
3. 用 `check_acq.py` 看 `positive_acq / test_statistic / threshold`，先区分“真捕获”还是“噪声 argmax”。
4. 再用 `analyze_multipath.py` / `plot_acq_grid.py` / `plot_acq_3d.py` 看第二峰是否在预期延迟附近。
5. 若 PRN9 + 1000m 模拟多径仍检不稳，再调 `multipath_max_delay_chips`、`multipath_threshold_fraction`、`pfa`、通道数和采样率；不要先改 PVT。

**协作注意**

- 当前主线仍是 B1I；B1C CNAV1 不阻塞这个阶段。
- 测试机必须 `conda activate gnsssdr` 且运行 `build-conda/src/main/gnss-sdr`。
- `my_bds_b1i_twopath.conf` 文件头里的旧命令还写 `GLOG_logtostderr=1 ./build/src/main/gnss-sdr`，容易误导；后续应改为 conda + `build-conda` 写法。

## 2026-07-13

## 2026-07-14

### 🕳️ 关键坑：USRP overflow → 样点损坏 → 多径检测/跟踪全是垃圾（模拟器验证时暴露）
- **现象**：B210 实时跑 `b1i_sim_prn9.conf`，满屏 `usrp_source: overflows occurred`；`analyze_multipath` 里**主径 chip 满量程乱跳**（1082→106→35→1584…，正常应平滑缓变）；有多径(1000m)和无多径两组结果**几乎一样**、Δ随机。
- **诊断**：**不是多径逻辑 bug**。overflow 丢样点 → 捕获在损坏数据上做相关 → 主峰都是随机的 → 第二峰自然随机。跟踪也因丢样点锁不住。**"主峰乱跳"是样点损坏的铁证。**
- **两个元凶（配置）**：① `Acquisition_B1.blocking=true`——实时下捕获同步跑、算 FFT 卡住采样消费 → overflow（实时 USRP **必须 `blocking=false`**）；② `Acquisition_B1.dump=true`——每份~7MB、狂重捕一次跑出 2737 份 → 磁盘 I/O 爆 → overflow。
- **已修（本地 `b1i_sim_prn9.conf` 与 `my_bds_b1i_twopath.conf`）**：`blocking=false`、`dump=false`。
- **多径验证正解**：实时开 dump 必溢出 → 改**离线**：先录一小段干净 B210 数据到文件，再用 File 源离线处理（无实时约束，随便 dump，可复现）。待 overflow 治好后做。
- **注意**：只发 PRN9 一颗星出不了 PVT 定位（需≥4星）；要复现"带定位/NMEA"的结果需模拟器多发几颗星或对真实天空多星测。

### 🧭 工作流变更：改本地文件 + GitHub 两边同步（不再直接改服务器）
- 用户要求：**Claude 只改本地 `gnss-sdr-lya` 文件，经 GitHub push/pull 同步到测试机**，不再给"服务器上 sed"命令。
- 影响：后续配置/代码/文档改动都落在本地副本；用户负责 git 同步。给命令时默认"文件已通过 git 同步到服务器"。

### 🧭 设计澄清：两条径进 PVT 的处理 + 与 xinghe 副本对比（回应"关键认知是否违背目标"）
- **用户疑问**：README 的"关键认知"（第二径不进 PVT、走旁路）会不会违背目标"追踪两条径的伪距信息"？
- **结论：不违背。** 目标是"追踪+输出两条径的伪距信息"——两条径都跟踪、都进 observables/dump/monitor **已达成**。
  争议仅在"要不要把两条径都塞进 PVT 解算"：反射径偏长，塞进 RTKLIB 当第二颗星观测会**拉偏定位**，故**只放行 path0**。
- **独立佐证**：平行副本 `../gnss-sdr-xinghe`（另一 AI）的 `rtklib_pvt_gs.cc:2077` 也是 `if (... && Signal_Path == 0U)`，
  注释同为"reflected path retained by Observables/monitors/dumps, but must not be interpreted as an additional satellite by RTKLIB"。**两 AI 收敛同一设计。**
- **两副本捕获层实现不同**（都能检第二径，可互鉴）：
  - `lya`（本副本）：独立 `find_second_peak()` + 邻域窗 `multipath_max_delay_chips` + 门限 `multipath_threshold_fraction` + `has_second_peak`；`Signal_Path==1` 触发。
  - `xinghe`：改 `first_vs_second_peak_statistic` + 可配 `second_peak_exclusion_chips`。
- **⚠️ 重要**：现阶段第二径只"输出/分析"，**尚未用于改善定位**。要真正"提升定位精度"，须下一步用第二径做 **LOS 判别 + 多径校正**（Stage 2/3）。README"下一步"已写三步路线。
- **PRN9 固定配置只是验证用**（`b1i_sim_prn9.conf`）：证明机制正确性；最终形态仍是通用 `signal_paths=2` 搜所有星（待解假捕获 + overflow）。

### ✅✅ 里程碑：conda GNU Radio 3.10 重编成功，B210 实收真实 B1I、多路径链路跑通
**结果**：`build-conda/src/main/gnss-sdr` 编译成功，`ldd` 确认链的是 conda 的 `libgnuradio-fft/runtime .so.3.10.11` + `libvolk.so.3.1`（不再是坏的系统 3.7）。B210 直采，**一大批真实北斗 B1I 卫星正常 Tracking**（PRN 01/02/03/04/06/07/09/11/12/14/17/20/22/25/26/27/28/30/... 二号+三号），**再无 `Can't connect channel 0`**。FFT 坑彻底解决。

**从 FFT 坏到跑通，踩的坑链（都在 conda 重编时）**：
1. **glog 头文件不兼容**：conda 新版 glog(0.7) 要 `GLOG_USE_GLOG_EXPORT`，GNSS-SDR 老式检测没设 → `<glog/logging.h> was not included correctly`。**修**：`-DENABLE_GLOG_AND_GFLAGS=OFF` 改用 Abseil（+`conda install abseil-cpp`）。
2. **系统 GR3.7 模块混入**：ZEROMQ/LimeSDR 解析到 `/usr/lib` 的 GR3.7 库，会和 conda 3.10 冲突。**修**：`-DENABLE_ZMQ=OFF -DENABLE_LIMESDR=OFF -DENABLE_OSMOSDR=OFF`。
3. **缺 pcap.h**：`gr_complex_ip_packet_source`(UDP源)无条件编译要 libpcap。**修**：`-DENABLE_RAW_UDP=OFF`（或 `conda install libpcap`）。
4. **CNAV1 无守卫 glog**：`beidou_cnav1_navigation_message.cc:38` 无守卫 `#include <glog/logging.h>`（GSoC2019 老代码），absl 模式下 `undefined reference to google::LogMessage`。**修**：改成 stock 守卫写法 `#if USE_GLOG_AND_GFLAGS ... #else #include <absl/log/log.h> #endif`。其它 B1C 文件都已带守卫，只此一个。

**完整重编配方 + 运行步骤**：见 `06`（已重写为 conda/B210/B1I 权威运行手册）。

**文档/仓库整理**：`dev_notes/sim/` 只留 `my_bds_b1i_twopath.conf`(主力) + `analyze_multipath.py`；历史配置/脚本移入 `sim/archive/`；删除可再生的 `.mat/.dat` dump（100MB+），加 `.gitignore`。

**遗留/下一步**：
- absl 日志下 `MULTIPATH`(LOG INFO) 可见性待调（真实干净信号本就无多径，等模拟器验证时处理）。
- ❓ 观察：`signal_paths=2` 下所有通道都在 Tracking（含 path=1）；真实无多径时 path=1 是否锁到噪声次峰，待模拟器加多径后核对门限。
- **下一步（用户主导）**：配 B1I 模拟器，给一路加延迟/补偿模拟北斗多径，验证第二径检测+双路径跟踪是否正确。

### 🧭 定案：ffttest 坐实 GNU Radio 3.7.11 FFT 损坏 → conda 隔离装 GR3.10（不动系统）
- **铁证**：`/tmp/ffttest`（独立最小程序，仅 `gr::fft::fft_complex f(4000,true,1)`）输出 `FFT threw: type=St9exception what=std::exception`。
  → 与 GNSS-SDR/B1I/B1C/多径**完全无关**，纯 GNU Radio 3.7.11 FFT 在本机就坏；`rm ~/.gr_fftw_wisdom` 无效（已排除 wisdom）。
- **约束**：测试机有他人重要环境，**不能重装/升级系统**。
- **定案路线**：**conda-forge 在 `$HOME` 装隔离的 GNU Radio 3.10 + UHD + 全依赖，用 conda 的编译器重编 GNSS-SDR**（对话里给了 4 段逐步命令）。
  - 关键：`conda create -n gnsssdr -c conda-forge cxx-compiler gnuradio-core gnuradio-uhd uhd boost-cpp armadillo openblas gflags glog libmatio pugixml libprotobuf protobuf openssl mako ...`
  - 重编：`cmake -S . -B build-conda -DCMAKE_PREFIX_PATH=$CONDA_PREFIX ...`；产物 `build-conda/src/main/gnss-sdr`，`--version` 应显示 GR3.10。
  - UHD：conda 的 `uhd_images_downloader` 下匹配固件，再跑 B210。
- **验证目标**：conda 版跑 `my_bds_b1i_twopath.conf` 不再 `Can't connect channel 0`，能出 `MULTIPATH`/双通道 Tracking。
- **⚠️ 给 Codex/后续 AI**：修复在**运行环境**（conda GR3.10），**不要**改 GNSS-SDR 代码来绕 FFT。系统那份 GR3.7 build 保留但弃用，实测用 `build-conda`。

### 🕳️ FFT 最小复现已确认：不重装系统，优先做隔离修复

**新增证据**：用户在测试机执行 `/tmp/ffttest`，输出：

```text
FFT threw: type=St9exception what=std::exception
```

这说明问题已经脱离 GNSS-SDR 配置、B1I/B1C 改造和 UHD 采集链路，可以用独立 FFT 最小程序复现。当前结论从“Channel0 创建阶段疑似 GNU Radio FFT 异常”升级为“测试机 GNU Radio FFT/FFTW 运行环境确实异常或不兼容”。

**约束**：测试机上还有他人重要环境，不能重装系统，也不应做大范围系统升级。

**处理优先级**

1. 先做无破坏验证：备份/移走 GNU Radio FFTW wisdom 后重跑 `/tmp/ffttest`，排除坏 wisdom。
2. 如果仍失败，优先采用用户目录隔离环境：在 `$HOME` 下用 conda/mamba 或本地 prefix 安装 GNU Radio/FFTW/UHD，再用该环境重新编译 GNSS-SDR。
3. 只有在确认是系统包文件损坏、且用户允许 sudo 的情况下，才考虑 `apt --reinstall` 精确重装 `libgnuradio-fft` / `libfftw3` 相关包；不要做 `dist-upgrade`、不要重装系统。
4. 继续避免改 GNSS-SDR 的 B1I/B1C 逻辑来绕这个问题；当前失败点在 FFT 运行时。

**建议下一步命令（测试机）**

```bash
mkdir -p ~/lya/fft_debug
ldd /tmp/ffttest | egrep 'gnuradio|fftw|volk|boost' | tee ~/lya/fft_debug/ffttest_ldd.txt
dpkg -l | egrep 'gnuradio|libfftw|volk|uhd' | tee ~/lya/fft_debug/gnuradio_fft_packages.txt
mv ~/.gr_fftw_wisdom ~/.gr_fftw_wisdom.bak.$(date +%Y%m%d_%H%M%S) 2>/dev/null || true
/tmp/ffttest 2>&1 | tee ~/lya/fft_debug/ffttest_after_wisdom_reset.txt
```

如果最后一条仍然抛异常，按“用户目录隔离环境”路线推进。

### 🕳️ 根因定位：`Can't connect channel 0` = GNU Radio 3.7.11 的 `gr::fft::fft_complex` 构造抛异常
- **现象**：测试机(NUC/Ubuntu18.04)上**任何 B1I 配置**（单路径/双路径/文件源/UHD 源都一样）Channel 0 捕获块创建即 `std::exception` → `Can't connect channel 0 internally`。
- **定位手段**：文件源复现(去掉 UHD 噪声) + `gdb -ex "catch throw" -ex run -ex "bt 15"`。调用栈铁证：
  ```
  #1 gr::fft::fft_complex::fft_complex(int,bool,int)  ← libgnuradio-fft.so.3.7.11 抛的
  #2 pcps_acquisition::pcps_acquisition(Acq_Conf const&)
  #4 BasePcpsAcquisition::...  #5 BeidouB1iPcpsAcquisition::...
  ```
- **结论**：**stock 代码**（非 B1C、非多径改动）。`pcps_acquisition` 构造时建 FFT（`gnss_sdr_fft.h`：GR<3.9 走 `gr::fft::fft_complex(size,forward)` 路径），在 **GNU Radio 3.7.11 运行时抛异常**。fft_size=4000（4MHz×1ms B1I，合法）。
  → 本质是 **GNSS-SDR 0.0.21（面向 GR3.8-3.10）在 GR3.7.11 上运行时不兼容**：能编过(cmake 最低要求 3.7.3 已过时)，但 FFT 运行时坏。
- **排查中（待用户测试机结果）**：① 独立最小测试 `gr::fft::fft_complex f(4000,true,1)` 是否也抛(拿真实 type/what)；② `rm ~/.gr_fftw_wisdom` 是否救。
- **大概率的根治**：换 **GNU Radio ≥3.8**（不动 18.04 则用 **conda-forge** 装 gnuradio 3.10 重编 GNSS-SDR；或升级 OS 20.04/22.04）。
- **⚠️ 给 Codex/后续 AI**：这是**环境/版本**问题，不是代码逻辑 bug——别再去改 B1C/多径/配置找它。修复方向是运行环境的 GNU Radio 版本。

### 🧭 Codex 协作接手：先按 README/05 对齐，再继续 B210 B1I 实测

**背景**：用户说明 Claude 已经处理过一轮，要求先查看文件结构和 README；后续 Codex 自己的判断、操作也要记录下来，方便多智能体协同。

**本轮已读**

- `dev_notes/README.md`：确认它是当前项目入口索引，后续接手先读这里。
- `dev_notes/05_pitfalls_and_decisions_log.md`：确认它是 append-only 的踩坑/决策日志。
- `dev_notes/USAGE_B1I.md`：确认当前 B210 测试目标应先落在 B1I 双路径跟踪，而不是继续把 B1C 当作阻塞项。
- `dev_notes/sim/my_bds_b1i_twopath.conf` / `my_bds_b1c_multipath.conf`：注意后者文件名仍容易误导，当前实测优先使用 B1I 配置链路。

**当前判断**

1. B210 之前日志中 USRP 初始化、RX2/LO/中心频率均正常，失败点是 Channel0 内部块创建/连接阶段，不是射频未采到信号导致。
2. 测试机日志仍显示旧的 `std::exception`，没有出现本地新增的 `Exception while creating GNSS channels...` 细分诊断，说明测试机很可能还没有重新编译/运行到最新二进制。
3. Ubuntu 18.04 + CMake 3.10.2 不支持新式 `cmake --build build ... -jN` 写法，应该使用：

```bash
cmake --build build --target gnss-sdr -- -j$(nproc)
# 或
cd build && make gnss-sdr -j$(nproc)
```

4. 当前协作原则：B1I 实测优先；B1C CNAV1/Telemetry 完整支持继续改造，但不阻塞 B210 对 B1I 双路径采集、跟踪和伪距输出验证。
5. 在 Windows PowerShell 下直接读中文 Markdown 可能出现乱码，后续查看中文文档优先使用 `Get-Content -Encoding UTF8`，或在 Ubuntu/WSL 下用 `cat/sed`。

**后续操作记录约定**

- 修改代码、配置或运行验证后，把关键判断追加到本文件对应日期下。
- 如果改变了项目阶段、推荐入口配置或运行步骤，再同步更新 `dev_notes/README.md`。
- 不覆盖 Claude 或用户已有记录；只追加自己的结论、命令和证据。

### ✅ 服务器(Ubuntu18.04/gcc7/GR3.7)编译通过 + B1I 双路径配置就绪
- **服务器环境**：NUC7i7，`gcc 7.3.0 / Boost 1.65.1 / UHD 3.10.3 / cmake 3.10.2`（≈Ubuntu 18.04）。代码在此**编译通过**，产物 `gnss-sdr 0.0.21`。
- **cmake 3.10.2 两个坑（之前报错主因）**：① `cmake -S . -B build` 语法要 cmake≥3.13，3.10.2 不支持 → 必须老式 `mkdir build && cd build && cmake ..`；② 拷来的旧 build 目录 CMakeCache 指向旧机路径 → 先 `rm -rf build*`。
- **版本门槛其实都过**：GNSS-SDR 要求 cmake≥2.8.12 / Boost≥1.53 / GNU Radio≥3.7.3，18.04 全满足；代码在 gcc7/GR3.7 也能编（不只 24.04）。
- **目标澄清 = B1I（不是 B1C）**：运行配置 `my_bds_b1c_multipath.conf`（名字有误导）其实是 **B1I**——`freq=1561098000`、`signal=B1`、全 `BEIDOU_B1I_*` stock 链路 + 多径检测。**B1C 那套代码本目标用不到**（且 B1C 缺 CNAV1 电文解码；B1I 电文/伪距 stock 就有，更适合"输出伪距"目标）。
- **双路径机制确认(读码)**：`Gnss_Synchro::Signal_Path` 驱动——`pcps_acquisition.cc:689/798/811` 里 `Signal_Path==1` 的通道**自动**捕获第二峰；`rtklib_pvt_gs.cc:2077` 只放行 `Signal_Path==0`。`Channels_<sig>.signal_paths=2`(`gnss_flowgraph.cc:1568` 等)信号无关，B1I 直接可用。
- **交付**：`dev_notes/sim/my_bds_b1i_twopath.conf`（B1I + `signal_paths=2` + dump）。服务器上可由 sed 从现有 B1I 配置生成（见对话）。
- **待用户**：B210 实跑结果（MULTIPATH 日志 / 同 PRN 两通道 Tracking / observables 双径伪距）；**确认信号确为 B1I@1561.098MHz**（若实发 B1C 则捕不到）。

### 🔎 Claude 重新接手（re-onboard）+ 报错排查中
- **上下文**：项目已从 `D:\...\gnss-sdr` 迁到本副本 `D:\...\gnss-sdr-main-gaizao\gnss-sdr\gnss-sdr-lya`；用户在此加了大量 B1C 支持，"还在报错"，要求重新了解并排查。
- **已确认（读 README/06/05 + 静态检查）**：B1C 接线**完整正确**——
  - CMakeLists：`beidou_b1c_telemetry_decoder(_gs)` 和 `beidou_b1c_dummy_telemetry_decoder(_gs)` 均已加入 telemetry_decoder 的 adapters/gnuradio_blocks CMakeLists。
  - 工厂 `gnss_block_factory.cc`：4 个 B1C 实现全注册（PCPS_Acquisition / DLL_PLL_Tracking / Telemetry_Decoder(真) / Dummy_Telemetry_Decoder），信号映射 `C1`/`B1C` 均在。
  - → 说明报错**不是**"新块没注册/没进 CMake"这类常见问题。
- **在 `/mnt/d` 上增量编译 8 分钟未编完也未报错**（印证 06 §4：Windows 挂载盘编大文件极慢）。已转后台全量编译 `build-wsl-codex/full_build.log` 复现。
- **待用户补**：① 确切报错文本（编译错？运行错？哪台机/哪个 build？指向哪个文件行）；② **目标到底是 B1I 还是 B1C**——本副本全是 B1C(1575.42MHz)，但最新口径说"B1I 频率"；注意 **stock GNSS-SDR 本就有 B1I 全链路**，若真做 B1I 未必需要自建 B1C。
- 最近活跃改动：`beidou_b1c_telemetry_decoder_gs.cc`(17:43)——正把 dummy 占位换成真 CNAV1 解码，报错很可能在此。

### ✅ B1C + USRP B210 直采双路径原型

**背景**：用户确认测试机为 USRP B210，要求 GNSS-SDR 本身采集后直接做多径检测，不要依赖固定采样文件；目标信号为 B1C，并要求每颗卫星两条路径持续跟踪并输出路径信息。

**关键改造**：
- 运行配置 `dev_notes/sim/my_bds_b1c_multipath.conf` 改为 `UHD_Signal_Source`，默认 `freq=1575420000`、`sampling_frequency=4000000`、`gain=50`、`antenna=RX2`。
- B1C 在运行链路里使用 `C1`，因为 `Gnss_Synchro.Signal` 是两字符字段，不能直接塞 `B1C` 三字符。
- `Channels_C1.signal_paths=2`：每颗 B1C PRN 自动生成 `Signal_Path=0/1` 两条通道；path 0 用主峰，path 1 自动用捕获阶段接受的第二峰。
- 新增 `BEIDOU_B1C_DLL_PLL_Tracking` 适配器，并在 `dll_pll_veml_tracking.cc` 里接入 B1C pilot/data 本地码生成。
- PVT/RTCM 侧只消费 `Signal_Path=0`，第二径保留在 tracking/observables/monitor dump 里做多径分析，避免反射径直接污染 RTKLIB。

**验证**：
- `tracking_gr_blocks` 编译通过。
- `tracking_adapters` 编译通过，并生成包含 `beidou_b1c_dll_pll_tracking.cc.o` 的 `libtracking_adapters.a`。
- `core_monitor` 编译通过，protobuf monitor 的 `signal_path` 字段可用。
- `gnss_flowgraph.cc.o` 和 `gnss_block_factory.cc.o` 单独编译完成。
- 当前 Windows/WSL `/mnt/d` 路径上完整 `gnss-sdr` Release 全量重编非常慢；已有 `build-wsl-codex/src/main/gnss-sdr` 可执行产物能输出 `gnss-sdr version 0.0.21`。测试机建议放 Linux 本地磁盘编译。

### ⚠️ 坑：B1C CNAV1 电文解码尚未完成

B1C acquisition 和 tracking 已经接入，但 native B1C CNAV1 telemetry decoder 还没有实现。

影响：
- 可以做 B210 直采、B1C 捕获、多径第二峰检测、两路径持续跟踪、tracking dump、monitor 输出。
- 如果没有 B1C CNAV1 解码，带 TOW 的有效伪距和 PVT 可能仍然无效。
- 配置里的 `TelemetryDecoder_C1.implementation=BEIDOU_B1C_Dummy_Telemetry_Decoder` 是直通占位，只负责把 tracking 输出继续送到 observables，不代表 B1C 电文解码已经完成。

### ✅ 修复：B1C 配置不能使用 GPS L1 C/A telemetry decoder

测试机日志显示：B210 已正常识别和调谐，但 Channel 0 实例化后工厂捕获 `std::exception`，随后 `Can't connect channel 0 internally`。原因是 `TelemetryDecoder_C1.implementation=GPS_L1_CA_Telemetry_Decoder` 不接受 `C1/B1C` 信号。

处理：
- 新增 `BEIDOU_B1C_Dummy_Telemetry_Decoder`。
- 内部 GNU Radio block 输入/输出都是 `Gnss_Synchro`，原样透传，但强制 `Flag_valid_word=false`、`Flag_valid_pseudorange=false`。
- 这样采集、捕获、两路径跟踪、dump/monitor 能跑通；有效伪距/PVT 仍等待 native B1C CNAV1 decoder。

---

## 2026-07-12

### ✅ 工具就绪：面向真实 B1I 数据的多径检测 + 双路径跟踪（明天可直接用）
**背景**：用户明天采真实 B1I 数据；今晚把工具做到"换数据路径即用"。真实数据走 `File_Signal_Source`（不经内置发生器），故"发生器不支持 B1I"无影响；多径检测在共享 `pcps_acquisition` 核心，B1I 直接受益。

**代码改动④（多径巡检日志）**：`send_positive_acquisition` 加 `LOG(INFO)`——每颗有第二径的卫星打印
`MULTIPATH <sys> <PRN>: 2nd path at X chips (main Y, delta Δ), power ratio Z dB, 2nd Doppler`。
⚠️ **glog 的 INFO 默认写文件不上屏 → 运行加 `GLOG_logtostderr=1` 才能在屏幕看到**（控制台的 "Tracking..." 是 cout，另一回事）。

**交付物（都在 `dev_notes/`）**：
- `USAGE_B1I.md`：明天的操作手册（改数据参数→跑 survey→读日志/分析→双路径跟踪→调参→局限）。
- `sim/bds_b1i_multipath.conf`：多径**扫描**（自动搜星，每星打印多径）。
- `sim/bds_b1i_dualpath.conf`：对指定 PRN **双路径跟踪**（成对固定通道，奇数通道 acquire_second_path）。
- `sim/analyze_multipath.py`：读 dump 出多径表（`--code-length 2046` 给 B1I；GPS 用 1023），自动按码长换算码片/米。

**校验（无真实数据，用假噪声文件烟测）**：B1I 全 12 通道正常构建、多径参数被接受、管线跑到 EOF 无错、退出码 0。
GPS L1 双径 sim 上多径日志实测正常（delta≈6码片、ratio≈4.6dB）。analyze_multipath.py 在 GPS dump 上验证出表。

### 🕳️ 坑：conditioner 的 DataTypeAdapter 必须匹配 item_type（烟测抓到）
- 初版 B1I 配置误把 `DataTypeAdapter=Pass_Through` 接 `byte` 数据 + `Freq_Xlating(input=short)` → `itemsize mismatch` 连接失败。
- 正解：`byte→Byte_To_Short`、`ishort→Ishort_To_Complex`、`gr_complex→Pass_Through`。已在两个 B1I 配置修正并加注释。
- 教训：**无真实数据也要用假文件烟测配置**，能提前抓出连接/类型错误。

### 🕳️ 补充：内置发生器 `data_flag=true` 也救不了持续跟踪
- 试 `data_flag=true`：跟踪照样反复丢锁，且无可解码电文（无 NAV message/PVT）。确认是**发生器保真度**问题，非数据位问题。
- → "双伪距→PVT/定位"必须靠**真实数据**（或高保真仿真）。这与"B1I 需真实数据"合流。

### ✅ Stage 1b 机制打通：两个通道同 PRN，分别跟踪直射/反射（零改 flowgraph/channel/FSM）
**关键调研结论**（Explore agent + 读码）：
- **两通道可跟同一 PRN，纯配置即可**：`Channel0.satellite=1`+`Channel1.satellite=1`+`Channels_1C.count=2`+`Channels.in_acquisition=2`。
  固定通道（satellite≠0）**不从 pool 抽取**，故通道0捕获成功时的 `remove_signal` 不影响通道1（`gnss_flowgraph.cc` assign_channels/acquisition_manager）。发现有 `duplicated_satellites_test`（利好 Stage 3）。
- **按通道配置捕获**：工厂 `get_role_name`(`gnss_block_factory.cc:236`)——`Acquisition_1C1` 仅当其 `.implementation` 存在时启用，
  **且不继承共享 `Acquisition_1C` 参数**（per-channel 块要写全）。

**代码改动③（Stage 1b，仍全在捕获层）**：
- `acq_conf.h/.cc`：加 `acquire_second_path`(bool)
- `pcps_acquisition.cc` 三处：① `acquire_second_path` 也触发 `find_second_peak`；② `update_synchro` 在该模式下把**第二峰**(index_time2/doppler2)写入 `Acq_delay_samples/Acq_doppler_hz` 交给跟踪；③ `acquisition_core` 判定：该模式下以 `has_second_peak` 为正捕获条件（无第二径不跟幽灵）。假定 `make_2_steps=false`。

**验证（`dev_notes/sim/gpsl1_2ch.conf`，脚本 `verify_stage1b.py`）**：
- 冷启动首份 dump：**通道0 交跟踪 355.0chip（直射）；通道1 交跟踪 361.1chip（反射）** ——两通道各锁一条径。
- 控制台：channel 0 与 channel 1 **同时都在 Tracking PRN 01**。
- 结论：**每卫星双径同时跟踪的机制打通**，零改 flowgraph/channel/FSM/tracking。

### 🕳️ 局限：仿真数据下产不出稳定伪距（跟踪反复丢锁）
- `data_flag=false` 无导航电文 → 电文解不出 TOW → **无伪距/PVT**；且发生器保真度有限 → 跟踪反复 Loss-of-lock 重捕。
- 影响：Stage 1b 的**机制**已验证，但"稳定输出两条伪距→进 PVT"需**更好的信号**：`data_flag=true` 的发生器 或 **真实数据**。与"B1I 需真实数据/扩展发生器"是同一问题。
- 待办：试 `data_flag=true` 看能否持续锁定出电文；或推进"给发生器加 B1I + 更真实信号"。
- 小遗留：dump 的第二峰变量目前只在 `multipath_detection` 下写；`acquire_second_path` 通道的 dump 里 has2/delay2 为空（不影响结果，acq_delay_samples 已正确）。可后续把 dump 门控也加上 `acquire_second_path`。

### ✅ Stage 1a 完成：捕获检测并报告第二径（多径），GPS L1 仿真验证通过
**代码改动②（对捕获核心的第一次实质修改，信号无关，B1I 同样受益）**：
- `acq_conf.h/.cc`：新增 3 个配置项
  - `multipath_detection`(bool, 默认 false)：开关
  - `multipath_max_delay_chips`(float, 默认 5)：主峰邻域搜索窗（±码片）
  - `multipath_threshold_fraction`(float, 默认 0.3)：第二峰判定门限 = 该比例 × 主峰 CFAR 门限
- `pcps_acquisition.h`：`AcquisitionResult` 加 `has_second_peak/index_time2/doppler2/test_statistics2/peak_ratio`；声明 `find_second_peak()`
- `pcps_acquisition.cc`：
  - 新增 `find_second_peak()`：定位主峰所在多普勒 bin → 在**同 bin**、主峰 **±window 码片**内、**排除 ±1 码片主瓣**后取次高点 = 第二峰；
    记录位置/多普勒/`ts2=mag2/input_power`/`peak_ratio=mag1/mag2`；`has_second_peak = ts2 > fraction×get_threshold()`
  - `acquisition_core` 在 `compute_statistics()` 后调用（仅非 step_two）；纯检测/记录，**不改跟踪交接**（那是 1b）
  - `dump_results` 加 `has_second_peak/acq_delay_samples_2/acq_doppler_hz_2/test_statistic_2/peak_ratio`；`log_acquisition` 加第二峰日志

**验证（配置 `dev_notes/sim/gpsl1_1sat.conf` 单径 / `gpsl1_2path.conf` 双径，分析脚本 `verify_stage1a.py`）**：
- 双径(直射355chip/50dB + 反射361chip/45dB，间隔6码片)：**每份 dump 都 has2=1，第二峰稳定在主峰+6码片、同多普勒**；#1 主峰355.0/第二峰361.1，与生成值分毫不差。ts2=31–68，peak_ratio=2.4–4.1。
- 单径(仅355chip)：**每份 has2=0**（窗内次高点只是噪声，ts2=6–13，peak_ratio=10–23）。
- 结论：算法能**判别多径 vs 单径**，不是"总能凑个次峰"。

### 🕳️ 坑：第二峰门限**不能用主峰门限**（第二径本就更弱）
- 反射比直射弱 5dB → ts2(反射)=30–65 却 < 主峰 CFAR 门限(=106.3, max_dwells=10)。用 `get_threshold()` 直接判会把真反射全判 0。
- **对策**：门限取主峰门限的**一个比例** `multipath_threshold_fraction`。数据：噪声 ts2≤17、反射 ts2≥30 → 取 **0.2×门限≈21** 稳妥分开（默认 0.3 偏严，-5dB 反射在噪声波动下会漏；测试配置里设 0.2）。**这是可调灵敏度旋钮**，弱多径可再降。
- 记录数值：threshold=106.3；单径主峰 ts=152、ts2=7；双径主峰 ts=165、ts2=65、peak_ratio=2.5。

### 🕳️ 坑：Python heredoc 里中文/f-string 转义易碎 → 一律写 `.py` 脚本文件跑
- `dev_notes/sim/` 下：`analyze_peaks.py`(相关面top峰)、`verify_stage1a.py`(第二峰变量)、`show_thresh.py`(门限/统计量)。

### ✅ Stage 0 完成：环境编译通过 + 仿真数据链路打通 + 双径可分辨验证
**环境**：WSL2 Ubuntu24.04，`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF` 配置通过；
`cmake --build build -j20` 编译成功（**坑**：首次用 `nohup &` 在 WSL 内跑被 SIGHUP 杀；改用工具的 `run_in_background` 保活 wsl.exe 进程即可）。产物 `build/src/main/gnss-sdr`（v0.0.21）。

**代码改动①（我们对仓库的第一处修改）——注册内置信号发生器为可用 SignalSource**：
- 目的：内置发生器没进工厂（`GetSignalSource` 无此实现），无法在 `.conf` 里用。注册后可造仿真数据。
- 改了 3 个文件 4 处：
  1. `src/algorithms/signal_generator/adapters/signal_generator.h`：基类 `GNSSBlockInterface`→`SignalSourceInterface`，
     include 换成 `signal_source_interface.h`，实现 `getRfChannels(){return 1;}`（该接口唯一多出的纯虚方法）。
  2. `src/core/receiver/gnss_block_factory.cc`：加 `#include "signal_generator.h"` + `else if (implementation=="Signal_Generator") return make_unique<SignalGenerator>(...)`。
  3. `src/core/receiver/CMakeLists.txt`：`core_receiver` 链接列表加 `signal_generator_adapters`。
- 增量重编通过，`SignalSource.implementation=Signal_Generator` 可用。

**验证数据链路（配置见 `dev_notes/sim/`）**：
- `gpsl1_1sat.conf`：单星 GPS L1 PRN1，捕获成功，dump 出相关面 `.mat`。用 h5py 读 `acq_grid`(40×4000=doppler×code)，
  峰值 `acq_doppler_hz=1500`、`acq_delay_samples=1388`(=355chip×4000/1023)，与生成参数**完全吻合**。分析脚本 `dev_notes/sim/analyze_peaks.py`。
- WSL 有 `python3 + h5py 3.10 + numpy 1.26`，可直接分析 dump。

### 🕳️ 关键发现：捕获"次峰"检测受**噪声底**限制 → 直接影响 Stage 1a 设计
- 单径信号（无反射）相关面里也有 ~-5dB 的伪峰 → 是**噪声底**不是反射。理论对得上：CN0=45dBHz/1ms/单积分 → 峰噪比~15dB，4000点最大噪声峰~主峰下 -3~-5dB。
- 后果：**天真地"全局找第二高峰"会选到噪声/伪峰，不是反射**。
- **对策（已验证有效）**：① 提高积分（`max_dwells=10` 非相干积分把噪声底压低~10dB）；② 提高 CN0；③ Stage 1a 里应在**主峰邻域内**找第二峰（多径是同星延迟副本，码相位近、同多普勒），而非全局。
- **验证成功的双径配方**（`gpsl1_2path.conf`）：同 PRN1 两条径，直射 CN0=50@355chip、反射 CN0=45@361chip、`max_dwells=10`
  → 直射峰 355.0chip(1.27e13)、**反射峰 360.9chip(4.36e12) 成为干净的第二峰**（高出噪声底 3.3×，幅度比 -4.6dB≈设定 -5dB）。

### 🕳️ 坑：内置信号发生器**不支持 BeiDou**（只 G/R/E）
- `signal_generator_c.cc` 三处生成循环（`:113/:173/:358`）只有 `system=="G"/"R"/"E"`，**无 "C" 分支**；适配器引 `Beidou_B1I.h` 仅用于算 `vector_length`。
- 影响：**用内置发生器造不出 B1I 仿真数据**。
- **对策**：Stage 1a 核心改动信号无关 → **先在 GPS L1 C/A 仿真多径验证**，再给发生器加 B1I 分支（复用 `beidou_b1i_signal_replica`）或用真实数据。目标仍是 B1I。

### 🧭 技巧：多径仿真数据"靠配置就能造"（无需改发生器，限 ≥1 码片）
- 发生器把每颗配置的星**叠加**进同一路输出（`:343-348`），每颗可独立配 `PRN/CN0_dB/doppler_Hz/delay_chips`。
- **给同一 PRN 配两条不同 `delay_chips`、不同 `CN0` 的信号 = 直射+反射双径**。
- 限制：`delay_chips` 是整数（`:360`），只能造 **≥1 码片**可分离多径（对应架构 A）。近距 <1 码片需给发生器加分数码片时延（Stage 2）。

### 🕳️ 坑：WSL 里 **sudo 需要密码** → 依赖安装须用户执行
- AI 无法非交互 apt 安装。装完依赖后 cmake/make/运行**不需要 sudo**，可由 AI 驱动。
- 备选：用户开免密 sudo 则 AI 可全自动。
- **依赖安装命令（Ubuntu 24.04，已核验包名均可得，仅 `libgnutls-openssl-dev` 缺→用 `libssl-dev` 代）**：
  ```bash
  sudo apt update && sudo apt install -y \
    build-essential cmake git pkg-config \
    gnuradio-dev libboost-all-dev \
    libarmadillo-dev libgflags-dev libgoogle-glog-dev \
    libmatio-dev libpugixml-dev libprotobuf-dev protobuf-compiler \
    libblas-dev liblapack-dev libgtest-dev python3-mako \
    libpcap-dev libspdlog-dev libfmt-dev libssl-dev
  ```
- 环境已探明：WSL2 Ubuntu 24.04.4，20 核/11GB/919GB 空闲；源码在 WSL 路径 `/mnt/d/work/project/usrp_gnss/gnss-sdr`（就地 build，`/mnt/d` I/O 偏慢但可接受）。
- 构建：`cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF && cmake --build build -j20`；运行 `./build/src/main/gnss-sdr --config_file=<conf>`。

### 🧭 决策锁定：目标 B1I / 提升定位 / 覆盖近距+远距 → 三阶段方案
- **用户 3 项回答**：① 用途=**提升定位精度**；② 两径间隔=**近距+远距都要**；③ 原型信号=**BeiDou B1I**。
- **推导出的方案骨架**（详见文档 04 定稿）：
  - **A（捕获搜 Top-2 峰）**：处理远距(>1码片)可分离两径，贴合用户设想，先做、易验证。拆 1a(捕获报告两峰) + 1b(接第二跟踪器，倾向 A-i 扩展 Channel)。
  - **B（跟踪域多相关器）**：处理近距(<1码片)多径，捕获域分不开，必须做；MEDLL/峰形拟合，研究级。
  - **PVT 整合**：每星只送一条干净/校正观测量，天然避开 RTKLIB 同 PRN 覆盖。
- **B1I 关键数**：码率 2.046Mcps / 码长 2046 / 周期 1ms / **1码片≈146.6m** / 示例 conf 用 25MHz(~12.2样点/码片) / NH 二级码 20bit / 捕获 dump 默认开。

### 🧭 关键认知：提升定位 ≠ 把两个伪距都塞进 PVT
- 反射径(NLOS)伪距**偏长**，作为独立观测量喂解算器会**恶化**定位。正解：双径→判别直射(LOS)→每星**一条**干净/校正伪距进 PVT，第二径走旁路做分析/校正/加权。
- 推论：RTKLIB "同 PRN 覆盖"其实与"每星一条观测量"的物理需求一致，不是纯障碍。**若用户真要两条独立观测进解算需再确认**（一般不利精度）。

### 🕳️ 坑（环境层，未踩先防）：Windows 编译 + 数据缺失
- 用户在 **Windows 11**，但 GNSS-SDR 原生 Windows 编译极难（依赖 GNU Radio/VOLK/Armadillo/gflags 等），通常需 **WSL2/Linux**。
- 示例 conf `gnss-sdr_BDS_B1I_byte.conf` 的数据指向 Linux 路径 `/archive/BDS3_datasets/BdsB1IStr01.dat`（byte,25MHz,IF≈6.25MHz），用户机器上大概率没有。
- **对策**：Stage 0 优先确认编译路线 + 数据来源（或用 signal_generator 造带多径仿真）；无数据时可先做 **Stage 1a 纯代码改造**，环境就绪再验证。
- 仓库现状：`main` 分支(v0.0.21 era)，**无 build 目录**（未编译），仓库内无采样数据。

### 🧭 需求明确 + 可行性调研：每颗卫星捕获两条径、同时跟踪各自伪距
- **用户需求（明确版）**：谱峰搜索时对每颗卫星找**强度最强的两条径（两个峰）**，**同时跟踪**这两条径，各自得到伪距等信息。
- **三点关键结论**（读码 + 3 个 Explore 定向调研，均有源码佐证）：
  1. **跟踪可行**：跟踪块自包含。用第二个峰的 `Acq_delay_samples`/`Acq_doppler_hz` 播种第二个跟踪实例即可独立跟第二条径
     （`dll_pll_veml_tracking.cc:791-800`）。相关器为 N 抽头、可扩展（当前 3/5 抽头，`:611-652`）。
  2. **分辨率硬约束**：捕获现有 `first_vs_second_peak_statistic` 找次峰时**排除主峰 ±1 码片**（`pcps_acquisition.cc:484-509`）。
     → 捕获域只能分开 **≳1 码片**的两径；**近距多径（<1 码片，最常见最有害）在捕获域分不开**，需在**跟踪域**用多相关器/超分辨。
  3. **下游冲突**：observables 按 `Channel_ID` 组织（不冲突）；但 **RTKLIB 解算器**按卫星号打包观测，
     同 (系统,PRN,信号) 的第二条观测**很可能覆盖第一条**（`rtklib_solver.cc` 观测装配循环，**待实测确认**）。
     → 两条径伪距**同时进同一定位解会冲突**；若只做"测量/导出"则无碍。
- **两条候选架构**（待用户定，详见文档 04）：
  - **A｜单通道两跟踪器**：一次捕获出两峰 → peak1/peak2 各播种一个跟踪块。贴合"捕获搜两峰"的心智，改动含 channel/FSM，无需动 PRN 池。
  - **B｜单跟踪器多相关器**：一个跟踪块内加密抽头、内部分辨两径（MEDLL 类）。贴合近距多径物理，但鉴别器算法复杂、双伪距输出需自定义。
- **通道 PRN 池备注**：若改走"两个独立通道同 PRN"，需改 `gnss_flowgraph.cc`（`remove_signal`@~1845、`search_next_signal`@~2290 的 pop）；
  但独立通道还有"第二通道怎么拿到第二个峰"的协调难题，不如 A 方案（一次捕获出两峰）干净。→ **不推荐独立通道路线**。

### ❓ 待用户确认（阻塞方案选型）
- 两条径伪距的**最终用途**（多径研究/测量 vs 提升定位 vs 抗欺骗）→ 决定要不要处理 RTKLIB 冲突。
- 关注的两径**间隔尺度**（>1 码片可分 vs <1 码片近距）→ 决定主战场在捕获域还是跟踪域。
- **原型目标信号**（建议 GPS L1 C/A 起步）。

### 🧭 决策：文档采用"索引优先 + 模块化多文件"结构
- **背景**：用户要求维护一份能让"无记忆 AI"快速接手的进度文档，但又不能让上下文爆炸。
- **方案**：`README.md` 作总纲（目标 / 文档地图 / 进度看板 / 结论速查 / 术语），
  详情拆成 01~05 独立文件，每篇开头有小目录和"何时读"。维护时只动 README 进度看板 + 相关那一篇 + 本日志。
- **好处**：接手的 AI 先读小的 README 建立全局观，再**按需**读一两篇详情，不必全量载入。

### 🧭 决策：文档放 `gnss-sdr/dev_notes/`，文件名用 ASCII
- 放仓库内便于随代码走、易被发现；文件名用 ASCII（如 `02_acquisition_2d_peak_search.md`）避免
  Windows/Git Bash 下中文路径在某些命令行工具里的编码问题；**正文用中文**。

### 🧭 决策：先吃透"捕获（Acquisition）"再动手
- 用户重点是"二维谱峰搜索"，已确认它 = 信号捕获 = PCPS 算法，核心在 `pcps_acquisition.cc`。
- 已通读该文件全 872 行，产出文档 02（核心篇）。

### 🕳️ 坑（预警，未踩但要小心）：`Gnss_Synchro` 加字段影响面
- 它按 `sizeof(Gnss_Synchro)` 在 GNU Radio 流端口间传递，且可能被 dump/序列化/外部监视工具消费。
- **对策**：新字段加在结构体**末尾**并给默认值 `{}`；改动前检查是否有 boost::serialization / 二进制 dump / monitor 依赖。

### 🕳️ 坑（预警）：捕获核心计算段在"解锁"状态运行
- `acquisition_core()` 里 `doppler_grid()`+`compute_statistics()` 跑在 `d_setlock` **解锁**期间（`pcps_acquisition.cc:677-684`）。
- **对策**：若在这段加共享状态，注意线程安全；写回 `d_gnss_synchro` 的部分要在重新上锁后做。

### 🧭 决策：改造遵循"小步快跑、先捕获层后跟踪层、每步用 dump 验证"
- 见文档 04 §4 的分阶段计划。先不碰 FPGA/OpenCL/实时分支。

### ❓ 疑问：待用户澄清的 6 个关键问题
- 见文档 04 §5（"多源"具体指哪种、多径做到哪一步、目标信号、数据来源、实时性、交付形态）。
- 这些直接影响改造方向与工作量，**建议尽早和用户确认**。

### ❓ 疑问 / 待办：尚未验证的事项
- [ ] 还没实际**编译/运行**过项目，也没 dump 出真实相关面 `.mat`（文档 02/04 里的算法理解来自读码，待跑通验证）。
- [ ] tracking 模块（多径的主战场）**还没读**，文档 04 §2.B 尚是占位，需下一步补。
- [ ] observables/多源架构还没细看，文档 04 §3 待细化。
- [ ] 文档 01/03 里的**行号是近似值**（部分来自 Explore 代理扫描），动手改前以实际文件为准。

---

*（新条目请加在本行上方、日期区块内）*
---

## 2026-07-20

### Fix: GNSS-SDR main stdout did not print pseudorange / C/N0

User observation: running `./build-conda/src/main/gnss-sdr --config_file=... | tee run.log`
only showed tracking, loss-of-lock and overflow messages. It did not print the
dual-path pseudorange or C/N0 values.

Root cause: previous Stage-A work exported those values through side paths:

- `Observables.dump_extended=true` writes `Signal_Path` and `CN0_dB_hz` into the
  observables binary dump.
- `Monitor.enable_monitor=true` can be watched by `watch_dualpath_monitor.py`.

But the GNSS-SDR main stdout path itself had no low-rate observables printer.
So a plain `gnss-sdr | tee run.log` was not enough to see pseudorange/CN0.

Change made:

- Added `Observables.stdout` and `Observables.stdout_interval_ms`.
- The print point is after `Hybrid_Observables::compute_pranges()`, so it prints
  the actual computed `Pseudorange_m`, not the acquisition code phase.
- Output prefixes:
  - `DUALPATH_OBS`: one valid channel/path row.
  - `DUALPATH_PAIR`: path0/path1 pair for the same PRN, including `delta_m`.
- Updated L5 generator and active B1I/L5 test configs to enable stdout every
  1000 ms.

How to inspect:

```bash
./build-conda/src/main/gnss-sdr --config_file=/tmp/l5_realtime_dualpath_prn18.conf 2>&1 | tee run.log
grep 'DUALPATH' run.log | tail -40
```

If there are no `DUALPATH_*` rows, Observables did not have a valid pseudorange
yet. Then check loss-of-lock, telemetry/word validity, PRN mismatch and overflow.

### Fix: L5I simulator was tracked as L5Q/pilot

User confirmed the simulator transmits GPS L5I only. The previous L5 test
configs used:

```ini
Acquisition_L5.implementation=GPS_L5i_PCPS_Acquisition
Tracking_L5.track_pilot=true
```

That is inconsistent: acquisition searches L5I, but tracking asks the generic
L5 tracking block to use the L5Q/pilot side. Runtime logs saying
`Tracking of GPS L5Q signal started` matched this mismatch. This can produce
short tracking starts, repeated loss-of-lock, weak/unstable C/N0, and missing
valid pseudorange for path1.

Change made:

```ini
Tracking_L5.track_pilot=false
```

Updated `make_l5_dualpath_conf.py` and active L5 configs so future PRN24/25
configs track the L5I data component emitted by the simulator.

---

## 2026-07-29

### Codex decision: Track B starts with trajectory diversity, not another snapshot fitter

Static real-data diagnostics showed that path0 residual texture can leave
several plausible delay solutions after subtraction. Adding another
unconstrained snapshot fit risks selecting one of those artifacts.

Track B therefore starts with a separate moving-receiver hypothesis:

- fixed transmitters and receiver geometry generate time-varying delay and
  relative Doppler;
- each segment keeps several delay-Doppler candidates;
- a physical transition law selects a continuous trajectory;
- static data remains a required negative control.

Important pitfall found during implementation: fitting free `K + dK/dtau`
coefficients independently at every epoch also absorbs a merged moving path.
That subtraction destroyed the temporal signature and produced false
main-lobe-edge candidates. It is diagnostic-only; the Track B default preserves
the temporal modulation.

Initial result: ideal and measured-PRN28-path0 faithful synthetics recover a
`0.37..0.55 chip` moving second source, while the corresponding static controls
are rejected. This is an algorithm milestone, not yet a real moving-capture
claim. Full commands and acceptance gates are in
`13_trackb_moving_trajectory_prototype.md`.

### Codex decision: post-correlation EKF needs multiple initial modes

The first Track B EKF used one delay-Doppler initialization candidate. It passed
the `-6 dB` moving case but failed the equal-power destructive-phase case:
source ordering swapped, initialization latched to the minimum delay, and the
local EKF reported false confidence.

The implemented correction keeps several initializer candidates, runs one small
delay/rate EKF per candidate, then selects using normalized residual, two-path
support, and boundary occupancy. This recovered the faithful equal-power case
with `1.55 m` P90 error.

Second pitfall: an EKF covariance can look precise while being wrong. Initial
noise settings reported `0.08 m` posterior standard deviation for errors above
`1 m`. Process and measurement floors were recalibrated against faithful
synthetic truth; final moving cases have `88.5..100%` coverage inside `+/-2
sigma`.

Details and commands are in `14_trackb_postcorrelation_ekf.md`.

## 2026-07-29 - Codex - Track B cross-reference result

The first faithful Track B benchmark used PRN28 run4. A 23-reference rerun now
covers PRN5/10/11/15/20/23/28 and measured CN0 about 39.6--59.9 dB-Hz.

Decision:

- retain the motion-diversity direction because several real textures still
  recover the 0.37--0.55 chip trajectory at meter-level P90;
- withdraw any implication that the PRN28 result already generalizes to all
  PRNs or sessions;
- use EKF rather than DP reliability for claims, because EKF rejected every
  static/path-absent control while DP accepted four static controls;
- add texture-aware initialization and covariance before real moving capture.

The strict EKF moving-case pass rate was 8/19 for both -6 dB and equal-power
cases. Point-estimate P90 was <=3 m in 11/19 and 10/19 respectively, showing
that uncertainty calibration and gross initialization failures are separate
problems. Full evidence is in `15_trackb_cross_reference_benchmark.md`.

## 2026-07-31 - Codex - Texture likelihood replaces geometry-only gating

The geometry-only confidence gate was rejected as a decision gate: at no
operating point with false-positive rate <=5% did it recover more than 16.7% of
the truth-reliable moving cases.

The first path0-texture-aware GLRT was implemented and evaluated with
leave-one-run-out models grouped by PRN and tap grid. It produced two separate
findings:

- second-source existence is nearly separable on the current benchmark
  (AUC 0.999; 53/54 H1 detected with 0/18 H0 false alarms at a provisional
  between-class threshold);
- trajectory recovery improved strongly for equal-power destructive cases but
  regressed for some -6 dB and low-CN0 cases.

Decision: preserve this ordering:

1. texture-aware existence likelihood;
2. strengthen it with measured B-only texture and recalibrate;
3. validate known-truth moving simulator trajectories;
4. perform OTA capture only after those gates pass.

Do not call `static_m6` an H0 case. It contains a second source and is H1 for
existence, even though it lacks the motion diversity needed for moving-mode
trajectory separation. Full results and reproduction commands are in
`15_trackb_cross_reference_benchmark.md`.

## 2026-07-31 - Codex - B-only texture strengthens the benchmark, not the claim

Existing PRN11/23/28 B-only captures were integrated as measured path1 kernels.
The benchmark exposed and fixed two hidden assumptions: a whitened residual map
must not mask its own strongest peak as path0, and a short texture record must
not accelerate the simulated receiver trajectory.

After quality gating, all eight same-PRN A/B references recovered both moving
-6 dB and equal-power cases. Path-absent controls remained rejected and
existence AUC was 1.0. A smoothed B residual added complexity without consistent
benefit, so the coherent B-only kernel is the default.

The low-CN0 stress test established a real boundary: measured CN0 around 45
dB-Hz and above passed all moving cases, while around 40 dB-Hz the H1
likelihood overlapped H0 and weak-path tracking failed. Decision: likelihood
thresholds must be conditional on CN0/noise; data below the validated envelope
returns `INSUFFICIENT/UNDECIDED`. The next evidence tier is a simulator-driven
moving receiver trajectory with known truth, followed later by OTA.

## 2026-08-03 - Codex - Static research pivots to four-antenna space-time data

Moving-receiver capture is paused. The next static research line uses up to
four synchronized antennas plus multi-epoch complex correlator observations.

Decision:

- treat spatial channels as the new identifiability dimension;
- treat repeated static epochs as statistical reinforcement, not synthetic
  spatial diversity;
- prefer a native phase-calibratable four-channel receiver; two synchronized
  B210 units are only a conditional prototype requiring per-run calibration;
- preserve one common carrier/code reference across all RF streams;
- prove the hardware and measured array manifold before implementing a large
  joint estimator;
- start with measured-template constrained GLRT/ML, then consider MSBL/SAGE;
- report same-direction or ill-conditioned cases as `UNRESOLVED`.

The first controlled fixture is a four-element L5 ULA at half-wavelength
spacing. A `2 x 2` planar array follows only after the one-dimensional proof.
The minimal screen fixes high CN0 and -6 dB power ratio, then tests
`0/0.5/1.0 chip` against `0/10/30/60 deg` before any full boundary campaign.
The complete plan and stop rules are in
`16_static_four_antenna_space_time_plan.md`.
