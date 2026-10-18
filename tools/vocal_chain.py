#!/usr/bin/env python3
"""Vocal cleanup + polish for a home/phone vocal (mono or stereo, any format ffmpeg reads).
  venv/bin/python tools/vocal_chain.py IN [OUT.wav]
Chain: HP 90 (24 dB/oct) -> gentle expander -> low-mid cut -> fast peak comp -> presence/air EQ -> split-band
de-esser -> leveling comp -> parallel tape saturation -> HF de-click -> LP 16k. It prints the band balance and
sibilance BEFORE and AFTER: read them. The EQ amounts were tuned on a dark phone memo (2.5-5 kHz sitting 18 dB
under 150-300 Hz); a brighter mic needs less presence boost (equalizer f=3500 g=6 below).
Noise: measure first. Low rumble with a clean top end wants this HP + expander, NOT spectral noise reduction
(artifacts for nothing)."""
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, firwin, lfilter, sosfilt, welch

SR = 44100
BANDS = [(80, 150), (150, 300), (300, 600), (600, 1200), (1200, 2500), (2500, 5000), (5000, 8000), (8000, 12000),
         (12000, 18000)]


def ff(inp, outp, chain):
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(inp), "-af", chain,
                    "-c:a", "pcm_f32le", str(outp)], check=True)


def env(x, att_ms, rel_ms):
    a, r = np.exp(-1 / (att_ms / 1000 * SR)), np.exp(-1 / (rel_ms / 1000 * SR))
    e = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(np.abs(x)):
        c = a if v > acc else r
        acc = c * acc + (1 - c) * v
        e[i] = acc
    return e


def deess(x, lo=5000, hi=10000, ratio=4.0, max_db=10.0, pct=85):
    """split-band: only the 5-10 kHz band is turned down, only while it peaks above its own 85th percentile"""
    taps = 511
    h = firwin(taps, [lo, hi], pass_zero=False, fs=SR)
    band = lfilter(h, 1, x)
    dly = np.concatenate([np.zeros(taps // 2), x[:-(taps // 2)]])  # linear-phase FIR: delay-match the dry path
    rest = dly - band
    e = env(band, 1.0, 40.0)
    edb = 20 * np.log10(e + 1e-9)
    act = edb > edb.max() - 50
    T = np.percentile(edb[act], pct)
    gr = np.clip((edb - T) * (1 - 1 / ratio), 0, max_db)
    out = rest + band * 10 ** (-gr / 20)
    return np.concatenate([out[taps // 2:], np.zeros(taps // 2)]), float(gr.max())


def declick(x, lo=6000, pct=99.0, rel_ms=8.0):
    """plosive/mouth-click tamer: the >6 kHz band is peak-limited to its own 99th-percentile envelope.
    Needed because the comp + air boost leave the source's HF bursts ("g", "p") 5x above the median
    sample jump; left alone they trip the master limiter on every plosive (audible pumping)."""
    taps = 511
    band = lfilter(firwin(taps, lo, pass_zero=False, fs=SR), 1, x)
    dly = np.concatenate([np.zeros(taps // 2), x[:-(taps // 2)]])
    e = env(band, 0.02, rel_ms)
    act = e > e.max() * 10 ** (-50 / 20)
    thr = np.percentile(e[act], pct)
    g = np.minimum(1.0, thr / (e + 1e-12))
    out = dly - band + band * g
    return np.concatenate([out[taps // 2:], np.zeros(taps // 2)]), float(-20 * np.log10(g.min()))


def profile(x, label):
    f, P = welch(x, SR, nperseg=4096)
    ref = 10 * np.log10(P[(f >= 150) & (f < 300)].sum())
    row = []
    for a, b in BANDS:
        s = (f >= a) & (f < b)
        row.append(f"{10 * np.log10(P[s].sum()) - ref:+5.1f}")
    fr = np.lib.stride_tricks.sliding_window_view(x, 1024)[::512]
    F = np.abs(np.fft.rfft(fr * np.hanning(1024), axis=1)) ** 2
    fq = np.fft.rfftfreq(1024, 1 / SR)
    tot = F.sum(1)
    loud = tot > np.percentile(tot, 40)
    sib = 10 * np.log10(F[loud][:, (fq > 5000) & (fq < 10000)].sum(1) / tot[loud] + 1e-12)
    print(f"  {label:7s} " + " ".join(row) + f" | sib p95 {np.percentile(sib, 95):+.1f} dB")


def main():
    import sys
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_polished.wav")
    OUT = out.parent
    OUT.mkdir(parents=True, exist_ok=True)
    SRC = OUT / f"_vc_src_{src.stem}.wav"     # normalise input: mono 44.1k float, whatever came in
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-ac", "1", "-ar",
                    str(SR), "-c:a", "pcm_f32le", str(SRC)], check=True)
    x, sr = sf.read(str(SRC))
    a, b = OUT / "_vc_a.wav", OUT / "_vc_b.wav"
    ff(SRC, a, ",".join([
        "highpass=f=90:poles=2", "highpass=f=90:poles=2",
        "agate=threshold=0.008:ratio=2.5:attack=2:release=160:range=0.25",   # -42 dB, at most -12 dB between phrases
        "equalizer=f=320:t=q:w=1.2:g=-3.5", "equalizer=f=170:t=q:w=1.0:g=-1.5",
        "acompressor=threshold=-20dB:ratio=4:attack=3:release=60:knee=4:makeup=3",
        "equalizer=f=3500:t=q:w=0.8:g=6", "equalizer=f=1600:t=q:w=1.0:g=2", "highshelf=f=9000:g=4",
    ]))
    y, _ = sf.read(str(a))
    y, gr = deess(y)
    sf.write(str(b), y, SR, subtype="FLOAT")
    ff(b, a, "acompressor=threshold=-24dB:ratio=2.5:attack=20:release=250:knee=6:makeup=2")
    y, _ = sf.read(str(a))
    y = y / (np.abs(y).max() + 1e-9)
    y = 0.75 * y + 0.25 * np.tanh(2.2 * y) / np.tanh(2.2)   # parallel saturation: harmonics for thickness
    y, dc = declick(y)
    # phone AAC: nothing musical above ~16 kHz, only codec hash the air shelf lifted
    y = sosfilt(butter(4, 16000, btype="low", fs=SR, output="sos"), y)
    y = y / np.abs(y).max() * 0.89
    a.unlink()
    b.unlink()
    SRC.unlink()
    sf.write(str(out), y, SR, subtype="PCM_24")
    print("band balance vs 150-300 Hz (dB):  80   150  300  600  1.2k 2.5k 5k   8k   12k")
    profile(x, "before")
    profile(y, "after")
    jump = np.abs(np.diff(y)).max() / np.abs(y).max()
    print(f"  de-esser max {gr:.1f} dB | de-click max {dc:.1f} dB | max sample jump {jump:.2f} of peak -> {out.name}")
    return out


if __name__ == "__main__":
    main()
