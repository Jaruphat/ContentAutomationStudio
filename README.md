# Content Automation Studio

A local-first application for AI-assisted storyboard creation, image/video generation via ComfyUI workflows, and automated video editing. Content Automation Studio turns a creative brief or plot into structured scenes, shots, compiled prompts, generation jobs, reviewed takes, a Timeline Manifest, and an automated review render.

---

## Architecture Overview

```
+------------------+         HTTP/REST         +------------------+
|                  | <-----------------------> |                  |
|  React + TS      |    localhost:8001/api      |  Python FastAPI  |
|  (Vite, port     |                           |  (Uvicorn, 8001) |
|   5173)          |                           |                  |
+------------------+                           +--------+---------+
                                                        |
                                               +--------+---------+
                                               |     SQLite        |
                                               |   (cas.db)        |
                                               +------------------+
```

- **Frontend**: React 19 + TypeScript, bundled with Vite, styled with Tailwind CSS v4. Uses React Router for page navigation, TanStack React Query for server state, and Axios for HTTP requests.
- **Backend**: Python FastAPI with SQLAlchemy ORM over SQLite. Modular routers for projects, scenes, shots, story, workflows, generation, review, timeline, and exports. Services layer handles prompt compilation, workflow registry, queue management, ComfyUI adapter (mock and real providers), timeline assembly, and export generation.
- **Database**: SQLite file (`backend/data/cas.db`) for all MVP metadata. No external database server required. Schema changes that only add columns are applied automatically at startup.
- **ComfyUI boundary**: business logic depends only on the `ComfyUIProvider` interface. Node IDs appear solely in a workflow record's `parameter_mapping`, so re-exporting H3 with different node numbering is a mapping fix, not a code change.

---

## Prerequisites

| Requirement   | Version  | Notes                                    |
|---------------|----------|------------------------------------------|
| Python        | 3.11+    | Required for backend                     |
| Node.js       | 18+      | Required for frontend                    |
| npm           | 9+       | Comes with Node.js                       |
| FFmpeg        | Optional | Enables the review render and MP4 mock takes; without it those steps report why they were skipped |

---

## Setup Instructions

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate    # Windows
# source .venv/bin/activate  # Linux/macOS
pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

### Configuration

Copy `.env.example` to `.env` in the project root and adjust as needed:

```bash
cp .env.example .env
```

| Variable               | Default                 | Description                                                                 |
|------------------------|-------------------------|-----------------------------------------------------------------------------|
| `COMFYUI_PROVIDER`     | `mock`                  | `mock` for deterministic placeholders, `real` to drive a live ComfyUI        |
| `COMFYUI_URL`          | `http://127.0.0.1:8000` | ComfyUI instance URL (used when provider is `real`)                          |
| `CAS_DATA_DIR`         | `backend/data`          | Base directory for the database, workflows, snapshots, media and exports    |
| `CAS_DISABLE_QUEUE`    | unset                   | Set to `1` to run the API without the background generation worker          |
| `CAS_MOCK_QUEUED_SEC`  | `1.0`                   | Seconds a mock job stays Queued (lower it to speed up the e2e run)          |
| `CAS_MOCK_RUNNING_SEC` | `2.0`                   | Seconds a mock job stays Running                                            |

All runtime data lives under `CAS_DATA_DIR` and is git-ignored:

```
backend/data/
├─ cas.db           SQLite metadata
├─ workflows/       imported ComfyUI API-format JSON
├─ snapshots/       exact graph submitted per job (reproducibility)
├─ generated/       provider outputs (mock placeholders or real downloads)
└─ exports/<project>/  review.mp4, concat list and per-shot segments
```

---

## Running the Application

### One-click start on Windows

Double-click `start-dev.bat` in the project root. It checks ComfyUI on port 8000, starts the backend on 8001 and frontend on 5173, waits until both are ready, then opens the app in Chrome. Running it again is safe: services that are already listening are not duplicated.

Double-click `stop-dev.bat` to stop only the development services listening on ports 8001 and 5173. It does not stop ComfyUI.

Open two terminal windows:

### 1. Start the Backend

```bash
cd backend
# Mock mode (default - no ComfyUI required):
COMFYUI_PROVIDER=mock python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# Real ComfyUI mode (requires running ComfyUI instance):
COMFYUI_PROVIDER=real COMFYUI_URL=http://127.0.0.1:8000 python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

The API server will be available at `http://localhost:8001`. ComfyUI uses `http://127.0.0.1:8000` on this workstation.

