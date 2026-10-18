#!/usr/bin/env python3
"""Loop -> arranged, mixed song. The shape every song script in this kit follows; copy it into projects/<song>/
and let Claude change sections, parts and mix moves from there.
  venv/bin/python examples/song_template.py --bpm 97 --drums LOOP.wav [--keys K.wav] [--pad P.wav] [--bass B.wav] \
      -o projects/mysong/out/song.wav
Every input must already be at --bpm and start on beat 1 (run tools/fit.py first). Each one is tiled to fill
its sections, so a 1-bar loop and a 16-bar take both work.
Steps: arrangement (which part plays in which section) -> one BUS per part (its own EQ/gain/pan) -> shared
SENDS (one plate reverb, one tempo delay) -> master (glue + one static gain + limiter, never more)."""
import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from mixlib import SR, delay, duck, env, fade, filt, load, lufs, master, pan, place, reverb, save, sweep, to_m4a  # noqa: E402

# (name, bars, parts playing). Contrast is the arrangement: something drops out or comes in every section.
SECTIONS = [("intro", 8, {"keys", "pad"}),
            ("hook", 8, {"drums", "keys", "pad", "bass"}),
            ("verse", 16, {"drums", "bass", "keys"}),        # room for a vocal: no pad
            ("hook", 8, {"drums", "keys", "pad", "bass"}),
            ("outro", 8, {"keys", "pad"})]
GAIN_DB = {"drums": 0, "bass": -2, "keys": -5, "pad": -9}   # gain-stage per part by ear, then by these numbers
PAN = {"keys": -0.25, "pad": 0.2}


def tile(x, n):
    reps = -(-n // x.shape[1])
    return np.tile(x, (1, reps))[:, :n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bpm", type=float, required=True)
    ap.add_argument("--drums", required=True)
    for p in ("keys", "pad", "bass"):
        ap.add_argument(f"--{p}")
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    bar = 240 / a.bpm
    parts = {p: load(getattr(a, p)) for p in ("drums", "keys", "pad", "bass") if getattr(a, p)}
    total = int((sum(b for _, b, _ in SECTIONS) * bar + 3) * SR)       # +3 s for reverb/delay tails
    bus = {p: np.zeros((2, total), np.float32) for p in parts}

    # 1. arrangement: place each part's tiled loop into the sections it plays in
    t = 0.0
    for name, bars, playing in SECTIONS:
        n = int(bars * bar * SR)
        for p in playing & parts.keys():
            clip = fade(tile(parts[p], n), 0.005, 0.02)
            if name == "intro" and p == "keys":
                clip = sweep(clip, "low", 400, 12000)                 # filter opens over the intro
            place(bus[p], clip, t)
        t += bars * bar

    # 2. buses: each part cleaned and leveled on its own
    if "bass" in bus:
        b = filt(filt(bus["bass"], "low", 220), "high", 35).mean(0)
        bus["bass"] = np.stack([b, b])                               # bass in mono
    for p in ("keys", "pad"):
        if p in bus:
            bus[p] = pan(filt(bus[p], "high", 160), PAN[p])           # out of the kick/bass range
    for p in bus:
        bus[p] = bus[p] * 10 ** (GAIN_DB[p] / 20)
    kick_env = env(filt(bus["drums"], "low", 120), 1, 120)
    for p in ("bass", "pad"):
        if p in bus:
            bus[p] = duck(bus[p], kick_env, 4)                       # sidechain to the kick

    # 3. sends: several buses feed ONE reverb and ONE delay
    send = sum(bus[p] * s for p, s in (("keys", 0.25), ("pad", 0.35), ("drums", 0.05)) if p in bus)
    mix = sum(bus.values()) + reverb(send, 1.8) * 0.5 + delay(send, 0.75 * 60 / a.bpm) * 0.3

    # 4. master: light, static
    y = master(mix.astype(np.float32), target_lufs=-11.0)
    save(a.out, y)
    print(f"-> {a.out}  ({y.shape[1] / SR:.1f} s, {lufs(y):.1f} LUFS, peak {np.abs(y).max():.2f})  m4a: {to_m4a(a.out)}")


if __name__ == "__main__":
    main()
