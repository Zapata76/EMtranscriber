# EMtranscriber

`EMtranscriber` is a Windows-first desktop application for local/offline transcription with speaker diarization, manual speaker mapping, transcript review, and multi-format export.

## Implemented baseline

- Job lifecycle with background processing and cancellation
- Real pipeline orchestration:
  - audio preparation/normalization
  - ASR (`faster-whisper`)
  - diarization (`pyannote/speaker-diarization-community-1`)
  - alignment and merged transcript persistence
- Review editor:
  - transcript text editing
  - speaker rename mapping
  - re-export
- Export formats:
  - `md`
  - `txt`
  - `json`
  - `srt`
- Optional AI analysis module (external API, explicit opt-in):
  - provider abstraction
  - prompt/template editor
  - persisted analysis request/response artifacts
- Multilingual interface support:
  - supported selection: `en`, `es`, `de`, `fr`, `it`
  - default behavior: system language
  - fallback: English

## Agreed product decisions

- Default ASR model: `large-v3`
- pyannote provisioning for MVP: local model path in Settings
- Priority: real ASR + diarization pipeline before deeper UI refinements

## Development setup

### 1. Base app (UI + persistence)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
emtranscriber
```

### 2. Real ML pipeline (optional dependencies)

```powershell
pip install -e ".[ml]"
# or:
pip install -r requirements-ml.txt
```

If ML dependencies are missing, the app reports explicit setup errors when starting ASR/diarization.

## Runtime settings

Open `Settings` in app and configure:

- interface language (`en`, `es`, `de`, `fr`, `it`, or system default)
- interface theme (`light` or `dark`)
- default ASR model/device/compute
- optional local paths for ASR model directories
- pyannote local model path (MVP provisioning path)
- optional Hugging Face token for gated model access
- optional AI analysis provider endpoint/model/api key

## AI analysis module

AI analysis is disabled by default and never changes the canonical transcript.

To enable:

1. Open `Settings` -> `AI analysis`
2. Enable the module
3. Choose provider (`openai_compatible`)
4. Set endpoint, model, and API key
5. In `Review`, click `Analyze (AI)` and choose prompt/template

Artifacts are saved under each job directory in `analysis/`:

- `analysis_request.json`
- `analysis_response.json`
- `analysis_output.md`

## Project layout

```text
src/emtranscriber/
  ui/
  application/
  domain/
  infrastructure/
  shared/
migrations/
docs/
```

## Notes

- SQLite schema is initialized automatically from files in `migrations/`.
- Default runtime directory:
  - `%APPDATA%\EMtranscriber` on Windows
  - override with `EMTRANSCRIBER_HOME` environment variable

## pyannote access note

`pyannote/speaker-diarization-community-1` is a gated Hugging Face model.
Before diarization works, you must:

1. Accept model terms on Hugging Face (`pyannote/speaker-diarization-community-1` page).
2. Create a Hugging Face access token:
   - preferred: token type `Read`
   - if `Fine-grained`: enable `Read access to contents of all public gated repos you can access`
3. Paste token in app Settings (`Hugging Face token`) or configure a local model path.

If access is missing, diarization fails with `401/GatedRepoError` and job ends in `PARTIAL_SUCCESS`.

## License

EMtranscriber is released under the **GNU General Public License v3.0 (GPL-3.0)**.

- See [LICENSE](LICENSE) for details.
- In-app credits page also includes a direct license viewer.

## Packaging (Windows)

```powershell
python -m pip install --user -e .[build] --no-build-isolation
python -m pip install --user -r requirements-ml.txt
python scripts/prepare_branding_assets.py --icon-source "C:\\path\\to\\icon-image.png" --sidebar-source "C:\\path\\to\\sidebar-image.jpg"
.\\scripts\\build_windows.ps1 -Profile ui-shell
```

`ui-shell` now builds an executable that uses the **real** pipeline adapters and can transcribe audio,
loading ML runtime packages from local Python site-packages (for example `%APPDATA%\Python\Python310\site-packages`).

PyInstaller output is generated in `dist\EMtranscriber`.


