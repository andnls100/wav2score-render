import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wav2score_render.pipeline import PipelineConfig, PipelineError, run_pipeline


class PipelineTests(unittest.TestCase):
    def test_missing_input_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sf = root / "test.sf2"
            sf.write_bytes(b"fake soundfont")
            with self.assertRaisesRegex(PipelineError, "Input audio file does not exist"):
                run_pipeline(PipelineConfig(root / "missing.wav", sf, output_dir=root / "out"))
            self.assertFalse((root / "out").exists())

    def test_existing_nonempty_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "in.wav"
            sf = root / "test.sf2"
            audio.write_bytes(b"fake audio")
            sf.write_bytes(b"fake soundfont")
            out = root / "out"
            out.mkdir()
            (out / "keep.txt").write_text("keep")
            with self.assertRaisesRegex(PipelineError, "not empty"):
                run_pipeline(PipelineConfig(audio, sf, output_dir=out))

    def test_end_to_end_orchestration_with_mocked_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "input.wav"
            sf = root / "test.sf2"
            audio.write_bytes(b"fake audio")
            sf.write_bytes(b"fake soundfont")
            out = root / "out"

            def fake_which(name):
                return f"/mock/bin/{name}"

            def fake_runner(command, stdout=None, stderr=None, text=None, check=None):
                if command[0] == "/mock/bin/song2score":
                    transcription = Path(command[command.index("--out") + 1])
                    midi_dir = transcription / "midi"
                    midi_dir.mkdir(parents=True, exist_ok=True)
                    (midi_dir / "piano.mid").write_bytes(b"midi")
                    return type("Result", (), {"returncode": 0, "stdout": "transcribed"})()
                if command[0] == "/mock/bin/fluidsynth":
                    target = Path(command[command.index("-F") + 1])
                    target.write_bytes(b"wav")
                    return type("Result", (), {"returncode": 0, "stdout": "rendered"})()
                if command[0] == "/mock/bin/ffmpeg":
                    Path(command[-1]).write_bytes(b"mixed wav")
                    return type("Result", (), {"returncode": 0, "stdout": "mixed"})()
                raise AssertionError(f"Unexpected command: {command}")

            with patch("wav2score_render.pipeline.shutil.which", side_effect=fake_which):
                report = run_pipeline(
                    PipelineConfig(audio, sf, output_dir=out),
                    runner=fake_runner,
                )
            self.assertEqual(report["status"], "success")
            self.assertEqual(len(report["midi_files"]), 1)
            self.assertEqual(len(report["rendered_wavs"]), 1)
            self.assertTrue((out / "rendered_tracks" / "piano.wav").is_file())
            self.assertTrue((out / "final_mix.wav").is_file())
            self.assertTrue((out / "pipeline-report.json").is_file())

    def test_failure_persists_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "input.wav"
            sf = root / "test.sf2"
            audio.write_bytes(b"fake audio")
            sf.write_bytes(b"fake soundfont")

            def fake_which(name):
                return f"/mock/bin/{name}"

            def fail_runner(command, **kwargs):
                return type("Result", (), {"returncode": 9, "stdout": "simulated error"})()

            with patch("wav2score_render.pipeline.shutil.which", side_effect=fake_which):
                with self.assertRaisesRegex(PipelineError, "exit code 9") as ctx:
                    run_pipeline(PipelineConfig(audio, sf, output_dir=root / "out"), runner=fail_runner)
            self.assertTrue(ctx.exception.report_path.is_file())
            self.assertEqual(
                __import__("json").loads(ctx.exception.report_path.read_text())["status"],
                "failed",
            )


if __name__ == "__main__":
    unittest.main()