### 2. Start the Frontend

```bash
cd frontend
npm run dev
```

Then open **http://localhost:5173** in your browser.

---

## Running Tests

### Backend Unit Tests

```bash
cd backend
python -m pytest tests/ -q
```

869 tests covering the data model, prompt compiler, workflow registry and
mapping, workflow format detection, node/model inventory and candidate mapping
derivation, dependency checking, immutable generation-run grouping, persisted
queue pause/restart state, reference conditioning and provenance, job payload
construction, queue state and retry policy, error classification, the review
API, additive schema migration, and the FFmpeg render. The analysis heuristics
are also exercised against the three real ComfyUI exports in
`workflows/source/ui/`, skipping if absent.
Tests redirect `CAS_DATA_DIR` to a temporary directory, so running them leaves
no files in your working tree. Render tests that shell out to FFmpeg skip
themselves automatically when it is not installed.

### Backend Lint

```bash
cd backend
python -m ruff check app/ tests/
```

### Frontend Lint and Typecheck

```bash
cd frontend
npm run lint     # oxlint
npx tsc -b       # typecheck
```

### Frontend Production Build

```bash
cd frontend
npm run build
```

### End-to-End Test (requires the backend running)

Drives the whole vertical slice over HTTP against a running server: workflow
import and mapping, project and Story Bible creation, 3 scenes with 9 shots,
preflight, generation, take approval, timeline build, render plan, every
export, and a persistence re-check.

```bash
cd backend
# In another terminal, start the server first. Short mock timings keep the run brief:
CAS_MOCK_QUEUED_SEC=0.2 CAS_MOCK_RUNNING_SEC=0.3 python -m uvicorn app.main:app --port 8001

python test_e2e.py
```

---

## Project Structure

