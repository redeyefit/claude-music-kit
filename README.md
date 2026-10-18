# claude-music-kit

Make songs on a Mac by talking to Claude Code: drop in a loop, ask for a song, get an arranged, mixed track.
Generated parts come from ElevenLabs (locked to your tempo and key), lyric transcripts from Whisper (local,
free), and stem splits from Demucs. No DAW required.

## What you need
- A Mac with Apple Silicon and ~2 GB free (PyTorch for Demucs + the Whisper model)
- [Homebrew](https://brew.sh)
- [Claude Code](https://claude.com/claude-code)
- An ElevenLabs account and API key (elevenlabs.io → profile → API keys). Music generation needs a paid
  plan (Starter works). Everything else in the kit is free and offline.

## Setup (once, ~5 min)
```bash
git clone <this repo> ~/music && cd ~/music
./setup.sh            # installs ffmpeg + whisper + python, builds venv/, downloads the Whisper model
open -e .env          # paste your key after ELEVENLABS_API_KEY=  and save
./test.sh             # should end "10 passed, 0 failed"  (./test.sh --eleven also checks your key)
```

## Use it
```bash
cd ~/music && claude
```
Put audio in `inbox/`, then ask in plain words:
- "Here's my loop `inbox/beat.wav`. What tempo and key is it?"
- "Make three ElevenLabs keys/strings parts that fit my loop, no drums, and let me hear each one over it."
- "Turn my loop into a 3-minute song: intro, hook, verse with room for a rap, hook, outro."
- "Split `inbox/song.mp3` into stems and give me just the drums."
- "Transcribe the vocal in `inbox/take3.m4a` with timestamps."
- "Clean up my vocal recording and put it over the beat at bar 9."

Claude can't hear. It measures (tempo, key, loudness) and hands you a file. **Your ears decide**: say what
you like and what you don't ("bass too loud in the verse", "the strings are too sweet"), and it changes the
script and renders again.

## Folder layout
```
inbox/      your audio (Claude only reads it)
projects/   one folder per song: its script, takes, renders
tools/      fit, eleven, stems, transcribe, vocal_chain, mixlib
examples/   song_template.py, the shape every song script follows
CLAUDE.md   the rules Claude follows in this folder (edit them as you learn)
```

## Costs
ElevenLabs music uses credits. Claude checks `tools/eleven.py credits` before a batch. Everything else costs
nothing.
