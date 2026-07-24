import argparse
import csv
import json
import logging
import os
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    import jieba

    jieba.setLogLevel(logging.WARNING)
except ImportError:  # pragma: no cover - optional dependency
    jieba = None

try:
    from pypinyin import lazy_pinyin
except ImportError:  # pragma: no cover - optional dependency
    lazy_pinyin = None


CSV_FIELDS = [
    "filename",
    "source_video",
    "segment_index",
    "text_hint",
    "big_label",
    "action_label",
    "confidence",
    "review",
    "notes",
]
JSON_SCHEMA_VERSION = 1

ACTION_LABELS = {
    1: "01_两手托天理三焦",
    2: "02_左右开弓似射雕",
    3: "03_调理脾胃须单举",
    4: "04_五劳七伤往后瞧",
    5: "05_摇头摆尾去心火",
    6: "06_两手攀足固肾腰",
    7: "07_攒拳怒目增气力",
    8: "08_背后七颠百病消",
}

INTRO_LABEL = "00_预备势"
OUTRO_LABEL = "09_收势"
OPENING_LABEL = "opening"
CLOSING_LABEL = "closing"

TERM_LEVEL_WEIGHTS = {
    "strong": 5,
    "medium": 3,
    "fuzzy": 2,
    "weak": 1,
}
ACTION_BOUNDARY_MIN_SCORE = TERM_LEVEL_WEIGHTS["medium"]
INTRO_OUTRO_MIN_SCORE = TERM_LEVEL_WEIGHTS["medium"]
PINYIN_MATCH_LEVELS = {"strong", "medium", "fuzzy"}
BOUNDARY_REVIEW_WINDOW = 2

IGNORE_TERMS = [
    "吸气",
    "呼气",
    "稀奇",
    "西齐",
    "喜起",
    "新奇",
    "呼起",
    "习起",
    "席气",
    "西奇",
    "c起",
    "city",
    "上",
    "下",
    "回收",
]

SEQUENCE_TRANSITION_TERMS = [
    "准备下",
    "准备下一个",
    "准备来到下",
    "再一次准备",
]

ACTION_RULES = {
    1: {
        "strong": ["第一个动作", "第一式", "第1个动作", "第1式", "两手托天", "托天理三焦", "理三焦"],
        "medium": [
            "第一个动",
            "托天",
            "三焦",
            "上托",
            "十指相扣向",
            "十指交叉",
        ],
        "fuzzy": [
            "两手拖天",
            "拖天",
            "托天顶",
            "拖天顶",
            "上脱",
            "上途",
            "上播",
            "上坡",
            "两掌交叉",
            "双手交叉",
            "吸气上锅",
            "上锅",
            "上屋",
        ],
        "weak": ["上举", "上撑", "掌心向上", "手落下到丹", "下落", "上呼"],
    },
    2: {
        "strong": ["第二个动作", "第二式", "第2个动作", "第2式", "左右开弓", "开弓似射雕", "似射雕"],
        "medium": [
            "第二个动",
            "开弓",
            "射雕",
            "四射雕",
            "拉弓",
        ],
        "fuzzy": [
            "开工",
            "开公",
            "拉工",
            "似射",
            "自射雕",
            "答话稀奇",
            "嗨公",
            "嗨过",
            "海公",
            "并不",
            "being",
            "bing",
            "开封",
            "答案稀奇",
            "下段西季开",
        ],
        "weak": ["搭腕", "搭万", "大万", "马步", "左开弓", "右开弓", "并步", "左拉弓"],
    },
    3: {
        "strong": ["第三个动作", "第三式", "第3个动作", "第3式", "调理脾胃", "脾胃须单举"],
        "medium": [
            "第三个动",
            "调理品味",
            "脾胃",
            "须单举",
            "虚单举",
            "品味虚单举",
            "单举",
            "上托下按",
            "辽宜品味",
            "遥离匹位",
            "小离匹位",
            "小李品味",
            "少举其职",
            "上句诗词",
            "左手上撑",
            "右手上撑",
        ],
        "fuzzy": [
            "调理皮胃",
            "皮胃",
            "品味",
            "虚单举示",
            "皮美",
            "银颅",
            "皮美银颅",
        ],
        "weak": ["一手上举", "一手下按", "左右交替", "上举下按", "上举左手", "下推左手"],
    },
    4: {
        "strong": ["第四个动作", "第四式", "第4个动作", "第4式", "五劳七伤", "五劳七伤往后瞧", "往后瞧"],
        "medium": [
            "第四个动",
            "五劳",
            "七伤",
            "后瞧",
            "后桥",
            "右桥",
            "缝桥",
            "向后看",
            "古老七上",
        ],
        "fuzzy": [
            "五劳七商",
            "五老七商",
            "古老",
            "七上",
            "向后乔",
            "往奉侨",
            "女生稀奇",
            "转正",
            "转正呼气",
            "转正呼吸",
            "好巧",
            "后脚",
            "木桥",
            "稀奇又厚巧",
        ],
        "weak": ["转头", "回头", "起身向左转", "起身向右转", "两臂外旋", "肩背", "起身吸气后"],
    },
    5: {
        "strong": ["第五个动作", "第五式", "第5个动作", "第5式", "摇头摆尾", "摇头摆尾去心火"],
        "medium": [
            "第五个动",
            "摇头",
            "摆尾",
            "心火",
            "尾闾",
        ],
        "fuzzy": [
            "白尾",
            "摆为",
            "心腿",
            "心谱",
            "呼气白尾",
            "吸气向后摇",
            "做青",
            "做清",
            "做玄",
            "作弦",
            "作询",
            "作选",
            "佐青",
            "索青",
            "左旋",
            "右转",
            "又青",
            "又清",
            "咬头",
            "有头",
            "有逃",
            "白纹",
            "摆稳",
        ],
        "weak": ["马步", "俯身", "身体旋转", "左右摆", "向左倾", "向右倾", "又亲", "又请", "又选", "右旋"],
    },
    6: {
        "strong": ["第六个动作", "第六式", "第6个动作", "第6式", "两手攀足", "两手攀足固肾腰", "攀足固肾腰"],
        "medium": [
            "第六个动",
            "攀足",
            "盘足",
            "双手盘足",
            "固肾腰",
            "顾肾腰",
            "肾腰",
            "西系上举",
        ],
        "fuzzy": [
            "双手攀足",
            "潘祖",
            "潘主",
            "潘子",
            "潘族",
            "攀祖",
            "潘足",
            "肾瑶",
            "固肾要",
            "顾圣娇",
            "反川",
            "百川",
            "抹育",
            "魔狱",
            "摩运",
            "魔韵",
            "魔芋",
            "魔浴",
            "摩玉",
            "国运",
            "国狱",
            "反川摩运",
            "反川魔韵",
            "散川",
            "返川",
            "反穿魔",
            "穿长",
            "下爱",
            "下二",
            "夏二",
            "上居",
            "上具",
            "51魔",
        ],
        "weak": ["俯身", "下按", "下案", "摸脚", "手滑过臀部", "臀部", "起身", "腰背", "下压"],
    },
    7: {
        "strong": ["第七个动作", "第七式", "第7个动作", "第7式", "攒拳怒目", "攒拳怒目增气力", "怒目增气力"],
        "medium": [
            "第七个动",
            "攒拳",
            "怒目",
            "增气力",
            "冲拳",
            "出拳",
            "握拳回收",
            "环环怒目",
        ],
        "fuzzy": [
            "传承怒目",
            "传全怒目",
            "传泉怒目",
            "全权怒目",
            "完全怒目",
            "传传怒",
            "全全怒",
            "团全怒目",
            "传传目目",
            "真气力",
            "生气力",
            "卓阿悟",
            "抓我",
            "抓我回收",
            "抓我回生",
            "传泉弩幕",
            "传传幕幕",
            "暴权稀器",
            "爆传",
            "报传",
            "随修",
        ],
        "weak": ["握拳", "双手握拳", "抓握", "刷物", "抓物", "收回", "目视", "马步", "回收"],
    },
    8: {
        "strong": ["第八个动作", "第八式", "第8个动作", "第8式", "最后一个动作", "最后一个动", "背后七颠", "背后七颠百病消", "七颠百病消"],
        "medium": [
            "第八个动",
            "七颠",
            "百病消",
            "背后",
            "背后七天",
            "最后一个",
        ],
        "fuzzy": [
            "背后七天摆并销",
            "七天",
            "七点",
            "摆并销",
            "编组",
            "别人",
            "天足",
            "天祖",
            "滇足",
            "提肿",
            "提中",
            "提种",
            "啤酒",
            "其中",
            "dn组",
            "呼起滇足",
            "呼起蝙蝠",
            "修士",
        ],
        "weak": ["提踵", "提起", "脚跟落地", "颠足", "点足", "上下颠", "放松"],
    },
}

