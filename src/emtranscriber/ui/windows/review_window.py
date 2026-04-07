from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from emtranscriber.bootstrap import AppContainer
from emtranscriber.domain.entities.job import Job
from emtranscriber.domain.entities.job_context_hints import JobContextHints
from emtranscriber.domain.entities.transcript_document import TranscriptDocument


class ReviewWindow(QMainWindow):
    def __init__(self, container: AppContainer, job_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._container = container
        self._tr = container.translator
        self._job_id = job_id
        self._original_segment_text_by_id: dict[str, str] = {}
        self._original_speaker_name_by_key: dict[str, str] = {}

        self._job: Job | None = None
        self._source_audio_file: Path | None = None
        self._last_played_source: Path | None = None

        self._audio_backend_checked = False
        self._audio_backend_available = False
        self._audio_output: object | None = None
        self._media_player: object | None = None

        self.setWindowTitle(self._tr.t("review.title", job=job_id[:8]))
        self.resize(1200, 760)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        toolbar = QHBoxLayout()
        root.addLayout(toolbar)

        self.refresh_button = QPushButton(self._tr.t("review.refresh"))
        self.refresh_button.clicked.connect(self._load)
        toolbar.addWidget(self.refresh_button)

        self.save_segments_button = QPushButton(self._tr.t("review.save_segments"))
        self.save_segments_button.clicked.connect(self._save_segment_edits)
        toolbar.addWidget(self.save_segments_button)

        self.save_speakers_button = QPushButton(self._tr.t("review.save_speakers"))
        self.save_speakers_button.clicked.connect(self._save_speaker_mapping)
        toolbar.addWidget(self.save_speakers_button)

        self.export_button = QPushButton(self._tr.t("review.reexport"))
        self.export_button.clicked.connect(self._export)
        toolbar.addWidget(self.export_button)

        toolbar.addStretch(1)
        self.status_label = QLabel("")
        toolbar.addWidget(self.status_label)

        config_group = QGroupBox(self._tr.t("review.job_config"))
        config_layout = QVBoxLayout(config_group)
        self.job_config_view = QPlainTextEdit()
        self.job_config_view.setReadOnly(True)
        self.job_config_view.setMinimumHeight(210)
        self.job_config_view.setMaximumHeight(250)
        config_layout.addWidget(self.job_config_view)
        config_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        config_group.setMaximumHeight(300)
        root.addWidget(config_group, 0)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        self.segment_table = QTableWidget(0, 5)
        self.segment_table.setHorizontalHeaderLabels(
            [
                self._tr.t("review.table.play"),
                self._tr.t("review.table.start"),
                self._tr.t("review.table.end"),
                self._tr.t("review.table.speaker"),
                self._tr.t("review.table.text"),
            ]
        )
        self.segment_table.horizontalHeader().setStretchLastSection(True)
        splitter.addWidget(self.segment_table)

        speaker_panel = QWidget()
        speaker_layout = QVBoxLayout(speaker_panel)

        speaker_group = QGroupBox(self._tr.t("review.speaker_mapping"))
        speaker_group_layout = QVBoxLayout(speaker_group)
        speaker_layout.addWidget(speaker_group)

        self.speaker_table = QTableWidget(0, 2)
        self.speaker_table.setHorizontalHeaderLabels([self._tr.t("review.map_key"), self._tr.t("review.map_name")])
        self.speaker_table.horizontalHeader().setStretchLastSection(True)
        speaker_group_layout.addWidget(self.speaker_table)

        splitter.addWidget(speaker_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)

        self._load()

    def _load(self) -> None:
        self._job = self._container.job_repository.get_by_id(self._job_id)
        hints = self._container.job_repository.get_context_hints(self._job_id)
        self._populate_job_config(self._job, hints)
        self._source_audio_file = self._resolve_source_audio_file(self._job)

        document_error: str | None = None
        try:
            document = self._container.get_transcript_document_use_case.execute(self._job_id)
        except Exception as exc:  # noqa: BLE001
            document = TranscriptDocument(job_id=self._job_id)
            document_error = str(exc)

        self._populate_segments(document)
        self._populate_speakers(document)
        if document_error is None:
            self._set_transcript_actions_enabled(True)
            self.status_label.setText(
                self._tr.t("review.status_counts", segments=len(document.segments), speakers=len(document.speakers))
            )
            self.status_label.setToolTip("")
            return

        self._set_transcript_actions_enabled(False)
        self.status_label.setText(self._tr.t("review.status_pending_document"))
        self.status_label.setToolTip(document_error)

    def _set_transcript_actions_enabled(self, enabled: bool) -> None:
        self.save_segments_button.setEnabled(enabled)
        self.save_speakers_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)

    def _populate_job_config(self, job: Job | None, hints: JobContextHints | None) -> None:
        if job is None:
            self.job_config_view.setPlainText(self._tr.t("review.job_config_missing"))
            return

        project_name = self._resolve_project_name(job.project_id)
        selected_language = (job.language_selected or "auto").strip() or "auto"
        detected_language = (job.language_detected or "-").strip() or "-"
        speaker_mode = (job.speaker_count_mode or "auto").strip() or "auto"
        exact = str(job.exact_speakers) if job.exact_speakers is not None else "-"
        min_speakers = str(job.min_speakers) if job.min_speakers is not None else "-"
        max_speakers = str(job.max_speakers) if job.max_speakers is not None else "-"
        execution_time = self._format_duration(job.execution_duration_seconds)

        lines = [
            f"{self._tr.t('new_job.project')}: {project_name}",
            f"{self._tr.t('new_job.source_file')}: {job.source_file_path}",
            f"{self._tr.t('new_job.output_dir')}: {(job.artifacts_root_path or '-')}",
            f"{self._tr.t('new_job.language')}: selected={selected_language}, detected={detected_language}",
            f"{self._tr.t('new_job.asr_model')}: {(job.model_name or '-')}",
            f"{self._tr.t('new_job.device')}: {(job.device_used or '-')}",
            f"{self._tr.t('new_job.compute')}: {(job.compute_type or '-')}",
            f"{self._tr.t('review.execution_time')}: {execution_time}",
            f"{self._tr.t('new_job.speaker_group')}: {self._tr.t('new_job.mode')}={speaker_mode}, {self._tr.t('new_job.exact')}={exact}, {self._tr.t('new_job.min')}={min_speakers}, {self._tr.t('new_job.max')}={max_speakers}",
            f"{self._tr.t('new_job.hints_toggle')}: {'on' if hints is not None else 'off'}",
        ]

        if hints is None:
            lines.extend(
                [
                    f"{self._tr.t('new_job.domain_context')}: -",
                    f"{self._tr.t('new_job.hotwords')}: -",
                    f"{self._tr.t('new_job.glossary')}: -",
                    f"{self._tr.t('new_job.participants')}: -",
                    f"{self._tr.t('new_job.acronyms')}: -",
                    f"{self._tr.t('new_job.entities')}: -",
                ]
            )
        else:
            domain_context = (hints.domain_context or "").strip() or "-"
            lines.extend(
                [
                    f"{self._tr.t('new_job.domain_context')}:",
                    domain_context,
                    f"{self._tr.t('new_job.hotwords')}: {self._format_csv(hints.hotwords)}",
                    f"{self._tr.t('new_job.glossary')}: {self._format_csv(hints.glossary_terms)}",
                    f"{self._tr.t('new_job.participants')}: {self._format_csv(hints.expected_participants)}",
                    f"{self._tr.t('new_job.acronyms')}: {self._format_csv(hints.expected_acronyms)}",
                    f"{self._tr.t('new_job.entities')}: {self._format_csv(hints.expected_entities)}",
                ]
            )

        self.job_config_view.setPlainText("\n".join(lines))

    def _populate_segments(self, document: TranscriptDocument) -> None:
        self._original_segment_text_by_id = {segment.segment_id: segment.text for segment in document.segments}
        self.segment_table.setRowCount(len(document.segments))

        can_play = self._source_audio_file is not None and self._ensure_audio_backend()
        for row_idx, seg in enumerate(document.segments):
            buttons_widget = QWidget()
            buttons_layout = QHBoxLayout(buttons_widget)
            buttons_layout.setContentsMargins(2, 2, 2, 2)
            buttons_layout.setSpacing(2)

            play_button = QPushButton()
            play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
            play_button.setToolTip(self._tr.t("review.play_button"))
            play_button.setEnabled(can_play)

            stop_button = QPushButton()
            stop_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaStop))
            stop_button.setToolTip(self._tr.t("review.stop_button"))
            stop_button.setEnabled(can_play)

            if can_play:
                play_button.clicked.connect(lambda _checked=False, start_ms=seg.start_ms, end_ms=seg.end_ms: self._play_segment(start_ms, end_ms))
                stop_button.clicked.connect(self._stop_playback)
            else:
                tooltip_key = "review.play_unavailable" if self._source_audio_file is None else "review.play_backend_unavailable"
                play_button.setToolTip(self._tr.t(tooltip_key))
                stop_button.setToolTip(self._tr.t(tooltip_key))

            buttons_layout.addWidget(play_button)
            buttons_layout.addWidget(stop_button)
            self.segment_table.setCellWidget(row_idx, 0, buttons_widget)

            start_item = QTableWidgetItem(self._clock(seg.start_ms))
            start_item.setFlags(start_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            start_item.setData(Qt.ItemDataRole.UserRole, seg.segment_id)

            end_item = QTableWidgetItem(self._clock(seg.end_ms))
            end_item.setFlags(end_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            speaker_item = QTableWidgetItem(seg.speaker_name_resolved or seg.speaker_key or "")
            speaker_item.setFlags(speaker_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            text_item = QTableWidgetItem(seg.text)

            self.segment_table.setItem(row_idx, 1, start_item)
            self.segment_table.setItem(row_idx, 2, end_item)
            self.segment_table.setItem(row_idx, 3, speaker_item)
            self.segment_table.setItem(row_idx, 4, text_item)

        self.segment_table.resizeColumnsToContents()

    def _populate_speakers(self, document: TranscriptDocument) -> None:
        self._original_speaker_name_by_key = {
            speaker.speaker_key: (speaker.display_name or "")
            for speaker in document.speakers
        }
        self.speaker_table.setRowCount(len(document.speakers))
        for row_idx, speaker in enumerate(document.speakers):
            key_item = QTableWidgetItem(speaker.speaker_key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemFlag.ItemIsEditable)

            name_item = QTableWidgetItem(speaker.display_name or "")
            self.speaker_table.setItem(row_idx, 0, key_item)
            self.speaker_table.setItem(row_idx, 1, name_item)

        self.speaker_table.resizeColumnsToContents()

    def _save_segment_edits(self) -> None:
        updates: list[tuple[str, str]] = []
        for row in range(self.segment_table.rowCount()):
            start_item = self.segment_table.item(row, 1)
            text_item = self.segment_table.item(row, 4)
            if start_item is None or text_item is None:
                continue

            segment_id = start_item.data(Qt.ItemDataRole.UserRole)
            if not segment_id:
                continue

            segment_id = str(segment_id)
            current_text = text_item.text()
            original_text = self._original_segment_text_by_id.get(segment_id, "")
            if current_text == original_text:
                continue

            updates.append((segment_id, current_text))

        if not updates:
            return

        self._container.transcript_repository.update_segment_texts_bulk(updates)
        self._load()
        QMessageBox.information(self, self._tr.t("common.saved"), self._tr.t("review.saved_segments"))

    def _save_speaker_mapping(self) -> None:
        updates: list[tuple[str, str]] = []
        for row in range(self.speaker_table.rowCount()):
            key_item = self.speaker_table.item(row, 0)
            name_item = self.speaker_table.item(row, 1)
            if key_item is None or name_item is None:
                continue

            speaker_key = key_item.text()
            current_name = name_item.text().strip()
            original_name = self._original_speaker_name_by_key.get(speaker_key, "").strip()
            if current_name == original_name:
                continue

            updates.append((speaker_key, name_item.text()))

        if not updates:
            return

        self._container.transcript_repository.rename_speakers_bulk(self._job_id, updates)
        self._load()
        QMessageBox.information(self, self._tr.t("common.saved"), self._tr.t("review.saved_speakers"))

    def _export(self) -> None:
        outputs = self._container.export_transcript_use_case.execute(self._job_id)
        export_lines = "\n".join(f"{fmt}: {path}" for fmt, path in outputs.items())
        QMessageBox.information(self, self._tr.t("review.export_done"), export_lines)

    def _resolve_project_name(self, project_id: str) -> str:
        project = self._container.project_repository.get_by_id(project_id)
        if project is not None and project.name.strip():
            return project.name.strip()
        return project_id

    def _play_segment(self, start_ms: int, end_ms: int | None = None) -> None:
        if self._source_audio_file is None or not self._ensure_audio_backend():
            return

        try:
            if not self._source_audio_file.exists() or not self._source_audio_file.is_file():
                missing_path = str(self._source_audio_file)
                self._source_audio_file = None
                self._set_play_buttons_enabled(False)
                raise FileNotFoundError(missing_path)

            source_url = QUrl.fromLocalFile(str(self._source_audio_file))
            source_changed = self._last_played_source != self._source_audio_file

            if source_changed:
                assert self._media_player is not None
                self._media_player.stop()
                self._media_player.setSource(source_url)
                self._last_played_source = self._source_audio_file
                QTimer.singleShot(120, lambda: self._start_playback_from(start_ms, end_ms))
                return

            self._start_playback_from(start_ms, end_ms)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(
                self,
                self._tr.t("review.play_error_title"),
                self._tr.t("review.play_error_text", error=str(exc)),
            )

    def _start_playback_from(self, start_ms: int, end_ms: int | None = None) -> None:
        if self._media_player is None:
            return
        
        self._playback_end_ms = end_ms
        self._media_player.setPosition(max(int(start_ms), 0))
        self._media_player.play()

    def _stop_playback(self) -> None:
        if self._media_player is not None:
            self._media_player.stop()
            self._playback_end_ms = None

    def _ensure_audio_backend(self) -> bool:
        if self._audio_backend_checked:
            return self._audio_backend_available

        self._audio_backend_checked = True
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: WPS433

            self._audio_output = QAudioOutput(self)
            self._media_player = QMediaPlayer(self)
            self._media_player.setAudioOutput(self._audio_output)
            self._audio_output.setVolume(1.0)
            self._audio_backend_available = True
            
            self._playback_end_ms: int | None = None
            self._media_player.positionChanged.connect(self._on_player_position_changed)
        except Exception:
            self._audio_output = None
            self._media_player = None
            self._audio_backend_available = False

        return self._audio_backend_available

    def _on_player_position_changed(self, position_ms: int) -> None:
        if self._playback_end_ms is not None and position_ms >= self._playback_end_ms:
            if self._media_player is not None:
                self._media_player.stop()
            self._playback_end_ms = None

    def _resolve_source_audio_file(self, job: Job | None) -> Path | None:
        if job is None:
            return None

        for base_dir in self._candidate_job_base_dirs(job):
            source_file = self._find_source_file(base_dir / "source", job.source_file_path)
            if source_file is not None:
                return source_file

        return None

    def _candidate_job_base_dirs(self, job: Job) -> list[Path]:
        candidates: list[Path] = []

        if job.working_audio_path:
            working_path = Path(job.working_audio_path)
            if working_path.parent.name.lower() == "working":
                candidates.append(working_path.parent.parent)

        root = Path(job.artifacts_root_path).expanduser() if job.artifacts_root_path else self._container.app_paths.projects_dir
        em_root = root / "EMtranscriber"

        if job.created_at is not None and job.source_file_path:
            folder_name = job.created_at.strftime("%Y%m%d_%H%M%S")
            candidates.append(em_root / folder_name)

        candidates.append(em_root / job.project_id / job.job_id)
        candidates.append(root / job.project_id / "jobs" / job.job_id)
        candidates.append(root / job.project_id / job.job_id)
        candidates.append(em_root / job.job_id)

        deduped: list[Path] = []
        seen: set[str] = set()
        for item in candidates:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return deduped

    def _set_play_buttons_enabled(self, enabled: bool) -> None:
        if enabled:
            tooltip = ""
        elif self._source_audio_file is None:
            tooltip = self._tr.t("review.play_unavailable")
        else:
            tooltip = self._tr.t("review.play_backend_unavailable")

        for row_idx in range(self.segment_table.rowCount()):
            widget = self.segment_table.cellWidget(row_idx, 0)
            if isinstance(widget, QWidget) and widget.layout() is not None:
                layout = widget.layout()
                for idx in range(layout.count()):
                    item = layout.itemAt(idx)
                    if item and item.widget() and isinstance(item.widget(), QPushButton):
                        btn = item.widget()
                        btn.setEnabled(enabled)
                        # Avoid overwriting Stop button tooltip unless disabled
                        if not enabled:
                            btn.setToolTip(tooltip)
            elif isinstance(widget, QPushButton):
                widget.setEnabled(enabled)
                widget.setToolTip(tooltip)

    @staticmethod
    def _find_source_file(source_dir: Path, original_source_path: str) -> Path | None:
        if not source_dir.exists() or not source_dir.is_dir():
            return None

        preferred = source_dir / Path(original_source_path).name
        if preferred.exists() and preferred.is_file():
            return preferred

        media_exts = (".wav", ".mp3", ".m4a", ".mp4", ".mov", ".mkv", ".flac", ".aac", ".ogg", ".opus", ".webm")
        for candidate in sorted(source_dir.iterdir()):
            if candidate.is_file() and candidate.suffix.lower() in media_exts:
                return candidate

        for candidate in sorted(source_dir.iterdir()):
            if candidate.is_file():
                return candidate

        return None

    @staticmethod
    def _format_duration(total_seconds: int | None) -> str:
        if total_seconds is None:
            return "-"
        seconds = max(int(total_seconds), 0)
        hours, remainder = divmod(seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @staticmethod
    def _format_csv(values: list[str]) -> str:
        cleaned = [item.strip() for item in values if item and item.strip()]
        return ", ".join(cleaned) if cleaned else "-"

    @staticmethod
    def _clock(total_ms: int) -> str:
        minutes, ms_remaining = divmod(max(total_ms, 0), 60_000)
        seconds, milliseconds = divmod(ms_remaining, 1000)
        return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
