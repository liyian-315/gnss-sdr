# 21 · 隧道 DAS 双端覆盖测量与功率配平工具

> 分支：`product/tunnel-das-balance-v1`
> 基线：`d1f8d16435cf4a38dde1f3f5aaba980eaa0597f3`（`product/l5-dualpath-receiver-v1` HEAD）
> 日期：2026-08-10 · 作者：Claude (Opus 5)

---

## 1. 工具目标

隧道 A、B 两端同时主动转发**同一颗 GPS L5 卫星、同一 PRN、同一频点**。
工作人员带 USRP B210 + 单接收天线 + NUC 走到隧道内某个**已知测点**，
启动 GNSS-SDR，终端每秒直接给出：

END_A CN0 · END_B CN0 · A−B CN0 差 · END_A 伪距 · END_B 伪距 · B−A 伪距差 · 当前测点 · 可信状态

**不写 CSV、不依赖 Python、不需要另开任何脚本。**

## 2. 基于哪个产品 SHA

`d1f8d1643`。完全复用既有 L5 双路径接收机：acquisition 第二峰门禁、双通道 tracking、
`DualPathPairManager` 六态质量机、`DUALPATH_STATUS` 全部**未改动**。
本轮只在其**之上**加了一层。

## 3. 输入

站点参数放在配置文件最顶端（`Tunnel.*` 全局作用域），换测点只改一行：

```ini
Tunnel.enable=true
Tunnel.length_m=1000
Tunnel.measurement_position_m=300      ; ← 换测点只改这行
Tunnel.end_a_name=END_A
Tunnel.end_b_name=END_B
Tunnel.end_a_fixed_delay_m=0
Tunnel.end_b_fixed_delay_m=0
Tunnel.identity_max_error_m=75         ; PROVISIONAL
Tunnel.identity_margin_m=50            ; PROVISIONAL
Tunnel.identity_confirm_epochs=5       ; PROVISIONAL
```

未做命令行参数覆盖——为一个参数改 GNSS-SDR 的 command-line 架构不划算，配置方式已足够。

启动即打印站点回执，供现场核对：

```
TUNNEL_DAS position_m=300.0 length_m=1000.0 end_a_name=END_A end_b_name=END_B
end_a_fixed_delay_m=0.0 end_b_fixed_delay_m=0.0 expected_delta_b_minus_a_m=400.0
```

## 4. END_A / END_B 定义

`path0` = 捕获主峰，`path1` = 捕获第二峰。**它们不是 END_A / END_B**，
功率变化或重捕后可能互换。

新增独立模块 `TunnelEndAssociation`（`src/algorithms/observables/libs/`），
职责**只有**身份关联：输入测点位置、隧道长度、固定延迟和一个 `DualPathPairStatus`，
输出 path→END 映射、expected delta、residual 和身份置信度。
它**不**重做 acquisition / tracking / CN0 / 伪距——全部沿用 GNSS-SDR 既有结果。
因此将来即使前端换成阵列或超相关，这一层仍可原样复用。

身份状态：`IDENTITY_UNKNOWN` / `IDENTITY_CANDIDATE` / `IDENTITY_RELIABLE`。

## 5. expected delta 计算

```
d_A = measurement_position_m
d_B = length_m - measurement_position_m
expected_delta_b_minus_a_m = (d_B + end_b_fixed_delay_m) - (d_A + end_a_fixed_delay_m)
```

两端固定延迟**不假定相等**。1000 m 隧道、测点 300 m、零补偿 → 期望 +400 m。

代价函数（只有两种排列）：

```
path0=A ⇒ observed_delta_b_minus_a = +delta_m
path1=A ⇒ observed_delta_b_minus_a = -delta_m
error_i = |observed_i - expected|
best_error = min, margin = |error_2 - error_1|
```

接受条件（全部必须满足）：

1. `best_error <= Tunnel.identity_max_error_m`
2. `margin >= Tunnel.identity_margin_m`
3. 连续 `Tunnel.identity_confirm_epochs` 个历元一致
4. 底层 `DualPathPairManager` 状态 == `RELIABLE`

中点处 `expected → 0` ⇒ `margin → 0` ⇒ **必然 UNKNOWN**，这是几何决定的，不是调参能绕过的。

**身份只依赖时延几何，绝不看 CN0 大小。** 两端强弱互换不会让 A/B 跟着换。
若 `path0/path1` 真的互换，映射会跟着翻——正是这样才让 END_A 始终指向同一物理端；
翻转必须重新确认，确认期间输出 `CANDIDATE` + `N/A`。
重捕（`reacquisition_count` 变化）同样强制重新确认。

## 6. 实时输出

新增 `TUNNEL_DAS_STATUS version=1`，每秒一行，是现场人员的主界面。
原 `DUALPATH_OBS` / `DUALPATH_PAIR` / `DUALPATH_STATUS` 保留用于兼容和调试。

方向固定，不会时而 A−B 时而 B−A：

- `cn0_delta_a_minus_b_db = END_A CN0 - END_B CN0`
- `pseudorange_delta_b_minus_a_m = END_B 伪距 - END_A 伪距`
- `delta_residual_m = pseudorange_delta_b_minus_a_m - expected_delta_b_minus_a_m`

