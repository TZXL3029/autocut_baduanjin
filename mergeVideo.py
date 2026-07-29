import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from autocut import utils


@dataclass(frozen=True)
class MergeGroup:
    directory: Path
    videos: List[Path]
    output: Path


@dataclass(frozen=True)
class MergePlan:
    group: MergeGroup
    action: str
    reason: str = ""


class MergeError(RuntimeError):
    pass


def parse_extensions(value: Optional[str]) -> Optional[Set[str]]:
    if not value:
        return None

    extensions = set()
    for item in value.split(","):
        ext = item.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = "." + ext
        extensions.add(ext)
    return extensions


def natural_key(value: str) -> List[object]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(part) if part.isdigit() else part for part in parts]


def is_video_file(path: Path, extensions: Optional[Set[str]] = None) -> bool:
    if extensions is not None:
        return path.suffix.lower() in extensions
    return utils.is_video(path.name.lower())


def output_path_for_directory(directory: Path) -> Path:
    return directory / f"{directory.name}.mp4"


def same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(
        os.path.abspath(right)
    )


def discover_video_groups(
    root: Path, extensions: Optional[Set[str]] = None
) -> List[MergeGroup]:
    groups = []
    for dirpath, _, filenames in os.walk(root):
        directory = Path(dirpath)
        output = output_path_for_directory(directory)
        videos = [
            directory / filename
            for filename in filenames
            if is_video_file(directory / filename, extensions)
            and not same_path(directory / filename, output)
        ]
        videos = sorted(videos, key=lambda path: natural_key(path.name))
        if videos:
            groups.append(MergeGroup(directory=directory, videos=videos, output=output))

    return sorted(groups, key=lambda group: natural_key(str(group.directory)))


def validate_group_sources(group: MergeGroup) -> None:
    for video in group.videos:
        if same_path(video, group.output):
            raise MergeError(f"Output path is also a source video: {group.output}")


def build_merge_plan(
    root: Path, extensions: Optional[Set[str]] = None, force: bool = False
) -> List[MergePlan]:
    plans = []
    for group in discover_video_groups(root, extensions):
        try:
            validate_group_sources(group)
        except MergeError as exc:
            plans.append(MergePlan(group=group, action="skip", reason=str(exc)))
            continue

        if len(group.videos) < 2:
            plans.append(
                MergePlan(group=group, action="skip", reason="only 1 video in this folder")
            )
            continue

        if group.output.exists() and not force:
            plans.append(
                MergePlan(
                    group=group,
                    action="skip",
                    reason="output exists; use --force to overwrite",
                )
            )
            continue

        plans.append(MergePlan(group=group, action="merge"))
    return plans


def concat_file_line(path: Path) -> str:
    normalized = str(path.resolve()).replace("\\", "/").replace("'", "'\\''")
    return f"file '{normalized}'\n"


def run_ffmpeg(command: Sequence[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise MergeError("ffmpeg command not found. Please install ffmpeg first.") from exc


def stderr_tail(process: subprocess.CompletedProcess, max_chars: int = 2000) -> str:
    stderr = process.stderr or ""
    return stderr[-max_chars:].strip()


def remove_partial_output(output: Path) -> None:
    if output.exists():
        output.unlink()


def merge_group(group: MergeGroup, force: bool = False) -> None:
    validate_group_sources(group)
    if len(group.videos) < 2:
        return
    if group.output.exists() and not force:
        return

    group.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", suffix=".txt", prefix="mergeVideo_", encoding="utf-8", delete=False
    ) as list_file:
        list_path = Path(list_file.name)
        for video in group.videos:
            list_file.write(concat_file_line(video))

    try:
        copy_command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(group.output),
        ]
        copy_result = run_ffmpeg(copy_command)
        if copy_result.returncode == 0:
            return

        remove_partial_output(group.output)

        transcode_command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(group.output),
        ]
        transcode_result = run_ffmpeg(transcode_command)
        if transcode_result.returncode != 0:
            remove_partial_output(group.output)
            raise MergeError(
                "ffmpeg concat copy failed, and fallback transcode also failed.\n"
                f"copy stderr:\n{stderr_tail(copy_result)}\n"
                f"transcode stderr:\n{stderr_tail(transcode_result)}"
            )
    finally:
        if list_path.exists():
            list_path.unlink()


def print_plan(plans: Iterable[MergePlan], dry_run: bool = False) -> None:
    prefix = "DRY-RUN " if dry_run else ""
    for plan in plans:
        group = plan.group
        if plan.action != "merge":
            print(f"{prefix}SKIP {group.directory}: {plan.reason}")
            continue

        print(f"{prefix}MERGE {group.directory} -> {group.output}")
        for video in group.videos:
            print(f"  - {video.name}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Recursively merge videos that live in the same folder. Each folder "
            "writes <folder-name>.mp4 inside that folder."
        )
    )
    parser.add_argument("folder", help="Root folder to scan recursively.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing non-source output files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print merge groups without writing output files.",
    )
    parser.add_argument(
        "--extensions",
        default=None,
        help="Comma-separated video extensions to include, such as .mp4,.mov.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    root = Path(args.folder)
    if not root.is_dir():
        print(f"Folder does not exist: {root}", file=sys.stderr)
        return 2

    extensions = parse_extensions(args.extensions)
    plans = build_merge_plan(root, extensions=extensions, force=args.force)
    if not plans:
        print(f"No video files found under {root}")
        return 0

    print_plan(plans, dry_run=args.dry_run)
    if args.dry_run:
        return 0

    failed = 0
    for plan in plans:
        if plan.action != "merge":
            continue
        try:
            merge_group(plan.group, force=args.force)
        except MergeError as exc:
            failed += 1
            print(f"FAILED {plan.group.directory}: {exc}", file=sys.stderr)
        else:
            print(f"SAVED {plan.group.output}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
