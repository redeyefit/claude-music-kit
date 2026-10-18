#!/usr/bin/env python3
"""Lock any audio (an ElevenLabs take, a sample, a stem) to a tempo + key and start it on beat 1.
  venv/bin/python tools/fit.py IN --bpm 97 --key C#m [--bars 16] [--assume-bpm 97] [-o OUT.wav]
Measures tempo (onset autocorrelation at 1/2/4/8-beat lags) and key (Krumhansl profiles), conforms with
ffmpeg's rubberband (tempo and pitch independently), then trims so the first bar line is at 0 s.
Prints what it measured and what it did; check the 'out:' numbers before trusting the file."""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mixlib import SR, filt, load  # noqa: E402

NOTES = "C C# D D# E F F# G G# A A# B".split()
FLAT = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}
KK_MAJ = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
KK_MIN = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def parse_key(s):
    q = "min" if s.endswith("m") else "maj"
    root = s[:-1] if q == "min" else s
    root = FLAT.get(root, root)
    return NOTES.index(root), q


def tempo_of(mono, near):
    """returns (bpm, trusted). Long lags are precise but only exist when the part repeats per bar. librosa's beat
    tracker was dropped: it read a 97.0 strings take as 97.65 (a 0.7% stretch drifts ~0.3 s over 16 bars) and a
    soft 97.0 pad as 86."""
    hop = 128
    fps = SR / hop
    e = librosa.onset.onset_strength(y=mono, sr=SR, hop_length=hop)
    e = e - e.mean()
    ac = np.correlate(e, e, "full")[len(e) - 1:]
    lo_bpm, hi_bpm = near * 0.9, near * 1.1
    est = {}
    for nb in (1, 2, 4, 8):
        lo, hi = int(nb * 60 / hi_bpm * fps), int(nb * 60 / lo_bpm * fps)
        if hi + 1 >= len(ac):
            continue
        i = lo + int(np.argmax(ac[lo:hi]))
        if lo < i < hi - 1:           # peak on the window edge = no real periodicity at that lag
            a, b, c = ac[i - 1], ac[i], ac[i + 1]
            est[nb] = nb * 60 / ((i + 0.5 * (a - c) / (a - 2 * b + c)) / fps)
    if 4 in est and 8 in est and abs(est[4] / est[8] - 1) < 0.003:
        return est[8], True
    short = [v for k, v in est.items() if k <= 2]
    return (float(np.mean(short)) if short else near), False


def key_of(mono, home):
    # HP 150 Hz first: kick and 808 fundamentals are pitched and louder than the chords, and drag the read off
    # (a C#m loop+keys mix read G#m unfiltered, C#m filtered; a synthetic Am loop read E with its kick in)
    c = librosa.feature.chroma_cqt(y=filt(mono, "high", 150, order=4).astype(np.float32), sr=SR).mean(1)
    sc = {(k, q): np.corrcoef(c, np.roll(p, k))[0, 1] for k in range(12)
          for p, q in ((KK_MAJ, "maj"), (KK_MIN, "min"))}
    best = max(sc, key=sc.get)
    rel = ((home[0] + 3) % 12, "maj") if home[1] == "min" else ((home[0] - 3) % 12, "min")
    h = max(home, rel, key=sc.get)
    # neighbour keys (one accidental apart) score within a hair of each other on dense material: only move off
    # the asked-for key (or its relative) when it is clearly beaten
    if sc[best] - sc[h] < 0.08:
        best = h
    return best, float(sc[best])


def downbeat(mono, bpm):
    """beat phase from onsets on the bpm grid; which beat is beat 1 from harmony (chords tend to change on the
    bar line). Onsets alone picked a bar start 3 beats off on one take."""
    beat, bar = 60 / bpm, 240 / bpm
    hop = 256
    fps = SR / hop
    e = librosa.onset.onset_strength(y=mono, sr=SR, hop_length=hop)
    dur = len(e) / fps

    def grid(o):
        return float(e[np.round(np.arange(o, dur - 0.05, beat) * fps).astype(int)].sum())

    ob = max(np.arange(0, beat, 0.005), key=grid)
    ch = librosa.feature.chroma_cqt(y=mono, sr=SR, hop_length=hop)
    w = int(beat * fps)

    def change(o):
        d = []
        for t in np.arange(o + beat, dur - beat, bar):
            i = int(round(t * fps))
            a, b = ch[:, i - w:i].mean(1), ch[:, i:i + w].mean(1)
            d.append(1 - float(a @ b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
        return float(np.mean(d)) if d else 0.0

    return max((ob + k * beat for k in range(4)), key=change)


def name(k):
    return NOTES[k[0]] + ("m" if k[1] == "min" else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--bpm", type=float, required=True)
    ap.add_argument("--key", required=True, help="e.g. C#m, Am, Eb")
    ap.add_argument("--bars", type=int, default=0, help="keep this many bars (0 = all)")
    ap.add_argument("--assume-bpm", type=float, default=0,
                    help="source tempo if you know it (e.g. you prompted it); skips measuring")
    ap.add_argument("--no-key", action="store_true", help="drums/percussion: don't pitch")
    ap.add_argument("-o", "--out")
    a = ap.parse_args()
    src = Path(a.src)
    out = Path(a.out) if a.out else src.with_name(f"{src.stem}_fit_{a.bpm:g}bpm.wav")
    home = parse_key(a.key)

    x = load(src)
    mono = x.mean(0)
    if a.assume_bpm:
        t, trusted = a.assume_bpm, True
    else:
        t, trusted = tempo_of(mono, a.bpm)
    ratio = a.bpm / t
    if not trusted or abs(ratio - 1) < 0.002:
        if abs(ratio - 1) >= 0.002:
            print(f"note: reads ~{t:.2f} BPM with no bar-level pulse; NOT stretching (pass --assume-bpm if known)")
        ratio = 1.0
    k, conf = key_of(mono, home)
    semis = 0 if a.no_key else ((home[0] - k[0] + 6) % 12 - 6 if k[1] == home[1]
                                 else ((home[0] + (3 if home[1] == "min" else -3)) - k[0] + 6) % 12 - 6)
    with tempfile.TemporaryDirectory() as d:
        w, f = Path(d) / "in.wav", Path(d) / "fit.wav"
        sf.write(str(w), x.T, SR, subtype="FLOAT")
        af = f"rubberband=tempo={ratio:.5f}:pitch={2 ** (semis / 12):.5f}:pitchq=quality:transients=smooth"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(w), "-af", af,
                        "-c:a", "pcm_f32le", str(f)], check=True)
        y, _ = sf.read(str(f), dtype="float32")
    y = y.T.copy()
    o = downbeat(y.mean(0), a.bpm)
    y = y[:, int(round(o * SR)):]
    if a.bars:
        n = int(a.bars * 240 / a.bpm * SR)
        y = np.pad(y[:, :n], ((0, 0), (0, max(0, n - y.shape[1]))))
    f = int(0.01 * SR)
    y[:, :f] *= np.linspace(0, 1, f)
    y[:, -f:] *= np.linspace(1, 0, f)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out), y.T, SR, subtype="PCM_24")
    t2, _ = tempo_of(y.mean(0), a.bpm)
    k2, _ = key_of(y.mean(0), home)
    print(f"in: {t:.2f} BPM {name(k)} (r={conf:.2f}) | stretch {100 * (ratio - 1):+.1f}% shift {semis:+d} st | "
          f"bar 1 at {o:.3f}s | out: {t2:.2f} BPM {name(k2)} -> {out}")


if __name__ == "__main__":
    main()
