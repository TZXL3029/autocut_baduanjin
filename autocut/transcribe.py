import logging
import os
import re
import time
from copy import copy
from dataclasses import dataclass
from typing import List, Any, Mapping, Sequence

import numpy as np
import srt
import torch

from . import utils, whisper_model
from .type import WhisperMode, SPEECH_ARRAY_INDEX, WhisperModel


AUTO_TRANSCRIBE_PROFILE = "auto"
DEFAULT_TRANSCRIBE_PROFILE = "default"

DEFAULT_ARG_VALUES = {
    "lang": "zh",
    "prompt": "",
    "whisper_mode": WhisperMode.WHISPER.value,
    "whisper_model": WhisperModel.SMALL.value,
    "vad": "auto",
    "device": None,
    "openai_rpm": 3,
}

BADUANJIN_PROMPT = (
    "八段锦健身气功教学字幕。常见口令和动作名称包括：预备势、两手托天理三焦、"
    "左右开弓似射雕、调理脾胃须单举、五劳七伤往后瞧、摇头摆尾去心火、"
    "两手攀足固肾腰、攒拳怒目增气力、背后七颠百病消、收势。"
)

TAIJI24_PROMPT = (
    "二十四式太极拳、24式简化太极拳教学字幕。常见口令和动作名称包括：起势、"
    "左右野马分鬃、白鹤亮翅、左右搂膝拗步、手挥琵琶、左右倒卷肱、"
    "左揽雀尾、右揽雀尾、单鞭、云手、高探马、右蹬脚、双峰贯耳、"
    "转身左蹬脚、左下势独立、右下势独立、左右穿梭、海底针、闪通背、"
    "转身搬拦捶、如封似闭、十字手、收势。"
)


@dataclass(frozen=True)
class TranscribeProfile:
    name: str
    match_terms: Sequence[str]
    overrides: Mapping[str, Any]


TRANSCRIBE_PROFILES = [
    TranscribeProfile(
        name=DEFAULT_TRANSCRIBE_PROFILE,
        match_terms=(),
        overrides={},
    ),
    TranscribeProfile(
        name="baduanjin",
        match_terms=(
            "baduanjin",
            "ba_duan_jin",
            "ba duan jin",
            "bdj",
            "八段锦",
            "八段錦",
            "健身气功八段锦",
        ),
        overrides={
            "lang": "zh",
            "prompt": BADUANJIN_PROMPT,
            "vad": "1",
        },
    ),
    TranscribeProfile(
        name="taiji24",
        match_terms=(
            "taiji24",
            "taiji",
            "taijiquan",
            "tai chi",
            "24taiji",
            "24式太极拳",
            "二十四式太极拳",
            "简化太极拳",
            "太极拳",
            "太极",
        ),
        overrides={
            "lang": "zh",
            "prompt": TAIJI24_PROMPT,
            "vad": "1",
        },
    ),
]

TRANSCRIBE_PROFILE_BY_NAME = {
    profile.name: profile for profile in TRANSCRIBE_PROFILES
}

TRANSCRIBE_PROFILE_ALIASES = {
    "ba_duan_jin": "baduanjin",
    "baduanjin": "baduanjin",
    "八段锦": "baduanjin",
    "八段錦": "baduanjin",
    "taiji": "taiji24",
    "taiji24": "taiji24",
    "taijiquan": "taiji24",
    "taichi": "taiji24",
    "太极拳": "taiji24",
    "太极": "taiji24",
}


def register_transcribe_profile(profile: TranscribeProfile) -> None:
    """Add or replace a transcribe profile for future routine-specific tuning."""
    if profile.name == AUTO_TRANSCRIBE_PROFILE:
        raise ValueError(f"{AUTO_TRANSCRIBE_PROFILE!r} is reserved")

    for index, existing in enumerate(TRANSCRIBE_PROFILES):
        if existing.name == profile.name:
            TRANSCRIBE_PROFILES[index] = profile
            break
    else:
        TRANSCRIBE_PROFILES.append(profile)
    TRANSCRIBE_PROFILE_BY_NAME[profile.name] = profile


def get_transcribe_profile_names() -> List[str]:
    return [AUTO_TRANSCRIBE_PROFILE, *TRANSCRIBE_PROFILE_BY_NAME.keys()]