```
ContentAutomationStudio/
|-- CLAUDE.md                          # Claude Code project context
|-- README.md                          # This file
|-- .env.example
|-- .gitignore
|
|-- docs/
|   |-- PRD_Content_Automation_Studio_v0.1.md / .docx
|   |-- PRD_Content_Automation_Studio_v0.2.md / .docx   # Source of truth
|   |-- ComfyUI_Workflow_Integration.md            # Adapter + supplied-workflow findings
|   +-- build_prd_docx.py
|
|-- workflows/
|   +-- source/
|      |-- ui/                         # Supplied ComfyUI editor graphs (read-only, checksummed)
|      +-- api/                        # API-format exports (submittable)
|
|-- backend/
|   |-- requirements.txt
|   |-- pytest.ini
|   |-- test_e2e.py                    # End-to-end integration test (HTTP)
|   |-- data/                          # Runtime data, git-ignored (see Configuration)
|   |-- app/
|   |   |-- main.py                    # FastAPI entry point, lifespan, health
|   |   |-- paths.py                   # Single source of truth for runtime paths
|   |   |-- database.py                # Engine, session, additive migrations
|   |   |-- models.py                  # ORM models
|   |   |-- schemas.py                 # Pydantic request/response schemas
|   |   |-- routers/
|   |   |   |-- projects.py            # Project CRUD
|   |   |   |-- story.py               # Story Bible (characters, locations, style)
|   |   |   |-- scenes.py              # Scene management and reorder
|   |   |   |-- shots.py               # Shot management and reorder
|   |   |   |-- workflows.py           # Workflow registry, mapping, validation
|   |   |   |-- generation.py          # Preflight, generate, jobs, queue control
|   |   |   |-- review.py              # Take review (approve/reject/regenerate)
|   |   |   |-- timeline.py            # Timeline manifest, render plan, render
|   |   |   +-- exports.py             # Export endpoints
|   |   +-- services/
|   |       |-- prompt_compiler.py     # Layered prompt compilation
|   |       |-- workflow_registry.py   # Workflow import, validation, mapping
|   |       |-- workflow_format.py     # UI vs API format detection
|   |       |-- workflow_analysis.py   # Node/model inventory, candidate mappings
|   |       |-- workflow_dependencies.py  # Checks against /object_info
|   |       |-- job_payload.py         # Job + mapping -> ComfyUI payload + snapshot
|   |       |-- comfyui_adapter.py     # Provider interface (no ComfyUI specifics)
|   |       |-- comfyui_provider.py    # Real ComfyUI HTTP provider
|   |       |-- mock_provider.py       # Deterministic mock provider
|   |       |-- queue_manager.py       # Persistent queue, reconcile, retry policy
|   |       |-- error_classifier.py    # PRD 10.5 error categories and retryability
|   |       |-- timeline_service.py    # Timeline manifest and render plan
|   |       |-- render_service.py      # FFmpeg review render
|   |       |-- media_probe.py         # ffprobe metadata, shared by render + provider
|   |       +-- export_service.py      # Storyboard/prompt/manifest export
|   +-- tests/
|       |-- conftest.py                # Fixtures; redirects CAS_DATA_DIR to tmp
|       |-- test_models.py
|       |-- test_prompt_compiler.py
|       |-- test_workflow_registry.py
|       |-- test_workflow_format.py
|       |-- test_workflow_analysis.py
|       |-- test_workflow_linked_inputs.py
|       |-- test_api_workflow_analysis.py
|       |-- test_job_payload.py
|       |-- test_queue_manager.py
|       |-- test_error_classifier.py
|       |-- test_render_service.py
|       |-- test_media_probe.py
|       |-- test_database_schema.py
|       |-- test_mock_provider.py
|       |-- test_comfyui_provider.py
|       |-- test_api_projects.py
|       |-- test_api_scenes_shots.py
|       |-- test_api_workflows.py
|       +-- test_api_review.py
|
+-- frontend/
    |-- index.html
    |-- package.json
    |-- tsconfig.json / tsconfig.app.json / tsconfig.node.json
    |-- vite.config.ts                 # Dev server, /api proxy to port 8001
    +-- src/
        |-- main.tsx                   # Application entry point
        |-- App.tsx                    # Router and providers
        |-- index.css                  # Tailwind CSS entry
        |-- types.ts                   # Shared types, mirroring the API
        |-- api/client.ts              # Axios API client
        |-- store/useProjectStore.ts   # App state context
        |-- components/
        |   |-- AppLayout.tsx          # Production cockpit layout
        |   |-- StageRail.tsx          # Left navigation rail
        |   |-- Inspector.tsx          # Right inspector panel
        |   +-- StatusBadge.tsx        # Status indicator
        +-- pages/
            |-- StoryPage.tsx          # Brief, plot and Story Bible
            |-- StoryboardPage.tsx     # Scene/shot storyboard grid
            |-- GeneratePage.tsx       # Preflight and generation queue
            |-- ReviewPage.tsx         # Take review
            |-- TimelinePage.tsx       # Timeline, render plan, review render
            +-- ExportPage.tsx         # Exports
```

---

## Vertical Slice Features (MVP)

This application implements the full vertical slice described in the PRD:

1. **Creative Brief and Plot Editing** -- Define project goals, audience, platform, duration, and story plot.
2. **Scene/Shot Hierarchy** -- Break the plot into 3 scenes with 9-15 shots total, each with shot type, camera, action, dialogue, and duration.
3. **Story Bible** -- Maintain Characters, Locations, and Visual Style entries as shared context for prompt compilation.
4. **Layered Prompt Compilation** -- Compile prompts from 8 layers (per PRD section 9.1): style bible, character, location, scene context, shot description, camera/composition, negative prompt, and technical parameters.
5. **Workflow Registry** -- Import ComfyUI workflow JSON. Map logical fields (prompt, seed, dimensions, etc.) to workflow node IDs without hardcoding in business logic. Validate mappings before use.
5a. **Workflow Format Detection and Diagnostics** -- Tell a ComfyUI editor graph from an API-format prompt file structurally, and refuse to submit the former. Inventory the node classes and model files a workflow needs, following subgraphs to the nodes that actually execute; check both against the live instance's `/object_info`; and propose candidate logical-field mappings from generic input-name and type heuristics. For an API-format workflow the proposal is a ready-to-apply `parameter_mapping`.
6. **Preflight Validation** -- Verify all shots have compiled prompts, a mapped workflow, and required parameters before generation begins.
7. **Persistent Generation Queue** -- Queue jobs with deterministic mock ComfyUI provider. Jobs persist across restarts with resumable states (Queued, Running, Completed, Failed).
8. **Queue Control** -- Pause, resume, cancel, and retry generation jobs.
9. **Take Review** -- Approve, reject, or regenerate individual takes. Only approved takes proceed to timeline.
10. **Timeline Manifest** -- Assemble a Timeline Manifest from approved takes with scene/shot ordering, durations, and transitions.
11. **Render Plan** -- Generate the FFmpeg command sequence for video assembly without executing anything.
12. **Review Render** -- Assemble approved takes into a `review.mp4`, normalising every item to the project resolution and frame rate (stills held for the shot duration, video trimmed). Runs only when FFmpeg is installed and every referenced media file exists; otherwise it reports why it was skipped rather than producing a fake result.
13. **Job Provenance** -- Every submission stores the exact ComfyUI graph it sent under `data/snapshots/` plus the SHA-256 of the registered workflow, so a job stays reproducible after a workflow is re-imported with different node IDs.
14. **Categorised Errors** -- Failures are classified per PRD 10.5 (ConnectionError, OutOfMemoryError, MissingModelError, MissingCustomNodeError, GenerationTimeout, OutputMissingError, MediaValidationError, WorkflowValidationError). Only transient categories are retried; OOM and missing dependencies fail once with a suggested action.
15. **Export** -- Export Storyboard (JSON, CSV, Markdown), Prompts, Generation Manifest (with provenance), Timeline Manifest, and full Project Archive.

