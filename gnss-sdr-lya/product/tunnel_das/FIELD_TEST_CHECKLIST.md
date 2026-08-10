# Tunnel DAS Field Test Checklist

> Hardware validation only. Do not mark this checklist complete without NUC + B210 + both tunnel ends.

## 1. Edit The Field Block

- Set `Tunnel.measurement_position_m` to distance from physical END_A.
- Set both `Channel0.satellite` and `Channel1.satellite` to the same L5 PRN.
- Set `SignalSource.device_serial` to the connected B210.
- Set the approved fixed `SignalSource.gain`; do not tune product thresholds on site.
- Leave fixed-delay values at the reviewed calibration values. Never learn them automatically from one run.

## 2. Start Both Ends And Receiver

```bash
./gnss-sdr --config_file=product/tunnel_das/conf/gps_l5_tunnel_dual_end_b210.conf
```

Confirm the first `TUNNEL_DAS_CONFIG` line shows the intended length, position, distances, delays, expected delta, and PRN. Stop on any `TUNNEL_CONFIG_ERROR`.

## 3. Establish The Pair

- Wait for `state=RELIABLE identity=RELIABLE`.
- Record `end_a_cn0_db_hz`, `end_b_cn0_db_hz`, and `cn0_delta_a_minus_b_db`.
- Record `pseudorange_delta_b_minus_a_m`, `expected_delta_b_minus_a_m`, and `delta_residual_m`.
- Treat `N/A`, `UNRESOLVED`, and `UNKNOWN` as honest non-measurements, not values to tune away.

## 4. Loss And Recovery Test

1. Turn off physical END_B.
2. Confirm `state=DEGRADED` then `state=LOST`.
3. Confirm `identity=UNKNOWN`, END_B and all A/B delta fields are `N/A`.
4. Confirm END_A tracking can continue while END_B is absent.
5. Turn END_B on again.
6. Confirm recovery starts at `CANDIDATE`, then becomes `RELIABLE` only after fresh confirmations.
7. Confirm `reacquisition_count` increments once.

## 5. Power Balance Check

- Adjust the approved A/B transmit powers one end at a time.
- Confirm the CN0 trend follows the adjustment.
- Confirm physical END_A/END_B labels do not follow whichever path is stronger.
- Save the terminal log and note position, PRN, B210 serial, gain, end powers, time, and operator.

Result: `HARDWARE_PASS` / `HARDWARE_FAIL` / `NOT_RUN` (circle one). This repository currently claims none of them.
