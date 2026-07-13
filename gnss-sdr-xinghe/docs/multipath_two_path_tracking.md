# 同一颗卫星的双路径捕获与跟踪

本实现让同一颗卫星使用两个独立的 GNSS-SDR Channel：`signal_path=0` 捕获相关搜索面的最强峰，`signal_path=1` 排除最强峰附近的码相位主瓣后捕获第二个独立峰。两个 Channel 随后分别运行现有的载波环、码环、遥测解码和观测量计算，因此会产生两套 `CN0_dB_hz`、`Carrier_Doppler_hz`、`Code_phase_samples` 和 `Pseudorange_m`。

## GPS L1 C/A 配置示例

下面用 PRN 11 演示。每颗需要双路径跟踪的卫星都要占用两个 Channel，并在两个 Channel 上配置相同的 PRN。删除固定卫星配置后，`Channels_1C.signal_paths=2` 会让动态调度器自动为候选 PRN 建立 path 0/path 1 两个条目；Channel 数量应设置为希望同时跟踪的卫星数的两倍。

```ini
Channels_1C.count=2
Channels_1C.signal_paths=2
Channels.in_acquisition=2

Channel0.satellite=11
Channel0.signal_path=0
Channel1.satellite=11
Channel1.signal_path=1

Acquisition_1C.implementation=GPS_L1_CA_PCPS_Acquisition_Fine_Doppler
Acquisition_1C.item_type=gr_complex
Acquisition_1C.coherent_integration_time_ms=1
Acquisition_1C.threshold=2.5
Acquisition_1C.doppler_max=10000
Acquisition_1C.doppler_step=500
Acquisition_1C.max_dwells=5

# 以码片为单位的峰保护区半宽。1.0 表示排除最强峰左右各约 1 chip。
Acquisition_1C.second_peak_exclusion_chips=1.0

Tracking_1C.implementation=GPS_L1_CA_DLL_PLL_Tracking
Tracking_1C.item_type=gr_complex

Observables.implementation=Hybrid_Observables
Observables.dump=true
Observables.dump_filename=./observables.dat
```

同样的 `signal_path` 和 `second_peak_exclusion_chips` 配置也适用于使用通用 `pcps_acquisition` 后端的信号。当前已直接支持：

- 通用软件 PCPS 捕获后端；
- `GPS_L1_CA_PCPS_Acquisition_Fine_Doppler`。

FPGA、OpenCL、QuickSync、Tong、assisted acquisition 等独立捕获实现仍只选择最强峰，使用它们时 `signal_path=1` 不会得到第二径。

## 输出和 PVT

`Gnss_Synchro.Signal_Path`（Protobuf 字段 `signal_path`）用于区分两条径。观测量 dump、Monitor、TrackingMonitor 和 AcquisitionMonitor 会保留两个 Channel 的数据。第二径不会送入 RTKLIB PVT/RTCM；否则同一颗卫星的两条相关观测会被误当作两颗独立卫星，导致定位解算的统计模型错误。

## 分辨率与参数限制

这是一种“相关面双峰 + 两套独立跟踪环”的实现，只适用于搜索面上已经能分开的两条径。`second_peak_exclusion_chips` 是保护区半宽：

- 太大时，近距离反射峰会被一起排除；
- 太小时，同一个主瓣的相邻采样或旁瓣会被误认为第二条径；
- 应结合前端带宽、采样率和实际相关面 dump 调整，建议先从 `1.0` 开始，再逐步减小。

当两条径的时延差小于接收机相关函数的可分辨宽度时，搜索面通常只有一个畸变主峰，两套普通 DLL 也可能最终收敛到同一位置。此时需要信号抵消、MEDLL/ML、稀疏重构等联合多径估计算法，不能仅靠寻找第二大采样点可靠分离。
