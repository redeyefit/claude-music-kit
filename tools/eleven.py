#!/usr/bin/env python3
"""ElevenLabs from the command line (key: ELEVENLABS_API_KEY in the kit's .env, never in a script).
  venv/bin/python tools/eleven.py music "PROMPT" --seconds 40 -o projects/x/eleven/take1.mp3
  venv/bin/python tools/eleven.py sfx "rain on a car roof at night" --seconds 10 -o projects/x/eleven/rain.mp3
  venv/bin/python tools/eleven.py credits
Prompt rules that save credits: describe the SOUND (instruments, era, mood, tempo, key, chords); naming a real
artist or song gets the request rejected (HTTP 400). Say 'exactly N BPM in KEY' and 'no drums, no bass' when the
take has to sit on top of your own beat, then lock it with tools/fit.py (takes often come back a half step off).
The music API cannot take your audio as input (audio reference is a web-app feature)."""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent
API = "https://api.elevenlabs.io/v1"


def api_key():
    k = os.environ.get("ELEVENLABS_API_KEY")
    env = KIT / ".env"
    if not k and env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("ELEVENLABS_API_KEY="):
                k = line.split("=", 1)[1].strip().strip('"').strip("'")
    return k or sys.exit("ELEVENLABS_API_KEY missing: put it in .env (see .env.example)")


def call(path, body=None, accept="audio/mpeg"):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"xi-api-key": api_key(), "Content-Type": "application/json",
                                          "Accept": accept})
    return urllib.request.urlopen(req, timeout=300).read()


def write(out, data):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    print("ok ", out)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("music")
    m.add_argument("prompt")
    m.add_argument("--seconds", type=float, default=30)
    m.add_argument("--vocals", action="store_true", help="allow vocals (default: instrumental)")
    m.add_argument("-o", "--out", required=True)
    s = sub.add_parser("sfx")
    s.add_argument("text")
    s.add_argument("--seconds", type=float, default=5)
    s.add_argument("--influence", type=float, default=0.5, help="0-1, how literally to follow the text")
    s.add_argument("-o", "--out", required=True)
    sub.add_parser("credits")
    a = ap.parse_args()
    try:
        if a.cmd == "credits":
            d = json.loads(call("/user/subscription", accept="application/json"))
            print(f"{d.get('tier')}: {d.get('character_count')} / {d.get('character_limit')} credits used")
        elif a.cmd == "music":
            for model in ("music_v2_5", "music_v2", "music_v1"):   # newest first; falls back if not on the plan
                try:
                    write(a.out, call("/music?output_format=mp3_44100_192",
                                      {"prompt": a.prompt, "music_length_ms": int(a.seconds * 1000),
                                       "model_id": model, "force_instrumental": not a.vocals}))
                    print("model", model)
                    break
                except urllib.error.HTTPError as e:
                    msg = e.read().decode(errors="replace")[:300]
                    print(f"fail {model} {e.code}: {msg}")
                    if e.code in (400, 401, 402):   # bad prompt / key / out of credits: another model won't help
                        sys.exit(1)
            else:
                sys.exit(1)
        else:
            write(a.out, call("/sound-generation?output_format=mp3_44100_192",
                              {"text": a.text, "duration_seconds": a.seconds, "prompt_influence": a.influence}))
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")


if __name__ == "__main__":
    main()
