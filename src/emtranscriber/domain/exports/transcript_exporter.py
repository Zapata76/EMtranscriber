from __future__ import annotations

import json
from datetime import datetime

from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.entities.transcript_document import TranscriptDocument


class TranscriptExporter:
    def build_markdown(self, job: Job, document: TranscriptDocument) -> str:
        speakers = sorted(document.speakers, key=lambda sp: sp.speaker_key)
        lines = [
            "# Transcript",
            "",
            f"- Source file: {job.source_file_path}",
            f"- Language: {job.language_detected or job.language_selected or 'unknown'}",
            f"- Generated at: {datetime.now().isoformat()}",
            "",
            "## Speakers",
        ]

        for speaker in speakers:
            lines.append(f"- {speaker.speaker_key} -> {speaker.resolved_name}")

        lines.extend(["", "## Transcript", ""])

        for segment in document.segments:
            lines.append(
                f"### [{self._clock(segment.start_ms)} - {self._clock(segment.end_ms)}] "
                f"{segment.speaker_name_resolved or segment.speaker_key or 'Speaker'}"
            )
            lines.append(segment.text)
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def build_txt(self, document: TranscriptDocument) -> str:
        lines = []
        for segment in document.segments:
            lines.append(
                f"[{self._clock(segment.start_ms)} - {self._clock(segment.end_ms)}] "
                f"{segment.speaker_name_resolved or segment.speaker_key or 'Speaker'}: {segment.text}"
            )
        return "\n".join(lines).rstrip() + "\n"

    def build_json(self, job: Job, document: TranscriptDocument) -> dict:
        return {
            "job": {
                "job_id": job.job_id,
                "source_file_path": job.source_file_path,
                "language_detected": job.language_detected,
                "model_name": job.model_name,
                "created_at": job.created_at.isoformat(),
            },
            "speakers": [
                {
                    "speaker_key": sp.speaker_key,
                    "display_name": sp.resolved_name,
                }
                for sp in document.speakers
            ],
            "segments": [
                {
                    "start_ms": segment.start_ms,
                    "end_ms": segment.end_ms,
                    "speaker_key": segment.speaker_key,
                    "speaker_name": segment.speaker_name_resolved,
                    "text": segment.text,
                }
                for segment in document.segments
            ],
        }

    def build_srt(self, document: TranscriptDocument) -> str:
        blocks: list[str] = []
        for idx, segment in enumerate(document.segments, start=1):
            blocks.append(str(idx))
            blocks.append(f"{self._srt_clock(segment.start_ms)} --> {self._srt_clock(segment.end_ms)}")
            blocks.append(f"{segment.speaker_name_resolved or segment.speaker_key or 'Speaker'}: {segment.text}")
            blocks.append("")
        return "\n".join(blocks).rstrip() + "\n"

    @staticmethod
    def to_json_text(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _clock(total_ms: int) -> str:
        minutes, ms_remaining = divmod(max(total_ms, 0), 60_000)
        seconds, milliseconds = divmod(ms_remaining, 1000)
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

    @staticmethod
    def _srt_clock(total_ms: int) -> str:
        total_ms = max(total_ms, 0)
        hours, rem = divmod(total_ms, 3_600_000)
        minutes, rem = divmod(rem, 60_000)
        seconds, milliseconds = divmod(rem, 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