### UX Layout

The frontend uses a production cockpit layout:

- **Left rail**: Stage navigation following the workflow `Story -> Storyboard -> Generate -> Review -> Timeline -> Export`
- **Center panel**: Storyboard grid or timeline view depending on the active stage
- **Right panel**: Inspector for prompt details, camera settings, references, seed, workflow selection, and take review
- **Status states**: Draft / Ready / Generating / Needs Review / Approved / Failed
- **Approval gates**: Required before Generation and Final Render stages

---

## Known Blockers

### ComfyUI Integration — T2I, T2V and I2V workflows connected

ComfyUI **is** reachable and healthy: version 0.34.0 on `http://127.0.0.1:8000`,
RTX 5080, 1800 registered node classes. The application backend runs on 8001 to
avoid the clash.

Three workflows were supplied on 2026-09-01 and are preserved unmodified with
SHA-256 checksums under `workflows/source/ui/`:

| Workflow | Purpose |
|---|---|
| `image_boogu_image_0_1_edit_int8.ui.json` | image edit (Boogu-Image-0.1-Edit) |
| `video_minimax_h3_t2v.ui.json` | text to video (MiniMax H3) |
| `video_minimax_h3_i2v.ui.json` | image to video (MiniMax H3) |

All three were supplied as ComfyUI **editor/UI graphs**, which `POST /prompt`
cannot execute. They are imported and fully analysed but recorded as
`source_format: "ui"` / `validation_status: "unsupported_format"`, and the
payload builder refuses to construct a submission from them. Nothing in this
repository posts an editor graph to ComfyUI.

**API-format exports have since arrived for the two video workflows** and are
preserved under `workflows/source/api/`. Both are detected as API format,
marked submittable, dependency-checked clean, and their suggested mappings
validate.

**Video generation is verified working.** One controlled real job ran through
the T2V workflow on 2026-09-01 and produced a genuine 864x480 h264+aac clip;
see the Verification Status section.

**Text-to-image is now operational through ComfyUI.** The supplied Z-Image
Turbo API export was preserved byte-for-byte. Its CLIP filename differed from
the installed filename, so a separately versioned local derivative records the
single substitution and provenance. It passed live dependency/mapping checks
and produced a real 512x512 PNG. The independent OpenAI Images path is also
verified. The optional Boogu image-edit workflow still needs an API-format
export before image-to-image editing can use that workflow.

**Everything else checked out.** Verified against the live instance:

- Every node class each workflow needs is registered — 15, 20 and 23
  respectively, including `TextEncodeBooguEdit`, `MiniMaxH3ImageToVideo`,
  `SamplerCustomAdvanced` and `LoraLoaderModelOnly`.
- Every model file they name is installed — 3, 5 and 5 respectively.
- **No missing custom node and no missing model.**
- Candidate logical mappings were derived for prompt, seed, width, height,
  reference image and output prefix on all three.

**To finish unblocking:** export the image workflow via
`Workflow → Export (API)` in ComfyUI and import it. The analysis endpoint
returns a `suggested_parameter_mapping` with concrete node ids that can be
applied and validated directly.

Three decisions remain on the two video workflows before a real run, all
reported by the analysis endpoint:

