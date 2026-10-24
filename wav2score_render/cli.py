"""Command-line entry point."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import PipelineConfig, PipelineError, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wav2score-render",
        description="Transcribe an audio file with song2score and render MIDI tracks with FluidSynth.",
    )
    parser.add_argument("input", type=Path, help="Input audio file supported by song2score")
    parser.add_argument("--soundfont", required=True, type=Path, help="Path to a .sf2/.sf3 SoundFont")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: outputs/<input-stem>-<timestamp>)")
    parser.add_argument("--title", default=None, help="Score title (defaults to input filename)")
    parser.add_argument("--stems", type=int, choices=(4, 6), default=4, help="song2score stem count (default: 4)")
    parser.add_argument("--parts", default=None, help="Comma-separated song2score parts, e.g. vocals,bass,guitar")
    parser.add_argument("--sample-rate", type=int, choices=(22050, 32000, 44100, 48000, 96000), default=44100)
    parser.add_argument("--gain", type=float, default=0.8, help="FluidSynth gain from 0 to 10 (default: 0.8)")
    parser.add_argument("--no-mix", action="store_true", help="Render individual tracks but do not mix them")
    parser.add_argument("--overwrite", action="store_true", help="Allow an existing non-empty output directory")
    parser.add_argument("--song2score", default="song2score", help="song2score executable (default: song2score)")
    parser.add_argument("--fluidsynth", default="fluidsynth", help="FluidSynth executable (default: fluidsynth)")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="FFmpeg executable (default: ffmpeg)")
    parser.add_argument("--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO")
    parser.add_argument("--version", action="version", version="wav2score-render 0.1.0")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level), format="%(levelname)s: %(message)s")
    config = PipelineConfig(
        input_path=args.input,
        soundfont_path=args.soundfont,
        output_dir=args.out,
        title=args.title,
        stems=args.stems,
        parts=args.parts,
        sample_rate=args.sample_rate,
        gain=args.gain,
        mix=not args.no_mix,
        overwrite=args.overwrite,
        song2score_executable=args.song2score,
        fluidsynth_executable=args.fluidsynth,
        ffmpeg_executable=args.ffmpeg,
    )
    try:
        report = run_pipeline(config)
    except (PipelineError, OSError, ValueError) as exc:
        logging.error("%s", exc)
        if getattr(exc, "report_path", None):
            logging.error("Failure report: %s", exc.report_path)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