INTRO_OUTRO_RULES = {
    "strong": ["预备势", "预备式", "起势", "起式", "收势", "收式"],
    "medium": [
        "准备动作",
        "首先是准备",
        "准备",
        "预备",
        "必备是",
        "示范",
        "左脚开步",
        "锁脚开步",
        "开步",
        "同宽",
        "意守丹田",
        "气成单",
        "两场何鱼",
        "两掌合于腹",
        "两掌合于父",
        "两场合鱼",
        "两场合余",
        "两长何余",
        "呼吸均匀",
        "呼吸君临",
        "呼吸君云",
        "气沉丹田",
        "收视",
    ],
    "fuzzy": [
        "与间同宽",
        "新神凝静",
        "锁脚",
        "挡抱父前",
        "忠正安疏",
        "心神隐境",
        "替太安祥",
        "替泰安翔周",
    ],
    "weak": ["屈膝", "凝静", "意守", "丹田", "放松", "站立", "呼吸自然"],
}

CLOSING_IRRELEVANT_RULES = {
    "strong": ["大家太棒了", "感谢观看", "谢谢观看", "下次见", "再见"],
    "medium": ["希望大家", "关注", "点赞", "订阅", "评论区", "今天的视频", "今天的练习"],
    "fuzzy": ["我也希望", "让我们变得", "好吧那我", "好吧,那我"],
    "weak": ["大家", "希望", "视频", "练习"],
}

