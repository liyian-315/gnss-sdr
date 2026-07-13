# 06 · B1C + USRP B210 双路径运行说明

## 1. 当前交付

- 运行配置：`dev_notes/sim/my_bds_b1c_multipath.conf`
- 设备：USRP B210，UHD 直采，不需要先采集成固定文件
- 信号：BeiDou B1C，内部使用 `C1` 作为两字符信号名
- 通道：`Channels_C1.count=24`，`Channels_C1.signal_paths=2`
- 机制：每颗星分配两条路径，`Signal_Path=0` 跟踪主峰，`Signal_Path=1` 自动使用捕获阶段接受的第二峰

## 2. 已接入的代码路径

- B1C 跟踪适配器：`src/algorithms/tracking/adapters/beidou_b1c_dll_pll_tracking.*`
- B1C 跟踪注册：`src/core/receiver/gnss_block_factory.cc`
- B1C 本地码接入 VEML 跟踪：`src/algorithms/tracking/gnuradio_blocks/dll_pll_veml_tracking.cc`
- 两路径通道分配：`src/core/receiver/gnss_flowgraph.cc`
- 路径字段传递：`Gnss_Signal::signal_path` 和 `Gnss_Synchro::Signal_Path`
- PVT 保护：`rtklib_pvt_gs.cc` 只把 `Signal_Path=0` 送入 RTKLIB，第二径留给 dump/monitor 分析

## 3. 关键限制

B1C acquisition 和 tracking 已接入，但 native B1C CNAV1 telemetry decoder 还没有实现。

因此：

- 可以直接从 B210 采集并做 B1C 多径捕获、两路径跟踪、tracking dump、observables/monitor 输出。
- 如果没有 B1C CNAV1 电文解码，带 TOW 的有效伪距和 PVT 可能仍然无效。
- 当前配置里 `TelemetryDecoder_C1.implementation=BEIDOU_B1C_Dummy_Telemetry_Decoder` 只是直通占位，用于保持标准 channel 链路可实例化，不代表已经完成 B1C 电文解码。

## 4. Ubuntu 测试机编译

建议把源码放在 Linux 本地磁盘，比如 `~/lya/gnss-sdr/gnss-sdr-lya`，不要在 `/mnt/d` 这类 Windows 挂载盘上编译，大 C++ 文件会非常慢。

```bash
cd ~/lya/gnss-sdr/gnss-sdr-lya
rm -rf build
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DENABLE_UNIT_TESTING=OFF
cmake --build build --target gnss-sdr -j"$(nproc)"
./build/src/main/gnss-sdr --version
```

## 5. B210 运行

```bash
uhd_find_devices
uhd_usrp_probe

cd ~/lya/gnss-sdr/gnss-sdr-lya
GLOG_logtostderr=1 ./build/src/main/gnss-sdr \
  --config_file=dev_notes/sim/my_bds_b1c_multipath.conf \
  2>&1 | tee b1c_b210_run.log
```

## 6. 常调参数

- `SignalSource.gain=50`：B210 增益，现场可在 40 到 60 之间试。
- `SignalSource.antenna=RX2`：按实际接线改成 `TX/RX` 或 `RX2`。
- `SignalSource.sampling_frequency=4000000`：B210 稳定起步值；提高采样率会增加 CPU 压力。
- `Channels.in_acquisition=24`：全通道同时捕获，CPU 压力大时可降到 4 或 8。
- `Acquisition_C1.multipath_threshold_fraction=0.25`：第二峰门限，弱反射可降低，误检多则提高。
- `Acquisition_C1.multipath_max_delay_chips=5`：第二峰只在主峰邻域内找，避免把噪声峰当多径。

## 7. 输出怎么看

- 控制台/日志：搜索 `MULTIPATH`，看每颗星的第二峰 delay、ratio、doppler。
- tracking dump：`bds_b1c_tracking_ch_*`，按 channel 区分两条路径。
- observables dump：`bds_b1c_observables.dat`。
- monitor UDP：proto 里有 `signal_path` 字段，可区分主径/第二径。

## 8. 踩坑

- `cmake -S . -B build =DCMAKE_BUILD_TYPE=Release` 是错的，应该是 `-DCMAKE_BUILD_TYPE=Release`。
- 如果拷贝了旧 build 目录，先 `rm -rf build`，否则 CMakeCache 会指向旧机器路径。
- B1C 字符串 `B1C` 是三字符，而 `Gnss_Synchro.Signal` 只有两字符，所以运行链路里使用 `C1`。
- 第二径不是送进 RTKLIB 的另一颗卫星。反射径伪距偏长，直接进 PVT 通常会变差。
