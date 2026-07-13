# 02 · 二维谱峰搜索（PCPS 信号捕获）详解 ★核心★

> **本篇是全项目最重要的一篇。** 讲清楚 GNSS-SDR 怎么做"二维谱峰搜索"（= 信号捕获 Acquisition）。
> 改捕获算法、做多径识别，都要先读这篇。
>
> **对应源码**：`src/algorithms/acquisition/gnuradio_blocks/pcps_acquisition.cc`（872 行）+ 同名 `.h`（251 行）
> 配置类：`src/algorithms/acquisition/libs/acq_conf.h`

## 本篇小目录
1. 什么是"二维"，两个维度怎么搜
2. 数据结构：二维幅度网格 & 关键成员
3. 核心算法逐步拆解（`doppler_grid` 是心脏）
4. 峰值搜索与检验统计量（两种方法）★多径切入点★
5. 门限计算（CFAR）
6. 两步捕获（粗搜 + 精搜多普勒）
7. GNU Radio 调度：`general_work` 状态机与线程模型
8. 结果去哪了（写入 Gnss_Synchro、通知 FSM）
9. 与多径/多源改造的关系（承上启下）

---

## 1. 什么是"二维"，两个维度怎么搜

捕获要同时估计两个未知量，构成一个二维搜索空间：

```
          码相位 (code phase / 时延)  →  用 FFT「并行」一次算完一整行
        ┌─────────────────────────────────────────────┐
 多普勒 │                                               │
 频率   │        d_magnitude_grid[doppler][code]        │   ← 这张二维网格就是「谱峰搜索面」
 (串行) │        每个格子 = |相关值|²                    │
   ↓    │                                               │
        └─────────────────────────────────────────────┘
                    找全局最大格子 = 谱峰
```

- **多普勒维（串行搜索）**：外层 `for` 循环，从 `-doppler_max + doppler_center` 到 `+doppler_max`，
  步进 `doppler_step`，共 `d_num_doppler_bins` 个频率 bin。每个 bin 对应一个"载波剥离"复指数。
  - bin 数：`d_num_doppler_bins = ceil(2*doppler_max / doppler_step)`（`pcps_acquisition.cc:113`）
  - 各 bin 的载波剥离向量预先算好存 `d_grid_doppler_wipeoffs`（`update_grid_doppler_wipeoffs()`, line 284）
- **码相位维（并行搜索）**：不逐个码相位试，而是用 **FFT 圆周相关**一次性算出**所有**码相位的相关值。
  这就是 "Parallel Code Phase Search" 名字的来历。长度 = `d_effective_fft_size`（≈ 一个码周期的样点数）。

> 直觉：时域圆周相关 = 频域相乘。所以"本地码 FFT 的共轭 × 接收信号 FFT，再 IFFT"就得到了
> 该多普勒下、**全部码相位**的相关序列——一次 FFT+IFFT 顶替了成千上万次逐点相关。

---

## 2. 数据结构：二维幅度网格 & 关键成员

（定义见 `.h`，初始化见 `.cc` 构造函数 `pcps_acquisition.cc:101-188`）

| 成员 | 含义 | 维度/类型 |
|------|------|-----------|
| `d_magnitude_grid` | **★二维搜索面★**：`[doppler_index][code_phase]` 的 \|相关\|² | `vector<vector<float>>`，`[d_num_doppler_bins][d_fft_size]` |
| `d_grid_doppler_wipeoffs` | 每个多普勒 bin 的载波剥离复指数（预计算） | `[d_num_doppler_bins][d_fft_size]` complex |
| `d_fft_codes` | 本地 PRN 码的 FFT 的**共轭**（相关用） | `[d_fft_size]` complex |
| `d_fft_if` / `d_ifft` | 正向 FFT / 逆向 IFFT 计算器 | GNU Radio FFT |
| `d_data_buffer` | 攒够一个处理长度的输入采样 | `[d_consumed_samples]` |
| `d_input_power` | 输入噪声功率估计（CFAR 用） | float |
| `d_threshold` | 检测门限 | float |
| `d_num_doppler_bins` | 多普勒 bin 数 | uint32 |
| `d_doppler_center` | 多普勒中心（外部辅助/assisted 时非 0） | int32 |

尺寸关系（构造函数，line 108-113）：
- `d_consumed_samples = sampled_ms * samples_per_ms * (bit_transition_flag ? 2 : 1)`
- `d_fft_size`：正常 = `d_consumed_samples`；若做线性相关(padding)则 = `2×`
- `d_effective_fft_size`：`bit_transition_flag` 时取一半（overlap-save 处理比特翻转）

