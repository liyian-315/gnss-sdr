#!/usr/bin/env python3
"""
录制 USRP B210 原始复采样到文件（source→file，无 GNSS 处理，基本不溢出）。
输出为 complex float32 (= gr_complex)，与 File_Signal_Source 的 item_type=gr_complex 匹配。

conda 环境里跑：
  conda activate gnsssdr
  python3 dev_notes/sim/record_b210.py --secs 10 -o /tmp/b1i_prn9.dat
默认：freq=1561.098MHz(B1I), rate=4MHz, gain=50, ant=RX2, subdev=A:A。
录制时若打印 overflow('O')，说明写盘跟不上——降 --rate 或换更快的盘。
"""
import argparse
from gnuradio import gr, blocks, uhd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", type=float, default=1561098000.0, help="中心频率[Hz]，B1I=1561098000")
    ap.add_argument("--rate", type=float, default=4000000.0, help="采样率[sps]")
    ap.add_argument("--gain", type=float, default=50.0, help="增益[dB]")
    ap.add_argument("--ant", default="RX2", help="天线口: RX2 或 TX/RX")
    ap.add_argument("--subdev", default="A:A", help="子设备")
    ap.add_argument("--secs", type=float, default=10.0, help="录制时长[秒]")
    ap.add_argument("-o", "--out", default="/tmp/b1i_prn9.dat", help="输出文件(complex float32)")
    a = ap.parse_args()

    nsamps = int(a.rate * a.secs)
    tb = gr.top_block()
    u = uhd.usrp_source("", uhd.stream_args(cpu_format="fc32", channels=[0]))
    try:
        u.set_subdev_spec(a.subdev, 0)
    except Exception as e:
        print("warn set_subdev_spec:", e)
    u.set_samp_rate(a.rate)
    u.set_center_freq(a.freq, 0)
    u.set_gain(a.gain, 0)
    u.set_antenna(a.ant, 0)

    h = blocks.head(gr.sizeof_gr_complex, nsamps)
    s = blocks.file_sink(gr.sizeof_gr_complex, a.out, False)
    s.set_unbuffered(False)
    tb.connect(u, h, s)

    print("recording %.1fs (%d samples) @ %.3f MHz, rate %.1f Msps, gain %g, ant %s -> %s"
          % (a.secs, nsamps, a.freq / 1e6, a.rate / 1e6, a.gain, a.ant, a.out))
    tb.run()
    print("done:", a.out)


if __name__ == "__main__":
    main()
