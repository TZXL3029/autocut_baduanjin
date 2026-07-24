import os
import sys
from collections import Counter
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from .routine_label import (
        ACTION_LABELS,
        ACTION_RULES,
        CLOSING_IRRELEVANT_RULES,
        CLOSING_LABEL,
        CSV_FIELDS,
        DEFAULT_CONFIG as BADUANJIN_CONFIG,
        INTRO_LABEL,
        INTRO_OUTRO_RULES,
        OPENING_LABEL,
        OUTRO_LABEL,
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
        ACTION_LABELS,
        ACTION_RULES,
        CLOSING_IRRELEVANT_RULES,
        CLOSING_LABEL,
        CSV_FIELDS,
        DEFAULT_CONFIG as BADUANJIN_CONFIG,
        INTRO_LABEL,
        INTRO_OUTRO_RULES,
        OPENING_LABEL,
        OUTRO_LABEL,
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


def scan_clips(input_dir: str) -> List[ClipRecord]:
    return _scan_clips(
        input_dir,
        action_rules=BADUANJIN_CONFIG.action_rules,
        intro_outro_rules=BADUANJIN_CONFIG.intro_outro_rules,
    )


def label_records(records: Sequence[ClipRecord]) -> List[Dict[str, str]]:
    return _label_records(records, BADUANJIN_CONFIG)


def auto_label_directory(input_dir: str) -> List[Dict[str, str]]:
    return _auto_label_directory(input_dir, BADUANJIN_CONFIG)


def build_json_manifest(
    rows: Sequence[Dict[str, str]],
    input_dir: str,
    csv_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> Dict[str, object]:
    return _build_json_manifest(
        rows,
        input_dir,
        config=BADUANJIN_CONFIG,
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
        config=BADUANJIN_CONFIG,
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
        config=BADUANJIN_CONFIG,
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
    _main(BADUANJIN_CONFIG)


if __name__ == "__main__":
    main()
