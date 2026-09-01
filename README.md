# Content Automation Studio

A local-first application for AI-assisted storyboard creation, image/video generation via ComfyUI workflows, and automated video editing. Content Automation Studio turns a creative brief or plot into structured scenes, shots, compiled prompts, generation jobs, reviewed takes, a Timeline Manifest, and an automated review render.

---

## Architecture Overview

```
+------------------+         HTTP/REST         +------------------+
|                  | <-----------------------> |                  |
|  React + TS      |    localhost:8000/api      |  Python FastAPI  |
|  (Vite, port     |                           |  (Uvicorn)       |
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
| `COMFYUI_URL`      | `http://127.0.0.1:8000`    | ComfyUI instance URL (used when provider is `real`)   |
| `CAS_DATA_DIR`         | `backend/data`          | Base directory for the database, workflows, snapshots, media and exports    |
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

287 tests covering the data model, prompt compiler, workflow registry and
mapping, job payload construction, queue state and retry policy, error
classification, the review API, schema migration, and the FFmpeg render.
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
CAS_MOCK_QUEUED_SEC=0.2 CAS_MOCK_RUNNING_SEC=0.3 python -m uvicorn app.main:app --port 8000

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
|   +-- build_prd_docx.py
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
|   |       |-- job_payload.py         # Job + mapping -> ComfyUI payload + snapshot
|   |       |-- comfyui_adapter.py     # Provider interface (no ComfyUI specifics)
|   |       |-- comfyui_provider.py    # Real ComfyUI HTTP provider
|   |       |-- mock_provider.py       # Deterministic mock provider
|   |       |-- queue_manager.py       # Persistent queue, reconcile, retry policy
|   |       |-- error_classifier.py    # PRD 10.5 error categories and retryability
|   |       |-- timeline_service.py    # Timeline manifest and render plan
|   |       |-- render_service.py      # FFmpeg review render and ffprobe
|   |       +-- export_service.py      # Storyboard/prompt/manifest export
|   +-- tests/
|       |-- conftest.py                # Fixtures; redirects CAS_DATA_DIR to tmp
|       |-- test_models.py
|       |-- test_prompt_compiler.py
|       |-- test_workflow_registry.py
|       |-- test_job_payload.py
|       |-- test_queue_manager.py
|       |-- test_error_classifier.py
|       |-- test_render_service.py
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
    |-- vite.config.ts                 # Dev server, /api proxy to port 8000
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
5. **Workflow Registry** -- Import ComfyUI API-format workflow JSON files. Map logical fields (prompt, seed, dimensions, etc.) to workflow node IDs without hardcoding in business logic. Validate mappings before use.
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

### H3 ComfyUI Integration (BLOCKED)

The real H3 image/video workflow JSON files have **not** been provided, and no
ComfyUI instance is reachable. Checked on 2026-09-01: nothing is listening on
`127.0.0.1:8001`, nor on 8188, 8000, 8080, 3000 or 7860.

**What this blocks:** real image and video generation, and therefore any claim
that the pipeline produces genuine ComfyUI output. That claim is not made
anywhere in this repository.

**What was still verified without it.** The `real` provider was pointed at the
unreachable instance and behaves correctly:

- `/api/health` reports `online: false` with the connection error and lists the
  blocker explicitly.
- Preflight reports ComfyUI unreachable while still validating workflow
  mappings against their JSON.
- A submitted job fails with `ConnectionError` after three retries, records a
  suggested action, and **creates no takes** - no output is invented.

The mock provider stands in for generation so the rest of the product can be
exercised end to end. It is deliberately honest about what it is:

- Jobs progress Queued -> Running -> Completed on a wall-clock schedule.
- Outputs are real files at the shot's requested dimensions - a gradient PNG
  for image shots, and an H.264 MP4 (via FFmpeg's synthetic source) for video
  shots - so the timeline and render stages operate on genuine media.
- `check_health()` reports `mock: true`, and the health endpoint says so.
- Nothing imitates a rendered frame or a ComfyUI response.

**To unblock real generation, provide:**

1. H3 image workflow API-format JSON
2. H3 video workflow API-format JSON
3. ComfyUI server URL and version
4. Required models/checkpoints/LoRA list
5. Required custom nodes list

See `docs/PRD_Content_Automation_Studio_v0.2.md` Appendix B for the required
handoff package format. Once supplied: import each workflow on the Workflows
screen, map its logical fields to node IDs, run Validate, then start the
backend with `COMFYUI_PROVIDER=real`. No business logic needs to change -
node IDs live only in the workflow record's `parameter_mapping`.

---

## Verification Status

Against the MVP Definition of Done in PRD section 20.2. "Verified" means it was
exercised against a running server on 2026-09-01, not merely implemented.

| # | Definition of Done item | Status | Evidence |
|---|-------------------------|--------|----------|
| 1 | Plot to editable scene/shot storyboard | Verified | e2e run creates 3 scenes and 9 shots, all editable via the API |
| 2 | Each shot has a prompt and checkable workflow mapping | Verified | Preflight validates each mapping against the workflow JSON; snapshots show the compiled prompt injected into node 6, negative into 7, seed into 3, dimensions into 5, with unmapped inputs untouched |
| 3 | Real image and video jobs through H3 | **BLOCKED** | No H3 JSON and no reachable ComfyUI - see Known Blockers |
| 4 | Job status, error and retry behave correctly | Verified | Categorised errors; connection failures retry three times, OOM and missing models fail once |
| 5 | One approved take per shot | Verified | 9 takes approved through the review API |
| 6 | Approved takes assembled into a review video | Verified | 45.0s 1920x1080 h264 `review.mp4` from 9 approved takes, confirmed with ffprobe |
| 7 | Project and queue state survive restart | Verified | Project, scenes and 9 approved takes intact after a hard kill and restart |
| 8 | Exports include video, storyboard, prompts and provenance | Verified | Storyboard JSON/CSV/Markdown, prompts, generation manifest with snapshot path and SHA-256, timeline manifest, project archive |
| 9 | Automated tests of data model, mapping and queue state | Verified | 287 backend tests |
| 10 | One end-to-end project with no manual file edits | Verified | `python test_e2e.py` passes start to finish |
| 11 | Restart mid-queue resumes only the stuck jobs | Verified | Server killed with 1 Running and 7 Queued; on restart the Running job was requeued, retried as attempt 2, and all 8 completed |
| 12 | Retiming the manifest re-renders without regenerating takes | Verified | Two items retimed, re-render went 45.0s to 36.0s, approved take files byte-identical and no new jobs created |

### Quality gates

| Gate | Command | Result |
|------|---------|--------|
| Backend tests | `python -m pytest tests/ -q` | 287 passed |
| Backend lint | `python -m ruff check app/ tests/` | clean |
| Frontend lint | `npm run lint` | clean |
| Frontend typecheck | `npx tsc -b` | clean |
| Frontend build | `npm run build` | succeeds |
| End-to-end | `python test_e2e.py` | all steps pass |
| API contract | client calls vs OpenAPI | 58/58 match on method and path |

---

## API Documentation

Start the backend server and visit **http://localhost:8000/docs** for the interactive Swagger UI, which documents all available REST endpoints with request/response schemas.

Alternatively, visit **http://localhost:8000/redoc** for the ReDoc-formatted API reference.

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
