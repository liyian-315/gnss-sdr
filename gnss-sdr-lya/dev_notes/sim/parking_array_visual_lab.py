#!/usr/bin/env python3
"""像 MATLAB 脚本一样：只改下面参数区，然后直接运行并看图。"""

from pathlib import Path

import compare_parking_array_geometries as simulation


# ======================== 实验参数区（从这里改） ========================

# 接收机在停车场平面内的位置，单位 m。
RECEIVER_X_M = 0.0
RECEIVER_Y_M = 5.0

# 两根发射天线的中点及间距。程序把 A/B 沿 X 轴对称放置。
TX_CENTER_X_M = 0.0
TX_CENTER_Y_M = 0.0
TX_SEPARATION_M = 20.0

# 两路信号相关系数：1.0=完全相干，0.0=完全不相关，中间值=部分相干。
SOURCE_CORRELATION = 1.0

# B 路相对 A 路的功率和相位。-6 dB 表示 B 路功率较弱。
SOURCE_RATIO_DB = -6.0
RELATIVE_PHASE_DEG = 60.0

# 仿真质量参数。SNR 越低峰越嘈杂；快拍越多，协方差估计越稳定。
SNR_DB = 15.0
SNAPSHOTS = 4096
RANDOM_SEED = 20260813

# 阵列参数：0.5 波长是半波长间距；方向角是阵列整体逆时针旋转角。
# GPS L5 波长约 25.5 cm，所以 0.5 波长约 12.7 cm。
ELEMENT_SPACING_WAVELENGTHS = 0.5
ARRAY_ORIENTATION_DEG = 0.0

# True 会弹出图窗；图片无论如何都会保存到该目录。
SHOW_FIGURES = True
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