- **Resolution** — `width`/`height` are wired from `ResolutionSelector`, which
  exposes `aspect_ratio`/`megapixels`/`multiple` rather than pixel dimensions.
- **Duration** — the frame count is computed by a math expression from a
  duration primitive; the adapter deliberately will not overwrite that formula.
- **Output mapping** — `output_mapping` is still empty and should name the
  `SaveVideo` node.

The single-shot test the handoff README asks for has now been run on the T2V
workflow and passed. No batch has been run.

`docs/ComfyUI_Workflow_Integration.md` has the full findings: per-workflow
candidate mappings, the two fields that need a decision after export
(`negativePrompt`, which the MiniMax video node does not accept, and `frames`,
computed inside the subgraph), and the exact commands.

**No application change is pending.** Node ids live only in a workflow record's
`parameter_mapping`, so adopting the exports is configuration, not code.

### Why the editor format is not converted here

All three workflows put their generation nodes inside a **subgraph** — a node
whose `type` is a UUID, with the real nodes under `definitions.subgraphs`.
ComfyUI flattens subgraphs and renumbers nodes during API export. Reimplementing
that flattening here would duplicate frontend logic and could silently produce a
graph that differs from what ComfyUI would run, so the adapter analyses the
editor file and asks for the real export rather than guessing. Candidate
mappings from a UI file therefore name a *node class and input*, never a node
id.

### Mock generation

The mock provider stands in so the rest of the product can be exercised. It is
deliberately honest about what it is:

- Jobs progress Queued → Running → Completed on a wall-clock schedule.
- Outputs are real files at the shot's requested dimensions — a gradient PNG for
  image shots, an H.264 MP4 for video shots — so the timeline and render stages
  operate on genuine media.
- `check_health()` reports `mock: true`, and the health endpoint says so.
- Nothing imitates a rendered frame or a ComfyUI response.

Mock generation keeps working with a UI-format workflow registered: the mock
never executes the graph, so the payload builder passes logical values through
instead of blocking. Re-verified after these changes — three shots to three
takes to a 1024×1024 h264 review render, with the live ComfyUI queue untouched.

---

## Verification Status

Against the MVP Definition of Done in PRD section 20.2. "Verified" means it was
exercised against a running server on 2026-09-01 or 2026-09-02, not merely
implemented.

| # | Definition of Done item | Status | Evidence |
|---|-------------------------|--------|----------|
| 1 | Plot to editable scene/shot storyboard | Verified | e2e run creates 3 scenes and 9 shots, all editable via the API |
| 2 | Each shot has a prompt and checkable workflow mapping | Verified | Preflight validates each mapping against the workflow JSON; snapshots show the compiled prompt injected into node 6, negative into 7, seed into 3, dimensions into 5, with unmapped inputs untouched |
| 3 | Real image and video generation paths | **Verified** | Local ComfyUI Z-Image T2I produced a 512x512 PNG; H3 T2V produced an 864x480 h264+aac clip (124 frames, 5.167s); OpenAI `gpt-image-1-mini` produced one paid 1024x1024 PNG at an estimated $0.011. Optional Boogu image editing still needs its API export. |
| 4 | Job status, error and retry behave correctly | Verified | Categorised errors; connection failures retry three times, OOM and missing models fail once |
| 5 | One approved take per shot | Verified | 9 takes approved through the review API |
| 6 | Approved takes assembled into a review video | Verified | Mock E2E: 45.0s 1920x1080 h264 from 9 approved takes. Paid-image E2E: approved PNG became a 3.000s, 1024x1024, 24fps h264 render. Both confirmed with ffprobe. |
| 7 | Project and queue state survive restart | Verified | Mock project/scenes/9 approved takes survived restart; the paid-image project, completed one-attempt job, approved take, timeline and streamable PNG also survived a hard backend restart. |
| 8 | Exports include video, storyboard, prompts and provenance | Verified | Storyboard JSON/CSV/Markdown, prompts, generation manifest with snapshot path and SHA-256, timeline manifest, project archive |
| 9 | Automated tests of data model, mapping and queue state | Verified | 685 backend tests and 8 frontend component/regression tests |
| 10 | One end-to-end project with no manual file edits | Verified | `python test_e2e.py` passes start to finish |
| 11 | Restart mid-queue resumes only the stuck jobs | Verified | Server killed with 1 Running and 7 Queued; on restart the Running job was requeued, retried as attempt 2, and all 8 completed |
| 12 | Retiming the manifest re-renders without regenerating takes | Verified | Two items retimed, re-render went 45.0s to 36.0s, approved take files byte-identical and no new jobs created |