class Transcribe:
    def __init__(self, args):
        self.args = args
        self.sampling_rate = 16000
        self.whisper_model = None
        self.whisper_model_key = None
        self.vad_model = None
        self.detect_speech = None

        inputs = getattr(args, "inputs", [])
        initial_args = self._args_for_input(inputs[0]) if inputs else args
        self._ensure_whisper_model(initial_args)

    def _ensure_whisper_model(self, args):
        model_key = (
            args.whisper_mode,
            getattr(args, "whisper_model", None),
            getattr(args, "device", None),
            getattr(args, "openai_rpm", None),
        )
        if self.whisper_model is not None and self.whisper_model_key == model_key:
            return

        tic = time.time()
        if args.whisper_mode == WhisperMode.WHISPER.value:
            self.whisper_model = whisper_model.WhisperModel(self.sampling_rate)
            self.whisper_model.load(args.whisper_model, args.device)
        elif args.whisper_mode == WhisperMode.OPENAI.value:
            self.whisper_model = whisper_model.OpenAIModel(
                args.openai_rpm, self.sampling_rate
            )
            self.whisper_model.load()
        elif args.whisper_mode == WhisperMode.FASTER.value:
            self.whisper_model = whisper_model.FasterWhisperModel(self.sampling_rate)
            self.whisper_model.load(args.whisper_model, args.device)
        else:
            raise ValueError(f"Unknown whisper mode: {args.whisper_mode}")
        self.whisper_model_key = model_key
        logging.info(f"Done Init model in {time.time() - tic:.1f} sec")

    def run(self):
        for input in self._transcription_inputs():
            effective_args = self._args_for_input(input)
            logging.info(
                f"Transcribing {input} with profile "
                f"{effective_args.transcribe_profile_name}"
            )
            output_base = self._output_base(input)
            output_dir = os.path.dirname(output_base)
            if getattr(effective_args, "output_dir", None) and output_dir:
                os.makedirs(output_dir, exist_ok=True)

            if utils.check_exists(
                output_base + ".md", getattr(effective_args, "force", False)
            ):
                continue

            audio = utils.load_audio(input, sr=self.sampling_rate)
            speech_array_indices = self._detect_voice_activity(audio, effective_args)
            transcribe_results = self._transcribe(
                input, audio, speech_array_indices, effective_args
            )

            output = output_base + ".srt"
            self._save_srt(output, transcribe_results, effective_args)
            logging.info(f"Transcribed {input} to {output}")
            self._save_md(output_base + ".md", output, input, effective_args)
            logging.info(f'Saved texts to {output_base + ".md"} to mark sentences')

    def _args_for_input(self, input):
        profile = self._profile_for_input(input)
        effective_args = copy(self.args)
        effective_args.transcribe_profile_name = profile.name

        for name, value in profile.overrides.items():
            if name == "prompt":
                value = self._merge_prompts(value, getattr(self.args, name, ""))
            elif not self._should_apply_profile_arg(name):
                continue
            setattr(effective_args, name, value)
        return effective_args

    def _profile_for_input(self, input):
        profile_name = getattr(
            self.args, "transcribe_profile", AUTO_TRANSCRIBE_PROFILE
        ) or AUTO_TRANSCRIBE_PROFILE
        if profile_name != AUTO_TRANSCRIBE_PROFILE:
            profile_name = TRANSCRIBE_PROFILE_ALIASES.get(
                self._normalize_profile_text(profile_name), profile_name
            )
            try:
                return TRANSCRIBE_PROFILE_BY_NAME[profile_name]
            except KeyError:
                valid_names = ", ".join(get_transcribe_profile_names())
                raise ValueError(
                    f"Unknown transcribe profile: {profile_name}. "
                    f"Valid profiles: {valid_names}"
                )

        input_text = self._normalize_profile_text(os.path.abspath(input))
        for profile in TRANSCRIBE_PROFILES:
            if profile.name == DEFAULT_TRANSCRIBE_PROFILE:
                continue
            for term in profile.match_terms:
                if self._normalize_profile_text(term) in input_text:
                    return profile
        return TRANSCRIBE_PROFILE_BY_NAME[DEFAULT_TRANSCRIBE_PROFILE]

    def _should_apply_profile_arg(self, name):
        current_value = getattr(self.args, name, None)
        default_value = DEFAULT_ARG_VALUES.get(name)
        return current_value is None or current_value == default_value

    def _merge_prompts(self, profile_prompt, user_prompt):
        if not profile_prompt:
            return user_prompt
        if not user_prompt:
            return profile_prompt
        if profile_prompt in user_prompt:
            return user_prompt
        return f"{profile_prompt}\n{user_prompt}"

    def _normalize_profile_text(self, text):
        return re.sub(r"[\s_\-]+", "", text.lower())

    def _transcription_inputs(self):
        inputs = []
        for input in self.args.inputs:
            if not os.path.isdir(input):
                inputs.append(input)
                continue

            media_files = [
                os.path.join(input, name)
                for name in sorted(os.listdir(input))
                if os.path.isfile(os.path.join(input, name))
                and self._is_transcribable_media(name)
            ]
            if media_files:
                logging.info(
                    f"Found {len(media_files)} media files in {input} for batch transcription"
                )
            else:
                logging.warning(f"No media files found in {input}")
            inputs.extend(media_files)
        return inputs

    def _is_transcribable_media(self, filename):
        filename = filename.lower()
        return utils.is_video(filename) or utils.is_audio(filename)

    def _output_base(self, input):
        name, _ = os.path.splitext(input)
        output_dir = getattr(self.args, "output_dir", None)
        if not output_dir:
            return name
        return os.path.join(output_dir, os.path.basename(name))

    def _detect_voice_activity(self, audio, args=None) -> List[SPEECH_ARRAY_INDEX]:
        """Detect segments that have voice activities"""
        args = args or self.args
        if getattr(args, "vad", "auto") in ("0", 0, False):
            return [{"start": 0, "end": len(audio)}]

        tic = time.time()
        if self.vad_model is None or self.detect_speech is None:
            # torch load limit https://github.com/pytorch/vision/issues/4156
            torch.hub._validate_not_a_forked_repo = lambda a, b, c: True
            self.vad_model, funcs = torch.hub.load(
                repo_or_dir="snakers4/silero-vad", model="silero_vad", trust_repo=True
            )

            self.detect_speech = funcs[0]

        speeches = self.detect_speech(
            audio, self.vad_model, sampling_rate=self.sampling_rate
        )

        # Remove too short segments
        speeches = utils.remove_short_segments(speeches, 1.0 * self.sampling_rate)

        # Expand to avoid to tight cut. You can tune the pad length
        speeches = utils.expand_segments(
            speeches, 0.2 * self.sampling_rate, 0.0 * self.sampling_rate, audio.shape[0]
        )

        # Merge very closed segments
        speeches = utils.merge_adjacent_segments(speeches, 0.5 * self.sampling_rate)

        logging.info(f"Done voice activity detection in {time.time() - tic:.1f} sec")
        return speeches if len(speeches) > 1 else [{"start": 0, "end": len(audio)}]

    def _transcribe(
        self,
        input: str,
        audio: np.ndarray,
        speech_array_indices: List[SPEECH_ARRAY_INDEX],
        args=None,
    ) -> List[Any]:
        args = args or self.args
        self._ensure_whisper_model(args)
        tic = time.time()
        res = (
            self.whisper_model.transcribe(
                audio, speech_array_indices, args.lang, args.prompt
            )
            if args.whisper_mode == WhisperMode.WHISPER.value
            or args.whisper_mode == WhisperMode.FASTER.value
            else self.whisper_model.transcribe(
                input, audio, speech_array_indices, args.lang, args.prompt
            )
        )

        logging.info(f"Done transcription in {time.time() - tic:.1f} sec")
        return res

    def _save_srt(self, output, transcribe_results, args=None):
        args = args or self.args
        subs = self.whisper_model.gen_srt(transcribe_results)
        with open(output, "wb") as f:
            f.write(srt.compose(subs).encode(args.encoding, "replace"))

    def _save_md(self, md_fn, srt_fn, video_fn, args=None):
        args = args or self.args
        with open(srt_fn, encoding=args.encoding) as f:
            subs = srt.parse(f.read())

        md = utils.MD(md_fn, args.encoding)
        md.clear()
        md.add_done_editing(False)
        md.add_video(self._relative_video_path(md_fn, video_fn))
        md.add(
            f"\nTexts generated from [{os.path.basename(srt_fn)}]({os.path.basename(srt_fn)})."
            "Mark the sentences to keep for autocut.\n"
            "The format is [subtitle_index,duration_in_second] subtitle context.\n\n"
        )

        for s in subs:
            sec = s.start.seconds
            pre = f"[{s.index},{sec // 60:02d}:{sec % 60:02d}]"
            md.add_task(False, f"{pre:11} {s.content.strip()}")
        md.write()

    def _relative_video_path(self, md_fn, video_fn):
        md_dir = os.path.dirname(os.path.abspath(md_fn)) or os.getcwd()
        video_abs = os.path.abspath(video_fn)
        try:
            video_path = os.path.relpath(video_abs, md_dir)
        except ValueError:
            video_path = video_abs
        return video_path.replace(os.sep, "/")
