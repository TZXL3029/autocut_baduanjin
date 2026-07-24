import logging
import os
import tempfile
from types import SimpleNamespace
import unittest

from parameterized import parameterized, param

from autocut.cut import Cutter
from config import TestArgs, TEST_MEDIA_PATH, TEST_MEDIA_FILE_SIMPLE, TEST_CONTENT_PATH


class TestCutBounds(unittest.TestCase):
    def test_media_safe_end_uses_shortest_stream_with_margin(self):
        media = SimpleNamespace(
            duration=10.0,
            audio=SimpleNamespace(
                duration=9.5,
                reader=SimpleNamespace(duration=9.0),
            ),
        )

        cut = Cutter(TestArgs())

        self.assertAlmostEqual(cut._media_safe_end(media), 8.99)

    def test_bounded_segment_clamps_end_to_safe_media_end(self):
        cut = Cutter(TestArgs())

        segment = cut._bounded_segment(3.0, 12.0, 8.99, "字幕", 7)

        self.assertEqual(segment["start"], 3.0)
        self.assertEqual(segment["end"], 8.99)
        self.assertEqual(segment["orig_index"], 7)

    def test_bounded_segment_skips_after_safe_media_end(self):
        cut = Cutter(TestArgs())

        self.assertIsNone(cut._bounded_segment(9.0, 12.0, 8.99, "字幕", 8))

    def test_safe_source_basename_collapses_whitespace(self):
        cut = Cutter(TestArgs())

        self.assertEqual(cut._safe_source_basename("my  class cut"), "my_class_cut")


class TestCutBatchInputs(unittest.TestCase):
    def test_cut_jobs_match_current_directory_vocals_cleaned_srt(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            cwd = os.getcwd()
            os.chdir(tmp_dir)
            try:
                os.makedirs("videos")
                media_fn = os.path.join("videos", "test3.mp4")
                srt_fn = "test3_vocals_cleaned.srt"
                open(media_fn, "w").close()
                open(srt_fn, "w").close()

                args = TestArgs()
                args.inputs = [media_fn]

                jobs = Cutter(args)._cut_jobs()

                self.assertEqual(len(jobs), 1)
                self.assertEqual(
                    os.path.abspath(jobs[0]["srt"]), os.path.abspath(srt_fn)
                )
            finally:
                os.chdir(cwd)

    def test_batch_media_inputs_expand_directory_without_recursing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            media_dir = os.path.join(tmp_dir, "videos")
            nested_dir = os.path.join(media_dir, "nested")
            os.makedirs(nested_dir)
            open(os.path.join(media_dir, "a.mp4"), "w").close()
            open(os.path.join(media_dir, "b.mp3"), "w").close()
            open(os.path.join(media_dir, "a.srt"), "w").close()
            open(os.path.join(nested_dir, "c.mp4"), "w").close()

            args = TestArgs()
            args.inputs = [media_dir]

            media_files = Cutter(args)._batch_media_inputs()

            self.assertEqual(
                [os.path.basename(media_fn) for media_fn in media_files],
                ["a.mp4", "b.mp3"],
            )

    def test_output_dir_uses_media_name_subdirectories_for_batch_jobs(self):
        args = TestArgs()
        args.output_dir = "out"

        out_dir = Cutter(args)._output_dir_for_job(
            {"media": os.path.join("videos", "test3.mp4")},
            multi_job=True,
        )

        self.assertEqual(out_dir, os.path.join("out", "test3_name"))

    def test_output_dir_collapses_media_name_spaces_for_batch_jobs(self):
        args = TestArgs()
        args.output_dir = "out"

        out_dir = Cutter(args)._output_dir_for_job(
            {"media": os.path.join("videos", "my  class.mp4")},
            multi_job=True,
        )

        self.assertEqual(out_dir, os.path.join("out", "my_class_name"))


class TestCut(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.info("检查测试文件是否正常存在")
        scan_file = os.listdir(TEST_MEDIA_PATH)
        logging.info(
            "应存在文件列表："
            + str(TEST_MEDIA_FILE_SIMPLE)
            + "  扫描到文件列表："
            + str(scan_file)
        )
        for file in TEST_MEDIA_FILE_SIMPLE:
            assert file in scan_file

    def tearDown(self):
        for file in TEST_MEDIA_FILE_SIMPLE:
            cut_prefix = os.path.splitext(file)[0] + "_cut"
            for output_file in os.listdir(TEST_MEDIA_PATH):
                if not output_file.startswith(cut_prefix):
                    continue
                if os.path.splitext(output_file)[1].lower() not in [".mp4", ".mp3"]:
                    continue
                os.remove(os.path.join(TEST_MEDIA_PATH, output_file))

    def assert_cut_output_exists(self, file_name):
        cut_prefix = os.path.splitext(file_name)[0] + "_cut_"
        self.assertTrue(
            any(
                output_file.startswith(cut_prefix)
                and os.path.splitext(output_file)[1].lower() in [".mp4", ".mp3"]
                for output_file in os.listdir(TEST_MEDIA_PATH)
            )
        )

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE_SIMPLE])
    def test_srt_cut(self, file_name):
        args = TestArgs()
        args.inputs = [
            os.path.join(TEST_MEDIA_PATH, file_name),
            os.path.join(TEST_CONTENT_PATH, "test_srt.srt"),
        ]
        cut = Cutter(args)
        cut.run()
        self.assert_cut_output_exists(file_name)

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE_SIMPLE])
    def test_md_cut(self, file_name):
        args = TestArgs()
        args.inputs = [
            TEST_MEDIA_PATH + file_name,
            os.path.join(TEST_CONTENT_PATH, "test.srt"),
            os.path.join(TEST_CONTENT_PATH, "test_md.md"),
        ]
        cut = Cutter(args)
        cut.run()
        self.assert_cut_output_exists(file_name)
