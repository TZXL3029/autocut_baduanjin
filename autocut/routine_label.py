import argparse
import csv
import json
import logging
import os
import re
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from .pinyin_utils import (
        contains_by_pinyin as _contains_by_pinyin,
        contains_by_text as _contains_by_text,
        normalize_text,
        text_to_pinyin,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    from pinyin_utils import (  # type: ignore
        contains_by_pinyin as _contains_by_pinyin,
        contains_by_text as _contains_by_text,
        normalize_text,
        text_to_pinyin,
    )


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
RULE_LEVELS = tuple(TERM_LEVEL_WEIGHTS)

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

ACTION_LABELS: Dict[int, str] = {}
ACTION_RULES: Dict[int, Dict[str, Sequence[str]]] = {}
INTRO_OUTRO_RULES: Dict[str, Sequence[str]] = {}
CLOSING_IRRELEVANT_RULES: Dict[str, Sequence[str]] = {}
CLIP_RE = re.compile(r"^(?P<source>.+)_(?P<index>\d+)_(?P<hint>.*)\.mp4$", re.I)


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


def _label_config_path(name: str) -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "label_configs",
        f"{name}.json",
    )


def _rule_levels(rules: Optional[Dict[str, Sequence[str]]]) -> Dict[str, Sequence[str]]:
    rules = rules or {}
    unknown_levels = set(rules) - set(RULE_LEVELS)
    if unknown_levels:
        raise ValueError(f"Unknown rule levels: {', '.join(sorted(unknown_levels))}")
    return {level: list(rules.get(level, [])) for level in RULE_LEVELS}


def _int_keyed_strings(data: Dict[str, str], field_name: str) -> Dict[int, str]:
    try:
        return {int(key): value for key, value in data.items()}
    except ValueError as exc:
        raise ValueError(f"{field_name} keys must be integers") from exc


def _int_keyed_rules(
    data: Dict[str, Dict[str, Sequence[str]]], field_name: str
) -> Dict[int, Dict[str, Sequence[str]]]:
    try:
        return {int(key): _rule_levels(value) for key, value in data.items()}
    except ValueError as exc:
        raise ValueError(f"{field_name} keys must be integers") from exc


def load_routine_config(name: str) -> RoutineConfig:
    path = _label_config_path(name)
    with open(path, encoding="utf-8") as config_file:
        data = json.load(config_file)

    labels = data.get("labels", {})
    return RoutineConfig(
        name=data["name"],
        action_labels=_int_keyed_strings(data["action_labels"], "action_labels"),
        action_rules=_int_keyed_rules(data["action_rules"], "action_rules"),
        intro_label=labels.get("intro"),
        outro_label=labels.get("outro"),
        opening_label=labels.get("opening", OPENING_LABEL),
        closing_label=labels.get("closing", CLOSING_LABEL),
        intro_outro_rules=_rule_levels(data.get("intro_outro_rules")),
        closing_irrelevant_rules=_rule_levels(data.get("closing_irrelevant_rules")),
        description=data.get(
            "description",
            "Generate reviewable CSV labels and folders for routine clips.",
        ),
    )


DEFAULT_CONFIG = load_routine_config("baduanjin")
ACTION_LABELS = DEFAULT_CONFIG.action_labels
ACTION_RULES = DEFAULT_CONFIG.action_rules
INTRO_OUTRO_RULES = DEFAULT_CONFIG.intro_outro_rules
CLOSING_IRRELEVANT_RULES = DEFAULT_CONFIG.closing_irrelevant_rules


@dataclass(frozen=True)
class TermMatch:
    term: str
    level: str
    method: str
    weight: int

    def note(self) -> str:
        return f"{self.level}:{self.term}:{self.method}"


def normalize_source_video_name(name: str) -> str:
    return re.sub(r"\s+", "_", str(name or "").strip())


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
    has_text_match = False
    if _is_only_ignored_text(text):
        return 0, ()

    for level, terms in rules.items():
        weight = TERM_LEVEL_WEIGHTS[level]
        level_matches = []
        for term in terms:
            text_matched = _contains_by_text(text, term)
            pinyin_matched = (
                not text_matched
                and not has_text_match
                and level in PINYIN_MATCH_LEVELS
                and _contains_by_pinyin(text, term)
            )
            if not text_matched and not pinyin_matched:
                continue
            method = "text" if text_matched else "pinyin"
            if text_matched:
                has_text_match = True
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


def bind_routine_label_module(
    module_globals: Dict[str, object],
    config_name: str,
    config_var_name: str,
) -> RoutineConfig:
    config = load_routine_config(config_name)

    def configured_scan_clips(input_dir: str) -> List[ClipRecord]:
        return scan_clips(
            input_dir,
            action_rules=config.action_rules,
            intro_outro_rules=config.intro_outro_rules,
        )

    def configured_label_records(
        records: Sequence[ClipRecord],
    ) -> List[Dict[str, str]]:
        return label_records(records, config)

    def configured_auto_label_directory(input_dir: str) -> List[Dict[str, str]]:
        return auto_label_directory(input_dir, config)

    def configured_build_json_manifest(
        rows: Sequence[Dict[str, str]],
        input_dir: str,
        csv_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> Dict[str, object]:
        return build_json_manifest(
            rows,
            input_dir,
            config=config,
            csv_path=csv_path,
            output_dir=output_dir,
        )

    def configured_write_json_manifest(
        rows: Sequence[Dict[str, str]],
        json_path: str,
        input_dir: str,
        csv_path: Optional[str] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        write_json_manifest(
            rows,
            json_path,
            input_dir,
            config=config,
            csv_path=csv_path,
            output_dir=output_dir,
        )

    def configured_run(
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
        return run(
            input_dir,
            config=config,
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

    def configured_main() -> None:
        main(config)

    module_globals.update(
        {
            config_var_name: config,
            "ACTION_LABELS": config.action_labels,
            "ACTION_RULES": config.action_rules,
            "INTRO_LABEL": config.intro_label,
            "OUTRO_LABEL": config.outro_label,
            "OPENING_LABEL": config.opening_label,
            "CLOSING_LABEL": config.closing_label,
            "INTRO_OUTRO_RULES": config.intro_outro_rules,
            "OPENING_RULES": config.intro_outro_rules,
            "CLOSING_IRRELEVANT_RULES": config.closing_irrelevant_rules,
            "CSV_FIELDS": CSV_FIELDS,
            "ClipRecord": ClipRecord,
            "RoutineConfig": RoutineConfig,
            "auto_label_directory": configured_auto_label_directory,
            "build_json_manifest": configured_build_json_manifest,
            "build_parser": build_parser,
            "default_csv_path": default_csv_path,
            "default_json_path": default_json_path,
            "default_output_dir": default_output_dir,
            "label_folder_parts": label_folder_parts,
            "label_records": configured_label_records,
            "main": configured_main,
            "parse_clip_filename": parse_clip_filename,
            "read_csv": read_csv,
            "run": configured_run,
            "scan_clips": configured_scan_clips,
            "summarize_rows": summarize_rows,
            "sync_labeled_folders": sync_labeled_folders,
            "text_to_pinyin": text_to_pinyin,
            "write_csv": write_csv,
            "write_json_manifest": configured_write_json_manifest,
        }
    )
    return config


if __name__ == "__main__":
    main()
