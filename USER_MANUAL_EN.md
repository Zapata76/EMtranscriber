# EMtranscriber User Manual (English)

This manual describes the current behavior of EMtranscriber based on the live codebase.
It is intended for end users and power users who want a complete view of the UI and runtime logic.

## 1. What EMtranscriber Does

EMtranscriber is a desktop app for offline transcription with:

- Automatic speech recognition (ASR) using faster-whisper
- Speaker diarization using pyannote
- Speaker-text alignment
- Transcript review and editing
- Export to `md`, `txt`, `json`, and `srt`

The app is designed around a sequential queue (one active job at a time), with an embedded processing panel and a review workflow.

## 2. Main Window Overview

The main window contains:

- Header label (`EMtranscriber - Offline Transcription`)
- Top toolbar
- Left sidebar image panel
- Jobs table
- Embedded processing panel (bottom)

### 2.1 Top Toolbar (Left to Right)

Current order:

1. `New Job`
2. `Refresh`
3. `Start Queue` or `Resume Queue` (dynamic label)
4. `Pause Queue`
5. `Sleep after queue` (toggle radio behavior, non-exclusive)
6. `Settings`
7. `Credits`

### 2.2 Sidebar Image Behavior

- Idle success image: `welcome`
- During active processing: image cycle changes every 2 minutes through:
  - `working1`, `working2`, `working3`, `working4`, `working5`, `tired`, `panic`, `desperate`, `fail`, `destruction`
- Queue end image:
  - `welcome` for success final states
  - `sad` for non-success endings

### 2.3 Jobs Table

Visible columns:

- `Project` (localized label may appear as `Registrazione` in Italian)
- `Status`
- `Created`
- `Completed`
- `Source`

Internal hidden columns exist for:

- `Job ID`
- `Project ID`

Other table behavior:

- Single row selection
- Read-only rows
- Double-click on row opens Review window
- Selection is preserved during refresh/progress updates when possible

## 3. Job Status Model

Possible statuses:

- `CREATED`
- `QUEUED`
- `PREPARING_AUDIO`
- `TRANSCRIBING`
- `DIARIZING`
- `ALIGNING`
- `READY_FOR_REVIEW`
- `COMPLETED`
- `PARTIAL_SUCCESS`
- `FAILED`
- `CANCELLED`

Queue display in table:

- While queued and running queue: `QUEUED (position/total)`
- While queued and paused queue: `QUEUED - PAUSED (position/total)`

## 4. Queue Logic and Controls

### 4.1 Core Queue Rules

- FIFO queue by `created_at` ascending for dispatching queued jobs
- Only one active job at a time
- Queue can be in `running` or `paused` state
- A queued job is started only when:
  - queue state is running
  - no active job exists
  - at least one queued job exists

### 4.2 `Start Queue` / `Resume Queue`

- Button text is dynamic:
  - `Start Queue` when queue is not paused
  - `Resume Queue` when queue is paused
- Enabled only when:
  - there is at least one queued job
  - there is no active job
- If clicked with no active and no queued jobs:
  - app shows info: no active or queued jobs

### 4.3 `Pause Queue`

- Enabled only when there is an active job
- If queue has active job, click shows a 3-option dialog:
  - `Yes`: pause queue after current job finishes
  - `No`: pause queue and cancel current job immediately
  - `Cancel`: do nothing
- If no active job but queued jobs exist (rare path), queue can still be paused by logic

### 4.4 `Sleep after queue`

- If enabled, after queue completion (no active worker and no queued jobs), app requests Windows sleep
- Uses Windows suspend API (`SetSuspendState`)
- If suspend call fails, app shows warning
- On non-Windows platforms, suspend call is not available

### 4.5 Startup Recovery of Interrupted Jobs

On app startup, jobs left in active processing states are moved back to `QUEUED`:

- `PREPARING_AUDIO`
- `TRANSCRIBING`
- `DIARIZING`
- `ALIGNING`

This enables automatic recovery after app or worker interruption.

## 5. Job Row Context Menu (Right Click)

Actions shown:

1. `Start`
2. `Open Review`
3. `Remove from queue`
4. Separator
5. `Delete Job`

Action availability logic:

- `Start`: enabled only for `CREATED` or `QUEUED` jobs that are not currently running
- `Open Review`: enabled for any selected job row
- `Remove from queue`: enabled only for `QUEUED`
- `Delete Job`: enabled only when job is not running

Visual behavior:

- Disabled items are shown with disabled menu styling

Action behavior:

- `Start`: enqueues selected job and attempts immediate start if queue allows
- `Open Review`: opens or focuses Review window for selected job
- `Remove from queue`: changes status to `CANCELLED`, marks completed, stores error message "Removed from queue by user."
- `Delete Job`: hard-deletes job data from DB (blocked while running)

### 5.1 Delete Job Database Scope

`Delete Job` removes:

