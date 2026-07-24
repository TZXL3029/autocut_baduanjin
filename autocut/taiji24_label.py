import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .routine_label import (
        CSV_FIELDS,
        ClipRecord,
        RoutineConfig,
        auto_label_directory as _auto_label_directory,
        build_json_manifest as _build_json_manifest,
        build_parser,
        default_csv_path,
        default_json_path,
        default_output_dir,
        label_folder_parts,
        label_records as _label_records,
        main as _main,
        parse_clip_filename,
        read_csv,
        run as _run,
        scan_clips as _scan_clips,
        summarize_rows,
        sync_labeled_folders,
        text_to_pinyin,
        write_csv,
        write_json_manifest as _write_json_manifest,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from routine_label import (  # type: ignore
        CSV_FIELDS,
        ClipRecord,
        RoutineConfig,
        auto_label_directory as _auto_label_directory,
        build_json_manifest as _build_json_manifest,
        build_parser,
        default_csv_path,
        default_json_path,
        default_output_dir,
        label_folder_parts,
        label_records as _label_records,
        main as _main,
        parse_clip_filename,
        read_csv,
        run as _run,
        scan_clips as _scan_clips,
        summarize_rows,
        sync_labeled_folders,
        text_to_pinyin,
        write_csv,
        write_json_manifest as _write_json_manifest,
    )


ACTION_LABELS = {
    1: "01_起势",
    2: "02_左右野马分鬃",
    3: "03_白鹤亮翅",
    4: "04_左右搂膝拗步",
    5: "05_手挥琵琶",
    6: "06_左右倒卷肱",
    7: "07_左揽雀尾",
    8: "08_右揽雀尾",
    9: "09_单鞭",
    10: "10_云手",
    11: "11_单鞭",
    12: "12_高探马",
    13: "13_右蹬脚",
    14: "14_双峰贯耳",
    15: "15_转身左蹬脚",
    16: "16_左下势独立",
    17: "17_右下势独立",
    18: "18_左右穿梭",
    19: "19_海底针",
    20: "20_闪通背",
    21: "21_转身搬拦捶",
    22: "22_如封似闭",
    23: "23_十字手",
    24: "24_收势",
}

CN_NUMBERS = {
    1: "一",
    2: "二",
    3: "三",
    4: "四",
    5: "五",
    6: "六",
    7: "七",
    8: "八",
    9: "九",
    10: "十",
    11: "十一",
    12: "十二",
    13: "十三",
    14: "十四",
    15: "十五",
    16: "十六",
    17: "十七",
    18: "十八",
    19: "十九",
    20: "二十",
    21: "二十一",
    22: "二十二",
    23: "二十三",
    24: "二十四",
}


def _numbered_terms(num: int) -> List[str]:
    cn = CN_NUMBERS[num]
    return [
        f"第{cn}式",
        f"第{num}式",
        f"第{cn}个动作",
        f"第{num}个动作",
        f"第{cn}动",
        f"第{num}动",
    ]


def _rules(
    num: int,
    name: str,
    medium: Sequence[str] = (),
    fuzzy: Sequence[str] = (),
    weak: Sequence[str] = (),
) -> Dict[str, Sequence[str]]:
    return {
        "strong": [*_numbered_terms(num), name],
        "medium": list(medium),
        "fuzzy": list(fuzzy),
        "weak": list(weak),
    }


ACTION_RULES = {
    1: _rules(
        1,
        "起势",
        medium=["太极起势", "开始动作", "开势", "起式"],
        fuzzy=["启势", "气势", "起式"],
        weak=["两脚开立", "开步", "两臂前举", "屈膝按掌", "按掌"],
    ),
    2: _rules(
        2,
        "左右野马分鬃",
        medium=["野马分鬃", "左野马", "右野马", "分鬃"],
        fuzzy=["野马分宗", "野马分棕", "野马分踪", "分宗", "分棕"],
        weak=["抱球", "弓步分手", "上步分手", "左分手", "右分手"],
    ),
    3: _rules(
        3,
        "白鹤亮翅",
        medium=["白鹤", "亮翅"],
        fuzzy=["白鹅亮翅", "百合亮翅", "白鹤亮志"],
        weak=["虚步", "右手上提", "左手下按"],
    ),
    4: _rules(
        4,
        "左右搂膝拗步",
        medium=["搂膝拗步", "左搂膝", "右搂膝", "搂膝"],
        fuzzy=["楼膝拗步", "搂膝奥步", "楼膝奥步"],
        weak=["搂膝推掌", "弓步推掌", "上步推掌"],
    ),
    5: _rules(
        5,
        "手挥琵琶",
        medium=["手挥琵琶", "挥琵琶", "琵琶"],
        fuzzy=["手挥琵把", "手回琵琶", "手挥匹帕"],
        weak=["跟步", "虚步合手", "两手合抱"],
    ),
    6: _rules(
        6,
        "左右倒卷肱",
        medium=["倒卷肱", "倒卷公", "倒撵猴"],
        fuzzy=["倒卷红", "倒卷弓", "倒卷功", "倒转肱"],
        weak=["退步", "卷肱", "撤步", "推掌"],
    ),
    7: _rules(
        7,
        "左揽雀尾",
        medium=["左揽雀尾", "左棚捋挤按", "左掤捋挤按"],
        fuzzy=["左懒雀尾", "左揽鹊尾", "左揽却尾"],
        weak=["左掤", "左捋", "左挤", "左按"],
    ),
    8: _rules(
        8,
        "右揽雀尾",
        medium=["右揽雀尾", "右棚捋挤按", "右掤捋挤按"],
        fuzzy=["右懒雀尾", "右揽鹊尾", "右揽却尾"],
        weak=["右掤", "右捋", "右挤", "右按"],
    ),
    9: _rules(
        9,
        "单鞭",
        medium=["第一遍单鞭", "第一个单鞭", "左单鞭"],
        fuzzy=["单边", "单编"],
        weak=["勾手", "侧弓步"],
    ),
    10: _rules(
        10,
        "云手",
        medium=["云手", "左右云手"],
        fuzzy=["运手", "云首"],
        weak=["横步", "并步", "两手云转", "云转"],
    ),
    11: _rules(
        11,
        "单鞭",
        medium=["第二遍单鞭", "第二个单鞭", "再做单鞭", "接单鞭"],
        fuzzy=["单边", "单编"],
        weak=["勾手", "侧弓步"],
    ),
    12: _rules(
        12,
        "高探马",
        medium=["高探马", "探马"],
        fuzzy=["高叹马", "高弹马"],
        weak=["跟步翻掌", "虚步推掌", "右手前推"],
    ),
    13: _rules(
        13,
        "右蹬脚",
        medium=["右蹬脚", "蹬脚"],
        fuzzy=["右登脚", "右灯脚", "右蹬腿"],
        weak=["分手蹬脚", "提膝", "蹬出"],
    ),
    14: _rules(
        14,
        "双峰贯耳",
        medium=["双峰贯耳", "双峰", "贯耳"],
        fuzzy=["双风贯耳", "双峰灌耳", "双拳贯耳"],
        weak=["双拳", "两拳", "弓步贯拳"],
    ),
    15: _rules(
        15,
        "转身左蹬脚",
        medium=["左蹬脚", "转身蹬脚", "转身左蹬"],
        fuzzy=["左登脚", "左灯脚", "转身左蹬腿"],
        weak=["转身", "左脚蹬出", "提膝蹬脚"],
    ),
    16: _rules(
        16,
        "左下势独立",
        medium=["左下势独立", "左下势", "左独立", "下势独立"],
        fuzzy=["左下式独立", "左下势杜立"],
        weak=["仆步", "左独立步", "挑掌"],
    ),
    17: _rules(
        17,
        "右下势独立",
        medium=["右下势独立", "右下势", "右独立", "下势独立"],
        fuzzy=["右下式独立", "右下势杜立"],
        weak=["仆步", "右独立步", "挑掌"],
    ),
    18: _rules(
        18,
        "左右穿梭",
        medium=["左右穿梭", "穿梭", "玉女穿梭"],
        fuzzy=["左右穿说", "左右穿缩", "玉女穿缩"],
        weak=["架推掌", "斜方推掌", "上步架掌"],
    ),
    19: _rules(
        19,
        "海底针",
        medium=["海底针"],
        fuzzy=["海底真", "海底珍"],
        weak=["插掌", "虚步插掌", "向下插"],
    ),
    20: _rules(
        20,
        "闪通背",
        medium=["闪通背", "闪通臂"],
        fuzzy=["闪通被", "闪同背"],
        weak=["弓步推掌", "上步撑掌", "架掌前推"],
    ),
    21: _rules(
        21,
        "转身搬拦捶",
        medium=["搬拦捶", "转身搬拦", "搬拦锤"],
        fuzzy=["搬兰捶", "搬拦垂", "搬拦锤"],
        weak=["搬拳", "拦掌", "打拳", "进步栽捶"],
    ),
    22: _rules(
        22,
        "如封似闭",
        medium=["如封似闭", "如封似", "封似闭"],
        fuzzy=["如风似闭", "如封四闭", "如风四闭"],
        weak=["后坐", "收掌", "按掌", "双手前按"],
    ),
    23: _rules(
        23,
        "十字手",
        medium=["十字手", "十字"],
        fuzzy=["十字首", "十字守"],
        weak=["两手交叉", "合抱", "开立步"],
    ),
    24: _rules(
        24,
        "收势",
        medium=["收式", "结束动作", "收尾"],
        fuzzy=["收拾", "手势"],
        weak=["还原", "并步", "两手下落", "自然站立"],
    ),
}

OPENING_RULES = {
    "strong": ["二十四式太极拳", "24式太极拳", "简化太极拳"],
    "medium": ["太极拳", "二十四式", "24式", "教学", "演示", "分解", "预备"],
    "fuzzy": ["太极", "太级", "二十式"],
    "weak": ["大家", "今天", "练习", "开始"],
}

CLOSING_IRRELEVANT_RULES = {
    "strong": ["谢谢观看", "感谢观看", "下次见", "再见"],
    "medium": ["关注", "点赞", "订阅", "评论区", "今天的视频", "今天的练习"],
    "fuzzy": ["欢迎大家", "希望大家", "我们下期"],
    "weak": ["谢谢", "视频", "练习"],
}

TAIJI24_CONFIG = RoutineConfig(
    name="taiji24",
    action_labels=ACTION_LABELS,
    action_rules=ACTION_RULES,
    intro_label=None,
    outro_label=None,
    intro_outro_rules=OPENING_RULES,
    closing_irrelevant_rules=CLOSING_IRRELEVANT_RULES,
    description="Generate reviewable CSV labels and folders for 24-form Taijiquan clips.",
)


def scan_clips(input_dir: str) -> List[ClipRecord]:
    return _scan_clips(
        input_dir,
        action_rules=TAIJI24_CONFIG.action_rules,
        intro_outro_rules=TAIJI24_CONFIG.intro_outro_rules,
    )


def label_records(records: Sequence[ClipRecord]) -> List[Dict[str, str]]:
    return _label_records(records, TAIJI24_CONFIG)


def auto_label_directory(input_dir: str) -> List[Dict[str, str]]:
    return _auto_label_directory(input_dir, TAIJI24_CONFIG)


def build_json_manifest(
    rows: Sequence[Dict[str, str]],
    input_dir: str,
    csv_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, object]:
    return _build_json_manifest(
        rows,
        input_dir,
        config=TAIJI24_CONFIG,
        csv_path=csv_path,
        output_dir=output_dir,
    )


def write_json_manifest(
    rows: Sequence[Dict[str, str]],
    json_path: str,
    input_dir: str,
    csv_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> None:
    _write_json_manifest(
        rows,
        json_path,
        input_dir,
        config=TAIJI24_CONFIG,
        csv_path=csv_path,
        output_dir=output_dir,
    )


def run(
    input_dir: str,
    csv_path: Optional[str] = None,
    json_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    copy_files: bool = True,
    write_json_file: bool = True,
    force: bool = False,
    move: bool = False,
    dry_run: bool = False,
    clean_output: bool = False,
) -> Tuple[List[Dict[str, str]], Counter]:
    return _run(
        input_dir,
        config=TAIJI24_CONFIG,
        csv_path=csv_path,
        json_path=json_path,
        output_dir=output_dir,
        copy_files=copy_files,
        write_json_file=write_json_file,
        force=force,
        move=move,
        dry_run=dry_run,
        clean_output=clean_output,
    )


def main() -> None:
    _main(TAIJI24_CONFIG)


if __name__ == "__main__":
    main()