FALLBACK_PINYIN = {
    "两": "liang",
    "手": "shou",
    "托": "tuo",
    "拖": "tuo",
    "天": "tian",
    "理": "li",
    "三": "san",
    "焦": "jiao",
    "左": "zuo",
    "右": "you",
    "开": "kai",
    "弓": "gong",
    "工": "gong",
    "公": "gong",
    "似": "si",
    "射": "she",
    "雕": "diao",
    "调": "tiao",
    "脾": "pi",
    "胃": "wei",
    "须": "xu",
    "单": "dan",
    "举": "ju",
    "辽": "liao",
    "宜": "yi",
    "品": "pin",
    "味": "wei",
    "五": "wu",
    "劳": "lao",
    "老": "lao",
    "七": "qi",
    "伤": "shang",
    "古": "gu",
    "往": "wang",
    "后": "hou",
    "瞧": "qiao",
    "桥": "qiao",
    "摇": "yao",
    "头": "tou",
    "摆": "bai",
    "尾": "wei",
    "白": "bai",
    "去": "qu",
    "心": "xin",
    "火": "huo",
    "攀": "pan",
    "盘": "pan",
    "潘": "pan",
    "足": "zu",
    "祖": "zu",
    "固": "gu",
    "肾": "shen",
    "腰": "yao",
    "瑶": "yao",
    "要": "yao",
    "攒": "zan",
    "拳": "quan",
    "怒": "nu",
    "目": "mu",
    "增": "zeng",
    "气": "qi",
    "力": "li",
    "环": "huan",
    "传": "chuan",
    "承": "cheng",
    "全": "quan",
    "完": "wan",
    "团": "tuan",
    "背": "bei",
    "颠": "dian",
    "点": "dian",
    "病": "bing",
    "消": "xiao",
    "销": "xiao",
    "预": "yu",
    "备": "bei",
    "势": "shi",
    "式": "shi",
    "第": "di",
    "一": "yi",
    "二": "er",
    "四": "si",
    "六": "liu",
    "八": "ba",
    "个": "ge",
    "动": "dong",
    "作": "zuo",
    "最": "zui",
    "后": "hou",
    "收": "shou",
    "示": "shi",
    "范": "fan",
    "准": "zhun",
    "脚": "jiao",
    "步": "bu",
    "与": "yu",
    "间": "jian",
    "同": "tong",
    "宽": "kuan",
    "屈": "qu",
    "膝": "xi",
    "凝": "ning",
    "静": "jing",
    "意": "yi",
    "守": "shou",
    "丹": "dan",
    "田": "tian",
    "顾": "gu",
    "圣": "sheng",
    "娇": "jiao",
    "商": "shang",
    "奉": "feng",
    "侨": "qiao",
    "乔": "qiao",
    "虚": "xu",
    "皮": "pi",
    "腿": "tui",
    "谱": "pu",
    "拉": "la",
    "搭": "da",
    "万": "wan",
    "抬": "tai",
    "起": "qi",
    "踵": "zhong",
    "沉": "chen",
    "视": "shi",
    "合": "he",
    "余": "yu",
    "复": "fu",
    "均": "jun",
    "临": "lin",
    "翔": "xiang",
    "周": "zhou",
    "臀": "tun",
    "部": "bu",
    "握": "wo",
    "抓": "zhua",
    "刷": "shua",
    "物": "wu",
    "出": "chu",
}

FALLBACK_PINYIN.update(
    {
        "太": "tai",
        "极": "ji",
        "拳": "quan",
        "野": "ye",
        "马": "ma",
        "分": "fen",
        "鬃": "zong",
        "白": "bai",
        "鹤": "he",
        "亮": "liang",
        "翅": "chi",
        "搂": "lou",
        "拗": "ao",
        "琵": "pi",
        "琶": "pa",
        "倒": "dao",
        "卷": "juan",
        "肱": "gong",
        "揽": "lan",
        "雀": "que",
        "尾": "wei",
        "鞭": "bian",
        "云": "yun",
        "探": "tan",
        "蹬": "deng",
        "峰": "feng",
        "贯": "guan",
        "耳": "er",
        "转": "zhuan",
        "身": "shen",
        "下": "xia",
        "势": "shi",
        "独": "du",
        "立": "li",
        "穿": "chuan",
        "梭": "suo",
        "海": "hai",
        "底": "di",
        "针": "zhen",
        "闪": "shan",
        "通": "tong",
        "搬": "ban",
        "拦": "lan",
        "捶": "chui",
        "如": "ru",
        "封": "feng",
        "闭": "bi",
        "十": "shi",
        "字": "zi",
    }
)

CLIP_RE = re.compile(r"^(?P<source>.+)_(?P<index>\d+)_(?P<hint>.*)\.mp4$", re.I)
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")


@dataclass
class ClipRecord:
    filename: str
    source_video: str
    segment_index: int
    text_hint: str
    direct_action: Optional[int] = None
    direct_action_candidates: Tuple[int, ...] = ()
    direct_action_score: int = 0
    direct_action_terms: Tuple[str, ...] = ()
    direct_intro_score: int = 0
    direct_intro_terms: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RoutineConfig:
    name: str
    action_labels: Dict[int, str]
    action_rules: Dict[int, Dict[str, Sequence[str]]]
    intro_label: Optional[str] = INTRO_LABEL
    outro_label: Optional[str] = OUTRO_LABEL
    opening_label: str = OPENING_LABEL
    closing_label: str = CLOSING_LABEL
    intro_outro_rules: Dict[str, Sequence[str]] = None
    closing_irrelevant_rules: Dict[str, Sequence[str]] = None
    description: str = "Generate reviewable CSV labels and folders for routine clips."

    def __post_init__(self) -> None:
        if not self.action_labels:
            raise ValueError("action_labels must not be empty")
        if set(self.action_labels) != set(self.action_rules):
            raise ValueError("action_labels and action_rules must use the same action numbers")
        if self.intro_outro_rules is None:
            object.__setattr__(self, "intro_outro_rules", INTRO_OUTRO_RULES)
        if self.closing_irrelevant_rules is None:
            object.__setattr__(
                self, "closing_irrelevant_rules", CLOSING_IRRELEVANT_RULES
            )


DEFAULT_CONFIG = RoutineConfig(
    name="baduanjin",
    action_labels=ACTION_LABELS,
    action_rules=ACTION_RULES,
    description="Generate reviewable CSV labels and folders for Baduanjin clips.",
)


