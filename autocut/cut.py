import logging
import os
import re

import srt
from moviepy import editor

from . import utils


MEDIA_END_EPSILON = 0.01


# Merge videos
class Merger:
    def __init__(self, args):
        self.args = args

    def write_md(self, videos):
        md = utils.MD(self.args.inputs[0], self.args.encoding)
        num_tasks = len(md.tasks())
        # Not overwrite if already marked as down or no new videos
        if md.done_editing() or num_tasks == len(videos) + 1:
            return

        md.clear()
        md.add_done_editing(False)
        md.add("\nSelect the files that will be used to generate `autocut_final.mp4`\n")
        base = lambda fn: os.path.basename(fn)
        for f in videos:
            md_fn = utils.change_ext(f, "md")
            video_md = utils.MD(md_fn, self.args.encoding)
            # select a few words to scribe the video
            desc = ""
            if len(video_md.tasks()) > 1:
                for _, t in video_md.tasks()[1:]:
                    m = re.findall(r"\] (.*)", t)
                    if m and "no speech" not in m[0].lower():
                        desc += m[0] + " "
                    if len(desc) > 50:
                        break
            md.add_task(
                False,
                f'[{base(f)}]({base(md_fn)}) {"[Edited]" if video_md.done_editing() else ""} {desc}',
            )
        md.write()

    def run(self):
        md_fn = self.args.inputs[0]
        md = utils.MD(md_fn, self.args.encoding)
        if not md.done_editing():
            return

        videos = []
        for m, t in md.tasks():
            if not m:
                continue
            m = re.findall(r"\[(.*)\]", t)
            if not m:
                continue
            fn = os.path.join(os.path.dirname(md_fn), m[0])
            logging.info(f"Loading {fn}")
            videos.append(editor.VideoFileClip(fn))

        dur = sum([v.duration for v in videos])
        logging.info(f"Merging into a video with {dur / 60:.1f} min length")

        merged = editor.concatenate_videoclips(videos)
        fn = os.path.splitext(md_fn)[0] + "_merged.mp4"
        merged.write_videofile(
            fn, audio_codec="aac", bitrate=self.args.bitrate
        )  # logger=None,
        logging.info(f"Saved merged video to {fn}")