内部结果小结构体 `AcquisitionResult`（`.h` 内）：`{ doppler, index_time(码相位下标), test_statistics, sample_count, positive_acq, index_doppler }`。

---

## 3. 核心算法逐步拆解（`doppler_grid` 是心脏）

### 3.1 准备本地码：`set_local_code()`（line 218-251）
把本地 PRN 码放进 FFT 输入缓冲（视配置在前面补零做线性相关），执行 FFT，**取共轭**存入 `d_fft_codes`：
```cpp
d_fft_if->execute();                                   // 本地码 FFT
volk_32fc_conjugate_32fc(d_fft_codes.data(), d_fft_if->get_outbuf(), d_fft_size);  // 共轭
```
> 共轭是因为相关 = 卷积的时间反转；频域里表现为一路取共轭再相乘。

### 3.2 主循环：`doppler_grid(in)`（line 522-560）★心脏★
对每个多普勒 bin `doppler_index`：
```cpp
// ① 载波剥离：接收信号 × 该多普勒的复指数
volk_32fc_x2_multiply_32fc(d_fft_if->get_inbuf(), in, grid_doppler_wipeoffs[doppler_index].data(), d_fft_size);
// ② 接收信号 FFT
d_fft_if->execute();
// ③ 频域相乘：信号FFT × 本地码FFT共轭  →  圆周相关的频域
volk_32fc_x2_multiply_32fc(d_ifft->get_inbuf(), d_fft_if->get_outbuf(), d_fft_codes.data(), d_fft_size);
// ④ IFFT，回到时域 → 得到「该多普勒下、所有码相位」的相关序列
d_ifft->execute();
// ⑤ 取模平方，写入/累加到二维网格的这一行
volk_32fc_magnitude_squared_32f(d_magnitude_grid[doppler_index].data(), d_ifft->get_outbuf() + offset, d_effective_fft_size);
//    非相干积分：若不是第一个 dwell，则累加而非覆盖（line 549-553）
```
跑完这个循环，`d_magnitude_grid` 就是完整的二维谱峰搜索面。若开了 dump，会同时拷进 `d_grid`（Armadillo 矩阵）以便导出 .mat。

### 3.3 载波剥离向量怎么来：`update_local_carrier()`（line 275-281）
```cpp
phase_step_rad = 2π * freq / fs_in;
volk_gnsssdr_s32f_sincos_32fc(...);   // 生成 e^{-j 2π f n / fs}
```
`update_grid_doppler_wipeoffs()`（line 284-291）对所有 bin 批量生成，多普勒取值：
`doppler = -doppler_max + d_doppler_center + doppler_step * doppler_index`。

---

## 4. 峰值搜索与检验统计量（两种方法）★多径切入点★

入口 `compute_statistics()`（line 563-577）按 `d_use_CFAR_algorithm_flag` 二选一：

### 4.1 CFAR：`max_to_input_power_statistic()`（line 409-449）
1. 遍历每个多普勒 bin，用 `volk_gnsssdr_32f_index_max_32u` 找该行最大值；跨行取全局最大 → 谱峰。
2. **噪声功率估计**很巧妙：取"对面"多普勒 bin `index_opp = (index_doppler + N/2) % N`（离主峰最远的频率），
   对整行求平均当作噪声底 `d_input_power`（line 430-431）。
3. 检验统计量 `test_statistics = grid_maximum / d_input_power`。

### 4.2 最高峰/次高峰：`first_vs_second_peak_statistic()`（line 452-519）★★多径直接相关★★
1. 找全局最高峰 `firstPeak`（及其多普勒 bin、码相位下标）。
2. **在同一多普勒 bin 内，排除主峰 ±1 码片**（`d_samplesPerChip`）的范围（line 484-509，环形边界处理），
   在剩余部分找**次高峰** `secondPeak`。
3. 检验统计量 `test_statistics = firstPeak / secondPeak`。

> **为什么这对多径重要**：多径（反射信号）通常滞后直射信号一小段（常在 1~1.5 码片内），
> 在相关面上表现为**主峰的畸变、肩峰、或邻近的次峰**。这个函数已经在做"排除主峰邻域找次峰"的逻辑，
> 是我们插入多径判别（比如：看主峰邻域的能量分布、峰形对称性、次峰位置/幅度比）的**最自然位置**。
> 详见文档 04。

### 4.3 结果换算
两个函数都把峰的多普勒下标、码相位下标换算回物理量（Hz、样点），填进 `AcquisitionResult`。

---

## 5. 门限计算（CFAR）