@dataclass(frozen=True)
class TermMatch:
    term: str
    level: str
    method: str
    weight: int

    def note(self) -> str:
        return f"{self.level}:{self.term}:{self.method}"


def normalize_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def normalize_source_video_name(name: str) -> str:
    return re.sub(r"\s+", "_", str(name or "").strip())


def _has_chinese(text: str) -> bool:
    return bool(CHINESE_RE.search(text))


def _char_to_pinyin(char: str) -> str:
    if not _has_chinese(char):
        return char
    if lazy_pinyin:
        pinyin = lazy_pinyin(char, errors="ignore")
        if pinyin:
            return pinyin[0]
    return FALLBACK_PINYIN.get(char, char)


@lru_cache(maxsize=4096)
def text_to_pinyin(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    return "".join(_char_to_pinyin(char) for char in normalized)


@lru_cache(maxsize=4096)
def _segment_text(text: str) -> Tuple[str, ...]:
    normalized = normalize_text(text)
    if not normalized:
        return ()
    if jieba:
        return tuple(token for token in jieba.lcut(normalized) if token)
    return tuple(re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized))


@lru_cache(maxsize=4096)
def text_to_pinyin_tokens(text: str) -> Tuple[str, ...]:
    return tuple(
        pinyin for pinyin in (text_to_pinyin(token) for token in _segment_text(text)) if pinyin
    )


def _contains_by_text(text: str, term: str) -> bool:
    return normalize_text(term) in normalize_text(text)


def _contains_by_pinyin(text: str, term: str) -> bool:
    if not _has_chinese(term):
        return False
    term_pinyin = text_to_pinyin(term)
    if len(term_pinyin) < 4:
        return False
    text_tokens = text_to_pinyin_tokens(text)
    term_tokens = text_to_pinyin_tokens(term)
    if text_tokens and term_tokens:
        max_window = min(len(text_tokens), len(term_tokens) + 1)
        for window_size in range(1, max_window + 1):
            for start in range(0, len(text_tokens) - window_size + 1):
                window_pinyin = "".join(text_tokens[start : start + window_size])
                if term_pinyin == window_pinyin or term_pinyin in window_pinyin:
                    return True
    return term_pinyin in text_to_pinyin(text)


def _is_only_ignored_text(text: str) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    changed = normalized
    for term in IGNORE_TERMS:
        changed = changed.replace(normalize_text(term), "")
    return changed == ""


def _score_rule_terms(
    text: str, rules: Dict[str, Sequence[str]]
) -> Tuple[int, Tuple[str, ...]]:
    score = 0
    matches = []
    if _is_only_ignored_text(text):
        return 0, ()

    for level, terms in rules.items():
        weight = TERM_LEVEL_WEIGHTS[level]
        level_matches = []
        for term in terms:
            text_matched = _contains_by_text(text, term)
            pinyin_matched = (
                not text_matched
                and level in PINYIN_MATCH_LEVELS
                and _contains_by_pinyin(text, term)
            )
            if not text_matched and not pinyin_matched:
                continue
            method = "text" if text_matched else "pinyin"
            level_matches.append(TermMatch(term, level, method, weight).note())
        if level_matches:
            score += weight
            matches.extend(level_matches)
    return score, tuple(matches)


def parse_clip_filename(filename: str) -> ClipRecord:
    match = CLIP_RE.match(filename)
    if not match:
        base, _ = os.path.splitext(filename)
        return ClipRecord(filename, normalize_source_video_name(base), -1, "")

    return ClipRecord(
        filename=filename,
        source_video=normalize_source_video_name(match.group("source")),
        segment_index=int(match.group("index")),
        text_hint=match.group("hint"),
    )


def _score_actions(
    text: str,
    action_rules: Dict[int, Dict[str, Sequence[str]]] = ACTION_RULES,
) -> List[Tuple[int, int, Tuple[str, ...]]]:
    scores = []
    for action_num, rules in action_rules.items():
        score, matched = _score_rule_terms(text, rules)
        if score > 0:
            scores.append((score, action_num, matched))
    return sorted(scores, reverse=True)


def _detect_action(
    text: str, action_rules: Dict[int, Dict[str, Sequence[str]]] = ACTION_RULES
) -> Tuple[Optional[int], int, Tuple[str, ...], bool, Tuple[int, ...]]:
    scores = _score_actions(text, action_rules)

    if not scores:
        return None, 0, (), False, ()

    top_score, top_action, top_terms = scores[0]
    ambiguous = len(scores) > 1 and scores[1][0] >= top_score - 1
    candidates = tuple(action_num for score, action_num, _ in scores if score >= top_score - 1)
    return top_action, top_score, top_terms, ambiguous, candidates


def scan_clips(
    input_dir: str,
    action_rules: Dict[int, Dict[str, Sequence[str]]] = ACTION_RULES,
    intro_outro_rules: Dict[str, Sequence[str]] = INTRO_OUTRO_RULES,
) -> List[ClipRecord]:
    records = []
    for entry in os.scandir(input_dir):
        if not entry.is_file() or not entry.name.lower().endswith(".mp4"):
            continue
        record = parse_clip_filename(entry.name)
        action, score, terms, ambiguous, candidates = _detect_action(
            record.text_hint, action_rules
        )
        intro_score, intro_terms = _score_rule_terms(record.text_hint, intro_outro_rules)
        record.direct_action_candidates = candidates
        record.direct_action_score = score
        record.direct_action_terms = terms
        if not ambiguous:
            record.direct_action = action
        record.direct_intro_score = intro_score
        record.direct_intro_terms = intro_terms
        records.append(record)

    return sorted(records, key=lambda x: (x.source_video, x.segment_index, x.filename))


