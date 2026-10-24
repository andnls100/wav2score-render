# Architecture and implementation plan

## First release scope

The initial release is a local command-line orchestrator. It keeps upstream tools independent and passes file paths through their public command-line interfaces.

### Stage A: transcribe

Invoke the documented song2score interface:

```text
song2score score INPUT --out OUTPUT --title TITLE --stems 4|6 [--parts PARTS]
```

Retain the complete song2score output folder, including separated stems, MIDI files, MusicXML, and report where produced.

### Stage B: render

For each MIDI file discovered recursively below `transcription/midi`, invoke FluidSynth:

```text
fluidsynth -ni -g GAIN -r SAMPLE_RATE -F OUTPUT.wav SOUNDFONT.sf2 INPUT.mid
```

Each MIDI file gets a separate WAV. MIDI files are not assumed to have stable or unique names; the renderer creates collision-safe output names.

### Stage C: mix

If requested, invoke FFmpeg with an `amix` filter and `duration=longest`. Track rendering is not normalized by default: automatic normalization can change the intended relative levels and can clip when summing tracks. Users should inspect peak levels and adjust gain or mixing settings when needed.

## Failure handling

- Validate local input and SoundFont before starting.
- Check required executables before launching long-running work.
- Save each subprocess output to `logs/`.
- Stop on a non-zero exit code.
- Write `pipeline-report.json` on success and on pipeline-stage failure.
- Keep intermediate files for troubleshooting.

## Follow-up milestones

1. Run integration tests on Windows with real song2score, FluidSynth, FFmpeg, and a licensed SoundFont.
2. Add configurable instrument-to-SoundFont preset mapping if needed; FluidSynth uses the MIDI program by default.
3. Add resume-by-stage only after stage outputs can be validated reliably.
4. Add batch jobs and a lightweight local UI only after CLI behavior is stable.
5. Add audio quality checks (duration, silence, peak clipping) and optional loudness normalization as explicit settings.

## Current limitations

- Mocked tests verify orchestration and failure handling, not the quality of transcription or synthesis.
- Real integration depends on external executables, model packages, model downloads, and a user-supplied SoundFont.
- The pipeline does not claim that synthesized audio will match the original mixed recording. It synthesizes the transcribed MIDI tracks.
