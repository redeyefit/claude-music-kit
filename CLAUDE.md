# Music folder: how Claude works here

This folder makes songs from the command line: loops and samples in, arranged and mixed songs out, with
ElevenLabs for generated parts and Whisper for lyrics. **You can't hear audio.** You measure it, and the person
you work with listens. Every render ends with a file they can play and the numbers you measured, never "sounds great".

## Layout
- `inbox/`: their source audio (loops, samples, recordings). Read-only: never edit, move or overwrite.
- `projects/<song>/`: one folder per song, holding its script (`song.py`), `eleven/` takes and `out/` renders.
- `tools/`: shared tools (below). `examples/song_template.py` is the starting point for every song script.
- Python is always `venv/bin/python`. Never the system python3.

## Tools
| Command | Does |
|---|---|
| `venv/bin/python tools/fit.py IN --bpm 97 --key C#m [--bars 16] [--no-key] [--assume-bpm N]` | Measures tempo and key, conforms both, starts on beat 1. Read the `out:` numbers |
| `venv/bin/python tools/eleven.py music "PROMPT" --seconds 40 -o projects/x/eleven/t1.mp3` | ElevenLabs music (instrumental unless `--vocals`) |
| `venv/bin/python tools/eleven.py sfx "TEXT" --seconds 5 -o ...` / `credits` | Sound effects / credits left |
| `tools/stems.sh IN [OUTDIR] [--two]` | Demucs stem split (drums/bass/other/vocals; `--two` = vocals + rest) |
| `tools/transcribe.sh IN` | Whisper lyrics → IN.txt / .srt / .json (word timings) |
| `venv/bin/python tools/vocal_chain.py IN [OUT]` | Raw home/phone vocal → cleaned, EQ'd, compressed, de-essed; prints tone balance before/after |
| `tools/mixlib.py` | Import in song scripts: load/save, filters, pan, reverb/delay sends, duck, sweep, lufs, master |
| `./test.sh` | ~30 s self-check. Run it after any change to `tools/` |

## Workflow
1. **Measure before touching anything.** Run fit.py on the source loop, or ask the person for the BPM and key
   if their DAW shows them. Write the tempo and key at the top of the song script.
2. **Generated parts (ElevenLabs).** Run `eleven.py credits` first and say what a batch costs. Prompt with the
   sound, not names: instruments, era, mood, "exactly 97 BPM in C sharp minor", the chord loop, and
   "no drums, no bass, no vocals" when it sits on their beat. Real artist or song names get the request
   rejected (HTTP 400). Make 2–3 different takes, fit.py each one, and render each over their loop so they
   compare in context. Takes often arrive a half step off; fit.py fixes that and reports it. The API can't
   take their audio as input.
3. **Song script.** Copy `examples/song_template.py` to `projects/<song>/song.py`. Arrangement first
   (sections; something enters or drops out every section), then one bus per part, then shared sends (one
   reverb, one delay), then `master()`.
4. **Mix rules.** Gain-stage each part on its own bus. EQ, compression and effects go on buses or sends,
   never stacked on the master. High-pass everything that isn't kick or bass (~150 Hz). Keep bass mono.
   Duck bass and pads off the kick.
5. **Master** = `mixlib.master()`: glue, ONE static gain to the target (−11 LUFS for streaming-loud, −14 for
   dynamic), limiter at 0.89. Never use ffmpeg `loudnorm` in its default dynamic mode: it rides the gain and
   flattens a quiet intro up to chorus level.
6. **Deliver.** Render `.wav` plus `.m4a` (`mixlib.to_m4a`) into `projects/<song>/out/` and run
   `open projects/<song>/out`. Report length, LUFS and peak, and say what changed since the last version
   and what to listen for (e.g. "bar 9: the strings come in").

## Gotchas (each one cost time once)
- Tempo: librosa's beat tracker misreads pads and soft parts. fit.py uses onset autocorrelation and refuses to
  stretch when there's no clear bar-level pulse. Pass `--assume-bpm` when you know it (e.g. you prompted it).
- Key: kicks and 808s are pitched and loud, so fit.py high-passes before reading the key. Neighbouring keys
  still score close on dense mixes. If the person knows the key, trust them over the read.
- Drums and percussion: `fit.py --no-key`, or they get pitched.
- Whisper makes up lyrics over a loud beat. Run `stems.sh --two` first and transcribe the vocals stem.
- macOS bash is 3.2: no associative arrays, and an empty `"${arr[@]}"` fails under `set -u`.
- Long renders: print progress. Write to a temp file and `mv` it into place, so a crash never leaves half a file.

## Keys and rights
- The ElevenLabs key lives only in `.env` (gitignored). Never print it, echo it, or put it in a script or commit.
- Sampling someone else's record is fine for practice. Releasing it needs clearance. Say so when a project
  is built on a commercial sample, and keep those projects out of anything published.
- What you may do with ElevenLabs output depends on their plan's terms. Check before anything gets released.