匿名命名空间的 `compute_threshold()`（line 52-56）：
```cpp
num_bins = effective_fft_size * num_doppler_bins;
threshold = 2.0 * gamma_p_inv(2.0 * max_dwells, pow(1 - pfa, 1/num_bins));
```
- 基于**卡方分布**（相关幅度平方在噪声下近似 χ²），用不完全 Gamma 反函数按给定虚警概率 `pfa` 求门限。
- 只有当 conf 里 `pfa > 0` 才用这个公式；否则直接用固定 `threshold`（`pcps_acquisition.cc:116`）。
- 两步捕获有各自门限：`d_threshold` / `d_threshold_step_two`（`get_threshold()`, line 731 按当前步返回）。

---

## 6. 两步捕获（粗搜 + 精搜多普勒）

由 `d_acq_parameters.make_2_steps` 开启，逻辑在 `handle_threshold_reached()`（line 605-632）：
1. **第一步（粗）**：用宽多普勒范围 + 大步进搜到一个峰，超门限后**不立即宣告成功**，
   而是把峰的多普勒设为中心 `d_doppler_center_step_two`，切换 `d_step_two=true`，重置非相干计数。
2. **第二步（精）**：在峰附近用 `num_doppler_bins_step2` 个更细的 `doppler_step2` 重搜（`update_grid_doppler_wipeoffs_step2()`, line 294），
   再次超门限才 `send_positive_acquisition()` 宣告成功。
> 好处：粗搜省时间，精搜提高多普勒精度。对我们做多径/精定位有参考价值（更细的分辨率有助分辨近距多径）。

---

## 7. GNU Radio 调度：`general_work` 状态机与线程模型

`general_work()`（line 749-853）是 GNU Radio 调度器反复调用的入口，内部一个小状态机 `d_state`：

- **state 0（复位）**：清零 Gnss_Synchro 的 Acq_* 字段，转 state 1。
- **state 1（攒数据）**：把输入采样拷进 `d_data_buffer`，攒够 `d_consumed_samples` 后转 state 2。
- **state 2（触发计算）**：调用 `acquisition_core()`。
  - `blocking=true`：同线程直接算（`acquisition_core`）。
  - `blocking=false`：起一个 `gr::thread::thread` worker 异步算，`d_worker_active=true`。

`acquisition_core(sample_count)`（line 648-728）串起全流程：
数据搬运 → `doppler_grid(in)` → `compute_statistics()` → `update_synchro()` → 比较门限
→ `handle_threshold_reached()` / `handle_integration_done()` → 需要则 `dump_results()`。

**并发注意**：`d_setlock` 互斥锁保护与调度线程共享的状态；`doppler_grid`/`compute_statistics` 这段耗时计算
在**解锁**状态下跑（line 677 `lk.unlock()` … line 684 `lk.lock()`），算完再上锁写回。改造时若加共享状态要注意锁。

---

## 8. 结果去哪了（写入 Gnss_Synchro、通知 FSM）

`update_synchro()`（line 580-602）把结果写进共享的 `d_gnss_synchro`：
```cpp
Acq_delay_samples = fmod(index_time, samples_per_code);   // 码相位（样点）
Acq_doppler_hz    = result.doppler;                       // 多普勒（Hz）
Acq_samplestamp_samples = ...;                            // 时间戳（样点）
```
成功时 `send_positive_acquisition()`（line 318-341）：
- 若 channel FSM 已设置，直接 `d_channel_fsm.lock()->Event_valid_acquisition()` 触发**捕获→跟踪交接**；
- 否则用消息端口 `message_port_pub("events", 1)` 通知（`1=成功, 2=失败, 0=停止`）。
- 若开了 `enable_monitor_output`，把 Gnss_Synchro 推入 `d_monitor_queue` 供外部监视。

失败：`send_negative_acquisition()`（line 344-351）发 `2`。

> 交接后，tracking 用 `Acq_delay_samples` / `Acq_doppler_hz` 作为码环/载波环初值。见文档 03。

---

## 9. 与多径/多源改造的关系（承上启下）

- **多径识别（本模块内）**：最直接的落点是 §4.2 的峰形/次峰分析，以及 §3.2 完整的 `d_magnitude_grid`
  相关面（可判峰宽、对称性、肩峰）。但要注意：**捕获阶段分辨率有限**，精细多径判别通常在 **tracking 的多相关器**里做
  （early/late/very-early/very-late 甚至多抽头相关器画相关函数）。两条线并行推进，见文档 04。
- **多源信号**：捕获是"每信号一路"的，多源更多是 **FlowGraph 挂多个 SignalSource + 多 Channel + observables/PVT 融合**
  的架构问题，本模块改动较小。见文档 01（架构）与 04（方案）。

---

*最后更新：2026-07-12 · 基于通读 pcps_acquisition.cc 全文 · 待补：跑一次 dump 看真实相关面 .mat*
