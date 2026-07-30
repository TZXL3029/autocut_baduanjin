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

    def test_output_path_uses_output_root_with_relative_group_path(self):
        root = Path("root")
        folder = root / "section" / "course01"
        output_root = Path("merged")

        self.assertEqual(
            output_path_for_directory(folder, root, output_root),
            output_root / "section" / "course01" / "course01.mp4",
        )

    def test_output_path_for_root_group_uses_root_directory_name(self):
        root = Path("courses")
        output_root = Path("merged")

        self.assertEqual(
            output_path_for_directory(root, root, output_root),
            output_root / "courses.mp4",
        )

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

    def test_discovery_skips_output_root_inside_input_root(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "source"
            output_root = root / "merged"
            source.mkdir()
            output_root.mkdir()
            (source / "1.mp4").touch()
            (source / "2.mp4").touch()
            (output_root / "old1.mp4").touch()
            (output_root / "old2.mp4").touch()

            groups = discover_video_groups(root, output_root=output_root)

            self.assertEqual([group.directory.name for group in groups], ["source"])
            self.assertEqual(groups[0].output, output_root / "source" / "source.mp4")


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

    def test_existing_output_dir_file_is_skipped_without_force(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            folder = root / "clips"
            output_root = root / "merged"
            folder.mkdir()
            (output_root / "clips").mkdir(parents=True)
            (folder / "1.mp4").touch()
            (folder / "2.mp4").touch()
            (output_root / "clips" / "clips.mp4").touch()

            [plan] = build_merge_plan(root, force=False, output_root=output_root)

            self.assertEqual(plan.action, "skip")
            self.assertIn("output exists", plan.reason)

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

    def test_successful_merge_deletes_source_videos_by_default(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            videos = [folder / "1.mp4", folder / "2.mp4"]
            for video in videos:
                video.touch()
            output = folder / "clips.mp4"
            group = MergeGroup(directory=folder, videos=videos, output=output)

            def fake_run_ffmpeg(command):
                output.write_text("merged", encoding="utf-8")
                return CompletedProcess(command, 0, stderr="")

            with patch("mergeVideo.run_ffmpeg", side_effect=fake_run_ffmpeg):
                merge_group(group, force=True)

            self.assertTrue(output.exists())
            self.assertFalse(videos[0].exists())
            self.assertFalse(videos[1].exists())

    def test_successful_merge_can_keep_source_videos(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            folder = Path(tmp_dir) / "clips"
            folder.mkdir()
            videos = [folder / "1.mp4", folder / "2.mp4"]
            for video in videos:
                video.touch()
            output = folder / "clips.mp4"
            group = MergeGroup(directory=folder, videos=videos, output=output)

            def fake_run_ffmpeg(command):
                output.write_text("merged", encoding="utf-8")
                return CompletedProcess(command, 0, stderr="")

            with patch("mergeVideo.run_ffmpeg", side_effect=fake_run_ffmpeg):
                merge_group(group, force=True, delete_sources=False)

            self.assertTrue(output.exists())
            self.assertTrue(videos[0].exists())
            self.assertTrue(videos[1].exists())


if __name__ == "__main__":
    unittest.main()