### Live ComfyUI integration (2026-09-01)

| Check | Result |
|---|---|
| ComfyUI health via the real provider | online, 0.34.0, RTX 5080, 14.6/15.9 GB VRAM free |
| Node catalogue fetched | 1800 classes via `GET /object_info` |
| Workflow format detection | all 3 supplied files correctly identified as UI format |
| Node dependencies | 15 / 20 / 23 classes required, all present |
| Model dependencies | 3 / 5 / 5 files required, all installed |
| Candidate mappings derived | 7 / 7 / 7 logical fields |
| UI-format submission guard | job failed `WorkflowValidationError`, `comfyui_prompt_id` null, 0 takes created, ComfyUI queue untouched |
| API exports detected | both video workflows: `api`, submittable, dependencies satisfied |
| Suggested mapping applied and validated | T2V 3 fields, I2V 4 fields, `valid: true` both |
| Unsafe bindings withheld | `frames` (would overwrite a computed formula) reported for review, excluded from auto-apply |
| Mock generation still working | 3 shots to 3 takes to a 1024x1024 h264 review render |

Rechecked on 2026-09-02 against the live ComfyUI instance: T2V and I2V were
both API format, submittable and mapping-valid; all 20/23 required node classes
and all five model files per workflow were present. No generation was submitted
during this recheck. Their `SaveVideo` output mappings were then configured and
both validated without warnings.

### First real ComfyUI image generation (2026-09-02)

The Z-Image Turbo API workflow passed preflight with `comfyui_mock: false`, all
10 node classes and all three model files available. One local 512x512 shot
completed in one attempt with ComfyUI prompt id
`753a6b1b-d297-4ce0-9898-df46ac2ca996`. The resulting PNG was visually
inspected: a coherent white paper boat on a calm sunrise pond, with no visible
text, logo, corruption or major artifact. The run has no vendor charge.
Evidence and checksums are under
`docs/release_evidence/2026-09-02/comfyui-image-e2e/`.

### First real generation (2026-09-01)

One authorised job on `video_minimax_h3_t2v.api.json`. Full record in
`docs/ComfyUI_Workflow_Integration.md` section 7.

| Check | Result |
|---|---|
| Payload diff vs untouched source | exactly 3 inputs changed, all authorised; resolution, duration, steps and LoRA switch byte-identical |
| Job outcome | `Completed`, 1 attempt, prompt_id `7bd626a7-...` |
| Wall clock | 300.7 s |
| Output (ffprobe) | h264 864x480, 24 fps, 124 frames, 5.167 s, + aac stereo; 416,626 bytes |
| Derived values | 864x480 = 0.4 MP @ 16:9 rounded to 32; 124 frames = the workflow's own duration expression |
| Provenance | snapshot written, workflow sha256 recorded, seed 42 reproducible |
| Defect found | takes recorded `0x0 / 0.0s / codec=mp4` - the provider never probed downloads. Fixed and regression-tested |
| Follow-up defect | the original review render dropped source audio and exposed workflow metadata; both were fixed, with provenance retained in a sidecar |

### Real H3 T2V through export (2026-09-02)

A fresh one-shot run exercised project creation, preflight, real ComfyUI H3 T2V,
job persistence, take approval, timeline assembly, FFmpeg rendering and every
metadata export. It completed in one attempt with prompt id
`cbf580d1-4471-4fe5-a2d9-28fac8a3ec88`; a hard backend restart preserved the
completed job, prompt id, approved take and one-item timeline.

The delivered review is h264 864x480 at 24 fps with 124 frames and AAC stereo;
its container duration is 5.188 seconds. There were no black intervals or
freezes over 0.5 seconds, and audio/video start and duration offsets remained
within one video frame. The delivery MP4 contains no prompt, workflow,
ComfyUI identifier or internal path. Two release warnings remain: generated
audio is quiet at -37.9 LUFS, and 864x480 is 9:5 rather than exact 16:9.
Evidence is under
`docs/release_evidence/2026-09-02/comfyui-h3-t2v-export-e2e/`.

### Paid OpenAI Images E2E (2026-09-02)

