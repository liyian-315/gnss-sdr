# 01 · 整体架构总览

> 目的：建立**大局观**——数据从天线/文件到定位结果，经过哪些块，怎么串起来的。
> 改动跨模块、或要理解某个块在链路里的位置时读这篇。细节按需再翻源码。

## 本篇小目录
1. 顶层信号处理链（一图流）
2. Channel（通道）抽象：捕获+跟踪+电文 的容器
3. 捕获→跟踪 的交接机制（FSM）
4. FlowGraph：块是怎么被装配和连线的
5. 配置系统：.conf 如何实例化出这些块
6. 捕获适配器的类层级

---

## 1. 顶层信号处理链（一图流）

```
SignalSource → SignalConditioner →  ┌─ Channel 0 (Acq→Trk→Nav) ─┐
 (文件/USRP)   (类型转换/滤波/重采样) │   Channel 1 ...            │ → Observables → PVT → 输出
                                     └─ Channel N ...            ┘   (伪距/载波)  (RTKLIB定位) (RINEX/NMEA/RTCM)
```

- 装配代码：`src/core/receiver/gnss_flowgraph.cc`，`connect_desktop_flowgraph()`（约 line 479-580）依次连：
  signal_sources → conditioners → channels → observables → pvt，再把它们串起来。
- 关键成员（`gnss_flowgraph.h` ~line 224-228）：`sig_source_[]`、`sig_conditioner_[]`、`channels_[]`、`observables_`、`pvt_`。
- **多源信号在此层体现**：`sig_source_` 是**向量**，可挂多个信号源（多天线/多频点/多星座）。

---

## 2. Channel（通道）抽象

`src/algorithms/channel/adapters/channel.h`（class `Channel`, ~line 60-113）把一路信号的三件套打包：
- `acq_` : `AcquisitionInterface`（捕获）
- `trk_` : `TrackingInterface`（跟踪）
- `nav_` : `TelemetryDecoderInterface`（电文解码）
- `channel_fsm_` : `ChannelFsm`（状态机，协调三者）
- `gnss_synchro_` : 一份贯穿本通道的 `Gnss_Synchro`（共享数据）

连线 `channel.cc::connect()`（~line 88-145）：acq/trk/nav 各自接入 top_block；
trk → nav 同步连接；并注册若干消息端口（acq→FSM "events"、trk→FSM "events"、nav→trk "telemetry_to_trk"）。

---

## 3. 捕获→跟踪 的交接机制（FSM）

`src/algorithms/channel/libs/channel_fsm.cc`。状态：`0=待机 1=捕获 2=跟踪`。
关键跃迁 `Event_valid_acquisition()`（~line 99-110）：
```cpp
if (state_ != 1) return false;
state_ = 2;          // 捕获 → 跟踪
start_tracking();    // 用 Gnss_Synchro 里的 Acq_* 初始化跟踪环
```
由 pcps_acquisition 捕获成功时直接调用（见文档 02 §8）。其它事件：`Event_start_acquisition`(0→1)、
`Event_failed_acquisition_repeat`(1→1 重试)、`Event_failed_acquisition_no_repeat`(1→0)、`Event_failed_tracking_standby`(2→0)。

---

## 4. FlowGraph：块的装配与连线

- `src/core/receiver/gnss_flowgraph.*`：`GNSSFlowgraph` 持有所有块，`connect()` 建图，`start()` 跑 GNU Radio 调度。
- 块都是 GNU Radio block，用消息端口传事件、用流端口传采样/Gnss_Synchro 数组。

---

## 5. 配置系统：.conf 如何实例化出这些块

- INI 风格 `.conf`（`conf/gnss-sdr.conf` 是默认样例，`conf/File_input/` 下有各星座离线样例）。
- `ConfigurationInterface`（`src/core/interfaces/configuration_interface.h`）：统一的 `property(name, default)` 读取接口。
- `GNSSBlockFactory`（`src/core/receiver/gnss_block_factory.*`）：按 `role` 字符串（如 `Acquisition_GPS_L1_CA`）
  + `.implementation`（如 `GPS_L1_CA_PCPS_Acquisition`）实例化对应 C++ 类。
  - **加新算法/新块**要在工厂里登记。改捕获实现名也在这里对应。
- 典型捕获配置段：
  ```ini
  [Acquisition_GPS_L1_CA]
  Acquisition_GPS_L1_CA.implementation=GPS_L1_CA_PCPS_Acquisition
  Acquisition_GPS_L1_CA.doppler_max=8000
  Acquisition_GPS_L1_CA.doppler_step=500
  ; pfa / threshold / make_2_steps / dump 等都在此配（对应 acq_conf.h 字段）
  ```

---

## 6. 捕获适配器的类层级

```
GNSSBlockInterface
   └─ AcquisitionInterface            (src/core/interfaces/acquisition_interface.h)
        └─ BasePcpsAcquisition        (adapters/base_pcps_acquisition.*  —— 通用 PCPS 适配器)
             └─ GpsL1CaPcpsAcquisition (adapters/gps_l1_ca_pcps_acquisition.*  —— 具体信号，负责生成本地码)
                  └─(wraps)→ pcps_acquisition  (gnuradio_blocks/pcps_acquisition.*  —— 真正的算法块，见文档02)
```
- **适配器**（adapter）：读配置、生成本地 PRN 码、把参数塞进 `Acq_Conf`、创建并配置算法块。
- **算法块**（GNU Radio block）：`pcps_acquisition`，干活的地方（二维搜索）。
- 各信号（GPS L1/L2/L5、Galileo E1/E5、BeiDou B1I/B3I、GLONASS、QZSS 等）各有一个 adapter，
  差异主要在**本地码生成**和**参数**，算法块基本复用同一个 `pcps_acquisition`。

> 含义：我们要改的二维搜索**核心逻辑只有一处**（`pcps_acquisition`），改一次全信号受益；
> 若只想对某信号生效，则在其 adapter 或 conf 上开关。

---

*最后更新：2026-07-12 · 基于 Explore 全库扫描 + 交叉验证 · 行号为近似，动手前以实际文件为准*
