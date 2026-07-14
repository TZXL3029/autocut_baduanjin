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

    # 辅助函数：清洗字幕内容，使其变成安全的文件名
    def _safe_filename(self, text):
        # 1. 移除换行和多余空格
        text = text.replace("\n", " ").strip()
        # 2. 过滤掉 Windows/Linux/Mac 系统的非法文件名字符
        text = re.sub(r'[\\/*?:"<>|]', "_", text)
        # 3. 截取前 5 个字符
        return text[:5].strip()

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

        # 将媒体加载提前，以便获取 media.duration
        if is_video_file:
            media = editor.VideoFileClip(fns["media"])
        else:
            media = editor.AudioFileClip(fns["media"])

        # 整理带字幕文本的片段列表
        segments = []
        subs.sort(key=lambda x: x.start)
        
        # ------------------ 修改点：构建带字幕文本的 segments ------------------
        if getattr(self.args, "cut_by_start", False):
            logging.info("Using 'cut by start time' logic.")
            for i in range(len(subs)):
                start_sec = subs[i].start.total_seconds()
                end_sec = subs[i+1].start.total_seconds() if i < len(subs) - 1 else media.duration
                text_clean = self._safe_filename(subs[i].content)
                
                if start_sec < end_sec:
                    segments.append({
                        "start": start_sec, 
                        "end": end_sec,
                        "text": text_clean,
                        "orig_index": subs[i].index  # 保留字幕本来的序号
                    })
        else:
            # 默认合并逻辑，如果有合并，就拼接参与合并的字幕文本
            # 为了简单起见，这里直接用每段合并区间内“第一条字幕”的文本和序号
            temp_segments = []
            for x in subs:
                start_sec = x.start.total_seconds()
                end_sec = x.end.total_seconds()
                text_clean = self._safe_filename(x.content)
                
                if len(temp_segments) == 0:
                    temp_segments.append({
                        "start": start_sec, 
                        "end": end_sec, 
                        "text": text_clean,
                        "orig_index": x.index
                    })
                else:
                    if start_sec - temp_segments[-1]["end"] < 0.5:
                        temp_segments[-1]["end"] = end_sec
                    else:
                        temp_segments.append({
                            "start": start_sec, 
                            "end": end_sec, 
                            "text": text_clean,
                            "orig_index": x.index
                        })
            segments = temp_segments

        # ------------------ 修改点：输出文件名拼接 ------------------
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
            # 新的命名规则：[原视频名]_字幕序号_[前5个字].mp4
            # 示例: test6_cut_12_今天天气真.mp4
            part_filename = f"{base_name}_{s['orig_index']}_{s['text']}{ext}"
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