- job row (`jobs`)
- context hints (`job_context_hints`)
- speakers (`speakers`)
- transcript segments (`transcript_segments`)
- transcript words (`transcript_words`)

If the job review window is open, it is also closed.

## 6. New Job Dialog

Window title: `New Job - EMtranscriber`

### 6.1 Fields

- `Source file` + `Browse`
- `Output folder` + `Browse`
- `Project`
- `Language`
- `ASR model`
- `Device`
- `Compute type`
- `Speaker count` group
- `Context hints (optional)` group

### 6.2 Source and Output

- Source file is mandatory
- Output folder is optional
  - If empty, defaults to source file parent folder
- If output path exists and is not a directory, creation fails

### 6.3 Language

Supported selection in dialog:

- `auto`
- `it`, `en`, `es`, `fr`, `de`

Context-hint language behavior:

- If language is not `auto`, it is passed as `language_hint` in context hints

### 6.4 ASR Model / Device / Compute

- Model choices: `small`, `medium`, `large-v3` plus additional configured path keys
- Device choices: `auto`, `cpu`, `gpu`
- Compute choices: `auto`, `float16`, `int8`

### 6.5 Speaker Count Modes

Mode selector values:

- `auto`
- `exact`
- `minmax`

Field activation logic:

- `exact` enables only exact speaker count
- `minmax` enables min and max
- `auto` disables numeric fields

Validation:

- In `minmax`, `min` must be less than or equal to `max`

### 6.6 Context Hints Group

Toggle:

- `Apply context hints to ASR`

When enabled, fields are active and saved:

- `Domain context`
- `Hotwords`
- `Glossary`
- `Expected participants`
- `Expected acronyms`
- `Expected entities`

Input parsing:

- CSV fields are parsed by comma
- Empty items are removed
- Whitespace is trimmed

If toggle is off:

- No context hints are saved for that job

### 6.7 Prefill Behavior

New Job dialog is prefilled from latest job when available:

- project name
- device
- compute type
- speaker mode and numeric values
- context hints toggle and values
- initial language heuristic:
  - uses previous selected language when valid
  - may use last detected language when previous selected language was `auto`

### 6.8 On Accept

Job creation flow:

1. Validate fields
2. Create project if needed
3. Create job (`CREATED`)
4. Save context hints (if enabled)
5. Refresh jobs table and select created job
6. Runtime requirements check
7. Enqueue created job

## 7. Runtime Requirements and Startup Behavior

### 7.1 First Run

On first run (missing settings file or DB), Settings dialog opens automatically with Hugging Face token field focused.

### 7.2 Runtime Checks

The app checks for modules and tools:

- `faster_whisper`
- `ctranslate2`
- `torch`
- `torchaudio`
- `pyannote.audio`
- `ffmpeg` (warning, non-critical)
- pyannote access configuration (token/path warning, non-critical)

If critical checks fail:

- Real transcription start is blocked
- User sees a detailed report
- App can offer launching `install_ml_runtime.ps1` if found

### 7.3 Stub Pipeline Warning

If app runs in stub mode, a warning is shown:

- Results are demo-only
- Not real transcription quality

## 8. Processing Panel (Embedded Bottom Panel)

UI elements:

- Title (`Processing Job - {job}`)
- Stage/status label
- Progress bar (0..100)
- Log text area with timestamps
- `Cancel` button

Behavior:

- Binds to active job when processing starts
- Appends initial config lines for job settings and hints
- Receives progress updates from worker events
- Adds heartbeat log if stage appears idle for >= 20s
- On finish/cancel/fail:
  - progress set to 100
  - cancel button disabled
  - total runtime log appended

Cancel behavior:

- Sends cancel request to worker
- Worker terminates child process if still running

## 9. Worker Model and Reliability Logic

Each job runs in an isolated subprocess:

- Frozen app: `EMtranscriber.exe --run-job <job_id>`
- Dev mode: `python -m emtranscriber.main --run-job <job_id>`

Parent UI process reads JSON-line events from child stdout:

- `progress`
- `finished`
- `error`

Benefits:

- Better crash containment per job
- Main app can remain responsive and continue queue control

## 10. Review Window

Window title: `Review Transcript - {job}`

Review is openable from:

- double click job row
- context menu `Open Review`
- auto-open after job end for statuses `COMPLETED`, `PARTIAL_SUCCESS`, `READY_FOR_REVIEW`

### 10.1 Pending Review Mode

If transcript document is not yet available:

- Review window still opens
- Job configuration panel is visible
- Segment/speaker data is empty
- Status label shows pending message
- Actions are disabled:
  - `Save segment edits`
  - `Save speaker mapping`
  - `Re-export`

### 10.2 Review Toolbar

- `Refresh`
- `Save segment edits`
- `Save speaker mapping`
- `Re-export`
- right-side status label (`Segments: X | Speakers: Y` or pending message)

### 10.3 Job Configuration Panel

