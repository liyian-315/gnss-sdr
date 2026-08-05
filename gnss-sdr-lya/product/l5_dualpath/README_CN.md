# GPS L5 Dual-Path Receiver v1

状态：**CODE COMPLETE，尚未完成正式文件回放和实时 B210 产品验收。**

本产品在捕获相关面已存在两个明确分离峰时，为同一 GPS L5 PRN 启动两条独立 tracking 链，并由 C++ 持续输出两路伪距、CN0、Doppler、伪距差和质量状态。运行不依赖 Python。

## 快速运行

先编辑配置顶部附近的 B210 序列号、增益和两个相同的 PRN，然后执行一行命令：

```bash
./bin/gnss-sdr --config_file=conf/l5_dualpath_b210_20msps.conf 2>&1 | tee l5_dualpath_run.log
```

低负载但带宽受限的模式：

```bash
./bin/gnss-sdr --config_file=conf/l5_dualpath_b210_10msps.conf 2>&1 | tee l5_dualpath_10m_run.log
```

文件回放前，编辑 `SignalSource.filename`、PRN 和采样率：

```bash
./bin/gnss-sdr --config_file=conf/l5_dualpath_file_replay.conf 2>&1 | tee l5_dualpath_replay.log
```

运行前检查及限时测试：

```bash
bash scripts/check_runtime.sh ./bin/gnss-sdr conf/l5_dualpath_b210_20msps.conf --run-seconds 60
```

## 输出

- `DUALPATH_OBS`：兼容输出，每条有效 tracking 路径的瞬时观测；
- `DUALPATH_PAIR`：同 system/signal/PRN 且接收时间对齐时的兼容配对；
- `DUALPATH_STATUS version=1`：产品状态，包含 `SEARCHING`、`CANDIDATE`、`RELIABLE`、`DEGRADED`、`NO_SECOND_SOURCE`、`LOST`；
- `dual_path_status.csv`：可选的低频 C++ CSV，不是原始 IQ 或大体量 dump。

第二径不存在时正式字段输出 `N/A`。`reacquisition_count` 表示管理器观察到 path1 从 LOST 恢复成功的次数，不是 acquisition 内部每次搜索尝试的总数。

## 默认行为

- 推荐 20 Msps；10 Msps 仅用于 CPU/USB 压力较大的长跑场景；
- L5Q pilot tracking，CNAV 仍由 L5 数据通道解码；
- acquisition 为 realtime nonblocking，避免捕获计算停止消费 UHD 数据；
- acquisition/tracking/dense/observables/raw-IQ dump 全部关闭；
- PVT 只消费 `Signal_Path=0`，第二径不会进入定位解算；
- 所有产品门限都有静态配置，但当前数值仍需正式回放矩阵校准。

## 构建与打包

在源码根目录执行：

```bash
bash product/l5_dualpath/scripts/build_release.sh
```

产物位于 `dist/`。在实时 B210 验收完成前，脚本生成 `code-complete` 包，不生成或宣称 `v1.0.0-rc1`。

详细限制见 [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)，测试协议见 [tests/README.md](tests/README.md)。