# Cut media
class Cutter:
    def __init__(self, args):
        self.args = args

    def _is_cuttable_media(self, filename):
        filename = filename.lower()
        return utils.is_video(filename) or utils.is_audio(filename)

    def _cut_jobs(self):
        explicit_job = self._explicit_cut_job()
        if explicit_job is not None:
            return [explicit_job]

        jobs = []
        for media_fn in self._batch_media_inputs():
            srt_fn = self._find_matching_srt(media_fn)
            if not srt_fn:
                logging.warning(f"No matching .srt file found for {media_fn}")
                continue
            jobs.append({"media": media_fn, "srt": srt_fn, "md": None})

        return jobs

    def _explicit_cut_job(self):
        media_files = []
        srt_fn = None
        md_fn = None
        has_directory = False

        for fn in self.args.inputs:
            if os.path.isdir(fn):
                has_directory = True
                continue

            ext = os.path.splitext(fn)[1].lower()
            if ext == ".srt":
                srt_fn = fn
            elif ext == ".md":
                md_fn = fn
            elif self._is_cuttable_media(fn):
                media_files.append(fn)

        if not srt_fn:
            return None

        assert not has_directory, "explicit .srt cuts must provide one media file"
        assert len(media_files) == 1, "explicit .srt cuts must provide one media file"
        return {"media": media_files[0], "srt": srt_fn, "md": md_fn}

    def _batch_media_inputs(self):
        media_files = []
        for input_fn in self.args.inputs:
            if os.path.isdir(input_fn):
                found = [
                    os.path.join(input_fn, name)
                    for name in sorted(os.listdir(input_fn))
                    if os.path.isfile(os.path.join(input_fn, name))
                    and self._is_cuttable_media(name)
                ]
                if found:
                    logging.info(
                        f"Found {len(found)} media files in {input_fn} for batch cut"
                    )
                else:
                    logging.warning(f"No media files found in {input_fn}")
                media_files.extend(found)
            elif self._is_cuttable_media(input_fn):
                media_files.append(input_fn)

        return list(dict.fromkeys(media_files))

    def _find_matching_srt(self, media_fn):
        media_base = os.path.splitext(os.path.basename(media_fn))[0]
        candidates = []

        for search_dir in self._srt_search_dirs(media_fn):
            for name in self._known_srt_names(media_base):
                candidate = os.path.join(search_dir, name)
                if os.path.isfile(candidate):
                    candidates.append(candidate)

            if not os.path.isdir(search_dir):
                continue
            for name in os.listdir(search_dir):
                candidate = os.path.join(search_dir, name)
                if (
                    os.path.isfile(candidate)
                    and os.path.splitext(name)[1].lower() == ".srt"
                    and self._is_related_srt_name(media_base, name)
                ):
                    candidates.append(candidate)

        unique_candidates = list(dict.fromkeys(os.path.abspath(c) for c in candidates))
        if not unique_candidates:
            return None

        unique_candidates.sort(key=lambda c: self._srt_match_score(media_base, c))
        matched = unique_candidates[0]
        logging.info(f"Matched subtitle {matched} for {media_fn}")
        return matched

    def _srt_search_dirs(self, media_fn):
        dirs = [os.path.dirname(media_fn) or ".", os.getcwd()]
        output_dir = getattr(self.args, "output_dir", None)
        if output_dir and os.path.isdir(output_dir):
            dirs.append(output_dir)

        seen = set()
        unique_dirs = []
        for directory in dirs:
            normalized = os.path.abspath(directory)
            key = os.path.normcase(normalized)
            if key in seen:
                continue
            seen.add(key)
            unique_dirs.append(normalized)
        return unique_dirs

    def _known_srt_names(self, media_base):
        return [
            f"{media_base}_vocals_cleaned.srt",
            f"{media_base}_Vocals_cleaned.srt",
            f"{media_base}_cleaned.srt",
            f"{media_base}.srt",
            f"{media_base}_vocals.srt",
            f"{media_base}_Vocals.srt",
        ]

    def _is_related_srt_name(self, media_base, srt_name):
        media_base = media_base.lower()
        srt_base = os.path.splitext(srt_name)[0].lower()
        return (
            srt_base == media_base
            or srt_base.startswith(media_base + "_")
            or srt_base.startswith(media_base + "-")
        )

    def _srt_match_score(self, media_base, srt_fn):
        name = os.path.basename(srt_fn).lower()
        base = media_base.lower()
        preferred_names = [
            f"{base}_vocals_cleaned.srt",
            f"{base}_cleaned.srt",
            f"{base}.srt",
            f"{base}_vocals.srt",
        ]
        try:
            score = preferred_names.index(name)
        except ValueError:
            score = len(preferred_names)
        return (score, len(name), name)

    def _output_dir_for_job(self, fns, multi_job):
        output_dir = getattr(self.args, "output_dir", None)
        media_base = self._safe_source_basename(
            os.path.splitext(os.path.basename(fns["media"]))[0]
        )

        if output_dir:
            if multi_job:
                return os.path.join(output_dir, f"{media_base}_name")
            return output_dir

        media_dir = os.path.dirname(fns["media"]) or "."
        if multi_job:
            return os.path.join(media_dir, f"{media_base}_name")
        return media_dir

    # 辅助函数：清洗字幕内容，使其变成安全的文件名
    def _safe_filename(self, text):
        # 1. 移除换行和多余空格
        text = text.replace("\n", " ").strip()
        # 2. 过滤掉 Windows/Linux/Mac 系统的非法文件名字符
        text = re.sub(r'[\\/*?:"<>|]', "_", text)
        # 3. 截取前 5 个字符
        return text[:5].strip()

    def _safe_source_basename(self, name):
        return re.sub(r"\s+", "_", str(name or "").strip())

    def _media_safe_end(self, media):
        durations = [getattr(media, "duration", None)]
        audio = getattr(media, "audio", None)
        if audio is not None:
            durations.append(getattr(audio, "duration", None))
            reader = getattr(audio, "reader", None)
            if reader is not None:
                durations.append(getattr(reader, "duration", None))

        durations = [d for d in durations if d is not None and d > 0]
        if not durations:
            return None
        return max(0, min(durations) - MEDIA_END_EPSILON)

    def _bounded_segment(self, start_sec, end_sec, safe_end, text, orig_index):
        start_sec = max(0, start_sec)
        if safe_end is not None:
            end_sec = min(end_sec, safe_end)

        if start_sec >= end_sec:
            logging.warning(
                f"Skip subtitle {orig_index}: segment is outside media duration "
                f"({start_sec:.3f}s -> {end_sec:.3f}s)."
            )
            return None

        return {
            "start": start_sec,
            "end": end_sec,
            "text": text,
            "orig_index": orig_index,
        }

    def run(self):
        jobs = self._cut_jobs()
        if not jobs:
            logging.warning("No cut jobs to run")
            return

        multi_job = len(jobs) > 1
        for fns in jobs:
            self._cut_one(fns, multi_job)

    def _cut_one(self, fns, multi_job=False):
        assert fns["media"], "must provide a media filename"
        assert fns["srt"], "must provide a srt filename"

        is_video_file = utils.is_video(fns["media"].lower())
        outext = "mp4" if is_video_file else "mp3"
        output_fn = utils.change_ext(utils.add_cut(fns["media"]), outext)

        with open(fns["srt"], encoding=self.args.encoding) as f:
            subs = list(srt.parse(f.read()))

        if fns["md"]:
            md = utils.MD(fns["md"], self.args.encoding)
            if not md.done_editing():
                return
            index = []
            for mark, sent in md.tasks():
                if not mark:
                    continue
                m = re.match(r"\[(\d+)", sent.strip())
                if m:
                    index.append(int(m.groups()[0]))
            subs = [s for s in subs if s.index in index]
            logging.info(f'Cut {fns["media"]} based on {fns["srt"]} and {fns["md"]}')
        else:
            logging.info(f'Cut {fns["media"]} based on {fns["srt"]}')

        # 将媒体加载提前，以便获取 media.duration
        if is_video_file:
            media = editor.VideoFileClip(fns["media"])
        else:
            media = editor.AudioFileClip(fns["media"])
        safe_media_end = self._media_safe_end(media)
        media_duration = getattr(media, "duration", None)
        if (
            safe_media_end is not None
            and media_duration is not None
            and safe_media_end < media_duration
        ):
            logging.info(
                f"Clamping segment end times to {safe_media_end:.3f}s "
                f"to avoid reading past the media stream."
            )

        # 整理带字幕文本的片段列表
        segments = []
        subs.sort(key=lambda x: x.start)

        # ------------------ 修改点：构建带字幕文本的 segments ------------------
        if getattr(self.args, "cut_by_start", False):
            logging.info("Using 'cut by start time' logic.")
            for i in range(len(subs)):
                start_sec = subs[i].start.total_seconds()
                end_sec = (
                    subs[i + 1].start.total_seconds()
                    if i < len(subs) - 1
                    else media.duration
                )
                text_clean = self._safe_filename(subs[i].content)
                segment = self._bounded_segment(
                    start_sec,
                    end_sec,
                    safe_media_end,
                    text_clean,
                    subs[i].index,
                )

                if segment is not None:
                    segments.append(segment)
        else:
            # 默认合并逻辑，如果有合并，就拼接参与合并的字幕文本
            # 为了简单起见，这里直接用每段合并区间内“第一条字幕”的文本和序号
            temp_segments = []
            for x in subs:
                start_sec = x.start.total_seconds()
                end_sec = x.end.total_seconds()
                text_clean = self._safe_filename(x.content)

                if len(temp_segments) == 0:
                    segment = self._bounded_segment(
                        start_sec,
                        end_sec,
                        safe_media_end,
                        text_clean,
                        x.index,
                    )
                    if segment is not None:
                        temp_segments.append(segment)
                else:
                    if start_sec - temp_segments[-1]["end"] < 0.5:
                        bounded_end = (
                            min(end_sec, safe_media_end)
                            if safe_media_end is not None
                            else end_sec
                        )
                        temp_segments[-1]["end"] = max(
                            temp_segments[-1]["end"], bounded_end
                        )
                    else:
                        segment = self._bounded_segment(
                            start_sec,
                            end_sec,
                            safe_media_end,
                            text_clean,
                            x.index,
                        )
                        if segment is not None:
                            temp_segments.append(segment)
            segments = temp_segments

        # ------------------ 修改点：输出文件名拼接 ------------------
        base_name, ext = os.path.splitext(os.path.basename(output_fn))
        base_name = self._safe_source_basename(base_name)
        total_segments = len(segments)

        # 确定输出文件夹
        out_dir = self._output_dir_for_job(fns, multi_job)
        os.makedirs(out_dir, exist_ok=True)

        logging.info(f"Total segments to cut: {total_segments}")
        logging.info(f"Output directory: {os.path.abspath(out_dir)}")

        for idx, s in enumerate(segments):
            # 新的命名规则：[原视频名]_字幕序号_[前5个字].mp4
            # 示例: test6_cut_12_今天天气真.mp4
            part_filename = f"{base_name}_{s['orig_index']}_{s['text']}{ext}"
            part_fn = os.path.join(out_dir, part_filename)
            if utils.check_exists(part_fn, self.args.force):
                continue

            # 重新实例化片段以避免句柄共享导致进程崩溃
            if is_video_file:
                temp_media = editor.VideoFileClip(fns["media"])
            else:
                temp_media = editor.AudioFileClip(fns["media"])

            clip = temp_media.subclip(s["start"], s["end"])

            logging.info(
                f"[{idx + 1}/{total_segments}] Saving to {part_fn} "
                f"(Duration: {clip.duration:.1f}s)"
            )

            try:
                if is_video_file:
                    # 尝试进行原版的音频优化
                    aud = clip.audio.set_fps(44100)
                    clip = clip.without_audio().set_audio(aud)

                    try:
                        # 尝试归一化音量
                        clip = clip.fx(editor.afx.audio_normalize)
                    except Exception as e:
                        logging.warning(
                            f"[{idx + 1}/{total_segments}] "
                            f"音频归一化失败，将使用原始音量导出。原因: {e}"
                        )

                    # 导出视频片段
                    clip.write_videofile(
                        part_fn, audio_codec="aac", bitrate=self.args.bitrate
                    )
                else:
                    try:
                        clip = clip.fx(editor.afx.audio_normalize)
                    except Exception as e:
                        logging.warning(
                            f"[{idx + 1}/{total_segments}] "
                            f"音频归一化失败，将使用原始音量导出。原因: {e}"
                        )

                    clip.write_audiofile(
                        part_fn,
                        codec="libmp3lame",
                        fps=44100,
                        bitrate=self.args.bitrate,
                    )
            finally:
                # 必须关闭当前的 clip 和临时打开的 media 句柄，彻底释放进程
                clip.close()
                temp_media.close()

        # ------------------------------------------------------------------
        media.close()
        logging.info(
            f"All segments saved successfully inside: {os.path.abspath(out_dir)}"
        )
