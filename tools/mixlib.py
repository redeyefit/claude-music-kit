"""Shared mixing helpers. Audio is float32, shape (2, n) stereo, 44.1 kHz throughout.
Import from a project script:  sys.path.insert(0, "<kit>/tools"); from mixlib import *
The model: every part goes on its own BUS (drums, bass, keys, pads, lead, fx), effects live on buses or on
SENDS (one shared plate/hall/delay that several buses feed), and the master only gets glue + one static gain +
a limiter. Never stack effects on the master to fix the mix."""
import re
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44100


def load(path, sr=SR):
    """any format ffmpeg reads -> (2, n) float32 at sr"""
    with tempfile.TemporaryDirectory() as d:
        w = Path(d) / "x.wav"
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(path), "-ar", str(sr),
                        "-ac", "2", "-c:a", "pcm_f32le", str(w)], check=True)
        y, _ = sf.read(str(w), dtype="float32")
    return y.T.copy()


def save(path, y, subtype="PCM_24"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(y).T, SR, subtype=subtype)


def to_m4a(wav, kbps=256):
    out = Path(wav).with_suffix(".m4a")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(wav), "-c:a", "aac",
                    "-b:a", f"{kbps}k", str(out)], check=True)
    return out


def filt(y, kind, hz, order=2):
    """kind = 'low' | 'high' | 'band' (hz=(lo, hi))"""
    return sosfilt(butter(order, hz, btype=kind, fs=SR, output="sos"), y, axis=-1)


def db(x):
    return 20 * np.log10(x + 1e-12)


def rms(y):
    return float(np.sqrt(np.mean(np.asarray(y, dtype=np.float64) ** 2)))


def st2(x):
    """mono (n,) or soundfile (n, ch) -> (2, n)"""
    x = np.asarray(x, dtype=np.float32)
    return np.stack([x, x]) if x.ndim == 1 else x.T.copy()


def fade(y, fin=0.003, fout=0.01):
    y = y.copy()
    a, b = min(y.shape[-1], int(fin * SR)), min(y.shape[-1], int(fout * SR))
    if a:
        y[..., :a] *= np.linspace(0, 1, a)
    if b:
        y[..., -b:] *= np.linspace(1, 0, b)
    return y


def place(bus, clip, t, gain=1.0):
    """add clip into bus at time t (seconds); clips past either end are cut, not wrapped"""
    i = int(round(t * SR))
    if i < 0:
        clip, i = clip[..., -i:], 0
    n = min(clip.shape[-1], bus.shape[-1] - i)
    if n > 0:
        bus[..., i:i + n] += clip[..., :n] * gain


def pan(y, p):
    """equal-power balance, p in -1..1"""
    a = (p + 1) * np.pi / 4
    return y * np.array([[np.cos(a)], [np.sin(a)]], dtype=np.float32) * np.sqrt(2)


def pitch(y, semis):
    """resample-style pitch shift (changes length, like a sampler); use fit.py / rubberband to keep tempo"""
    if semis == 0:
        return y
    return librosa.resample(y, orig_sr=SR * 2 ** (semis / 12), target_sr=SR, axis=-1)


def reverb(y, rt60, pre=0.02, seed=3, lp=6000, hp=250):
    """send effect: feed it a send bus, add the return to the mix. HP'd so it never muddies the low end"""
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    ir = np.random.default_rng(seed).standard_normal((2, n)) * np.exp(-6.9 * t / rt60)
    ir = np.concatenate([np.zeros((2, int(pre * SR))), filt(ir, "low", lp)], axis=1)
    wet = np.stack([fftconvolve(y[c], ir[c])[:y.shape[-1]] for c in range(2)]) / np.sqrt(n) * 3
    return filt(wet, "high", hp).astype(np.float32)


def delay(y, secs, fb=0.35, taps=6, lp=3500, hp=400, pingpong=True):
    """tempo delay send; dotted 8th = 0.75 * 60 / bpm"""
    out = np.zeros_like(y)
    d = int(secs * SR)
    x = filt(y, "high", hp)
    for k in range(1, taps + 1):
        x = filt(x, "low", lp, order=1) * fb
        sh = np.zeros_like(y)
        sh[:, k * d:] = x[:, :y.shape[-1] - k * d]
        if pingpong:
            sh = sh[::-1] if k % 2 else sh
        out += sh
    return out.astype(np.float32)


def env(x, att_ms, rel_ms):
    """peak follower in 1 ms blocks (a per-sample Python loop is far too slow on minutes of audio)"""
    m = np.abs(np.atleast_2d(x)).max(0)
    blk = SR // 1000
    nb = len(m) // blk + 1
    mb = np.pad(m, (0, nb * blk - len(m))).reshape(nb, blk).max(1)
    a, r = np.exp(-1 / att_ms), np.exp(-1 / rel_ms)
    e = np.empty(nb)
    acc = 0.0
    for i, v in enumerate(mb):
        c = a if v > acc else r
        acc = c * acc + (1 - c) * v
        e[i] = acc
    return np.interp(np.arange(len(m)) / blk, np.arange(nb), e)


def duck(y, key_env, depth_db):
    """sidechain: turn y down by up to depth_db while the key (usually the kick) hits"""
    k = key_env / (key_env.max() + 1e-9)
    return (y * 10 ** (-depth_db * k / 20)).astype(np.float32)


def sweep(y, kind, f0, f1, n=10):
    """filter sweep across the whole clip (risers, intros)"""
    fs = np.geomspace(f0, f1, n)
    renders = [filt(y, kind, f, order=2) for f in fs]
    pos = np.linspace(0, n - 1, y.shape[-1])
    out = np.zeros_like(y)
    for k in range(n):
        out += renders[k] * np.clip(1 - np.abs(pos - k), 0, 1)
    return out


def ffx(y, chain):
    """run an ffmpeg -af chain (acompressor, equalizer, alimiter, ...) on a (2, n) array, same length back"""
    with tempfile.TemporaryDirectory() as d:
        a, b = Path(d) / "in.wav", Path(d) / "out.wav"
        sf.write(str(a), y.T, SR, subtype="FLOAT")
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(a), "-af", chain,
                        "-c:a", "pcm_f32le", str(b)], check=True)
        z, _ = sf.read(str(b), dtype="float32")
    z = z.T
    return z[:, :y.shape[1]] if z.shape[1] >= y.shape[1] else np.pad(z, ((0, 0), (0, y.shape[1] - z.shape[1])))


def lufs(y):
    """integrated loudness (EBU R128) via ffmpeg"""
    with tempfile.TemporaryDirectory() as d:
        a = Path(d) / "m.wav"
        sf.write(str(a), y.T, SR, subtype="FLOAT")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(a), "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True)
    return float(re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)[-1])


def master(mix, target_lufs=-11.0, ceiling=0.89, glue=True):
    """glue comp -> ONE static gain to the target -> limiter. Static on purpose: ffmpeg's loudnorm in its default
    dynamic mode rides the gain and flattens a quiet intro up to chorus level, killing the arrangement's dynamics."""
    y = ffx(mix, "acompressor=threshold=-14dB:ratio=1.5:attack=30:release=200:knee=6") if glue else mix
    lim = f"alimiter=limit={ceiling}:attack=5:release=60:level=disabled"
    g = target_lufs - lufs(y)
    out = ffx(y * 10 ** (g / 20), lim)
    # the limiter eats loudness on punchy mixes (a kick-heavy loop landed 1 dB under target), so measure once
    # after it and correct. A big correction means the mix is too peaky: tame the drum bus instead of pushing on
    g += target_lufs - lufs(out)
    return ffx(y * 10 ** (g / 20), lim)
