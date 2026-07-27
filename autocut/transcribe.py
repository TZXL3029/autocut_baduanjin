import logging
import os
import re
import time
from dataclasses import dataclass
from typing import List, Any, Sequence

import numpy as np
import srt
import torch

from . import utils, whisper_model
from .type import WhisperMode, SPEECH_ARRAY_INDEX


@dataclass(frozen=True)
class VadParameters:
    remove_short_sec: float
    expand_head_sec: float
    expand_tail_sec: float
    merge_gap_sec: float


@dataclass(frozen=True)
class TranscribeProfile:
    name: str
    match_terms: Sequence[str]
    vad_parameters: VadParameters


DEFAULT_VAD_PARAMETERS = VadParameters(
    remove_short_sec=1.0,
    expand_head_sec=0.2,
    expand_tail_sec=0.0,
    merge_gap_sec=0.5,
)

TRANSCRIBE_PROFILES = [
    TranscribeProfile(
        name="default",
        match_terms=(),
        vad_parameters=DEFAULT_VAD_PARAMETERS,
    ),
    TranscribeProfile(
        name="baduanjin",
        match_terms=("八段锦", "八段錦", "baduanjin", "ba duan jin", "bdj"),
        vad_parameters=VadParameters(
            remove_short_sec=0.3,
            expand_head_sec=0.2,
            expand_tail_sec=0.1,
            merge_gap_sec=0.7,
        ),
    ),
    TranscribeProfile(
        name="taiji",
        match_terms=("太极拳", "太極拳", "太极", "太極", "taiji", "taijiquan"),
        vad_parameters=VadParameters(
            remove_short_sec=0.2,
            expand_head_sec=0.2,
            expand_tail_sec=0.1,
            merge_gap_sec=0.5,
        ),
    ),
]

TRANSCRIBE_PROFILE_BY_NAME = {
    profile.name: profile for profile in TRANSCRIBE_PROFILES
}


def register_transcribe_profile(profile: TranscribeProfile) -> None:
    for index, existing in enumerate(TRANSCRIBE_PROFILES):
        if existing.name == profile.name:
            TRANSCRIBE_PROFILES[index] = profile
            break
    else:
        TRANSCRIBE_PROFILES.append(profile)
    TRANSCRIBE_PROFILE_BY_NAME[profile.name] = profile


class Transcribe:
    def __init__(self, args):
        self.args = args
        self.sampling_rate = 16000
        self.whisper_model = None
        self.vad_model = None
        self.detect_speech = None

        tic = time.time()
        if self.whisper_model is None:
            if self.args.whisper_mode == WhisperMode.WHISPER.value:
                self.whisper_model = whisper_model.WhisperModel(self.sampling_rate)
                self.whisper_model.load(self.args.whisper_model, self.args.device)
            elif self.args.whisper_mode == WhisperMode.OPENAI.value:
                self.whisper_model = whisper_model.OpenAIModel(
                    self.args.openai_rpm, self.sampling_rate
                )
                self.whisper_model.load()
            elif self.args.whisper_mode == WhisperMode.FASTER.value:
                self.whisper_model = whisper_model.FasterWhisperModel(
                    self.sampling_rate
                )
                self.whisper_model.load(self.args.whisper_model, self.args.device)
        logging.info(f"Done Init model in {time.time() - tic:.1f} sec")

    def run(self):
        for input in self._transcription_inputs():
            profile = self._profile_for_input(input)
            logging.info(f"Transcribing {input} with profile {profile.name}")
            output_base = self._output_base(input)
            output_dir = os.path.dirname(output_base)
            if getattr(self.args, "output_dir", None) and output_dir:
                os.makedirs(output_dir, exist_ok=True)

            if utils.check_exists(output_base + ".md", self.args.force):
                continue

            audio = utils.load_audio(input, sr=self.sampling_rate)
            speech_array_indices = self._detect_voice_activity(
                audio, profile.vad_parameters
            )
            transcribe_results = self._transcribe(input, audio, speech_array_indices)

            output = output_base + ".srt"
            self._save_srt(output, transcribe_results)
            logging.info(f"Transcribed {input} to {output}")
            self._save_md(output_base + ".md", output, input)
            logging.info(f'Saved texts to {output_base + ".md"} to mark sentences')

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

    def _profile_for_input(self, input) -> TranscribeProfile:
        explicit_profile = self._explicit_profile()
        if explicit_profile is not None:
            return explicit_profile

        input_text = self._normalize_profile_text(os.path.abspath(input))
        for profile in TRANSCRIBE_PROFILES:
            if profile.name == "default":
                continue
            for term in profile.match_terms:
                if self._normalize_profile_text(term) in input_text:
                    return profile
        return TRANSCRIBE_PROFILE_BY_NAME["default"]

    def _explicit_profile(self):
        if getattr(self.args, "baduanjin", False):
            return TRANSCRIBE_PROFILE_BY_NAME["baduanjin"]
        if getattr(self.args, "taiji", False):
            return TRANSCRIBE_PROFILE_BY_NAME["taiji"]
        return None

    def _normalize_profile_text(self, text):
        return re.sub(r"[\s_\-]+", "", text.lower())

    def _detect_voice_activity(
        self, audio, vad_parameters: VadParameters = DEFAULT_VAD_PARAMETERS
    ) -> List[SPEECH_ARRAY_INDEX]:
        """Detect segments that have voice activities"""
        if self.args.vad == "0":
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
        speeches = utils.remove_short_segments(
            speeches, vad_parameters.remove_short_sec * self.sampling_rate
        )

        # Expand to avoid to tight cut. You can tune the pad length
        speeches = utils.expand_segments(
            speeches,
            vad_parameters.expand_head_sec * self.sampling_rate,
            vad_parameters.expand_tail_sec * self.sampling_rate,
            audio.shape[0],
        )

        # Merge very closed segments
        speeches = utils.merge_adjacent_segments(
            speeches, vad_parameters.merge_gap_sec * self.sampling_rate
        )

        logging.info(f"Done voice activity detection in {time.time() - tic:.1f} sec")
        return speeches if len(speeches) > 1 else [{"start": 0, "end": len(audio)}]

    def _transcribe(
        self,
        input: str,
        audio: np.ndarray,
        speech_array_indices: List[SPEECH_ARRAY_INDEX],
    ) -> List[Any]:
        tic = time.time()
        res = (
            self.whisper_model.transcribe(
                audio, speech_array_indices, self.args.lang, self.args.prompt
            )
            if self.args.whisper_mode == WhisperMode.WHISPER.value
            or self.args.whisper_mode == WhisperMode.FASTER.value
            else self.whisper_model.transcribe(
                input, audio, speech_array_indices, self.args.lang, self.args.prompt
            )
        )

        logging.info(f"Done transcription in {time.time() - tic:.1f} sec")
        return res

    def _save_srt(self, output, transcribe_results):
        subs = self.whisper_model.gen_srt(transcribe_results)
        with open(output, "wb") as f:
            f.write(srt.compose(subs).encode(self.args.encoding, "replace"))

    def _save_md(self, md_fn, srt_fn, video_fn):
        with open(srt_fn, encoding=self.args.encoding) as f:
            subs = srt.parse(f.read())

        md = utils.MD(md_fn, self.args.encoding)
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
