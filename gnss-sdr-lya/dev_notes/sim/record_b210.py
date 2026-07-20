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
import time
from gnuradio import gr, blocks, uhd


SAMPLE_TYPES = {
    "gr_complex": {
        "cpu_format": "fc32",
        "item_size": gr.sizeof_gr_complex,
        "label": "complex float32",
    },
    "ishort": {
        "cpu_format": "sc16",
        "item_size": gr.sizeof_short * 2,
        "label": "interleaved int16 IQ",
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", type=float, default=1561098000.0, help="中心频率[Hz]，B1I=1561098000")
    ap.add_argument("--rate", type=float, default=4000000.0, help="采样率[sps]")
    ap.add_argument("--gain", type=float, default=50.0, help="增益[dB]")
    ap.add_argument("--ant", default="RX2", help="天线口: RX2 或 TX/RX")
    ap.add_argument("--subdev", default="A:A", help="子设备")
    ap.add_argument("--device-args", default="", help="UHD device args, e.g. serial=30F4100")
    ap.add_argument("--bw", type=float, default=0.0, help="模拟RX带宽[Hz]，0=用采样率(★限带防混叠，关键)")
    ap.add_argument("--secs", type=float, default=10.0, help="录制时长[秒]")
    ap.add_argument("--retries", type=int, default=5, help="UHD device open retries")
    ap.add_argument("--retry-delay", type=float, default=2.0, help="seconds between UHD open retries")
    ap.add_argument("--sample-type", choices=sorted(SAMPLE_TYPES), default="gr_complex",
                    help="output sample type: gr_complex=fc32, ishort=sc16 interleaved IQ")
    ap.add_argument("-o", "--out", default="/tmp/b1i_prn9.dat", help="输出文件(complex float32)")
    a = ap.parse_args()
    sample_type = SAMPLE_TYPES[a.sample_type]

    nsamps = int(a.rate * a.secs)
    tb = gr.top_block()
    u = None
    last_error = None
    for attempt in range(1, max(1, a.retries) + 1):
        try:
            u = uhd.usrp_source(a.device_args, uhd.stream_args(cpu_format=sample_type["cpu_format"], channels=[0]))
            break
        except RuntimeError as e:
            last_error = e
            print("warn UHD open failed attempt %d/%d: %s" % (attempt, max(1, a.retries), e))
            if attempt < max(1, a.retries):
                time.sleep(a.retry_delay)
    if u is None:
        raise last_error
    try:
        u.set_subdev_spec(a.subdev, 0)
    except Exception as e:
        print("warn set_subdev_spec:", e)
    u.set_samp_rate(a.rate)
    u.set_center_freq(a.freq, 0)
    u.set_gain(a.gain, 0)
    u.set_antenna(a.ant, 0)
    try:
        u.set_bandwidth(a.bw if a.bw > 0 else a.rate, 0)  # ★限带防混叠：不设会把带外噪声混进 4MHz 淹没弱信号
    except Exception as e:
        print("warn set_bandwidth:", e)
    # 打印实际生效值(核对 rate/freq/gain/bw 是否真的设上了)
    try:
        print("actual: rate=%.3f Msps  freq=%.4f MHz  gain=%g dB  bw=%.3f MHz"
              % (u.get_samp_rate() / 1e6, u.get_center_freq(0) / 1e6, u.get_gain(0), u.get_bandwidth(0) / 1e6))
    except Exception as e:
        print("warn get actuals:", e)

    h = blocks.head(sample_type["item_size"], nsamps)
    s = blocks.file_sink(sample_type["item_size"], a.out, False)
    s.set_unbuffered(False)
    tb.connect(u, h, s)

    print("recording %.1fs (%d samples, %s) @ %.3f MHz, rate %.1f Msps, gain %g, ant %s -> %s"
          % (a.secs, nsamps, sample_type["label"], a.freq / 1e6, a.rate / 1e6, a.gain, a.ant, a.out))
    tb.run()
    print("done:", a.out)


if __name__ == "__main__":
    main()
