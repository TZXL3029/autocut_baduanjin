import os
import tempfile
import unittest
from importlib import util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "autocut" / "taiji24_label.py"
SPEC = util.spec_from_file_location("taiji24_label", MODULE_PATH)
taiji24_label = util.module_from_spec(SPEC)
SPEC.loader.exec_module(taiji24_label)

auto_label_directory = taiji24_label.auto_label_directory
build_json_manifest = taiji24_label.build_json_manifest
parse_clip_filename = taiji24_label.parse_clip_filename
sync_labeled_folders = taiji24_label.sync_labeled_folders
text_to_pinyin = taiji24_label.text_to_pinyin


class TestTaiji24Label(unittest.TestCase):
    def test_auto_label_directory_labels_formal_actions(self):
        names = [
            "taiji_cut_1_二十四式太极拳.mp4",
            "taiji_cut_3_起势.mp4",
            "taiji_cut_4_两臂前举.mp4",
            "taiji_cut_7_野马分鬃.mp4",
            "taiji_cut_12_白鹤亮翅.mp4",
            "taiji_cut_16_搂膝拗步.mp4",
            "taiji_cut_20_手挥琵琶.mp4",
            "taiji_cut_23_倒卷肱.mp4",
            "taiji_cut_28_左揽雀尾.mp4",
            "taiji_cut_34_右揽雀尾.mp4",
            "taiji_cut_41_单鞭.mp4",
            "taiji_cut_46_云手.mp4",
            "taiji_cut_50_单鞭.mp4",
            "taiji_cut_55_高探马.mp4",
            "taiji_cut_58_右蹬脚.mp4",
            "taiji_cut_62_双峰贯耳.mp4",
            "taiji_cut_65_转身左蹬脚.mp4",
            "taiji_cut_69_下势独立.mp4",
            "taiji_cut_73_下势独立.mp4",
            "taiji_cut_77_穿梭.mp4",
            "taiji_cut_81_海底针.mp4",
            "taiji_cut_84_闪通背.mp4",
            "taiji_cut_88_搬拦捶.mp4",
            "taiji_cut_92_如封似闭.mp4",
            "taiji_cut_96_十字手.mp4",
            "taiji_cut_100_收势.mp4",
            "taiji_cut_101_谢谢观看.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[1]["big_label"], "irrelevant")
            self.assertEqual(by_index[1]["action_label"], "opening")
            self.assertEqual(by_index[3]["action_label"], "01_起势")
            self.assertEqual(by_index[4]["action_label"], "01_起势")
            self.assertEqual(by_index[7]["action_label"], "02_左右野马分鬃")
            self.assertEqual(by_index[12]["action_label"], "03_白鹤亮翅")
            self.assertEqual(by_index[16]["action_label"], "04_左右搂膝拗步")
            self.assertEqual(by_index[20]["action_label"], "05_手挥琵琶")
            self.assertEqual(by_index[23]["action_label"], "06_左右倒卷肱")
            self.assertEqual(by_index[28]["action_label"], "07_左揽雀尾")
            self.assertEqual(by_index[34]["action_label"], "08_右揽雀尾")
            self.assertEqual(by_index[41]["action_label"], "09_单鞭")
            self.assertEqual(by_index[46]["action_label"], "10_云手")
            self.assertEqual(by_index[50]["action_label"], "11_单鞭")
            self.assertEqual(by_index[55]["action_label"], "12_高探马")
            self.assertEqual(by_index[58]["action_label"], "13_右蹬脚")
            self.assertEqual(by_index[62]["action_label"], "14_双峰贯耳")
            self.assertEqual(by_index[65]["action_label"], "15_转身左蹬脚")
            self.assertEqual(by_index[69]["action_label"], "16_左下势独立")
            self.assertEqual(by_index[73]["action_label"], "17_右下势独立")
            self.assertEqual(by_index[77]["action_label"], "18_左右穿梭")
            self.assertEqual(by_index[81]["action_label"], "19_海底针")
            self.assertEqual(by_index[84]["action_label"], "20_闪通背")
            self.assertEqual(by_index[88]["action_label"], "21_转身搬拦捶")
            self.assertEqual(by_index[92]["action_label"], "22_如封似闭")
            self.assertEqual(by_index[96]["action_label"], "23_十字手")
            self.assertEqual(by_index[100]["big_label"], "action")
            self.assertEqual(by_index[100]["action_label"], "24_收势")
            self.assertEqual(by_index[101]["big_label"], "irrelevant")
            self.assertEqual(by_index[101]["action_label"], "closing")

    def test_auto_label_directory_handles_noisy_testb_boundaries(self):
        names = [
            "testB_cut_1_24世太极.mp4",
            "testB_cut_2_分角开步.mp4",
            "testB_cut_6_呼气下安.mp4",
            "testB_cut_7_左右野马分.mp4",
            "testB_cut_14_白喝量赤.mp4",
            "testB_cut_18_左右捞稀澳.mp4",
            "testB_cut_25_手灰琵琶.mp4",
            "testB_cut_26_左右道卷工.mp4",
            "testB_cut_29_灼烂却尾.mp4",
            "testB_cut_36_公布庞守.mp4",
            "testB_cut_43_元首三.mp4",
            "testB_cut_44_勾手转体.mp4",
            "testB_cut_48_双风罐.mp4",
            "testB_cut_50_转身左灯角.mp4",
            "testB_cut_53_是我下世独.mp4",
            "testB_cut_56_又下时都没.mp4",
            "testB_cut_58_左右传说.mp4",
            "testB_cut_63_虚不叉仗.mp4",
            "testB_cut_64_转身斑斓.mp4",
            "testB_cut_68_如风似壁.mp4",
            "testB_cut_72_交叉搭手.mp4",
            "testB_cut_75_并无怀缘.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[1]["big_label"], "irrelevant")
            self.assertEqual(by_index[2]["action_label"], "01_起势")
            self.assertEqual(by_index[7]["action_label"], "02_左右野马分鬃")
            self.assertEqual(by_index[14]["action_label"], "03_白鹤亮翅")
            self.assertEqual(by_index[18]["action_label"], "04_左右搂膝拗步")
            self.assertEqual(by_index[25]["action_label"], "05_手挥琵琶")
            self.assertEqual(by_index[26]["action_label"], "06_左右倒卷肱")
            self.assertEqual(by_index[29]["action_label"], "07_左揽雀尾")
            self.assertEqual(by_index[36]["action_label"], "08_右揽雀尾")
            self.assertEqual(by_index[43]["action_label"], "10_云手")
            self.assertEqual(by_index[44]["action_label"], "11_单鞭")
            self.assertEqual(by_index[48]["action_label"], "14_双峰贯耳")
            self.assertEqual(by_index[50]["action_label"], "15_转身左蹬脚")
            self.assertEqual(by_index[53]["action_label"], "16_左下势独立")
            self.assertEqual(by_index[56]["action_label"], "17_右下势独立")
            self.assertEqual(by_index[58]["action_label"], "18_左右穿梭")
            self.assertEqual(by_index[63]["action_label"], "19_海底针")
            self.assertEqual(by_index[64]["action_label"], "21_转身搬拦捶")
            self.assertEqual(by_index[68]["action_label"], "22_如封似闭")
            self.assertEqual(by_index[72]["action_label"], "23_十字手")
            self.assertEqual(by_index[75]["action_label"], "24_收势")

    def test_auto_label_directory_handles_noisy_ordinal_suffixes(self):
        names = [
            "testB_cut_81_第十四世.mp4",
            "testB_cut_83_第15式.mp4",
            "testB_cut_89_一十六十.mp4",
            "testB_cut_93_第17世.mp4",
            "testB_cut_99_第十八事.mp4",
            "testB_cut_106_第19时.mp4",
            "testB_cut_111_第21世.mp4",
            "testB_cut_116_第22史.mp4",
            "testB_cut_120_第23世.mp4",
            "testB_cut_123_第24集.mp4",
        ]

        with tempfile.TemporaryDirectory() as temp_dir:
            for name in names:
                open(os.path.join(temp_dir, name), "wb").close()

            rows = auto_label_directory(temp_dir)
            by_index = {int(row["segment_index"]): row for row in rows}

            self.assertEqual(by_index[81]["action_label"], "14_双峰贯耳")
            self.assertEqual(by_index[83]["action_label"], "15_转身左蹬脚")
            self.assertEqual(by_index[89]["action_label"], "16_左下势独立")
            self.assertEqual(by_index[93]["action_label"], "17_右下势独立")
            self.assertEqual(by_index[99]["action_label"], "18_左右穿梭")
            self.assertEqual(by_index[106]["action_label"], "19_海底针")
            self.assertEqual(by_index[111]["action_label"], "21_转身搬拦捶")
            self.assertEqual(by_index[116]["action_label"], "22_如封似闭")
            self.assertEqual(by_index[120]["action_label"], "23_十字手")
            self.assertEqual(by_index[123]["action_label"], "24_收势")

    def test_pypinyin_handles_taiji_terms(self):
        self.assertEqual(text_to_pinyin("倒卷肱"), "daojuangong")
        self.assertEqual(text_to_pinyin("搬拦捶"), "banlanchui")

    def test_build_json_manifest_uses_taiji24_label_taxonomy(self):
        rows = [
            {
                "filename": "taiji_cut_3_起势.mp4",
                "source_video": "taiji_cut",
                "segment_index": "3",
                "text_hint": "起势",
                "big_label": "action",
                "action_label": "01_起势",
                "confidence": "high",
                "review": "no",
                "notes": "",
            }
        ]

        with tempfile.TemporaryDirectory() as input_dir:
            manifest = build_json_manifest(rows, input_dir)

        self.assertEqual(manifest["task"]["routine"], "taiji24")
        self.assertEqual(len(manifest["label_taxonomy"]["actions"]), 24)
        self.assertEqual(manifest["samples"][0]["label_id"], 1)
        self.assertEqual(manifest["samples"][0]["label_name"], "01_起势")

    def test_parse_and_sync_reuse_common_helpers(self):
        record = parse_clip_filename("taiji_cut_41_单鞭.mp4")

        self.assertEqual(record.source_video, "taiji_cut")
        self.assertEqual(record.segment_index, 41)
        self.assertEqual(record.text_hint, "单鞭")

        with tempfile.TemporaryDirectory() as input_dir:
            with tempfile.TemporaryDirectory() as output_dir:
                filename = "taiji_cut_3_起势.mp4"
                open(os.path.join(input_dir, filename), "wb").close()
                counts = sync_labeled_folders(
                    [
                        {
                            "filename": filename,
                            "big_label": "action",
                            "action_label": "01_起势",
                        }
                    ],
                    input_dir,
                    output_dir,
                )

                self.assertEqual(counts["copied"], 1)
                self.assertTrue(
                    os.path.exists(
                        os.path.join(output_dir, "action", "01_起势", filename)
                    )
                )


if __name__ == "__main__":
    unittest.main()
