"""Subprocess-based orchestration for song2score and FluidSynth."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Callable, Sequence

LOGGER = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    """Pipeline failure with optional path to the persisted failure report."""

    def __init__(self, message: str, report_path: Path | None = None):
        super().__init__(message)
        self.report_path = report_path


@dataclass
class PipelineConfig:
    input_path: Path
    soundfont_path: Path
    output_dir: Path | None = None
    title: str | None = None
    stems: int = 4
    parts: str | None = None
    sample_rate: int = 44100
    gain: float = 0.8
    mix: bool = True
    overwrite: bool = False
    song2score_executable: str = "song2score"
    fluidsynth_executable: str = "fluidsynth"
    ffmpeg_executable: str = "ffmpeg"


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _run(command: Sequence[str], log_path: Path, *, runner: Callable = subprocess.run) -> None:
    """Run a command and persist combined stdout/stderr even when it fails."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("Running: %s", subprocess.list2cmdline(list(command)) if os.name == "nt" else " ".join(command))
    try:
        result = runner(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        output = result.stdout or ""
        log_path.write_text(output, encoding="utf-8", errors="replace")
        if result.returncode != 0:
            raise PipelineError(
                f"Command failed with exit code {result.returncode}: {command[0]}. See log: {log_path}"
            )
    except OSError as exc:
        log_path.write_text(str(exc), encoding="utf-8")
        raise PipelineError(f"Could not execute {command[0]}: {exc}. See log: {log_path}") from exc


def _find_executable(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise PipelineError(f"Executable not found on PATH: {name}")
    return found


def _safe_stem(path: Path) -> str:
    stem = "".join(c if c.isalnum() or c in "-_." else "_" for c in path.stem).strip("._")
    return stem or "track"


def _mix_tracks(track_paths: list[Path], output_path: Path, ffmpeg: str, log_path: Path, *, runner: Callable = subprocess.run) -> None:
    if len(track_paths) == 1:
        # Still use FFmpeg so the mix output has a consistent documented path.
        command = [ffmpeg, "-y", "-i", str(track_paths[0]), "-c:a", "pcm_s16le", str(output_path)]
    else:
        inputs: list[str] = []
        for track in track_paths:
            inputs.extend(["-i", str(track)])
        labels = "".join(f"[{i}:a]" for i in range(len(track_paths)))
        filter_graph = f"{labels}amix=inputs={len(track_paths)}:duration=longest:normalize=0[mix]"
        command = [ffmpeg, "-y", *inputs, "-filter_complex", filter_graph, "-map", "[mix]", "-c:a", "pcm_s16le", str(output_path)]
    _run(command, log_path, runner=runner)


def run_pipeline(config: PipelineConfig, *, runner: Callable = subprocess.run) -> dict:
    """Execute the full pipeline and return its JSON-serializable report."""
    started = time.monotonic()
    input_path = Path(config.input_path).expanduser().resolve()
    soundfont_path = Path(config.soundfont_path).expanduser().resolve()
    if not input_path.is_file():
        raise PipelineError(f"Input audio file does not exist: {input_path}")
    if not soundfont_path.is_file():
        raise PipelineError(f"SoundFont file does not exist: {soundfont_path}")
    if config.stems not in (4, 6):
        raise ValueError("stems must be 4 or 6")
    if config.sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not 0 <= config.gain <= 10:
        raise ValueError("gain must be between 0 and 10")

    output_dir = Path(config.output_dir).expanduser().resolve() if config.output_dir else (
        Path.cwd() / "outputs" / f"{_safe_stem(input_path)}-{_timestamp()}"
    )
    if output_dir.exists() and any(output_dir.iterdir()) and not config.overwrite:
        raise PipelineError(f"Output directory is not empty: {output_dir}. Use --overwrite to reuse it.")
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir = output_dir / "logs"
    transcription_dir = output_dir / "transcription"
    rendered_dir = output_dir / "rendered_tracks"
    logs_dir.mkdir(exist_ok=True)
    rendered_dir.mkdir(exist_ok=True)
    report_path = output_dir / "pipeline-report.json"
    report = {
        "status": "running",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "input": str(input_path),
        "soundfont": str(soundfont_path),
        "output_dir": str(output_dir),
        "settings": {
            "stems": config.stems,
            "parts": config.parts,
            "sample_rate": config.sample_rate,
            "gain": config.gain,
            "mix": config.mix,
        },
        "commands": [],
        "midi_files": [],
        "rendered_wavs": [],
        "final_mix": None,
        "error": None,
    }

    def save_report() -> None:
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        song2score = _find_executable(config.song2score_executable)
        fluidsynth = _find_executable(config.fluidsynth_executable)
        ffmpeg = _find_executable(config.ffmpeg_executable) if config.mix else None

        title = config.title or input_path.stem
        command = [
            song2score, "score", str(input_path), "--out", str(transcription_dir),
            "--title", title, "--stems", str(config.stems),
        ]
        if config.parts:
            command.extend(["--parts", config.parts])
        report["commands"].append(command)
        _run(command, logs_dir / "song2score.log", runner=runner)

        midi_dir = transcription_dir / "midi"
        midi_files = sorted(p for p in midi_dir.rglob("*") if p.is_file() and p.suffix.lower() in {".mid", ".midi"}) if midi_dir.exists() else []
        if not midi_files:
            raise PipelineError(f"song2score completed but no MIDI files were found under {midi_dir}. Check its log and output structure.")
        report["midi_files"] = [str(p) for p in midi_files]

        used_names: set[str] = set()
        rendered_paths: list[Path] = []
        for midi_path in midi_files:
            name = _safe_stem(midi_path)
            if name in used_names:
                name = f"{name}-{len(used_names) + 1}"
            used_names.add(name)
            wav_path = rendered_dir / f"{name}.wav"
            render_command = [
                fluidsynth, "-ni", "-g", str(config.gain), "-r", str(config.sample_rate),
                "-F", str(wav_path), str(soundfont_path), str(midi_path),
            ]
            report["commands"].append(render_command)
            _run(render_command, logs_dir / f"fluidsynth-{name}.log", runner=runner)
            if not wav_path.is_file():
                raise PipelineError(f"FluidSynth exited successfully but did not create expected file: {wav_path}")
            rendered_paths.append(wav_path)
        report["rendered_wavs"] = [str(p) for p in rendered_paths]

        if config.mix:
            mix_path = output_dir / "final_mix.wav"
            mix_command_note = {"tool": "ffmpeg", "output": str(mix_path), "inputs": [str(p) for p in rendered_paths]}
            report["commands"].append(mix_command_note)
            _mix_tracks(rendered_paths, mix_path, ffmpeg, logs_dir / "ffmpeg-mix.log", runner=runner)
            if not mix_path.is_file():
                raise PipelineError(f"FFmpeg exited successfully but did not create expected file: {mix_path}")
            report["final_mix"] = str(mix_path)

        report["status"] = "success"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report()
        LOGGER.info("Pipeline completed: %s", output_dir)
        return report
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        save_report()
        if isinstance(exc, PipelineError):
            exc.report_path = report_path
            raise
        raise PipelineError(f"Pipeline failed: {exc}. See report: {report_path}", report_path) from exc
