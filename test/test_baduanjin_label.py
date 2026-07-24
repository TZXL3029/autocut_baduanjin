import json
import os
import tempfile
import unittest
from importlib import util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "autocut" / "baduanjin_label.py"
SPEC = util.spec_from_file_location("baduanjin_label", MODULE_PATH)
baduanjin_label = util.module_from_spec(SPEC)
SPEC.loader.exec_module(baduanjin_label)

auto_label_directory = baduanjin_label.auto_label_directory
build_json_manifest = baduanjin_label.build_json_manifest
default_json_path = baduanjin_label.default_json_path
parse_clip_filename = baduanjin_label.parse_clip_filename
run = baduanjin_label.run
scan_clips = baduanjin_label.scan_clips
sync_labeled_folders = baduanjin_label.sync_labeled_folders
text_to_pinyin = baduanjin_label.text_to_pinyin


class TestBaduanjinLabel(unittest.TestCase):
    def test_parse_clip_filename(self):
        record = parse_clip_filename("test6_cut_113_环环怒目.mp4")

        self.assertEqual(record.source_video, "test6_cut")
        self.assertEqual(record.segment_index, 113)
        self.assertEqual(record.text_hint, "环环怒目")

    def test_parse_clip_filename_normalizes_source_video_spaces(self):
        record = parse_clip_filename("my  class cut_12_两手拖天.mp4")

        self.assertEqual(record.filename, "my  class cut_12_两手拖天.mp4")
        self.assertEqual(record.source_video, "my_class_cut")
        self.assertEqual(record.segment_index, 12)
        self.assertEqual(record.text_hint, "两手拖天")

    def test_auto_label_directory_uses_text_and_sequence(self):
        names = [
            "test6_cut_1_预备示范.mp4",
            "test6_cut_9_两手拖天顶.mp4",
            "test6_cut_10_上 呼 习.mp4",
            "test6_cut_19_呼气.mp4",
            "test6_cut_21_开工呼气四.mp4",
            "test6_cut_39_辽宜品味.mp4",
            "test6_cut_51_古老七上.mp4",
            "test6_cut_63_摇头摆尾.mp4",
            "test6_cut_81_两手攀足呼.mp4",
            "test6_cut_113_环环怒目.mp4",
            "test6_cut_130_背后七天.mp4",
            "test6_cut_145_气成单.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[1]["big_label"], "intro_outro")
            self.assertEqual(by_index[9]["action_label"], "01_两手托天理三焦")
            self.assertEqual(by_index[10]["action_label"], "01_两手托天理三焦")
            self.assertEqual(by_index[21]["action_label"], "02_左右开弓似射雕")
            self.assertEqual(by_index[39]["action_label"], "03_调理脾胃须单举")
            self.assertEqual(by_index[51]["action_label"], "04_五劳七伤往后瞧")
            self.assertEqual(by_index[63]["action_label"], "05_摇头摆尾去心火")
            self.assertEqual(by_index[81]["action_label"], "06_两手攀足固肾腰")
            self.assertEqual(by_index[113]["action_label"], "07_攒拳怒目增气力")
            self.assertEqual(by_index[130]["action_label"], "08_背后七颠百病消")
            self.assertEqual(by_index[145]["big_label"], "intro_outro")
            self.assertEqual(by_index[19]["review"], "yes")
            self.assertIn("near_next_action_boundary", by_index[19]["notes"])

    def test_pinyin_matching_handles_same_sound_typos(self):
        names = [
            "test6_cut_1_两手拖天顶.mp4",
            "test6_cut_2_吸气.mp4",
            "test6_cut_3_开工呼气四.mp4",
            "test6_cut_4_辽宜品味.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(text_to_pinyin("两手拖天"), text_to_pinyin("两手托天"))
            self.assertEqual(by_index[1]["action_label"], "01_两手托天理三焦")
            self.assertEqual(by_index[3]["action_label"], "02_左右开弓似射雕")
            self.assertEqual(by_index[4]["action_label"], "03_调理脾胃须单举")
            self.assertNotIn("matched_action_terms", by_index[2]["notes"])

    def test_roman_aliases_do_not_pinyin_match_chinese_words(self):
        names = [
            "test6_cut_1_病气良.mp4",
            "test6_cut_2_BING.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            records = scan_clips(temp_dir)
            by_hint = {record.text_hint: record for record in records}

            self.assertIsNone(by_hint["病气良"].direct_action)
            self.assertEqual(by_hint["BING"].direct_action, 2)
            self.assertEqual(by_hint["BING"].direct_action_score, 2)

    def test_numbered_action_prompts_create_boundaries(self):
        names = [
            "test8_cut_1_准备动作.mp4",
            "test8_cut_2_向上吸气.mp4",
            "test8_cut_55_第二个动作.mp4",
            "test8_cut_56_拉弓下蹲.mp4",
            "test8_cut_74_第三个动作.mp4",
            "test8_cut_75_上举左手.mp4",
            "test8_cut_86_第四个动作.mp4",
            "test8_cut_98_第五个动作.mp4",
            "test8_cut_117_第六个动作.mp4",
            "test8_cut_146_第七个动作.mp4",
            "test8_cut_168_最后一个动.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[1]["big_label"], "intro_outro")
            self.assertEqual(by_index[55]["action_label"], "02_左右开弓似射雕")
            self.assertEqual(by_index[74]["action_label"], "03_调理脾胃须单举")
            self.assertEqual(by_index[86]["action_label"], "04_五劳七伤往后瞧")
            self.assertEqual(by_index[98]["action_label"], "05_摇头摆尾去心火")
            self.assertEqual(by_index[117]["action_label"], "06_两手攀足固肾腰")
            self.assertEqual(by_index[146]["action_label"], "07_攒拳怒目增气力")
            self.assertEqual(by_index[168]["action_label"], "08_背后七颠百病消")

    def test_current_transcription_typos_create_missing_action_boundaries(self):
        names = [
            "test2_cut_1_左脚开步.mp4",
            "test2_cut_7_两手拖天里.mp4",
            "test2_cut_18_左右开工自.mp4",
            "test2_cut_33_遥离匹位.mp4",
            "test2_cut_40_右桥.mp4",
            "test2_cut_52_摇头摆尾.mp4",
            "test2_cut_75_双手盘足.mp4",
            "test2_cut_96_握拳回收.mp4",
            "test2_cut_112_背后七天.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[33]["action_label"], "03_调理脾胃须单举")
            self.assertEqual(by_index[40]["action_label"], "04_五劳七伤往后瞧")
            self.assertEqual(by_index[75]["action_label"], "06_两手攀足固肾腰")
            self.assertEqual(by_index[96]["action_label"], "07_攒拳怒目增气力")

    def test_corpus_aliases_match_without_moving_boundaries(self):
        names = [
            "test38_cut_1_两手托天.mp4",
            "test38_cut_2_吸气上锅.mp4",
            "test38_cut_18_左右开工.mp4",
            "test38_cut_19_BING.mp4",
            "test38_cut_33_调理品味.mp4",
            "test38_cut_46_后桥.mp4",
            "test38_cut_47_右转.mp4",
            "test38_cut_58_摇头摆为去.mp4",
            "test38_cut_59_做青.mp4",
            "test38_cut_73_两手攀足.mp4",
            "test38_cut_74_潘族.mp4",
            "test38_cut_96_攒拳怒目.mp4",
            "test38_cut_97_卓阿悟.mp4",
            "test38_cut_112_背后七天.mp4",
            "test38_cut_113_天足.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[2]["action_label"], "01_两手托天理三焦")
            self.assertIn("吸气上锅", by_index[2]["notes"])
            self.assertEqual(by_index[19]["action_label"], "02_左右开弓似射雕")
            self.assertIn("bing", by_index[19]["notes"].lower())
            self.assertEqual(by_index[47]["action_label"], "04_五劳七伤往后瞧")
            self.assertEqual(by_index[59]["action_label"], "05_摇头摆尾去心火")
            self.assertIn("做青", by_index[59]["notes"])
            self.assertEqual(by_index[74]["action_label"], "06_两手攀足固肾腰")
            self.assertIn("潘族", by_index[74]["notes"])
            self.assertEqual(by_index[97]["action_label"], "07_攒拳怒目增气力")
            self.assertIn("卓阿悟", by_index[97]["notes"])
            self.assertEqual(by_index[113]["action_label"], "08_背后七颠百病消")
            self.assertIn("天足", by_index[113]["notes"])

    def test_transition_cues_repair_skipped_action_numbers(self):
        names = [
            "test9_cut_30_第一个动作.mp4",
            "test9_cut_59_左右开工.mp4",
            "test9_cut_88_调理皮胃.mp4",
            "test9_cut_125_五老七商往.mp4",
            "test9_cut_154_再一次准备.mp4",
            "test9_cut_160_吸气身体再.mp4",
            "test9_cut_181_第六个动作.mp4",
            "test9_cut_221_准备下一个.mp4",
            "test9_cut_229_握拳回收.mp4",
            "test9_cut_251_第八个动作.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[154]["big_label"], "transition")
            self.assertEqual(by_index[154]["action_label"], "setup_transition")
            self.assertEqual(by_index[160]["action_label"], "05_摇头摆尾去心火")
            self.assertEqual(by_index[221]["big_label"], "transition")
            self.assertEqual(by_index[221]["action_label"], "setup_transition")
            self.assertEqual(by_index[229]["action_label"], "07_攒拳怒目增气力")

    def test_transition_cue_is_not_labeled_as_first_or_eighth_action(self):
        names = [
            "test9_cut_30_第一个动作.mp4",
            "test9_cut_58_我们准备下.mp4",
            "test9_cut_59_左右开工.mp4",
            "test9_cut_221_准备下一个.mp4",
            "test9_cut_229_握拳回收.mp4",
            "test9_cut_251_第八个动作.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[58]["big_label"], "transition")
            self.assertEqual(by_index[58]["action_label"], "setup_transition")
            self.assertEqual(by_index[221]["big_label"], "transition")
            self.assertEqual(by_index[221]["action_label"], "setup_transition")

    def test_misrecognized_closing_terms_are_not_labeled_as_eighth_action(self):
        names = [
            "test10_cut_1_第一个动作.mp4",
            "test10_cut_20_第二个动作.mp4",
            "test10_cut_30_第三个动作.mp4",
            "test10_cut_40_第四个动作.mp4",
            "test10_cut_50_第五个动作.mp4",
            "test10_cut_60_第六个动作.mp4",
            "test10_cut_70_第七个动作.mp4",
            "test10_cut_80_第八个动作.mp4",
            "test10_cut_90_呼气颠足.mp4",
            "test10_cut_100_气沉丹田.mp4",
            "test10_cut_101_呼吸君临.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[90]["action_label"], "08_背后七颠百病消")
            self.assertEqual(by_index[100]["big_label"], "intro_outro")
            self.assertEqual(by_index[100]["action_label"], "09_收势")
            self.assertEqual(by_index[101]["big_label"], "intro_outro")
            self.assertEqual(by_index[101]["action_label"], "09_收势")

    def test_intro_interval_starts_at_misrecognized_prepare_prompt(self):
        names = [
            "test7_cut_1_八段紧12.mp4",
            "test7_cut_2_必备是 锁.mp4",
            "test7_cut_3_屈膝下蹲.mp4",
            "test7_cut_4_两手拖天.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[1]["big_label"], "irrelevant")
            self.assertEqual(by_index[1]["action_label"], "opening")
            self.assertEqual(by_index[2]["big_label"], "intro_outro")
            self.assertEqual(by_index[2]["action_label"], "00_预备势")
            self.assertEqual(by_index[3]["big_label"], "intro_outro")
            self.assertEqual(by_index[3]["action_label"], "00_预备势")
            self.assertEqual(by_index[4]["action_label"], "01_两手托天理三焦")

    def test_irrelevant_opening_and_closing_are_strict_intervals(self):
        names = [
            "test8_cut_1_Hello.mp4",
            "test8_cut_2_今天给大家.mp4",
            "test8_cut_23_首先是准备.mp4",
            "test8_cut_24_脚自然的稍.mp4",
            "test8_cut_40_十指相扣向.mp4",
            "test8_cut_55_第二个动作.mp4",
            "test8_cut_74_第三个动作.mp4",
            "test8_cut_86_第四个动作.mp4",
            "test8_cut_98_第五个动作.mp4",
            "test8_cut_117_第六个动作.mp4",
            "test8_cut_146_第七个动作.mp4",
            "test8_cut_168_最后一个动.mp4",
            "test8_cut_170_提起教育兼.mp4",
            "test8_cut_177_两掌合于父.mp4",
            "test8_cut_178_大家太棒了.mp4",
            "test8_cut_179_我也希望大.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[1]["big_label"], "irrelevant")
            self.assertEqual(by_index[1]["action_label"], "opening")
            self.assertEqual(by_index[23]["big_label"], "intro_outro")
            self.assertEqual(by_index[23]["action_label"], "00_预备势")
            self.assertEqual(by_index[24]["big_label"], "intro_outro")
            self.assertEqual(by_index[24]["action_label"], "00_预备势")
            self.assertEqual(by_index[170]["big_label"], "action")
            self.assertEqual(by_index[170]["action_label"], "08_背后七颠百病消")
            self.assertEqual(by_index[177]["big_label"], "intro_outro")
            self.assertEqual(by_index[177]["action_label"], "09_收势")
            self.assertEqual(by_index[178]["big_label"], "irrelevant")
            self.assertEqual(by_index[178]["action_label"], "closing")
            self.assertEqual(by_index[179]["action_label"], "closing")

    def test_sync_labeled_folders_copies_to_action_subfolder(self):
        with tempfile.TemporaryDirectory() as input_dir:
            with tempfile.TemporaryDirectory() as output_dir:
                filename = "test6_cut_9_两手拖天顶.mp4"
                open(os.path.join(input_dir, filename), "wb").close()
                rows = [
                    {
                        "filename": filename,
                        "big_label": "action",
                        "action_label": "01_两手托天理三焦",
                    }
                ]

                counts = sync_labeled_folders(rows, input_dir, output_dir)

                self.assertEqual(counts["copied"], 1)
                self.assertTrue(
                    os.path.exists(
                        os.path.join(
                            output_dir,
                            "action",
                            "01_两手托天理三焦",
                            filename,
                        )
                    )
                )

    def test_build_json_manifest_marks_action_samples_for_training(self):
        rows = [
            {
                "filename": "test6_cut_9_两手拖天顶.mp4",
                "source_video": "test6 cut",
                "segment_index": "9",
                "text_hint": "两手拖天顶",
                "big_label": "action",
                "action_label": "01_两手托天理三焦",
                "confidence": "high",
                "review": "no",
                "notes": "matched_action_terms=strong:两手托天:pinyin; sequence_inferred",
            },
            {
                "filename": "test6_cut_1_预备示范.mp4",
                "source_video": "test6_cut",
                "segment_index": "1",
                "text_hint": "预备示范",
                "big_label": "intro_outro",
                "action_label": "00_预备势",
                "confidence": "medium",
                "review": "yes",
                "notes": "inside_intro_interval",
            },
        ]

        with tempfile.TemporaryDirectory() as input_dir:
            manifest = build_json_manifest(
                rows,
                input_dir,
                csv_path=os.path.join(input_dir, "labels.csv"),
                output_dir=os.path.join(input_dir, "labeled"),
            )

        action_sample = manifest["samples"][0]
        intro_sample = manifest["samples"][1]

        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["task_type"], "video_classification")
        self.assertEqual(manifest["task"]["routine"], "baduanjin")
        self.assertEqual(action_sample["id"], "test6_cut:9")
        self.assertEqual(action_sample["source_video"], "test6_cut")
        self.assertEqual(action_sample["label_id"], 1)
        self.assertEqual(action_sample["label_name"], "01_两手托天理三焦")
        self.assertTrue(action_sample["training_eligible"])
        self.assertFalse(action_sample["review_required"])
        self.assertEqual(action_sample["split"], "unassigned")
        self.assertEqual(
            action_sample["notes"],
            [
                "matched_action_terms=strong:两手托天:pinyin",
                "sequence_inferred",
            ],
        )
        self.assertIsNone(intro_sample["label_id"])
        self.assertFalse(intro_sample["training_eligible"])
        self.assertTrue(intro_sample["review_required"])
        self.assertEqual(manifest["summary"]["total_segments"], 2)
        self.assertEqual(manifest["summary"]["action_segments"], 1)
        self.assertEqual(manifest["summary"]["review_required"], 1)

    def test_run_writes_json_manifest_next_to_csv_by_default(self):
        names = [
            "test6_cut_1_预备示范.mp4",
            "test6_cut_9_两手拖天顶.mp4",
        ]

        with tempfile.TemporaryDirectory() as input_dir:
            for name in names:
                open(os.path.join(input_dir, name), "wb").close()

            run(input_dir, copy_files=False)
            json_path = default_json_path(input_dir)

            self.assertTrue(os.path.exists(json_path))
            with open(json_path, encoding="utf-8") as json_file:
                manifest = json.load(json_file)

            self.assertEqual(manifest["task"]["routine"], "baduanjin")
            self.assertEqual(len(manifest["samples"]), 2)
            self.assertEqual(manifest["samples"][1]["label_id"], 1)


if __name__ == "__main__":
    unittest.main()