def _action_boundaries(
    records: Sequence[ClipRecord],
    action_labels: Dict[int, str] = ACTION_LABELS,
) -> List[Tuple[int, int]]:
    boundaries = []
    last_index = -1
    for action_num in sorted(action_labels):
        anchor_index = next(
            (
                record.segment_index
                for record in records
                if record.segment_index > last_index
                and record.direct_action_score >= ACTION_BOUNDARY_MIN_SCORE
                and (
                    record.direct_action == action_num
                    or action_num in record.direct_action_candidates
                )
            ),
            None,
        )
        if anchor_index is not None:
            boundaries.append((anchor_index, action_num))
            last_index = anchor_index
    repaired = _repair_missing_action_boundaries(records, boundaries, action_labels)
    return _prefer_transition_cue_boundaries(records, repaired)


def _has_sequence_transition_cue(text: str) -> bool:
    return any(_contains_by_text(text, term) for term in SEQUENCE_TRANSITION_TERMS)


def _repair_missing_action_boundaries(
    records: Sequence[ClipRecord],
    boundaries: Sequence[Tuple[int, int]],
    action_labels: Dict[int, str] = ACTION_LABELS,
) -> List[Tuple[int, int]]:
    if len(boundaries) < 2:
        return list(boundaries)

    repaired: List[Tuple[int, int]] = []
    sorted_boundaries = sorted(boundaries)
    max_action_num = max(action_labels)

    for pos, (current_index, current_action) in enumerate(sorted_boundaries):
        repaired.append((current_index, current_action))
        if pos + 1 >= len(sorted_boundaries):
            continue

        next_index, next_action = sorted_boundaries[pos + 1]
        if next_action <= current_action + 1:
            continue

        last_inserted_index = current_index
        for missing_action in range(current_action + 1, next_action):
            if missing_action not in action_labels:
                continue
            anchor_index = _find_gap_anchor_for_missing_action(
                records,
                missing_action,
                last_inserted_index,
                next_index,
                allow_transition_cue=missing_action < max_action_num,
            )
            if anchor_index is None:
                continue
            repaired.append((anchor_index, missing_action))
            last_inserted_index = anchor_index

    return sorted(repaired)