`identity != RELIABLE` 时，全部 A/B 正式字段输出 `N/A`；
`path0_cn0_db_hz` / `path1_cn0_db_hz` / `identity_error_m` / `identity_margin_m`
始终输出作为诊断，但**不带 A/B 标签**。

`state` 取值：`SEARCHING` / `NO_SECOND_SOURCE` / `LOST` / `UNRESOLVED` / `RELIABLE`。
第二端丢失 ⇒ `LOST` 且 A/B 立即 `N/A`，不显示上一次的 B 端值。

## 7. 测试结果

### 单元测试（本轮实测）

WSL2 Ubuntu 24.04 / g++ 13.3 / gtest，编译四个独立套件 + 新增隧道套件：

```
30 tests from 5 test suites ran.  [  PASSED  ] 30 tests.
```

`TunnelEndAssociation` 11 个用例，覆盖任务要求的全部 8 项：

| 要求 | 用例 | 结果 |
|---|---|---|
| 1. position=300/length=1000 正确识别 A/B | `IdentifiesEndsFromMeasurementPosition` | PASS |
| 2. path0/path1 交换，身份保持物理连续 | `PathSwapKeepsPhysicalEndLabels` | PASS |
| 3. CN0 大小交换，身份不跟着换 | `Cn0SwapDoesNotSwapEndIdentity` | PASS |
| 4. 测点 500 m 无法区分 → UNKNOWN | `MidpointIsReportedUnknown` | PASS |
| 5. observed 严重偏离 expected → UNKNOWN | `DeltaFarFromExpectedIsReportedUnknown` | PASS |
| 6. 重捕后先 CANDIDATE、N 个历元后 RELIABLE | `ReacquisitionMustReconfirmBeforeReliable` | PASS |
| 7. 第二径 LOST → A/B 正式结果 N/A | `SecondEndLossClearsFormalResult` | PASS |
| 8. 非零 fixed delay 下 expected 正确 | `AsymmetricFixedDelaysShiftExpectedDelta` | PASS |
| 额外 | `ExpectedDeltaFollowsPositionAndFixedDelays` | PASS |
| 额外：DEGRADED 不得发布正式端 | `DegradedPairNeverPublishesFormalEnds` | PASS |
| 额外：输出格式逐字符锁定 | `StableVersionOneFieldOutput` | PASS |

### 集成编译（本轮实测）

WSL2 CMake Release 全新配置，逐目标构建通过：

```
observables_libs  OK   (含 tunnel_end_association.cc)
obs_gr_blocks     OK   (含改动后的 hybrid_observables_gs.cc)
obs_adapters      OK   (含改动后的 hybrid_observables.cc)
```

### 第二层：B210 双端实验

**本轮未执行。** 测试 A（已知位置双端可分）、测试 B（功率阶梯 0/−3/−6 dB 趋势）、
测试 C（A/B 强弱互换）**全部 NOT_RUN**。NUC 本轮 SSH 不可达，无 B210、无双模拟器。

## 8. 已知边界

见 `product/tunnel_das/KNOWN_LIMITATIONS.md`。最关键三条：

1. 只适用于当前接收机能可靠分离的测点；中点附近**必然** `UNRESOLVED`，这是几何结论。
2. CN0 只做**同接收机、同测点、同 PRN** 的相对比较，不是绝对功率 dBm。
3. 本轮不定义 `BALANCED` 阈值，只输出 `cn0_delta_a_minus_b_db` 数值。

## 9. 哪些是实测

| 项 | 证据等级 |
|---|---|
| 身份关联逻辑（8 项要求全覆盖） | **UNIT_TEST**（本轮 30/30 通过）|
| `TUNNEL_DAS_STATUS` 字段顺序与精度 | **UNIT_TEST**（逐字符断言）|
| 与 GNSS-SDR 主链路集成可编译 | **BUILD**（WSL CMake Release 三目标通过）|
| 运行不依赖 Python / 不写 CSV | **STATIC_CODE**（配置 `dual_path_csv=false`，全链路无 Python）|

## 10. 哪些还是 PROVISIONAL

| 项 | 状态 |
|---|---|
| `identity_max_error_m=75` | PROVISIONAL，未标定 |
| `identity_margin_m=50` | PROVISIONAL，未标定 |
| `identity_confirm_epochs=5` | PROVISIONAL，未标定 |
| 两端固定延迟补偿量 | 现场必须实测填入，默认 0 无依据 |
| B210 双端实测 / 功率趋势 / 强弱互换 | **NOT_RUN** |
| 可用作现场演示版？ | 代码与逻辑就绪，但**未经任何射频实测**，只能作为**待验证的现场演示候选** |

## 11. 遗留（继承自 `dev_notes/20`，本轮未修）

隧道层在 `ends_valid` 为假时一律输出 `N/A`，因此不受 M11 影响；
但底层 B-1（丢星期间管理器不被 tick）会让隧道层同样收不到 tick，
恢复后可能不重新确认身份。**上 B210 之前建议先修 B-1。**

-- Claude (Opus 5)，2026-08-10
