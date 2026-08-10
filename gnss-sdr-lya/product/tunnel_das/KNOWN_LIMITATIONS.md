# Known Limitations — Tunnel DAS Balance Tool v1

1. 只适用于当前 GPS L5 双路径接收机**能够可靠分离**的测点。两端时延过近时输出
   `UNRESOLVED` / `IDENTITY_UNKNOWN`，这是正确行为，不是故障。
2. 隧道中点附近 `expected_delta_b_minus_a_m → 0`，两种 A/B 排列在几何上等价，
   身份**必然** `UNKNOWN`。中点覆盖测量不在 v1 范围内。
3. CN0 是 GNSS-SDR tracking 的载噪比估计，**只用于同一接收机、同一测点、同一 PRN 下
   两端的相对比较**。不是绝对 RF 功率 dBm，不能替代校准功率计，不能跨测点/跨设备直接比。
4. 本轮**不定义** `BALANCED` 之类的判定阈值（例如 ±1 dB）。工具只输出
   `cn0_delta_a_minus_b_db` 数值，配平判据由现场标准另行规定。
5. `Tunnel.identity_max_error_m` / `identity_margin_m` / `identity_confirm_epochs`
   目前是 **PROVISIONAL**，未经现场标定。
6. 两端固定链路延迟默认 0。真实 DAS 有馈线、放大器、数字链路延迟，且两端不一定相等；
   未补偿时身份判定可能长期 `UNKNOWN`。补偿值必须现场实测填入。
7. 测点位置由人工输入，v1 不做自动定位；位置填错会直接导致身份判错或判不出来。
8. 第二端（`path1`）不进入 PVT，主径 `path0` 仍照常参与原有定位解算。
9. 继承自 L5 双路径接收机 v1 的全部限制：不承诺亚码片 / 0.5 chip 分离、不承诺阵列测向、
   不承诺三路及以上、不承诺最小可分距离数值。见
   `../l5_dualpath/KNOWN_LIMITATIONS.md`。
10. 继承自第二轮审查（`dev_notes/20`）的未关闭项，**在真实实验中必须留意**：
    - **B-1 复开**：整机所有通道同时无效（丢星）期间管理器收不到 tick，
      恢复后第一个历元可能重发陈旧 `RELIABLE`。表现为 `track_age_s` 跳变而
      `reacquisition_count` 不增；隧道层的 `identity` 也会因此可能不重新确认。
    - **M11**：底层 `DUALPATH_STATUS` 在配对被质量门拒绝时把 `delta_m` 渲染成
      `0.000` 而非 `N/A`。隧道层不受影响（`ends_valid` 为假时一律输出 `N/A`），
      但看底层行时要注意。
    - **M4**：`multipath_min_delay_chips=1.25` 实际生效约 **60 m**（20 与 10 Msps 相同），
      即捕获域的物理分离下限约 60 m，而不是 36.6 m。
11. 尚未执行：B210 双端实测、功率阶梯（0 / −3 / −6 dB）趋势验证、A/B 强弱互换验证、
    30 分钟长跑。因此本工具**尚不能作为验收结论的依据**。