Exactly one confirmed paid request used `gpt-image-1-mini`; the estimate was
$0.011. It completed in one attempt and produced a nonempty 1,311,910-byte,
1024x1024 PNG. The take was visually inspected, approved with rating 5, placed
on a one-item timeline and rendered locally with FFmpeg. `ffprobe` confirmed a
3.000-second, 1024x1024, 24fps h264 output with 72 frames. A hard backend
restart preserved the project, job, approval, timeline and media stream.

Evidence, checksums and the safe provenance sidecar are under
`docs/release_evidence/2026-09-02/openai-image-e2e/`. The rendered MP4 contains
no embedded workflow or provenance metadata keys. Representative error checks
also passed: unconfirmed paid generation returned 409 without creating a job,
unknown provider returned 400, duplicate approval returned 400 and a missing
take returned 404.

### Quality gates

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `python -m pytest tests/ -q` | 685 passed (2026-09-02) |
| Backend lint | `python -m ruff check app/ tests/` | clean |
| Frontend tests | `npm test -- --run` | 16 passed (2026-09-02) |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc -b` | clean |
| Frontend build | `npm run build` | succeeds |
| End-to-end | `python test_e2e.py` | all steps pass |
| API contract | client calls vs OpenAPI | all client calls match on method and path |
| Live ComfyUI | `GET /object_info` via the real provider | 1800 node classes; all workflow dependencies satisfied |

> On Windows the full-suite run prints `Windows fatal exception: access
> violation` from pytest's faulthandler. It appears only in the combined run,
> never when the same tests run in isolation or when the same code runs outside
> pytest, and the suite still exits 0 with every test passing. It is a
> pytest/anyio artifact on this platform, not an application fault; the handler
> is deliberately left enabled so a genuine crash would still be reported.

---

## API Documentation

Start the backend server and visit **http://localhost:8001/docs** for the interactive Swagger UI, which documents all available REST endpoints with request/response schemas.

Alternatively, visit **http://localhost:8001/redoc** for the ReDoc-formatted API reference.

---

## Technology Stack

| Layer      | Technology              | Version    | Purpose                                  |
|------------|-------------------------|------------|------------------------------------------|
| Frontend   | React                   | 19.x       | UI component library                     |
| Frontend   | TypeScript              | 6.x        | Type-safe JavaScript                     |
| Frontend   | Vite                    | 8.x        | Development server and build tool        |
| Frontend   | Tailwind CSS            | 4.x        | Utility-first CSS framework              |
| Frontend   | React Router            | 6.x        | Client-side routing                      |
| Frontend   | TanStack React Query    | 5.x        | Server state management and caching      |
| Frontend   | Axios                   | 1.x        | HTTP client                              |
| Frontend   | Lucide React            | 1.x        | Icon library                             |
| Frontend   | oxlint                  | 1.x        | JavaScript/TypeScript linter             |
| Backend    | Python                  | 3.11+      | Runtime                                  |
| Backend    | FastAPI                 | 0.115.x    | Web framework with async support         |
| Backend    | Uvicorn                 | 0.30.x     | ASGI server                              |
| Backend    | SQLAlchemy              | 2.0.x      | ORM and database toolkit                 |
| Backend    | Pydantic                | 2.9.x      | Data validation and serialization        |
| Backend    | httpx                   | 0.27.x     | Async HTTP client (for ComfyUI adapter)  |
| Backend    | aiofiles                | 24.x       | Async file I/O                           |
| Database   | SQLite                  | Built-in   | Metadata storage (no server required)    |
| Testing    | pytest                  | 8.3.x      | Backend test framework                   |
| Testing    | requests                | 2.34.x     | Drives test_e2e.py against a live server |
| Testing    | pytest-asyncio          | 0.24.x     | Async test support                       |
| Linting    | Ruff                    | 0.6.x      | Python linter and formatter              |
| Optional   | FFmpeg / ffprobe        | 8.x tested | Review render, media probing, MP4 mock takes |

---

## Platform Support

The application runs on **Windows** and handles paths containing spaces and Unicode characters; this project's own path (`Thinkpad_and_PC_Sync`) sits under a directory tree with spaces, and a test covers a `CAS_DATA_DIR` containing both a space and Thai characters. All runtime paths resolve through `app/paths.py`, so relocating the data directory is a single environment variable.

---

## License

See project documentation for license details.
