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
- **Database**: SQLite file (`backend/data/cas.db`) for all MVP metadata. No external database server required.

---

## Prerequisites

| Requirement   | Version  | Notes                                    |
|---------------|----------|------------------------------------------|
| Python        | 3.11+    | Required for backend                     |
| Node.js       | 18+      | Required for frontend                    |
| npm           | 9+       | Comes with Node.js                       |
| FFmpeg        | Optional | Only needed for real video render output |

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

| Variable           | Default                    | Description                                           |
|--------------------|----------------------------|-------------------------------------------------------|
| `COMFYUI_PROVIDER` | `mock`                     | `mock` for deterministic testing, `real` for ComfyUI  |
| `COMFYUI_URL`      | `http://127.0.0.1:8001`    | ComfyUI instance URL (used when provider is `real`)   |

---

## Running the Application

Open two terminal windows:

### 1. Start the Backend

```bash
cd backend
# Mock mode (default - no ComfyUI required):
COMFYUI_PROVIDER=mock python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Real ComfyUI mode (requires running ComfyUI instance):
COMFYUI_PROVIDER=real COMFYUI_URL=http://127.0.0.1:8001 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The API server will be available at `http://localhost:8000`.

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
python -m pytest tests/ -v
```

### Backend Lint

```bash
cd backend
python -m ruff check app/ tests/
```

### Frontend Typecheck

```bash
cd frontend
npx tsc --noEmit
```

### Frontend Production Build

```bash
cd frontend
npm run build
```

### End-to-End Test (requires backend running)

```bash
cd backend
python test_e2e.py
```

---

## Project Structure

```
ContentAutomationStudio/
|-- CLAUDE.md                          # Claude Code project context
|-- README.md                          # This file
|-- .gitignore
|
|-- docs/
|   |-- PRD_Content_Automation_Studio_v0.1.md
|   |-- PRD_Content_Automation_Studio_v0.1.docx
|   |-- PRD_Content_Automation_Studio_v0.2.md   # Current PRD (source of truth)
|   |-- PRD_Content_Automation_Studio_v0.2.docx
|   +-- build_prd_docx.py
|
|-- backend/
|   |-- requirements.txt
|   |-- test_e2e.py                    # End-to-end integration test
|   |-- data/
|   |   +-- cas.db                     # SQLite database
|   |-- app/
|   |   |-- __init__.py
|   |   |-- main.py                    # FastAPI application entry point
|   |   |-- database.py                # SQLAlchemy engine and session
|   |   |-- models.py                  # ORM models
|   |   |-- schemas.py                 # Pydantic request/response schemas
|   |   |-- data/
|   |   |   |-- exports/              # Generated export files
|   |   |   |-- generated/            # Mock-generated asset files
|   |   |   +-- workflows/            # Imported workflow JSON files
|   |   |-- routers/
|   |   |   |-- projects.py           # Project CRUD
|   |   |   |-- story.py              # Story Bible (characters, locations, style)
|   |   |   |-- scenes.py             # Scene management
|   |   |   |-- shots.py              # Shot management
|   |   |   |-- workflows.py          # Workflow registry and mapping
|   |   |   |-- generation.py         # Generation queue and job control
|   |   |   |-- review.py             # Take review (approve/reject/regenerate)
|   |   |   |-- timeline.py           # Timeline Manifest generation
|   |   |   +-- exports.py            # Export endpoints
|   |   +-- services/
|   |       |-- prompt_compiler.py     # Layered prompt compilation
|   |       |-- workflow_registry.py   # Workflow import, validation, mapping
|   |       |-- comfyui_adapter.py     # ComfyUI adapter interface
|   |       |-- mock_provider.py       # Deterministic mock ComfyUI provider
|   |       |-- queue_manager.py       # Persistent generation queue
|   |       |-- timeline_service.py    # Timeline Manifest and render plan
|   |       +-- export_service.py      # Storyboard/prompt/manifest export
|   +-- tests/
|       +-- __init__.py
|
+-- frontend/
    |-- index.html
    |-- package.json
    |-- tsconfig.json
    |-- tsconfig.app.json
    |-- tsconfig.node.json
    |-- vite.config.ts
    |-- .oxlintrc.json
    |-- public/
    |   |-- favicon.svg
    |   +-- icons.svg
    +-- src/
        |-- main.tsx                   # Application entry point
        |-- App.tsx                    # Router and layout setup
        |-- index.css                  # Tailwind CSS entry
        |-- types.ts                   # Shared TypeScript types
        |-- api/
        |   +-- client.ts             # Axios API client
        |-- store/
        |   +-- useProjectStore.ts    # Zustand/state management
        |-- components/
        |   |-- AppLayout.tsx          # Production cockpit layout
        |   |-- StageRail.tsx          # Left navigation rail
        |   |-- Inspector.tsx          # Right inspector panel
        |   +-- StatusBadge.tsx        # Status indicator component
        +-- pages/
            |-- StoryPage.tsx          # Story and Creative Brief editing
            |-- StoryboardPage.tsx     # Scene/Shot storyboard grid
            |-- GeneratePage.tsx       # Generation queue management
            |-- ReviewPage.tsx         # Take review interface
            |-- TimelinePage.tsx       # Timeline Manifest view
            +-- ExportPage.tsx         # Export options and downloads
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
11. **Render Plan Generation** -- Generate FFmpeg command sequences for video assembly. FFmpeg is used only when installed and real media assets exist.
12. **Export** -- Export Storyboard (JSON, CSV, Markdown), Prompts, Generation Manifest, Timeline Manifest, and full Project Archive.

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

The real H3 image/video workflow JSON files and a reachable ComfyUI instance have **NOT** been provided. The system currently uses a **deterministic mock provider** that simulates the ComfyUI API:

- Jobs progress through Queued -> Running -> Completed states
- Placeholder 1x1 PNG files are generated as mock outputs
- No real image or video generation occurs

**To unblock real generation, provide:**

1. H3 image workflow API-format JSON
2. H3 video workflow API-format JSON
3. ComfyUI server URL and version
4. Required models/checkpoints/LoRA list
5. Required custom nodes list

See `docs/PRD_Content_Automation_Studio_v0.2.md` Appendix B for the required handoff package format.

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
| Testing    | pytest-asyncio          | 0.24.x     | Async test support                       |
| Linting    | Ruff                    | 0.6.x      | Python linter and formatter              |
| Optional   | FFmpeg                  | Any        | Video assembly (only for real media)     |

---

## Platform Support

The application is designed to run on **Windows** and supports paths containing spaces and Unicode characters. All file paths are handled safely through the backend services layer.

---

## License

See project documentation for license details.
