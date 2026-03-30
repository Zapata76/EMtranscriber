from __future__ import annotations

from collections import defaultdict

from emtranscriber.domain.entities.speaker import Speaker
from emtranscriber.domain.entities.transcript_document import TranscriptDocument
from emtranscriber.domain.entities.transcript_segment import TranscriptSegment
from emtranscriber.domain.entities.transcript_word import TranscriptWord
from emtranscriber.infrastructure.persistence.sqlite import SQLiteDatabase


class TranscriptRepository:
    def __init__(self, database: SQLiteDatabase) -> None:
        self._database = database

    def replace_transcript(self, job_id: str, segments: list[TranscriptSegment], speakers: list[Speaker]) -> None:
        with self._database.connect() as conn:
            conn.execute(
                "DELETE FROM transcript_words WHERE segment_id IN (SELECT segment_id FROM transcript_segments WHERE job_id = ?)",
                (job_id,),
            )
            conn.execute("DELETE FROM transcript_segments WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM speakers WHERE job_id = ?", (job_id,))

            for speaker in speakers:
                conn.execute(
                    """
                    INSERT INTO speakers(
                      speaker_key,
                      job_id,
                      display_name,
                      color_tag,
                      is_manually_named,
                      notes
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        speaker.speaker_key,
                        job_id,
                        speaker.display_name,
                        speaker.color_tag,
                        1 if speaker.is_manually_named else 0,
                        speaker.notes,
                    ),
                )

            for segment in segments:
                conn.execute(
                    """
                    INSERT INTO transcript_segments(
                      segment_id,
                      job_id,
                      start_ms,
                      end_ms,
                      speaker_key,
                      speaker_name_resolved,
                      text,
                      source_type,
                      confidence,
                      order_index
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        segment.segment_id,
                        job_id,
                        segment.start_ms,
                        segment.end_ms,
                        segment.speaker_key,
                        segment.speaker_name_resolved,
                        segment.text,
                        segment.source_type,
                        segment.confidence,
                        segment.order_index,
                    ),
                )

                for word in segment.words:
                    conn.execute(
                        """
                        INSERT INTO transcript_words(
                          word_id,
                          segment_id,
                          start_ms,
                          end_ms,
                          speaker_key,
                          text,
                          probability,
                          order_index
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            word.word_id,
                            segment.segment_id,
                            word.start_ms,
                            word.end_ms,
                            word.speaker_key,
                            word.text,
                            word.probability,
                            word.order_index,
                        ),
                    )

            conn.commit()

    def load_document(self, job_id: str) -> TranscriptDocument:
        with self._database.connect() as conn:
            speaker_rows = conn.execute(
                "SELECT * FROM speakers WHERE job_id = ? ORDER BY speaker_key",
                (job_id,),
            ).fetchall()
            segment_rows = conn.execute(
                "SELECT * FROM transcript_segments WHERE job_id = ? ORDER BY order_index",
                (job_id,),
            ).fetchall()
            word_rows = conn.execute(
                """
                SELECT w.*
                FROM transcript_words w
                JOIN transcript_segments s ON s.segment_id = w.segment_id
                WHERE s.job_id = ?
                ORDER BY w.order_index
                """,
                (job_id,),
            ).fetchall()

        words_by_segment: dict[str, list[TranscriptWord]] = defaultdict(list)
        for row in word_rows:
            words_by_segment[row["segment_id"]].append(
                TranscriptWord(
                    word_id=row["word_id"],
                    segment_id=row["segment_id"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                    speaker_key=row["speaker_key"],
                    text=row["text"],
                    probability=row["probability"],
                    order_index=row["order_index"],
                )
            )

        segments = [
            TranscriptSegment(
                segment_id=row["segment_id"],
                job_id=row["job_id"],
                start_ms=row["start_ms"],
                end_ms=row["end_ms"],
                speaker_key=row["speaker_key"],
                speaker_name_resolved=row["speaker_name_resolved"],
                text=row["text"],
                source_type=row["source_type"],
                confidence=row["confidence"],
                order_index=row["order_index"],
                words=words_by_segment.get(row["segment_id"], []),
            )
            for row in segment_rows
        ]

        speakers = [
            Speaker(
                speaker_key=row["speaker_key"],
                display_name=row["display_name"],
                color_tag=row["color_tag"],
                is_manually_named=bool(row["is_manually_named"]),
                notes=row["notes"],
            )
            for row in speaker_rows
        ]

        return TranscriptDocument(job_id=job_id, segments=segments, speakers=speakers)

    def rename_speaker(self, job_id: str, speaker_key: str, display_name: str) -> None:
        self.rename_speakers_bulk(job_id, [(speaker_key, display_name)])

    def rename_speakers_bulk(self, job_id: str, updates: list[tuple[str, str]]) -> None:
        normalized_updates: list[tuple[str, str | None, int, str]] = []
        for speaker_key, display_name in updates:
            value = (display_name or "").strip()
            resolved_name = value if value else speaker_key
            normalized_updates.append((value if value else None, 1 if value else 0, speaker_key, resolved_name))

        if not normalized_updates:
            return

        with self._database.connect() as conn:
            conn.executemany(
                """
                UPDATE speakers
                SET
                  display_name = ?,
                  is_manually_named = ?
                WHERE job_id = ? AND speaker_key = ?
                """,
                [(display_name, manual, job_id, speaker_key) for display_name, manual, speaker_key, _resolved_name in normalized_updates],
            )
            conn.executemany(
                """
                UPDATE transcript_segments
                SET speaker_name_resolved = ?
                WHERE job_id = ? AND speaker_key = ?
                """,
                [(resolved_name, job_id, speaker_key) for _display_name, _manual, speaker_key, resolved_name in normalized_updates],
            )
            conn.commit()

    def update_segment_text(self, segment_id: str, text: str) -> None:
        self.update_segment_texts_bulk([(segment_id, text)])

    def update_segment_texts_bulk(self, updates: list[tuple[str, str]]) -> None:
        if not updates:
            return

        with self._database.connect() as conn:
            conn.executemany(
                """
                UPDATE transcript_segments
                SET text = ?, source_type = 'edited'
                WHERE segment_id = ?
                """,
                [(text, segment_id) for segment_id, text in updates],
            )
            conn.commit()
