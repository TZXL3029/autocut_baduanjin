import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from mergeVideo import (
    MergeError,
    MergeGroup,
    build_merge_plan,
    discover_video_groups,
    merge_group,
    output_path_for_directory,
    parse_extensions,
    run_ffmpeg,
    validate_group_sources,
)


class TestMergeVideoDiscovery(unittest.TestCase):
    def test_discovers_each_directory_with_direct_videos(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            first = root / "first"
            second = root / "nested" / "second"
            empty = root / "empty"
            first.mkdir()
            second.mkdir(parents=True)
            empty.mkdir()

            (first / "a.mp4").touch()
            (first / "b.MP4").touch()
            (second / "clip.mov").touch()
            (empty / "note.txt").touch()

            groups = discover_video_groups(root)

            self.assertEqual(
                {group.directory.name for group in groups},
                {"first", "second"},
            )

    def test_sorts_videos_by_natural_filename_order(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            for name in ["10.mp4", "1.mp4", "2.mp4"]:
                (folder / name).touch()

            [group] = discover_video_groups(Path(tmp_dir))

            self.assertEqual(
                [path.name for path in group.videos],
                ["1.mp4", "2.mp4", "10.mp4"],
            )

    def test_output_path_uses_video_directory_name(self):
        folder = Path("root") / "course01"

        self.assertEqual(output_path_for_directory(folder), folder / "course01.mp4")

    def test_custom_extensions_override_default_video_extensions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            (folder / "a.xyz").touch()
            (folder / "b.mp4").touch()

            [group] = discover_video_groups(
                Path(tmp_dir),
                extensions=parse_extensions(".xyz"),
            )

            self.assertEqual([path.name for path in group.videos], ["a.xyz"])


class TestMergeVideoPlan(unittest.TestCase):
    def test_single_video_group_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            (folder / "a.mp4").touch()

            [plan] = build_merge_plan(Path(tmp_dir))

            self.assertEqual(plan.action, "skip")
            self.assertIn("only 1 video", plan.reason)

    def test_existing_output_is_skipped_without_force(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            (folder / "1.mp4").touch()
            (folder / "2.mp4").touch()
            (folder / "clips.mp4").touch()

            [plan] = build_merge_plan(Path(tmp_dir), force=False)

            self.assertEqual(plan.action, "skip")
            self.assertIn("output exists", plan.reason)

    def test_existing_output_merges_with_force(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            (folder / "1.mp4").touch()
            (folder / "2.mp4").touch()
            (folder / "clips.mp4").touch()

            [plan] = build_merge_plan(Path(tmp_dir), force=True)

            self.assertEqual(plan.action, "merge")
            self.assertEqual(
                [path.name for path in plan.group.videos],
                ["1.mp4", "2.mp4"],
            )

    def test_output_path_in_sources_is_rejected(self):
        folder = Path("clips")
        output = folder / "clips.mp4"
        group = MergeGroup(
            directory=folder,
            videos=[folder / "1.mp4", output],
            output=output,
        )

        with self.assertRaises(MergeError):
            validate_group_sources(group)


class TestMergeVideoEngine(unittest.TestCase):
    def test_run_ffmpeg_uses_stable_output_decoding(self):
        command = ["ffmpeg", "-version"]
        completed = CompletedProcess(command, 0, stdout="ok", stderr="")

        with patch("mergeVideo.subprocess.run", return_value=completed) as run:
            result = run_ffmpeg(command)

        self.assertIs(result, completed)
        run.assert_called_once_with(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_copy_failure_removes_partial_output_before_transcode_fallback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            videos = [folder / "1.mp4", folder / "2.mp4"]
            for video in videos:
                video.touch()
            output = folder / "clips.mp4"
            group = MergeGroup(directory=folder, videos=videos, output=output)
            calls = []

            def fake_run_ffmpeg(command):
                calls.append(command)
                if len(calls) == 1:
                    output.write_text("partial", encoding="utf-8")
                    return CompletedProcess(command, 1, stderr="copy failed")

                self.assertFalse(output.exists())
                output.write_text("merged", encoding="utf-8")
                return CompletedProcess(command, 0, stderr="")

            with patch("mergeVideo.run_ffmpeg", side_effect=fake_run_ffmpeg):
                merge_group(group, force=True)

            self.assertEqual(output.read_text(encoding="utf-8"), "merged")
            self.assertIn("copy", calls[0])
            self.assertIn("libx264", calls[1])


if __name__ == "__main__":
    unittest.main()