Read-only summary includes:

- project
- source file
- output folder
- selected and detected language
- ASR model, device, compute
- execution time
- speaker mode config
- hints toggle state
- hints values

### 10.4 Segment Table

Columns:

- Play controls
- Start
- End
- Speaker
- Text

Behavior:

- Start/end/speaker are read-only
- Text is editable
- Play/stop buttons per segment

Save logic:

- Saves only changed segment rows
- Marks edited rows as `source_type='edited'` in DB

### 10.5 Speaker Mapping Table

Columns:

- Speaker key (read-only)
- Display name (editable)

Save logic:

- Saves only changed speaker rows
- Updates both speaker display names and resolved names in transcript segments

### 10.6 Audio Playback in Review

Playback requires:

- Source media file available in discovered `source` folder candidates
- PySide multimedia backend available in runtime

If unavailable:

- Play/stop disabled
- Tooltip explains reason

### 10.7 Re-export

`Re-export` regenerates and writes:

- `transcript.md`
- `transcript.txt`
- `transcript.json`
- `transcript.srt`

A result dialog shows output paths.

## 11. Settings Dialog

Window title: `Settings - EMtranscriber`

Current sections:

1. `Defaults`
2. `ASR model local paths (optional)`
3. `Diarization model provisioning`

Dialog details:

- Fixed-height window sized to content
- `OK` and `Cancel` buttons

### 11.1 Defaults Section

- Interface language:
  - System default
  - English
  - Spanish
  - German
  - French
  - Italian
- Interface theme:
  - Light
  - Dark
- Default ASR model
- Default device
- Default compute

### 11.2 ASR Local Paths Section

Optional local directories for:

- `small`
- `medium`
- `large-v3`

### 11.3 Diarization Provisioning Section

- pyannote local path
- Hugging Face token (password-masked)

### 11.4 Settings Save Effects

On `OK`:

- Settings are saved to `settings.json`
- Theme is applied immediately
- If language changed, app shows message to restart for full language refresh

## 12. Credits Dialog

Access via `Credits` button.

Contains:

- Author profile
- External links (GitHub, Website, LinkedIn)
- About section
- License info and `View License`

Link opening failures show warning dialog.

## 13. Output Files and Directory Layout

For each job, app creates directories:

- `base`
- `source`
- `working`
- `raw`
- `merged`
- `exports` (same as base)

Typical modern layout:

`<output_root>/EMtranscriber/<YYYYMMDD_HHMMSS>/`

Main files:

- `source/<original_filename>`
- `working/working_audio.wav`
- `raw/asr_output.json`
- `raw/diarization_output.json`
- `merged/transcript.json`
- `transcript.md`
- `transcript.txt`
- `transcript.json`
- `transcript.srt`

## 14. Data, Settings, and Logs

App data root resolution:

1. `EMTRANSCRIBER_HOME` env var (if set)
2. Frozen app default: `<exe_folder>/data`
3. Dev mode default on Windows: `%APPDATA%\\EMtranscriber`

Inside base dir:

- `emtranscriber.db`
- `settings.json`
- `logs/`
- `cache/`
- `models/`
- `projects/`

Logs:

- `logs/emtranscriber.log`
- `logs/emtranscriber-crash.log` (native crash diagnostics via `faulthandler`)

## 15. ASR and Diarization Hint Logic

Hints are transformed as follows:

- `Domain context`, `Expected participants`, `Glossary + Hotwords`, `Expected acronyms`, `Expected entities`, `Language hint`
  -> merged into one `initial_prompt` text (max 800 chars)
- `Hotwords`
  -> also passed directly as ASR hotwords string

Practical guidance:

- Use short, precise hint lists
- Put only critical terms in hotwords
- Keep domain context concise and relevant

## 16. Final Status Meanings

- `COMPLETED`: full pipeline success
- `PARTIAL_SUCCESS`: usable output, but with reduced quality/coverage (for example diarization failure, or stub mode)
- `FAILED`: unrecoverable runtime failure
- `CANCELLED`: user cancellation

## 17. Common User Scenarios

### 17.1 "Start Queue does nothing"

Expected when:

- no queued jobs exist
- an active job is already running
- runtime critical checks are failing

### 17.2 "Open Review opens but no transcript"

This is valid pending mode:

- job config is visible
- transcript actions are disabled until transcript data is available

### 17.3 "Remove from queue is disabled"

Expected unless selected job status is `QUEUED`.

### 17.4 "Delete Job is disabled"

Expected for running jobs.

## 18. Known UI Behavior Notes

- Jobs are displayed by newest created first (`created_at DESC`).
- Queue order is FIFO by creation time among queued items.
- Double-click on any job row opens Review window.
- Right-click menu actions are state-aware.
- On app close with active workers, app asks for confirmation and may refuse close if worker shutdown is still in progress.

---

Manual generated for current codebase behavior.
