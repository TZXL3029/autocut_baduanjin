import os
import subprocess
import torch
import torchaudio
import numpy as np

from demucs.pretrained import get_model
from demucs.apply import apply_model


VIDEO_DIR = "videos"
OUTPUT_DIR = "output"
VOCALS_SUFFIX = "_vocals.wav"
VIDEO_EXTENSIONS = (
    ".mp4",
    ".mkv",
    ".avi",
    ".mov",
    ".m4v",
    ".webm",
    ".wmv",
    ".flv",
)


class VocalExtractor:
    """
    Demucs 人声提取器

    输入:
        视频文件

    输出:
        vocals.wav
    """

    def __init__(
        self,
        model_name="htdemucs",
        device=None
    ):

        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"

        self.device = device

        print(f"[Demucs] device = {device}")

        # 加载模型
        self.model = get_model(model_name)

        self.model.to(device)

        self.model.eval()

        print(
            f"[Demucs] loaded model: {model_name}"
        )


    def extract_audio(
        self,
        video_path,
        wav_path
    ):
        """
        ffmpeg 提取音频
        """

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            video_path,
            "-vn",
            "-ac",
            "2",
            "-ar",
            "44100",
            wav_path
        ]

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        print(wav_path)
        print(os.path.exists(wav_path))
        print(os.path.getsize(wav_path))


    def separate(
        self,
        wav_path,
        output_path
    ):
        """
        Demucs 分离
        """

        wav, sr = torchaudio.load(wav_path)


        # Demucs要求:
        # [batch, channels, samples]

        wav = wav.to(self.device)


        with torch.no_grad():

            sources = apply_model(
                self.model,
                wav.unsqueeze(0),
                device=self.device
            )


        # htdemucs:
        #
        # 0 vocals
        # 1 drums
        # 2 bass
        # 3 other
        #

        vocals = sources[0][
            self.model.sources.index("vocals")
        ]


        vocals = vocals.cpu()


        torchaudio.save(
            output_path,
            vocals,
            sr
        )


    def extract(
        self,
        video_path,
        output_dir
    ):

        os.makedirs(
            output_dir,
            exist_ok=True
        )


        name = get_video_name(
            video_path
        )


        vocals_file = get_vocals_path(
            video_path,
            output_dir
        )

        if is_completed_output(
            vocals_file
        ):
            print(
                f"\nSkipped, already separated: {vocals_file}"
            )
            return vocals_file


        temp_audio = os.path.join(
            output_dir,
            f"_{name}_temp.wav"
        )


        print(
            f"\nProcessing: {video_path}"
        )


        try:
            # 视频 -> wav

            self.extract_audio(
                video_path,
                temp_audio
            )


            # wav -> vocals

            self.separate(
                temp_audio,
                vocals_file
            )
        finally:
            if os.path.exists(
                temp_audio
            ):
                os.remove(
                    temp_audio
                )



        print(
            f"Saved: {vocals_file}"
        )


        return vocals_file


def get_video_name(
    video_path
):
    return os.path.splitext(
        os.path.basename(video_path)
    )[0]


def get_vocals_path(
    video_path,
    output_dir=OUTPUT_DIR
):
    return os.path.join(
        output_dir,
        f"{get_video_name(video_path)}{VOCALS_SUFFIX}"
    )


def is_completed_output(
    path
):
    return os.path.isfile(
        path
    ) and os.path.getsize(
        path
    ) > 0


def find_completed_outputs(
    output_dir=OUTPUT_DIR
):
    """
    直接扫描 output 文件夹，找出已经分离完成的 vocals 文件。
    """

    if not os.path.isdir(
        output_dir
    ):
        return set()

    completed = set()

    for filename in os.listdir(
        output_dir
    ):
        path = os.path.join(
            output_dir,
            filename
        )

        if filename.lower().endswith(
            VOCALS_SUFFIX
        ) and is_completed_output(
            path
        ):
            completed.add(
                filename.lower()
            )

    return completed


def find_videos(
    video_dir=VIDEO_DIR
):
    """
    查找 videos 文件夹下支持的视频文件。
    """

    if not os.path.isdir(
        video_dir
    ):
        raise FileNotFoundError(
            f"Video directory not found: {video_dir}"
        )

    videos = []

    for filename in os.listdir(
        video_dir
    ):
        path = os.path.join(
            video_dir,
            filename
        )

        if not os.path.isfile(
            path
        ):
            continue

        if filename.lower().endswith(
            VIDEO_EXTENSIONS
        ):
            videos.append(
                path
            )

    return sorted(
        videos
    )


def extract_batch(
    video_dir=VIDEO_DIR,
    output_dir=OUTPUT_DIR,
    model_name="htdemucs",
    device=None
):
    """
    批量转换 videos 文件夹下的视频。
    """

    videos = find_videos(
        video_dir
    )

    if not videos:
        print(
            f"No videos found in: {video_dir}"
        )
        return []

    completed_outputs = find_completed_outputs(
        output_dir
    )

    results = []
    pending = []
    skipped = []
    failed = []

    for video_path in videos:
        vocals_file = get_vocals_path(
            video_path,
            output_dir
        )
        output_name = os.path.basename(
            vocals_file
        ).lower()

        if output_name in completed_outputs:
            skipped.append(
                vocals_file
            )
            results.append(
                vocals_file
            )
            print(
                f"Skipped, already separated: {vocals_file}"
            )
        else:
            pending.append(
                video_path
            )

    if not pending:
        print(
            "\nAll finished!"
        )
        print(
            f"Ready: {len(results)}"
        )
        print(
            f"Processed: 0"
        )
        print(
            f"Skipped: {len(skipped)}"
        )
        print(
            "Failed: 0"
        )
        return results

    extractor = VocalExtractor(
        model_name=model_name,
        device=device
    )

    processed = []

    for index, video_path in enumerate(
        pending,
        start=1
    ):
        print(
            f"\n[{index}/{len(pending)}]"
        )

        try:
            vocals_file = extractor.extract(
                video_path,
                output_dir
            )
            processed.append(
                vocals_file
            )
            results.append(
                vocals_file
            )
        except Exception as exc:
            failed.append(
                (video_path, exc)
            )
            print(
                f"Failed: {video_path}"
            )
            print(
                exc
            )

    print(
        "\nAll finished!"
    )
    print(
        f"Ready: {len(results)}"
    )
    print(
        f"Processed: {len(processed)}"
    )
    print(
        f"Skipped: {len(skipped)}"
    )
    print(
        f"Failed: {len(failed)}"
    )

    if failed:
        print(
            "\nFailed files:"
        )

        for video_path, exc in failed:
            print(
                f"- {video_path}: {exc}"
            )

    return results


if __name__ == "__main__":
    extract_batch()
