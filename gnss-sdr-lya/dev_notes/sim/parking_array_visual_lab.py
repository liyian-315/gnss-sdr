#!/usr/bin/env python3
"""像 MATLAB 脚本一样：只改下面参数区，然后直接运行并看图。"""

from pathlib import Path

import compare_parking_array_geometries as simulation


# ======================== 实验参数区（从这里改） ========================

# 接收机的全局 X 坐标，单位 m。增大表示接收机向图中右侧移动。
RECEIVER_X_M = 0.0
# 接收机的全局 Y 坐标，单位 m。正值表示位于两发射天线连线上方。
RECEIVER_Y_M = 5.0

# 两根发射天线连线中点的全局 X 坐标，单位 m。
TX_CENTER_X_M = 0.0
# 两根发射天线连线中点的全局 Y 坐标，单位 m。
TX_CENTER_Y_M = 0.0
# A、B 两根发射天线的物理间距，单位 m；程序沿 X 轴对称放置它们。
TX_SEPARATION_M = 20.0

# 两路信号相关系数，范围 0.0~1.0：1.0=完全相干，0.0=完全不相关。
SOURCE_CORRELATION = 1.0

# B 路相对 A 路的功率，单位 dB：0=等功率，-6=B 路弱 6 dB。
SOURCE_RATIO_DB = -6.0
# B 路相对 A 路的初始载波相位，单位 deg；会改变完全相干时的叠加峰形。
RELATIVE_PHASE_DEG = 60.0

# 阵列接收信噪比，单位 dB；越低时空间谱越嘈杂、误峰越多。
SNR_DB = 15.0
# 协方差矩阵使用的时间快拍数；越多结果越稳定，但运行时间越长。
SNAPSHOTS = 4096
# 随机噪声种子；保持不变可复现实验，修改后可检查结果是否依赖偶然噪声。
RANDOM_SEED = 20260813

# 相邻阵元间距，以载波波长为单位；0.5=半波长，L5 上约为 12.7 cm。
ELEMENT_SPACING_WAVELENGTHS = 0.5
# 阵列相对全局 X 轴逆时针旋转角，单位 deg；用于测试阵列安装朝向。
ARRAY_ORIENTATION_DEG = 0.0

# 是否弹出交互图窗：True=弹窗并保存，False=只保存图片。
SHOW_FIGURES = True
# 图片和 JSON 结果的保存目录；相对路径从仓库根目录开始计算。
OUTPUT_DIR = Path("dev_notes/sim/results/coherent_music_parking")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    simulation.run_single_point(
        output_dir=OUTPUT_DIR,
        seed=RANDOM_SEED,
        receiver_xy=(RECEIVER_X_M, RECEIVER_Y_M),
        tx_center_xy=(TX_CENTER_X_M, TX_CENTER_Y_M),
        tx_separation_m=TX_SEPARATION_M,
        correlation=SOURCE_CORRELATION,
        source_ratio_db=SOURCE_RATIO_DB,
        relative_phase_deg=RELATIVE_PHASE_DEG,
        snr_db=SNR_DB,
        snapshots=SNAPSHOTS,
        spacing_wl=ELEMENT_SPACING_WAVELENGTHS,
        orientation_deg=ARRAY_ORIENTATION_DEG,
        show=SHOW_FIGURES,
    )


if __name__ == "__main__":
    main()
