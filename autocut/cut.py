import logging
import os
import re

import srt
from moviepy import editor

from . import utils


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

    def run(self):
        fns = {"srt": None, "media": None, "md": None}
        for fn in self.args.inputs:
            ext = os.path.splitext(fn)[1][1:]
            fns[ext if ext in fns else "media"] = fn

        assert fns["media"], "must provide a media filename"
        assert fns["srt"], "must provide a srt filename"

        is_video_file = utils.is_video(fns["media"].lower())
        outext = "mp4" if is_video_file else "mp3"
        output_fn = utils.change_ext(utils.add_cut(fns["media"]), outext)
        if utils.check_exists(output_fn, self.args.force):
            return

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

        # ---- 修改点 1：将媒体加载提前，以便获取 media.duration ----
        if is_video_file:
            media = editor.VideoFileClip(fns["media"])
        else:
            media = editor.AudioFileClip(fns["media"])

        segments = []
        # Avoid disordered subtitles
        subs.sort(key=lambda x: x.start)
        
        # ---- 修改点 2：增加仅按 start 划分的分支逻辑 ----
        if getattr(self.args, "cut_by_start", False):
            logging.info("Using 'cut by start time' logic.")
            for i in range(len(subs)):
                start_sec = subs[i].start.total_seconds()
                
                # 如果不是最后一个字幕，结束时间就是下一个字幕的开始时间
                if i < len(subs) - 1:
                    end_sec = subs[i+1].start.total_seconds()
                else:
                    # 如果是最后一个字幕，结束时间就是媒体总时长
                    end_sec = media.duration
                
                # 确保时间合法才加入
                if start_sec < end_sec:
                    segments.append({"start": start_sec, "end": end_sec})
        else:
            # 默认的原版逻辑
            for x in subs:
                if len(segments) == 0:
                    segments.append(
                        {"start": x.start.total_seconds(), "end": x.end.total_seconds()}
                    )
                else:
                    if x.start.total_seconds() - segments[-1]["end"] < 0.5:
                        segments[-1]["end"] = x.end.total_seconds()
                    else:
                        segments.append(
                            {"start": x.start.total_seconds(), "end": x.end.total_seconds()}
                        )

        # ------------------ 安全地单独循环导出（保留之前的修改） ------------------
        base_name, ext = os.path.splitext(os.path.basename(output_fn))
        total_segments = len(segments)
        
        # 确定输出文件夹
        if getattr(self.args, "output_dir", None):
            out_dir = self.args.output_dir
            # 如果文件夹不存在则自动创建
            os.makedirs(out_dir, exist_ok=True)
        else:
            # 默认保存在输入媒体文件的同目录下
            out_dir = os.path.dirname(fns["media"]) or "."

        logging.info(f"Total segments to cut: {total_segments}")
        logging.info(f"Output directory: {os.path.abspath(out_dir)}")

        for idx, s in enumerate(segments):
            # 拼接目标保存路径，例如: d:\your_path\test6_cut_1.mp4
            part_filename = f"{base_name}_{idx + 1}{ext}"
            part_fn = os.path.join(out_dir, part_filename)
            
            # 重新实例化片段以避免句柄共享导致进程崩溃
            if is_video_file:
                temp_media = editor.VideoFileClip(fns["media"])
            else:
                temp_media = editor.AudioFileClip(fns["media"])
                
            clip = temp_media.subclip(s["start"], s["end"])
            
            logging.info(f"[{idx + 1}/{total_segments}] Saving to {part_fn} (Duration: {clip.duration:.1f}s)")

            try:
                if is_video_file:
                    # 尝试进行原版的音频优化
                    aud = clip.audio.set_fps(44100)
                    clip = clip.without_audio().set_audio(aud)
                    
                    try:
                        # 尝试归一化音量
                        clip = clip.fx(editor.afx.audio_normalize)
                    except Exception as e:
                        logging.warning(f"[{idx + 1}/{total_segments}] 音频归一化失败，将使用原始音量导出。原因: {e}")
                    
                    # 导出视频片段
                    clip.write_videofile(
                        part_fn, audio_codec="aac", bitrate=self.args.bitrate
                    )
                else:
                    try:
                        clip = clip.fx(editor.afx.audio_normalize)
                    except Exception as e:
                        logging.warning(f"[{idx + 1}/{total_segments}] 音频归一化失败，将使用原始音量导出。原因: {e}")
                        
                    clip.write_audiofile(
                        part_fn, codec="libmp3lame", fps=44100, bitrate=self.args.bitrate
                    )
            finally:
                # 必须关闭当前的 clip 和临时打开的 media 句柄，彻底释放进程
                clip.close()
                temp_media.close()

        # ------------------------------------------------------------------
        media.close()
        logging.info(f"All segments saved successfully inside: {os.path.abspath(out_dir)}")