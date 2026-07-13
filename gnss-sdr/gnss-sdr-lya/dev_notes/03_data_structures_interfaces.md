# 03 · 关键数据结构与接口（参考手册）

> 查字段、传参、扩展结构体、加配置项时翻这篇。偏参考性质，不必通读。

## 本篇小目录
1. `Gnss_Synchro`：贯穿全链路的同步结构体
2. `Acq_Conf`：捕获配置参数
3. `AcquisitionInterface`：捕获块对外接口
4. 扩展这些结构/接口时的注意事项

---

## 1. `Gnss_Synchro`（`src/core/system_parameters/gnss_synchro.h`）

一份数据从捕获一路写到 PVT，是**跨模块传值的主载体**。关键字段分组：

**卫星/信号标识**（由 `Channel::set_signal()` 设）
```cpp
char System;          // 系统: 'G'=GPS 'E'=Galileo 'R'=GLONASS 'C'=BeiDou ...
char Signal[3];       // 信号: "1C"=GPS L1 C/A 等
uint32_t PRN;         // 卫星号
int32_t  Channel_ID;  // 通道号
```
**捕获输出**（pcps_acquisition 写，见文档 02 §8）
```cpp
double   Acq_delay_samples;       // 码相位/时延 [样点]
double   Acq_doppler_hz;          // 多普勒 [Hz]
uint64_t Acq_samplestamp_samples; // 捕获完成时间戳 [样点]
uint32_t Acq_doppler_step;        // 多普勒搜索步进 [Hz]
bool     Flag_valid_acquisition;
```
**跟踪输出**
```cpp
int64_t  fs;                       // 采样率
double   Prompt_I, Prompt_Q;       // Prompt 相关器 I/Q
double   CN0_dB_hz;                // 载噪比
double   Carrier_Doppler_hz;       // 跟踪估计的多普勒
double   Carrier_phase_rads;
double   Code_phase_samples;
uint64_t Tracking_sample_counter;
int32_t  correlation_length_ms;
```
**观测量/状态**：`Pseudorange_m`、`RX_time`、`interp_TOW_ms`、`Flag_valid_*` 等。

> **多径改造常在此扩字段**：如加 `Multipath_flag` / `Multipath_delay_chips` / `MEE`（多径估计误差）/ 峰形特征等，
> 让捕获或跟踪算出的多径指标能随结构体流到 observables/PVT。⚠️ 见 §4 注意事项。

---

## 2. `Acq_Conf`（`src/algorithms/acquisition/libs/acq_conf.h`）

捕获块全部配置参数的容器。由 adapter 的 `SetFromConfiguration()` 从 `.conf` 填充。常用字段：

| 字段 | 默认 | 含义 |
|------|------|------|
| `fs_in` | 4e6 | 输入采样率 |
| `doppler_max` / `doppler_min` | ±5000 | 多普勒搜索范围 [Hz] |
| `doppler_step` | 500 | 多普勒步进 [Hz]（决定多普勒 bin 数） |
| `doppler_step2` | 125 | 第二步精搜步进 |
| `num_doppler_bins_step2` | 4 | 第二步 bin 数 |
| `threshold` | 0 | 固定门限（pfa=0 时用） |
| `pfa` / `pfa2` | 0 | 虚警概率（>0 则用 CFAR 算门限） |
| `max_dwells` | 1 | 非相干积分次数 |
| `sampled_ms` / `ms_per_code` | 1 | 处理时长 / 一个码周期时长 |
| `samples_per_chip` | 2 | 每码片样点数（次峰排除范围用） |
| `bit_transition_flag` | false | 处理导航比特翻转（线性相关 padding） |
| `use_CFAR_algorithm_flag` | true | 选峰值/功率法(true) 还是 峰1/峰2 法(false) |
| `make_2_steps` | false | 是否两步捕获 |
| `use_automatic_resampler` | false | 自动重采样 |
| `dump` / `dump_filename` / `dump_channel` | false | 导出相关网格到 .mat（调试/看相关面用！） |
| `enable_monitor_output` | false | 输出 Gnss_Synchro 给外部监视 |

> **加新配置项**（比如多径判别开关/参数）：① 在 `acq_conf.h` 加成员；② 在 `acq_conf.cc::SetFromConfiguration` 里读；
> ③ 在 `pcps_acquisition` 构造函数里取用。三处齐动。

---

## 3. `AcquisitionInterface`（`src/core/interfaces/acquisition_interface.h`）

所有捕获块必须实现的接口（纯虚）：
```cpp
virtual void set_gnss_synchro(Gnss_Synchro*) = 0;   // 绑定共享数据
virtual void set_channel(unsigned int) = 0;
virtual void set_channel_fsm(std::weak_ptr<ChannelFsm>) = 0;  // 绑 FSM 以便交接
virtual void set_local_code() = 0;                  // 生成/装载本地码
virtual signed int mag() = 0;
virtual void reset() = 0;
virtual void stop_acquisition() = 0;
virtual void set_resampler_latency(uint32_t) = 0;
```
对应地，`TrackingInterface`（`tracking_interface.h`）有 `start_tracking()/stop_tracking()/set_gnss_synchro()/set_channel()`。

---

## 4. 扩展这些结构/接口时的注意事项 ⚠️

- **`Gnss_Synchro` 是通过流端口按 `sizeof(Gnss_Synchro)` 传递的 POD**。加字段会改变结构体大小与布局：
  - 所有以 `sizeof(Gnss_Synchro)` 定 item_size 的块（observables 等）会自动跟着变，一般没问题；
  - 但若有**二进制 dump / 网络序列化 / 与外部工具（如 gnss-sdr-monitor）对接**，字段布局变化会破坏兼容性。
  - 建议：新字段加在**末尾**，给默认值（`{}`），减少影响面。
- **改 `pcps_acquisition` 核心**一处生效全信号；若只想对某信号生效，用 conf 开关或在 adapter 层分流。
- **加配置项**记得"三处齐动"（见 §2 末）。
- 结构体定义处附近通常有 `Gnss_Synchro` 的注释和可能的序列化（boost::serialization）定义，改前先看全定义。

---

*最后更新：2026-07-12 · 字段以实际头文件为准（行号随版本略变）*
