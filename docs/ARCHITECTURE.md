# Architecture

How the pieces fit together, what is in each directory, and what the application is built out of.

---

## Architecture Overview

```
             Browser -- Vite dev server, port 5173
  Channel -> Story -> Storyboard -> Generate -> Review -> Timeline -> Export
                          Workflows  (register a graph, bind its inputs)
                                   |
                                   |  HTTP/REST, localhost:8001/api
                                   v
  +--------------------------------------------------------------------+
  |  FastAPI (Uvicorn, port 8001)                                       |
  |                                                                     |
  |  prompt compiler -> workflow adapter -> job queue -> takes ->        |
  |  review -> timeline manifest -> render                              |
  +------+-------------------------+------------------+----------------+
         |                         |                  |
         | submits a graph with    | authors story,   | assembles the
         | node ids taken only     | draws images,    | approved media
         | from parameter_mapping  | speaks narration | into one file
         v                         v                  v
  ComfyUI 127.0.0.1:8000      OpenAI API         FFmpeg (local binary)
  local models: H3 I2V,       GPT-4.1 authoring, cut, narration mix,
  Boogu Edit, Z-Image         Images, TTS        captions, loudness

  State: SQLite at backend/data/cas.db, media and exports under CAS_DATA_DIR.
  ComfyUI, OpenAI and FFmpeg are each optional: mock providers stand in for
  the first two, and a render plan is produced when FFmpeg is absent.
```

- **Frontend**: React 19 + TypeScript, bundled with Vite, styled with Tailwind CSS v4. Uses React Router for page navigation, TanStack React Query for server state, and Axios for HTTP requests.
- **Backend**: Python FastAPI with SQLAlchemy ORM over SQLite. Modular routers for channels, projects, story, references, character sets, scenes, shots, continuity frames, workflows, generation, review, quality, analytics, publishing, premises, sound, timeline, exports, AI and media. Services layer handles prompt compilation, workflow registry, queue management, ComfyUI adapter (mock and real providers), timeline assembly, and export generation.
- **Database**: SQLite file (`backend/data/cas.db`) for all MVP metadata. No external database server required. Schema changes that only add columns are applied automatically at startup.
- **ComfyUI boundary**: business logic depends only on the `ComfyUIProvider` interface. Node IDs appear solely in a workflow record's `parameter_mapping`, so re-exporting H3 with different node numbering is a mapping fix, not a code change.

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

## API Documentation

Start the backend server and visit **http://localhost:8001/docs** for the interactive Swagger UI, which documents all available REST endpoints with request/response schemas.

Alternatively, visit **http://localhost:8001/redoc** for the ReDoc-formatted API reference.

---

## Platform Support

The application runs on **Windows** and handles paths containing spaces and Unicode characters; this project's own path (`Thinkpad_and_PC_Sync`) sits under a directory tree with spaces, and a test covers a `CAS_DATA_DIR` containing both a space and Thai characters. All runtime paths resolve through `app/paths.py`, so relocating the data directory is a single environment variable.

---

## UX Layout

The frontend uses a production cockpit layout:

- **Left rail**: Stage navigation following the workflow `Story -> Storyboard -> Generate -> Review -> Timeline -> Export`
- **Center panel**: Storyboard grid or timeline view depending on the active stage
- **Right panel**: Inspector for the compiled prompt, camera and motion direction, on-screen captions, references, seed and take review
- **Workflows**: Graph registration, field mapping, frame rate, fixed settings and validation. Nothing generates until one is registered and mapped.
- **Status states**: Draft / Ready / Generating / Needs Review / Approved / Failed
- **Approval gates**: Required before Generation and Final Render stages

#### Everything is reachable from the browser

An audit on 2026-09-06 looked for a caller of every method in the API client
and found seven decisions that could only be made by posting to the API. All
seven now have controls, and the browser walk-through exercises them:

- A **scene** is editable - title, summary, purpose, time of day, emotional
  beat, planned duration, location and cast. Time of day and summary reach the
  compiled prompt, which is why the form says so beside them.
- **Scenes and shots reorder.** The storyboard used to draw a drag handle that
  did not drag; it is now two buttons per row that do, and are reachable by
  keyboard.
- The **creative brief** has a field on the Story page, beside the plot. The AI
  author reads both and either one alone is enough.
- **Publication title, series, description and hashtags** are typed in the
  publish gate and saved with the package.
- `lens_framing`, `environment` and `video_prompt` are on the shot; the video
  prompt only where a clip is actually made.
- A project's **frame rate and delivery resolution** are editable whether or
  not it came from a channel. A clip's frame count is computed from the rate.
- A **project can be deleted**, after confirming in place.

Re-running the audit against the finished work found four more of the same
kind, now also built: the cut's clips can be reordered and trimmed in place;
what an episode did on the platform can be recorded on the export page (blank
means unmeasured, not zero); and a channel or a character set can be deleted.
What is left with no caller is a dozen single-item getters whose list
equivalent is used - nothing that decides anything.

---
