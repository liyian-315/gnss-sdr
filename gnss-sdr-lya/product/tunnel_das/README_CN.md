# 隧道 DAS 双端覆盖测量与功平配平工具 v1

状态：**SOFTWARE READY FOR HARDWARE VALIDATION。Release 完整构建、35 项产品回归测试和配置预检通过；尚未做 B210 双端实测。**

隧道 A、B 两端同时转发同一颗 GPS L5 卫星、同一 PRN、同一频点。
工作人员带 USRP B210 + 接收天线 + NUC 走到隧道内某个已知测点，启动 GNSS-SDR，
终端每秒直接给出 A 端 CN0、B 端 CN0、两者差值和 B−A 伪距差。

**运行不依赖 Python，不写 CSV，不需要另开任何脚本。**

---

## 最短现场操作

1. 改一行——当前测点距 A 端多少米：

   ```ini
   Tunnel.measurement_position_m=300
   ```

2. 启动：

   ```bash
   ./gnss-sdr --config_file=product/tunnel_das/conf/gps_l5_tunnel_dual_end_b210.conf
   ```

3. 看终端，等 `state=RELIABLE identity=RELIABLE`。

4. 读 `end_a_cn0_db_hz`、`end_b_cn0_db_hz`、`cn0_delta_a_minus_b_db`、
   `pseudorange_delta_b_minus_a_m`。

启动时会先打印一行站点回执，**先确认它和现场一致再看数据**：

```
TUNNEL_DAS_CONFIG length_m=1000.0 position_m=300.0 distance_to_a_m=300.0 distance_to_b_m=700.0 end_a_name=END_A end_b_name=END_B end_a_fixed_delay_m=0.0 end_b_fixed_delay_m=0.0 expected_delta_b_minus_a_m=400.0 prn=18
```

---

## 现场输出

```
TUNNEL_DAS_STATUS version=1 position_m=300.0 prn=18 state=RELIABLE identity=RELIABLE
end_a_path=0 end_b_path=1 end_a_cn0_db_hz=42.60 end_b_cn0_db_hz=39.80
cn0_delta_a_minus_b_db=2.80 end_a_pseudorange_m=20000000.000
end_b_pseudorange_m=20000400.000 pseudorange_delta_b_minus_a_m=400.000
expected_delta_b_minus_a_m=400.0 delta_residual_m=0.000 end_a_doppler_hz=-1200.000
end_b_doppler_hz=-1199.000 path0_cn0_db_hz=42.60 path1_cn0_db_hz=39.80
identity_error_m=0.0 identity_margin_m=800.0 identity_confirm=3 reacquisition_count=0
```

（实际是一整行，这里为了阅读折行。）

无法可靠区分两端时：

```
TUNNEL_DAS_STATUS version=1 position_m=500.0 prn=18 state=UNRESOLVED identity=UNKNOWN
end_a_path=N/A end_b_path=N/A end_a_cn0_db_hz=N/A end_b_cn0_db_hz=N/A
cn0_delta_a_minus_b_db=N/A ... pseudorange_delta_b_minus_a_m=N/A ...
path0_cn0_db_hz=41.20 path1_cn0_db_hz=40.90 identity_error_m=... identity_margin_m=...
```

`path0_cn0_db_hz` / `path1_cn0_db_hz` 始终输出，是**诊断量**，
说明接收机确实在跟两路——但**它们没有被标成 A/B，不要当成 A 端/B 端读**。

第二端丢失时 `state=LOST`，A/B 正式字段立刻变 `N/A`，不会继续显示上一次的 B 端值。

---

## 字段定义（方向固定，不会时而 A−B 时而 B−A）

| 字段 | 定义 |
|---|---|
| `cn0_delta_a_minus_b_db` | `END_A CN0 − END_B CN0`。正值 = A 端在当前测点更强 |
| `pseudorange_delta_b_minus_a_m` | `END_B 伪距 − END_A 伪距` |
| `expected_delta_b_minus_a_m` | `(d_B + delay_B) − (d_A + delay_A)`，其中 `d_A = position_m`，`d_B = length_m − position_m` |
| `delta_residual_m` | 实测 `pseudorange_delta_b_minus_a_m` − `expected_delta_b_minus_a_m` |
| `identity_error_m` | 较优身份假设与预期时延差的偏差 |
| `identity_margin_m` | 两种身份假设的代价差，越小越难区分 |

**CN0 的含义**：这是 GNSS-SDR tracking 输出的载噪比，用于在**同一台接收机、同一测点、
同一 PRN** 下比较两端信号的相对覆盖强弱。**它不是绝对 RF 接收功率 dBm，
本工具不是校准功率计。** 跨测点、跨设备、跨时间的绝对比较不成立。

---

## END_A / END_B 是怎么定的

`path0` / `path1` 是捕获域的**主峰 / 第二峰**，不是隧道两端，功率变化或重捕后可能互换。
本工具在双路径接收机之上加了一层独立的 `TunnelEndAssociation`：

1. 由测点位置和两端固定延迟算出 `expected_delta_b_minus_a_m`；
2. 两种排列各算一次误差：`path0=A` 时观测差为 `+delta_m`，`path1=A` 时为 `−delta_m`；
3. 取误差小的一种，但必须同时满足
   `identity_error_m ≤ Tunnel.identity_max_error_m` 且
   `identity_margin_m ≥ Tunnel.identity_margin_m`；
4. 还要连续 `Tunnel.identity_confirm_epochs` 个历元一致，才从 `CANDIDATE` 升到 `RELIABLE`；
5. **身份只看时延几何，不看谁的 CN0 大。** 两端强弱互换不会让 A/B 标签跟着换。
6. 若 `path0/path1` 真的互换，标签会跟着翻，从而让 **END_A 始终指向同一个物理端**；
   翻转需要重新确认，确认期间输出 `CANDIDATE` + `N/A`。
7. 发生重捕（`reacquisition_count` 变化）后必须重新确认。

只有底层 `DUALPATH_STATUS` 已经是 `RELIABLE` 时，`identity` 才允许是 `RELIABLE`。

**如果 `identity` 长期 `UNKNOWN` 而 `identity_error_m` 稳定偏大**，
多半是两端固定链路延迟没补偿：把差值填进
`Tunnel.end_a_fixed_delay_m` / `Tunnel.end_b_fixed_delay_m`。

---

## 隧道中点附近

越靠近中点，`expected_delta_b_minus_a_m` 越接近 0，两种身份解释就越无法区分，
同时两路码延迟也越接近当前接收机的分离能力下限。

**本工具的双端同时在线监测只适用于当前 L5 双路径接收机能够可靠分离的测点。
在两端时延过近的位置，输出 `UNRESOLVED`。**

这是设计上的诚实输出，不是故障。v1 不引入 MEDLL、超相关、阵列、双 RX、
Python 拟合或任何亚码片算法来强行解决中点。

详见 [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)。