def _prefer_transition_cue_boundaries(
    records: Sequence[ClipRecord],
    boundaries: Sequence[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    if len(boundaries) < 2:
        return list(boundaries)

    adjusted = [boundaries[0]]
    sorted_boundaries = sorted(boundaries)
    last_action_num = max(action_num for _, action_num in sorted_boundaries)
    for current_index, current_action in sorted_boundaries[1:]:
        previous_index = adjusted[-1][0]
        transition_index = None
        if current_action < last_action_num:
            transition_index = next(
                (
                    record.segment_index
                    for record in records
                    if previous_index < record.segment_index < current_index
                    and _has_sequence_transition_cue(record.text_hint)
                ),
                None,
            )
        adjusted.append(
            (transition_index if transition_index is not None else current_index, current_action)
        )
    return adjusted


def _find_gap_anchor_for_missing_action(
    records: Sequence[ClipRecord],
    action_num: int,
    start_index: int,
    end_index: int,
    allow_transition_cue: bool,
) -> Optional[int]:
    gap_records = [
        record
        for record in records
        if start_index < record.segment_index < end_index
    ]
    direct_anchor = next(
        (
            record.segment_index
            for record in gap_records
            if record.direct_action_score >= ACTION_BOUNDARY_MIN_SCORE
            and (
                record.direct_action == action_num
                or action_num in record.direct_action_candidates
            )
        ),
        None,
    )
    if direct_anchor is not None:
        return direct_anchor

    if not allow_transition_cue:
        return None
    return next(
        (
            record.segment_index
            for record in gap_records
            if _has_sequence_transition_cue(record.text_hint)
        ),
        None,
    )


def _infer_action_from_boundaries(
    segment_index: int, boundaries: Sequence[Tuple[int, int]]
) -> Optional[int]:
    inferred = None
    for boundary_index, action_num in boundaries:
        if segment_index >= boundary_index:
            inferred = action_num
        else:
            break
    return inferred


def _next_boundary_index(
    action_num: int, boundaries: Sequence[Tuple[int, int]]
) -> Optional[int]:
    for pos, (_, current_action) in enumerate(boundaries):
        if current_action == action_num and pos + 1 < len(boundaries):
            return boundaries[pos + 1][0]
    return None


def _first_intro_index_before_action(
    records: Sequence[ClipRecord], first_action_index: Optional[int]
) -> Optional[int]:
    if first_action_index is None:
        return None
    intro_indexes = [
        record.segment_index
        for record in records
        if record.segment_index < first_action_index
        and record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE
    ]
    return min(intro_indexes) if intro_indexes else None


def _first_outro_index_after_action(
    records: Sequence[ClipRecord], action8_index: Optional[int]
) -> Optional[int]:
    if action8_index is None:
        return None
    outro_indexes = [
        record.segment_index
        for record in records
        if record.segment_index > action8_index
        and record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE
    ]
    return min(outro_indexes) if outro_indexes else None


def _first_closing_index_after_outro(
    records: Sequence[ClipRecord],
    outro_start: Optional[int],
    closing_irrelevant_rules: Dict[str, Sequence[str]] = CLOSING_IRRELEVANT_RULES,
) -> Optional[int]:
    if outro_start is None:
        return None
    closing_indexes = [
        record.segment_index
        for record in records
        if record.segment_index > outro_start
        and _score_rule_terms(record.text_hint, closing_irrelevant_rules)[0]
        >= INTRO_OUTRO_MIN_SCORE
    ]
    return min(closing_indexes) if closing_indexes else None


def _row(
    record: ClipRecord,
    big_label: str,
    action_label: str,
    confidence: str,
    review: str,
    notes: Iterable[str],
) -> Dict[str, str]:
    return {
        "filename": record.filename,
        "source_video": record.source_video,
        "segment_index": "" if record.segment_index < 0 else str(record.segment_index),
        "text_hint": record.text_hint,
        "big_label": big_label,
        "action_label": action_label,
        "confidence": confidence,
        "review": review,
        "notes": "; ".join(x for x in notes if x),
    }


def label_records(
    records: Sequence[ClipRecord],
    config: RoutineConfig = DEFAULT_CONFIG,
) -> List[Dict[str, str]]:
    rows = []
    groups = defaultdict(list)
    for record in records:
        groups[record.source_video].append(record)

    for source_video in sorted(groups):
        source_records = sorted(groups[source_video], key=lambda x: x.segment_index)
        boundaries = _action_boundaries(source_records, config.action_labels)
        first_action_index = boundaries[0][0] if boundaries else None
        last_action_num = max(config.action_labels)
        last_action_index = next(
            (idx for idx, num in boundaries if num == last_action_num), None
        )
        intro_start = (
            _first_intro_index_before_action(source_records, first_action_index)
            if config.intro_label
            else None
        )
        outro_start = (
            _first_outro_index_after_action(source_records, last_action_index)
            if config.outro_label
            else None
        )
        closing_search_start = (
            outro_start if outro_start is not None else last_action_index
        )
        closing_irrelevant_start = _first_closing_index_after_outro(
            source_records,
            closing_search_start,
            config.closing_irrelevant_rules,
        )

        for record in source_records:
            notes = []
            if record.direct_action_terms:
                notes.append("matched_action_terms=" + "|".join(record.direct_action_terms))
            if record.direct_intro_terms:
                notes.append("matched_intro_terms=" + "|".join(record.direct_intro_terms))

            if record.segment_index < 0:
                rows.append(
                    _row(record, "unknown", "unknown", "low", "yes", ["filename_not_parsed"])
                )
                continue

            if first_action_index is not None and record.segment_index < first_action_index:
                if intro_start is not None and record.segment_index >= intro_start:
                    rows.append(
                        _row(
                            record,
                            "intro_outro",
                            config.intro_label,
                            "high" if record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE else "medium",
                            "no" if record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE else "yes",
                            notes + ["inside_intro_interval"],
                        )
                    )
                else:
                    rows.append(
                        _row(
                            record,
                            "irrelevant",
                            config.opening_label,
                            "medium",
                            "yes",
                            notes + ["before_first_action"],
                        )
                )
                continue

            if (
                closing_irrelevant_start is not None
                and record.segment_index >= closing_irrelevant_start
            ):
                closing_score, closing_terms = _score_rule_terms(
                    record.text_hint, config.closing_irrelevant_rules
                )
                closing_notes = notes + ["after_last_action"]
                if closing_terms:
                    closing_notes.append("matched_closing_terms=" + "|".join(closing_terms))
                rows.append(
                    _row(
                        record,
                        "irrelevant",
                        config.closing_label,
                        "high" if closing_score >= INTRO_OUTRO_MIN_SCORE else "medium",
                        "no" if closing_score >= INTRO_OUTRO_MIN_SCORE else "yes",
                        closing_notes,
                    )
                )
                continue

            if outro_start is not None and record.segment_index >= outro_start:
                rows.append(
                    _row(
                        record,
                        "intro_outro",
                        config.outro_label,
                        "high" if record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE else "medium",
                        "no" if record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE else "yes",
                        notes + ["inside_outro_interval"],
                    )
                )
                continue

            inferred_action = _infer_action_from_boundaries(record.segment_index, boundaries)
            if inferred_action is None:
                if record.direct_intro_score >= 2 and config.intro_label:
                    rows.append(
                        _row(
                            record,
                            "intro_outro",
                            config.intro_label,
                            "medium",
                            "yes",
                            notes,
                        )
                    )
                elif record.direct_intro_score >= 2:
                    rows.append(
                        _row(
                            record,
                            "irrelevant",
                            config.opening_label,
                            "medium",
                            "yes",
                            notes,
                        )
                    )
                else:
                    rows.append(_row(record, "unknown", "unknown", "low", "yes", notes))
                continue

            if _has_sequence_transition_cue(record.text_hint):
                rows.append(
                    _row(
                        record,
                        "transition",
                        "setup_transition",
                        "medium",
                        "yes",
                        notes
                        + [f"sequence_action={config.action_labels[inferred_action]}"],
                    )
                )
                continue

            if (
                inferred_action == min(config.action_labels)
                and record.direct_intro_score >= INTRO_OUTRO_MIN_SCORE
                and not record.direct_action
                and config.intro_label
            ):
                rows.append(
                    _row(
                        record,
                        "intro_outro",
                        config.intro_label,
                        "medium",
                        "yes",
                        notes + ["intro_cue_inside_first_action_interval"],
                    )
                )
                continue

            if (
                record.direct_action
                and record.direct_action != inferred_action
                and record.direct_action_score >= ACTION_BOUNDARY_MIN_SCORE
            ):
                rows.append(
                    _row(
                        record,
                        "transition",
                        "multi_action",
                        "low",
                        "yes",
                        notes
                        + [f"sequence_action={config.action_labels[inferred_action]}"],
                    )
                )
                continue

            next_boundary = _next_boundary_index(inferred_action, boundaries)
            near_next_boundary = (
                next_boundary is not None
                and 0 < next_boundary - record.segment_index <= BOUNDARY_REVIEW_WINDOW
            )
            if record.direct_action == inferred_action and record.direct_action_score >= 5:
                confidence = "high"
                review = "no"
            elif record.direct_action == inferred_action and record.direct_action_score >= 3:
                confidence = "medium"
                review = "no"
            else:
                confidence = "medium"
                review = "yes"
                notes.append("sequence_inferred")

            if near_next_boundary:
                review = "yes"
                notes.append("near_next_action_boundary")

            rows.append(
                _row(
                    record,
                    "action",
                    config.action_labels[inferred_action],
                    confidence,
                    review,
                    notes,
                )
            )

    return rows


def default_csv_path(input_dir: str) -> str:
    input_dir = os.path.normpath(input_dir)
    parent = os.path.dirname(input_dir)
    name = os.path.basename(input_dir)
    return os.path.join(parent, f"{name}_labels.csv")


def default_json_path(input_dir: str) -> str:
    input_dir = os.path.normpath(input_dir)
    parent = os.path.dirname(input_dir)
    name = os.path.basename(input_dir)
    return os.path.join(parent, f"{name}_labels.json")


def default_output_dir(input_dir: str) -> str:
    input_dir = os.path.normpath(input_dir)
    parent = os.path.dirname(input_dir)
    name = os.path.basename(input_dir)
    return os.path.join(parent, f"{name}_labeled")


def write_csv(rows: Sequence[Dict[str, str]], csv_path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in CSV_FIELDS})


def read_csv(csv_path: str) -> List[Dict[str, str]]:
    with open(csv_path, encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        missing = [field for field in CSV_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing CSV columns: {', '.join(missing)}")
        return [{field: row.get(field, "") for field in CSV_FIELDS} for row in reader]


def _manifest_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    abs_path = os.path.abspath(path)
    try:
        path = os.path.relpath(abs_path, os.getcwd())
    except ValueError:
        path = abs_path
    return os.path.normpath(path).replace(os.sep, "/")


def _parse_segment_index(value: str) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_review_required(value: str) -> bool:
    return str(value).strip().lower() in {"yes", "true", "1"}


def _parse_notes(value: str) -> List[str]:
    return [note.strip() for note in str(value or "").split(";") if note.strip()]


def _action_label_id(row: Dict[str, str], config: RoutineConfig) -> Optional[int]:
    if row.get("big_label") != "action":
        return None
    label_to_id = {label: label_id for label_id, label in config.action_labels.items()}
    return label_to_id.get(row.get("action_label", ""))


def build_json_manifest(
    rows: Sequence[Dict[str, str]],
    input_dir: str,
    config: RoutineConfig = DEFAULT_CONFIG,
    csv_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, object]:
    samples = []
    review_required_count = 0
    action_segment_count = 0

    for row in rows:
        filename = row.get("filename", "")
        source_video = normalize_source_video_name(row.get("source_video", ""))
        segment_index = _parse_segment_index(row.get("segment_index", ""))
        review_required = _parse_review_required(row.get("review", ""))
        label_id = _action_label_id(row, config)
        action_label = row.get("action_label", "")
        if review_required:
            review_required_count += 1
        if label_id is not None:
            action_segment_count += 1

        sample_id = (
            f"{source_video}:{segment_index}"
            if segment_index is not None
            else filename
        )
        samples.append(
            {
                "id": sample_id,
                "video_path": _manifest_path(os.path.join(input_dir, filename)),
                "filename": filename,
                "source_video": source_video,
                "segment_index": segment_index,
                "text_hint": row.get("text_hint", ""),
                "label_id": label_id,
                "label_name": action_label if label_id is not None else None,
                "label": {
                    "big_label": row.get("big_label", ""),
                    "action_label": action_label,
                },
                "confidence": row.get("confidence", ""),
                "review_required": review_required,
                "split": "unassigned",
                "training_eligible": label_id is not None,
                "notes": _parse_notes(row.get("notes", "")),
            }
        )

    label_counts = [
        {
            "big_label": big_label,
            "action_label": action_label,
            "count": count,
        }
        for (big_label, action_label), count in sorted(summarize_rows(rows).items())
    ]

    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "task_type": "video_classification",
        "task": {
            "routine": config.name,
            "input_dir": _manifest_path(input_dir),
            "csv_path": _manifest_path(csv_path),
            "output_dir": _manifest_path(output_dir),
        },
        "label_taxonomy": {
            "big_labels": ["action", "intro_outro", "irrelevant", "transition", "unknown"],
            "actions": [
                {
                    "id": label_id,
                    "name": label,
                    "display_name": label.split("_", 1)[1] if "_" in label else label,
                }
                for label_id, label in sorted(config.action_labels.items())
            ],
            "non_action_labels": [
                label
                for label in [
                    config.intro_label,
                    config.outro_label,
                    config.opening_label,
                    config.closing_label,
                    "setup_transition",
                    "unknown",
                ]
                if label
            ],
        },
        "samples": samples,
        "summary": {
            "total_segments": len(samples),
            "action_segments": action_segment_count,
            "review_required": review_required_count,
            "label_counts": label_counts,
        },
    }


def write_json_manifest(
    rows: Sequence[Dict[str, str]],
    json_path: str,
    input_dir: str,
    config: RoutineConfig = DEFAULT_CONFIG,
    csv_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    manifest = build_json_manifest(
        rows,
        input_dir,
        config=config,
        csv_path=csv_path,
        output_dir=output_dir,
    )
    with open(json_path, "w", encoding="utf-8") as json_file:
        json.dump(manifest, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")


def _safe_folder_name(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return cleaned or "unknown"


def label_folder_parts(row: Dict[str, str]) -> Tuple[str, ...]:
    big_label = row.get("big_label") or "unknown"
    action_label = row.get("action_label") or "unknown"
    if big_label == "action":
        return ("action", _safe_folder_name(action_label))
    if big_label == "intro_outro":
        return ("intro_outro", _safe_folder_name(action_label))
    if big_label == "irrelevant":
        return ("irrelevant", _safe_folder_name(action_label))
    return (_safe_folder_name(big_label),)


def sync_labeled_folders(
    rows: Sequence[Dict[str, str]],
    input_dir: str,
    output_dir: str,
    force: bool = False,
    move: bool = False,
) -> Counter:
    counts = Counter()
    os.makedirs(output_dir, exist_ok=True)
    for row in rows:
        filename = row.get("filename", "")
        source_path = os.path.join(input_dir, filename)
        if not os.path.isfile(source_path):
            counts["missing"] += 1
            logging.warning("Missing source clip: %s", source_path)
            continue

        dest_dir = os.path.join(output_dir, *label_folder_parts(row))
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, filename)
        if os.path.exists(dest_path) and not force:
            counts["skipped_existing"] += 1
            continue

        if move:
            shutil.move(source_path, dest_path)
            counts["moved"] += 1
        else:
            shutil.copy2(source_path, dest_path)
            counts["copied"] += 1
    return counts


def summarize_rows(rows: Sequence[Dict[str, str]]) -> Counter:
    return Counter((row["big_label"], row["action_label"]) for row in rows)


def auto_label_directory(
    input_dir: str,
    config: RoutineConfig = DEFAULT_CONFIG,
) -> List[Dict[str, str]]:
    records = scan_clips(
        input_dir,
        action_rules=config.action_rules,
        intro_outro_rules=config.intro_outro_rules,
    )
    return label_records(records, config)


def run(
    input_dir: str,
    config: RoutineConfig = DEFAULT_CONFIG,
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
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    csv_path = csv_path or default_csv_path(input_dir)
    json_path = json_path or default_json_path(input_dir)
    output_dir = output_dir or default_output_dir(input_dir)

    if os.path.exists(csv_path) and not force:
        logging.info("Using existing CSV labels: %s", csv_path)
        rows = read_csv(csv_path)
    else:
        rows = auto_label_directory(input_dir, config)
        if dry_run:
            logging.info("Dry run: would write CSV to %s", csv_path)
        else:
            write_csv(rows, csv_path)
            logging.info("Wrote CSV labels: %s", csv_path)

    if write_json_file:
        if dry_run:
            logging.info("Dry run: would write JSON manifest to %s", json_path)
        else:
            write_json_manifest(
                rows,
                json_path,
                input_dir,
                config=config,
                csv_path=csv_path,
                output_dir=output_dir,
            )
            logging.info("Wrote JSON manifest: %s", json_path)

    sync_counts = Counter()
    if copy_files or move:
        if dry_run:
            logging.info("Dry run: would sync labeled folders to %s", output_dir)
        else:
            if clean_output and os.path.exists(output_dir):
                shutil.rmtree(output_dir)
                logging.info("Cleaned output directory: %s", output_dir)
            sync_counts = sync_labeled_folders(
                rows, input_dir, output_dir, force=force, move=move
            )
            logging.info("Synced labeled folders: %s", output_dir)
    return rows, sync_counts


def build_parser(config: RoutineConfig = DEFAULT_CONFIG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=config.description
    )
    parser.add_argument("input_dir", help="Directory containing cut MP4 clips.")
    parser.add_argument("--csv", dest="csv_path", default=None, help="Output/input CSV path.")
    parser.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Output JSON dataset manifest path.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        default=None,
        help="Directory for copied clips grouped by labels.",
    )
    parser.add_argument(
        "--copy",
        dest="copy_files",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Copy clips into labeled folders after writing/reading CSV.",
    )
    parser.add_argument(
        "--write-json",
        dest="write_json_file",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Write a JSON dataset manifest next to the CSV.",
    )
    parser.add_argument(
        "--move",
        action="store_true",
        help="Move clips instead of copying them. Copying is the default.",
    )
    parser.add_argument(
        "--force",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Regenerate CSV and overwrite existing copied files.",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Show what would happen without writing CSV or copying clips.",
    )
    parser.add_argument(
        "--clean-output",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Delete the labeled output directory before copying clips.",
    )
    return parser


def main(config: RoutineConfig = DEFAULT_CONFIG) -> None:
    logging.basicConfig(
        format=f"[{config.name}_label:%(filename)s:L%(lineno)d] %(levelname)-6s %(message)s",
        level=logging.INFO,
    )
    args = build_parser(config).parse_args()
    rows, sync_counts = run(
        args.input_dir,
        config=config,
        csv_path=args.csv_path,
        json_path=args.json_path,
        output_dir=args.output_dir,
        copy_files=args.copy_files,
        write_json_file=args.write_json_file,
        force=args.force,
        move=args.move,
        dry_run=args.dry_run,
        clean_output=args.clean_output,
    )

    logging.info("Label summary:")
    for (big_label, action_label), count in sorted(summarize_rows(rows).items()):
        logging.info("  %s / %s: %d", big_label, action_label, count)
    if sync_counts:
        logging.info("Folder sync summary: %s", dict(sync_counts))


if __name__ == "__main__":
    main()
