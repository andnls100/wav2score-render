# wav2score-render

Automated audio-to-score-to-audio pipeline. This project orchestrates upstream tools; it does not copy their implementation.

- **[song2score](https://github.com/winjayran/song2score)** separates a mixed song into stems, transcribes stems to MIDI, and exports MusicXML.
- **[FluidSynth](https://github.com/FluidSynth/fluidsynth)** renders MIDI using a SoundFont into WAV.

> **Quality note:** song2score describes itself as alpha software. Transcription can miss notes, misclassify instruments, or drift in timing. FluidSynth faithfully renders the MIDI it receives; it cannot recover information lost during transcription. Listen to the results and review MIDI/MusicXML before relying on them.

## What the pipeline does

1. Validate the input audio, FluidSynth executable, and SoundFont.
2. Run `song2score score` and retain its stems, MIDI, MusicXML, and report.
3. Render each discovered MIDI file to an individual WAV. MusicXML/MXL can also be supplied directly with `--musicxml`; MuseScore converts it to MIDI before rendering.
4. Optionally mix rendered WAVs into one `final_mix.wav` using FFmpeg.
5. Save logs and a machine-readable `pipeline-report.json`.

Failures stop the pipeline and are recorded in the report. Intermediate outputs are preserved for debugging. A rerun uses a new timestamped job folder unless `--out` is explicitly provided; an existing non-empty output folder is rejected unless `--overwrite` is set.

## Requirements

- Python 3.10+ (Python 3.11 recommended).
- `song2score` installed in the active environment (audio-input mode).
- MuseScore 4 CLI available on `PATH` (only for `--musicxml` mode).
- FluidSynth CLI available on `PATH`.
- A General MIDI-compatible SoundFont (`.sf2` or `.sf3`).
- FFmpeg on `PATH` for the optional final mix.

Install song2score following its upstream instructions. For example, on Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
git clone https://github.com/winjayran/song2score vendor/song2score
python -m pip install -e "vendor/song2score[demucs,basic-pitch,madmom,torch]"
python -m pip install -e .
```

Install FluidSynth and FFmpeg separately, then verify:

```powershell
song2score --help
fluidsynth --version
ffmpeg -version
```

## Quick start

```powershell
wav2score-render "D:\audio\song.wav" --soundfont "D:\soundfonts\GeneralUser-GS.sf2" --out "D:\renders\song"
```

Or run from a source checkout:

```powershell
python -m wav2score_render "D:\audio\song.wav" --soundfont "D:\soundfonts\GeneralUser-GS.sf2" --out "D:\renders\song" --stems 6
```

### Render MusicXML as accompaniment audio

Pass a MusicXML (`.musicxml`/`.xml`) or compressed MusicXML (`.mxl`) file with `--musicxml`. MuseScore CLI converts the score to MIDI, then FluidSynth renders it with your SoundFont. This renders the notes/instruments already present in the score; it does not automatically compose missing accompaniment parts.

```powershell
wav2score-render "D:\scores\song.musicxml" --musicxml --soundfont "D:\soundfonts\GeneralUser-GS.sf2" --out "D:\renders\song"
```

If MuseScore is not on `PATH`, pass its executable explicitly:

```powershell
wav2score-render "D:\scores\song.musicxml" --musicxml --musescore "C:\Program Files\MuseScore 4\bin\MuseScore4.exe" --soundfont "D:\soundfonts\GeneralUser-GS.sf2"
```

The output includes `transcription/midi/song.mid`, `rendered_tracks/song.wav`, and (unless `--no-mix` is used) `final_mix.wav`.

To skip final mixing (individual rendered tracks are still produced):

```powershell
wav2score-render input.wav --soundfont piano.sf2 --no-mix
```

Useful options:

- `--parts vocals,bass,guitar,piano`: choose song2score parts.
- `--stems 4|6`: choose 4- or 6-stem separation.
- `--sample-rate 44100`: FluidSynth render sample rate.
- `--gain 0.8`: FluidSynth gain (range 0–10; default 0.8).
- `--overwrite`: allow output in an existing non-empty directory.
- `--no-mix`: do not run FFmpeg to create the final mix.

## Output layout

```text
<out>/
  transcription/        # song2score output (stems/, midi/, musicxml/, report.json)
  rendered_tracks/      # one WAV per MIDI file
  logs/
    song2score.log
    fluidsynth-*.log
    ffmpeg-mix.log      # if mixing is enabled
  final_mix.wav         # if mixing is enabled and tracks were rendered
  pipeline-report.json
```

## Development and tests

Tests use mocked subprocess calls and do not require audio models, FluidSynth, FFmpeg, or a SoundFont:

```powershell
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

## Design boundaries

- Upstream tools are invoked as subprocesses to keep dependency conflicts and licenses isolated.
- No proprietary model weights or SoundFonts are bundled.
- The first version is a local CLI, not a web service or queue.
- SoundFont licensing varies; provide your own file and check its license.
- FluidSynth is LGPL-licensed. See the upstream [license](https://github.com/FluidSynth/fluidsynth/blob/master/LICENSE). song2score currently declares MIT in its README; check the upstream repository for current terms.

## Upstream references

- https://github.com/winjayran/song2score
- https://github.com/FluidSynth/fluidsynth
