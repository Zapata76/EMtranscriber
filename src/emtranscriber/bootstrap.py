from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from emtranscriber.application.services.transcription_orchestrator import TranscriptionOrchestrator
from emtranscriber.application.use_cases.analyze_transcript import AnalyzeTranscriptUseCase
from emtranscriber.application.use_cases.create_job import CreateJobUseCase
from emtranscriber.application.use_cases.export_transcript import ExportTranscriptUseCase
from emtranscriber.application.use_cases.get_transcript_document import GetTranscriptDocumentUseCase
from emtranscriber.application.use_cases.list_jobs import ListJobsUseCase
from emtranscriber.application.use_cases.rename_speaker import RenameSpeakerUseCase
from emtranscriber.application.use_cases.update_segment_text import UpdateSegmentTextUseCase
from emtranscriber.domain.alignment.speaker_aligner import SpeakerAligner
from emtranscriber.domain.exports.transcript_exporter import TranscriptExporter
from emtranscriber.infrastructure.ai_analysis.provider_factory import build_analysis_provider
from emtranscriber.infrastructure.asr.faster_whisper_service_stub import FasterWhisperServiceStub
from emtranscriber.infrastructure.audio.audio_normalizer import AudioNormalizer
from emtranscriber.infrastructure.diarization.pyannote_service_stub import PyannoteDiarizationServiceStub
from emtranscriber.infrastructure.persistence.artifact_store import JobArtifactStore
from emtranscriber.infrastructure.persistence.job_repository import JobRepository
from emtranscriber.infrastructure.persistence.project_repository import ProjectRepository
from emtranscriber.infrastructure.persistence.sqlite import SQLiteDatabase
from emtranscriber.infrastructure.persistence.transcript_repository import TranscriptRepository
from emtranscriber.infrastructure.settings.app_settings import AppSettings
from emtranscriber.infrastructure.settings.settings_store import SettingsStore
from emtranscriber.shared.i18n import UiTranslator, resolve_ui_language
from emtranscriber.shared.logging_config import configure_logging
from emtranscriber.shared.paths import AppPaths, get_app_paths


_EXTERNAL_DLL_DIR_HANDLES: list[object] = []
_EXTERNAL_DLL_DIRS_SEEN: set[str] = set()
_CORE_ML_PACKAGES = ("faster_whisper", "ctranslate2", "torch", "torchaudio", "pyannote")


@dataclass(slots=True)
class AppContainer:
    app_paths: AppPaths
    settings_store: SettingsStore
    settings: AppSettings
    ui_language: str
    translator: UiTranslator
    pipeline_is_stub: bool
    is_first_run: bool
    project_repository: ProjectRepository
    job_repository: JobRepository
    transcript_repository: TranscriptRepository
    create_job_use_case: CreateJobUseCase
    list_jobs_use_case: ListJobsUseCase
    get_transcript_document_use_case: GetTranscriptDocumentUseCase
    rename_speaker_use_case: RenameSpeakerUseCase
    update_segment_text_use_case: UpdateSegmentTextUseCase
    export_transcript_use_case: ExportTranscriptUseCase
    analyze_transcript_use_case: AnalyzeTranscriptUseCase
    orchestrator: TranscriptionOrchestrator


def _build_pipeline_services(settings: AppSettings, logger, use_stub_pipeline: bool):
    logger.debug("Building pipeline services (stub=%s)", use_stub_pipeline)
    if use_stub_pipeline:
        logger.warning("Using stub ASR/diarization services due to EMTRANSCRIBER_ALLOW_STUB_PIPELINE=1")
        return FasterWhisperServiceStub(), PyannoteDiarizationServiceStub(), True

    if _is_frozen_app():
        _configure_frozen_ml_runtime()
        _inject_external_site_packages(logger)

    try:
        logger.debug("Importing faster-whisper service...")
        asr_module = import_module("emtranscriber.infrastructure.asr.faster_whisper_service")
        logger.debug("Importing pyannote service...")
        diar_module = import_module("emtranscriber.infrastructure.diarization.pyannote_service")
        
        logger.debug("Instantiating pipeline services...")
        asr_service = asr_module.FasterWhisperService(settings, logger)
        diar_service = diar_module.PyannoteDiarizationService(settings, logger)
        logger.info("Real pipeline services instantiated successfully")
        return asr_service, diar_service, False
    except ModuleNotFoundError as exc:
        logger.exception("A required ML module was not found")
        if _is_frozen_app():
            raise RuntimeError(
                "Real transcription modules are unavailable in this executable. "
                "Install ML runtime dependencies (python -m pip install --user -r requirements-ml.txt) "
                "and rebuild. Set EMTRANSCRIBER_ALLOW_STUB_PIPELINE=1 only for demo mode."
            ) from exc

        logger.warning("Real pipeline modules are unavailable (%s). Falling back to stubs.", exc)
        return FasterWhisperServiceStub(), PyannoteDiarizationServiceStub(), True
    except Exception:
        logger.exception("Failed to build real pipeline services. Falling back to stubs.")
        return FasterWhisperServiceStub(), PyannoteDiarizationServiceStub(), True


