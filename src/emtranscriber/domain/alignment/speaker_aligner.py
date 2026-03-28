from __future__ import annotations

from collections import Counter
from uuid import uuid4

from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_document import TranscriptDocument
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment
from emtranscriber.domain.entities.transcript_word import TranscriptWord
from emtranscriber.domain.pipeline.asr_types import AsrResult, AsrSegment, AsrWord
from emtranscriber.domain.pipeline.diarization_types import DiarizationResult, SpeakerTurn


class SpeakerAligner:
    def __init__(self, merge_gap_threshold_s: float = 0.6) -> None:
        self._merge_gap_threshold_s = merge_gap_threshold_s

    def align(
        self,
        job_id: str,
        asr_result: AsrResult,
        diarization_result: DiarizationResult | None,
    ) -> TranscriptDocument:
        raw_turns = diarization_result.turns if diarization_result is not None else []

        raw_labels = self._collect_raw_labels(asr_result, raw_turns)
        if not raw_labels:
            raw_labels = ["SPEAKER_00"]

        speaker_map = {raw: f"SPEAKER_{idx:02d}" for idx, raw in enumerate(raw_labels)}
        speakers = [Speaker(speaker_key=value) for value in speaker_map.values()]

        provisional = [
            self._segment_from_asr(job_id, seg, idx, raw_turns, speaker_map)
            for idx, seg in enumerate(asr_result.segments)
        ]
        merged = self._merge_adjacent(provisional)

        for idx, segment in enumerate(merged):
            segment.order_index = idx
            segment.speaker_name_resolved = segment.speaker_key
            for w_idx, word in enumerate(segment.words):
                word.order_index = w_idx

        return TranscriptDocument(job_id=job_id, segments=merged, speakers=speakers)

    def _collect_raw_labels(self, asr_result: AsrResult, turns: list[SpeakerTurn]) -> list[str]:
        labels: list[str] = []

        for segment in asr_result.segments:
            assigned = self._dominant_speaker_for_segment(segment, turns)
            if assigned and assigned not in labels:
                labels.append(assigned)

        for turn in turns:
            if turn.speaker_label not in labels:
                labels.append(turn.speaker_label)

        return labels

    def _segment_from_asr(
        self,
        job_id: str,
        source: AsrSegment,
        order_index: int,
        turns: list[SpeakerTurn],
        speaker_map: dict[str, str],
    ) -> TranscriptSegment:
        dominant_raw = self._dominant_speaker_for_segment(source, turns)
        if dominant_raw is None:
            dominant_raw = next(iter(speaker_map))
        speaker_key = speaker_map[dominant_raw]

        words: list[TranscriptWord] = []
        for idx, asr_word in enumerate(source.words):
            raw_speaker = self._speaker_for_time((asr_word.start_s + asr_word.end_s) / 2.0, turns) or dominant_raw
            mapped = speaker_map.get(raw_speaker, speaker_key)
            words.append(
                TranscriptWord(
                    word_id=str(uuid4()),
                    segment_id="",
                    start_ms=self._to_ms(asr_word.start_s),
                    end_ms=self._to_ms(asr_word.end_s),
                    speaker_key=mapped,
                    text=asr_word.text.strip(),
                    probability=asr_word.probability,
                    order_index=idx,
                )
            )

        segment = TranscriptSegment(
            segment_id=str(uuid4()),
            job_id=job_id,
            start_ms=self._to_ms(source.start_s),
            end_ms=self._to_ms(source.end_s),
            speaker_key=speaker_key,
            speaker_name_resolved=speaker_key,
            text=source.text.strip(),
            source_type="merged",
            confidence=source.avg_logprob,
            order_index=order_index,
            words=words,
        )

        for word in segment.words:
            word.segment_id = segment.segment_id

        return segment

    def _dominant_speaker_for_segment(self, segment: AsrSegment, turns: list[SpeakerTurn]) -> str | None:
        if not turns:
            return None

        if segment.words:
            # Assign each word by midpoint to reduce boundary errors on overlaps.
            counts: Counter[str] = Counter()
            for word in segment.words:
                speaker = self._speaker_for_time((word.start_s + word.end_s) / 2.0, turns)
                if speaker:
                    counts[speaker] += 1
            if counts:
                return counts.most_common(1)[0][0]

        segment_mid = (segment.start_s + segment.end_s) / 2.0
        return self._speaker_for_time(segment_mid, turns)

    @staticmethod
    def _speaker_for_time(time_s: float, turns: list[SpeakerTurn]) -> str | None:
        for turn in turns:
            if turn.start_s <= time_s <= turn.end_s:
                return turn.speaker_label
        return None

    def _merge_adjacent(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        if not segments:
            return []

        merged: list[TranscriptSegment] = [segments[0]]
        for current in segments[1:]:
            previous = merged[-1]
            gap_s = (current.start_ms - previous.end_ms) / 1000.0

            if previous.speaker_key == current.speaker_key and gap_s <= self._merge_gap_threshold_s:
                previous.end_ms = current.end_ms
                previous.text = f"{previous.text} {current.text}".strip()
                offset = len(previous.words)
                for idx, word in enumerate(current.words):
                    word.order_index = offset + idx
                    word.segment_id = previous.segment_id
                    previous.words.append(word)
            else:
                merged.append(current)

        return merged

    @staticmethod
    def _to_ms(value_s: float) -> int:
        return int(round(value_s * 1000.0))
