import logging
import os
import tempfile
from types import SimpleNamespace
import unittest

from parameterized import parameterized, param
import srt

from autocut.utils import MD
from config import (
    TEST_MEDIA_FILE,
    TestArgs,
    TEST_MEDIA_FILE_SIMPLE,
    TEST_MEDIA_FILE_LANG,
    TEST_MEDIA_PATH,
)
from autocut.transcribe import Transcribe


class TestTranscribeOutputPaths(unittest.TestCase):
    def test_transcription_inputs_expands_folder_to_non_recursive_media(self):
        transcribe = Transcribe.__new__(Transcribe)

        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_dir = os.path.join(tmp_dir, "nested.mp4")
            os.makedirs(nested_dir)
            for name in [
                "b.mov",
                "a.mp4",
                "audio.wav",
                "voice.mp3",
                "notes.md",
                "c.MP4",
            ]:
                with open(os.path.join(tmp_dir, name), "wb"):
                    pass
            with open(os.path.join(nested_dir, "nested.mp4"), "wb"):
                pass

            transcribe.args = SimpleNamespace(inputs=[tmp_dir])

            self.assertEqual(
                transcribe._transcription_inputs(),
                [
                    os.path.join(tmp_dir, "a.mp4"),
                    os.path.join(tmp_dir, "audio.wav"),
                    os.path.join(tmp_dir, "b.mov"),
                    os.path.join(tmp_dir, "c.MP4"),
                    os.path.join(tmp_dir, "voice.mp3"),
                ],
            )

    def test_transcription_inputs_keeps_file_inputs(self):
        transcribe = Transcribe.__new__(Transcribe)
        transcribe.args = SimpleNamespace(inputs=[os.path.join("media", "clip.mp4")])

        self.assertEqual(
            transcribe._transcription_inputs(),
            [os.path.join("media", "clip.mp4")],
        )

    def test_output_base_uses_output_dir(self):
        transcribe = Transcribe.__new__(Transcribe)
        transcribe.args = SimpleNamespace(output_dir="out")

        self.assertEqual(
            transcribe._output_base(os.path.join("media", "clip.mp4")),
            os.path.join("out", "clip"),
        )

    def test_save_md_links_video_relative_to_output_dir(self):
        transcribe = Transcribe.__new__(Transcribe)
        transcribe.args = SimpleNamespace(encoding="utf-8")

        with tempfile.TemporaryDirectory() as tmp_dir:
            media_dir = os.path.join(tmp_dir, "media")
            output_dir = os.path.join(tmp_dir, "out")
            os.makedirs(media_dir)
            os.makedirs(output_dir)
            video_fn = os.path.join(media_dir, "clip.mp4")
            srt_fn = os.path.join(output_dir, "clip.srt")
            md_fn = os.path.join(output_dir, "clip.md")

            with open(video_fn, "wb"):
                pass
            subtitle = srt.Subtitle(
                index=1,
                start=srt.srt_timestamp_to_timedelta("00:00:00,000"),
                end=srt.srt_timestamp_to_timedelta("00:00:01,000"),
                content="hello",
            )
            with open(srt_fn, "wb") as f:
                f.write(srt.compose([subtitle]).encode("utf-8"))

            transcribe._save_md(md_fn, srt_fn, video_fn)

            with open(md_fn, encoding="utf-8") as f:
                md_content = f.read()

        self.assertIn('src="../media/clip.mp4"', md_content)


class TestTranscribe(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        logging.info("检查测试文件是否正常存在")
        scan_file = os.listdir(TEST_MEDIA_PATH)
        logging.info(
            "应存在文件列表："
            + str(TEST_MEDIA_FILE)
            + str(TEST_MEDIA_FILE_LANG)
            + str(TEST_MEDIA_FILE_SIMPLE)
            + "  扫描到文件列表："
            + str(scan_file)
        )
        for file in TEST_MEDIA_FILE:
            assert file in scan_file
        for file in TEST_MEDIA_FILE_LANG:
            assert file in scan_file
        for file in TEST_MEDIA_FILE_SIMPLE:
            assert file in scan_file

    @classmethod
    def tearDownClass(cls):
        for file in os.listdir(TEST_MEDIA_PATH):
            if file.endswith("md") or file.endswith("srt"):
                os.remove(TEST_MEDIA_PATH + file)

    def tearDown(self):
        for file in TEST_MEDIA_FILE_SIMPLE:
            if os.path.exists(TEST_MEDIA_PATH + file.split(".")[0] + ".md"):
                os.remove(TEST_MEDIA_PATH + file.split(".")[0] + ".md")
            if os.path.exists(TEST_MEDIA_PATH + file.split(".")[0] + ".srt"):
                os.remove(TEST_MEDIA_PATH + file.split(".")[0] + ".srt")

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE])
    def test_default_transcribe(self, file_name):
        logging.info("检查默认参数生成字幕")
        args = TestArgs()
        args.inputs = [TEST_MEDIA_PATH + file_name]
        transcribe = Transcribe(args)
        transcribe.run()
        self.assertTrue(
            os.path.exists(TEST_MEDIA_PATH + file_name.split(".")[0] + ".md")
        )

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE])
    def test_jump_done_transcribe(self, file_name):
        logging.info("检查默认参数跳过生成字幕")
        args = TestArgs()
        args.inputs = [TEST_MEDIA_PATH + file_name]
        transcribe = Transcribe(args)
        transcribe.run()
        self.assertTrue(
            os.path.exists(TEST_MEDIA_PATH + file_name.split(".")[0] + ".md")
        )

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE_LANG])
    def test_en_transcribe(self, file_name):
        logging.info("检查--lang='en'参数生成字幕")
        args = TestArgs()
        args.lang = "en"
        args.inputs = [TEST_MEDIA_PATH + file_name]
        transcribe = Transcribe(args)
        transcribe.run()
        self.assertTrue(
            os.path.exists(TEST_MEDIA_PATH + file_name.split(".")[0] + ".md")
        )

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE_LANG])
    def test_force_transcribe(self, file_name):
        logging.info("检查--force参数生成字幕")
        args = TestArgs()
        args.force = True
        args.inputs = [TEST_MEDIA_PATH + file_name]
        md0_lens = len(
            "".join(
                MD(
                    TEST_MEDIA_PATH + file_name.split(".")[0] + ".md", args.encoding
                ).lines
            )
        )
        transcribe = Transcribe(args)
        transcribe.run()
        md1_lens = len(
            "".join(
                MD(
                    TEST_MEDIA_PATH + file_name.split(".")[0] + ".md", args.encoding
                ).lines
            )
        )
        self.assertLessEqual(md1_lens, md0_lens)

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE_SIMPLE])
    def test_encoding_transcribe(self, file_name):
        logging.info("检查--encoding参数生成字幕")
        args = TestArgs()
        args.encoding = "gbk"
        args.inputs = [TEST_MEDIA_PATH + file_name]
        transcribe = Transcribe(args)
        transcribe.run()
        with open(
            os.path.join(TEST_MEDIA_PATH + file_name.split(".")[0] + ".md"),
            encoding="gbk",
        ):
            self.assertTrue(True)

    @parameterized.expand([param(file) for file in TEST_MEDIA_FILE_SIMPLE])
    def test_vad_transcribe(self, file_name):
        logging.info("检查--vad参数生成字幕")
        args = TestArgs()
        args.force = True
        args.vad = True
        args.inputs = [TEST_MEDIA_PATH + file_name]
        transcribe = Transcribe(args)
        transcribe.run()
        self.assertTrue(
            os.path.exists(TEST_MEDIA_PATH + file_name.split(".")[0] + ".md")
        )