def _is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def _configure_frozen_ml_runtime() -> None:
    # In PyInstaller windowed mode stdout/stderr may be unavailable; disable hub/tqdm progress bars.
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TQDM_DISABLE", "1")


def _inject_external_site_packages(logger) -> None:
    _inject_external_stdlib_paths(logger)

    version_tag = f"Python{sys.version_info.major}{sys.version_info.minor}"
    candidates: list[Path] = []

    env_override = os.getenv("EMTRANSCRIBER_EXTERNAL_SITE_PACKAGES", "").strip()
    if env_override:
        for chunk in env_override.split(os.pathsep):
            chunk = chunk.strip()
            if chunk:
                candidates.append(Path(chunk))

    appdata = os.getenv("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "Python" / version_tag / "site-packages")

    global_roots = [
        Path(f"C:/Python{sys.version_info.major}{sys.version_info.minor}"),
        Path(f"C:/Python{sys.version_info.major}{sys.version_info.minor}-32"),
    ]
    for root in global_roots:
        candidates.append(root / "Lib" / "site-packages")
        candidates.append(root / "lib" / "site-packages")

    python_home = os.getenv("PYTHONHOME")
    if python_home:
        root = Path(python_home)
        candidates.append(root / "Lib" / "site-packages")
        candidates.append(root / "lib" / "site-packages")

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Python" / version_tag / "Lib" / "site-packages")
        candidates.append(Path(local_appdata) / "Programs" / version_tag / "Lib" / "site-packages")

    filtered_candidates: list[Path] = []
    for candidate in candidates:
        if _is_torchcodec_only_site_packages(candidate):
            logger.warning(
                "Skipping external site-packages path because it only contributes torchcodec and can destabilize runtime: %s",
                candidate,
            )
            continue
        filtered_candidates.append(candidate)

    added_paths = _add_paths_to_sys_path(filtered_candidates)
    for site_path in added_paths:
        _register_dll_directories(Path(site_path), logger)

    if added_paths:
        logger.info("Added external ML site-packages paths: %s", added_paths)


def _is_torchcodec_only_site_packages(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False

    has_torchcodec = _has_site_package(path, "torchcodec")
    if not has_torchcodec:
        return False

    has_core_ml = any(_has_site_package(path, package_name) for package_name in _CORE_ML_PACKAGES)
    return not has_core_ml


def _has_site_package(site_packages_path: Path, package_name: str) -> bool:
    if (site_packages_path / package_name).exists():
        return True

    pattern = f"{package_name}.*"
    return any(site_packages_path.glob(pattern))


def _inject_external_stdlib_paths(logger) -> None:
    version_tag = f"Python{sys.version_info.major}{sys.version_info.minor}"
    candidates: list[Path] = []

    env_override = os.getenv("EMTRANSCRIBER_EXTERNAL_STDLIB", "").strip()
    if env_override:
        for chunk in env_override.split(os.pathsep):
            chunk = chunk.strip()
            if chunk:
                candidates.append(Path(chunk))

    global_roots = [
        Path(f"C:/Python{sys.version_info.major}{sys.version_info.minor}"),
        Path(f"C:/Python{sys.version_info.major}{sys.version_info.minor}-32"),
    ]
    for root in global_roots:
        candidates.append(root / "Lib")
        candidates.append(root / "lib")

    python_home = os.getenv("PYTHONHOME")
    if python_home:
        root = Path(python_home)
        candidates.append(root / "Lib")
        candidates.append(root / "lib")

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Python" / version_tag / "Lib")
        candidates.append(Path(local_appdata) / "Programs" / version_tag / "Lib")

    added_paths = _add_paths_to_sys_path(candidates)
    if added_paths:
        logger.info("Added external Python stdlib paths: %s", added_paths)


def _add_paths_to_sys_path(candidates: list[Path]) -> list[str]:
    added: list[str] = []
    seen: set[str] = set()

    for path in candidates:
        normalized = str(path.resolve()) if path.exists() and path.is_dir() else ""
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)

        if normalized not in sys.path:
            sys.path.append(normalized)
            added.append(normalized)

    return added


def _register_dll_directories(site_packages_path: Path, logger) -> None:
    if not hasattr(os, "add_dll_directory"):
        return

    candidates = [
        site_packages_path,
        site_packages_path / "numpy.libs",
        site_packages_path / "onnxruntime" / "capi",
        site_packages_path / "ctranslate2",
        site_packages_path / "torch" / "lib",
    ]

    for candidate in candidates:
        if not candidate.exists() or not candidate.is_dir():
            continue

        normalized = str(candidate.resolve())
        if normalized in _EXTERNAL_DLL_DIRS_SEEN:
            continue

        try:
            handle = os.add_dll_directory(normalized)
            _EXTERNAL_DLL_DIR_HANDLES.append(handle)
            _EXTERNAL_DLL_DIRS_SEEN.add(normalized)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Unable to add DLL directory %s: %s", normalized, exc)


def build_container() -> AppContainer:
    try:
        app_paths = get_app_paths()
        settings_file_existed = app_paths.settings_file.exists()
        db_file_existed = app_paths.db_file.exists()
        app_paths.ensure()

        logger = configure_logging(app_paths.logs_dir)
        logger.info("--- Starting EMtranscriber session ---")
        logger.debug("App paths initialized: %s", app_paths)

        settings_store = SettingsStore(app_paths.settings_file)
        settings = settings_store.load()
        is_first_run = (not settings_file_existed) or (not db_file_existed)
        logger.debug("Settings loaded (is_first_run=%s)", is_first_run)

        ui_language = resolve_ui_language(settings.ui_language)
        translator = UiTranslator(ui_language)
        logger.debug("UI language resolved: %s", ui_language)

        database = SQLiteDatabase(app_paths)
        database.apply_migrations()
        logger.debug("Database initialized and migrations applied")

        project_repository = ProjectRepository(database)
        job_repository = JobRepository(database)
        transcript_repository = TranscriptRepository(database)
        logger.debug("Repositories initialized")

        artifact_store = JobArtifactStore(app_paths.projects_dir)
        logger.debug("Artifact store initialized")

        create_job_use_case = CreateJobUseCase(project_repository, job_repository)
        list_jobs_use_case = ListJobsUseCase(job_repository)
        get_transcript_document_use_case = GetTranscriptDocumentUseCase(transcript_repository)
        rename_speaker_use_case = RenameSpeakerUseCase(transcript_repository)
        update_segment_text_use_case = UpdateSegmentTextUseCase(transcript_repository)
        logger.debug("Core use cases initialized")

        exporter = TranscriptExporter()
        export_transcript_use_case = ExportTranscriptUseCase(
            job_repository=job_repository,
            transcript_repository=transcript_repository,
            artifact_store=artifact_store,
            exporter=exporter,
        )
        logger.debug("Export use case initialized")

        analyze_transcript_use_case = AnalyzeTranscriptUseCase(
            job_repository=job_repository,
            transcript_repository=transcript_repository,
            artifact_store=artifact_store,
            exporter=exporter,
            provider_factory=lambda: build_analysis_provider(settings, logger),
        )
        logger.debug("Analysis use case initialized")

        use_stub_pipeline = os.getenv("EMTRANSCRIBER_ALLOW_STUB_PIPELINE") == "1"
        asr_service, diarization_service, pipeline_is_stub = _build_pipeline_services(
            settings,
            logger,
            use_stub_pipeline,
        )

        orchestrator = TranscriptionOrchestrator(
            job_repository=job_repository,
            transcript_repository=transcript_repository,
            artifact_store=artifact_store,
            audio_normalizer=AudioNormalizer(logger),
            asr_service=asr_service,
            diarization_service=diarization_service,
            aligner=SpeakerAligner(),
            exporter=exporter,
            logger=logger,
        )
        logger.debug("Orchestrator initialized")

        container = AppContainer(
            app_paths=app_paths,
            settings_store=settings_store,
            settings=settings,
            ui_language=ui_language,
            translator=translator,
            pipeline_is_stub=pipeline_is_stub,
            is_first_run=is_first_run,
            project_repository=project_repository,
            job_repository=job_repository,
            transcript_repository=transcript_repository,
            create_job_use_case=create_job_use_case,
            list_jobs_use_case=list_jobs_use_case,
            get_transcript_document_use_case=get_transcript_document_use_case,
            rename_speaker_use_case=rename_speaker_use_case,
            update_segment_text_use_case=update_segment_text_use_case,
            export_transcript_use_case=export_transcript_use_case,
            analyze_transcript_use_case=analyze_transcript_use_case,
            orchestrator=orchestrator,
        )
        logger.info("Application container built successfully")
        return container
    except Exception:
        logger.exception("Failed to build application container")
        raise
