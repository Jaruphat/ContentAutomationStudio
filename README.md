# Content Automation Studio

A local-first application for AI-assisted storyboard creation, image/video generation via ComfyUI workflows, and automated video editing. Content Automation Studio turns a creative brief or plot into structured scenes, shots, compiled prompts, generation jobs, reviewed takes, a Timeline Manifest, and an automated review render.

**[คู่มือเริ่มต้นภาษาไทย →](README.th.md)**

It is built for someone who already has a GPU and a working ComfyUI, and wants
a place to keep a story, its characters and its shots so that generating a few
hundred frames stays organised. It was developed against an RTX 5080 (16 GB)
and ComfyUI 0.34.0 on Windows, and every timing in this file was measured on
that machine.

Nothing is required to try it. With no API key and no ComfyUI running, the
studio starts on deterministic mock providers: every page works, shots
generate placeholder images, and the render produces a plan. Point it at a real
ComfyUI when you want real frames.

Current product scope: [PRD v0.4](docs/PRD_Content_Automation_Studio_v0.4.md).
Implementation checks and the YouTube pilot: [production report](docs/PRODUCTION_RELIABILITY_2026-09-05.md).

---

## What it makes

![Two consecutive shots from MELLO EP003: the same marshmallow character, drawn separately for each shot, animated from its own approved still](docs/media/marshmallow-moving.gif)

Six seconds spanning one cut. The two shots were drawn independently and
animated separately, and the character holds its shape, colours, scarf and
backpack across the join -- which is the problem this application exists to
solve. Subtitles are burned in by the render.

Five films have been produced end to end with it:

| Film | Length | Made of |
|------|--------|---------|
| MELLO EP003 — Marshmallow, Moving | 3:19 | stills animated into clips, narrated, subtitled |
| NORI EP001 — The Rice Ball Is Older Than The Bowl | 10:13 | 79 narrated lines over reference-conditioned stills |
| MELLO EP002 — The Name That Outlived The Plant | 9:38 | one character, one world, narrated throughout |
| The Boy Who Swept the Sky | 3:04 | vertical 576x1024 |
| The Cartographer of Small Things | 3:04 | the first full pass through the pipeline |

The films themselves are attached to the
[releases](../../releases) rather than committed, so cloning this
repository does not drag a hundred megabytes of video with it. A frame-by-frame
[contact sheet](docs/release_evidence/2026-09-05/short-film/contact-sheet.png)
and the measurements behind each run are under
[docs/release_evidence/](docs/release_evidence/).

---

## Quick start

```bash
git clone <this repo> && cd ContentAutomationStudio
cp .env.example .env                 # defaults are fine; nothing needs filling in

cd backend
python -m venv .venv && .venv\Scripts\activate   # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001

# in a second terminal
cd frontend && npm install && npm run dev
```

Open <http://localhost:5173>. After that first install, `start-dev.bat` starts
both services and opens the browser in one double-click; it checks for the
virtualenv and `node_modules` and tells you what is missing rather than
installing anything itself.

That is the whole install. The sections below cover what to change when you
want it driving your own ComfyUI: [which models](#models-this-was-built-against),
[what to put in `.env`](#configuration), and
[registering your first workflow](#3-register-a-workflow-before-anything-else),
which is the one step a fresh install cannot skip -- a shot has nothing to
generate with until a graph is mapped.

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

## Prerequisites

| Requirement   | Version  | Notes                                    |
|---------------|----------|------------------------------------------|
| Python        | 3.11+    | Required for backend                     |
| Node.js       | 18+      | Required for frontend                    |
| npm           | 9+       | Comes with Node.js                       |
| FFmpeg        | Optional | Enables the review render and MP4 mock takes; without it those steps report why they were skipped |
| ComfyUI       | Optional | 0.34.0 or newer, for real generation. Without it the mock provider stands in |
| GPU           | Optional | 16 GB was enough for everything below, one pipeline resident at a time |

---

## Models this was built against

None of these ship with the repo and none of them are required to start it.
They are what the workflows under `workflows/derived/` load, so this is the
shopping list for making the mock provider real. Sizes are the files on disk
here; folders are relative to your ComfyUI `models/` directory.

**If you are starting from nothing, download the first two groups.** Z-Image
draws the stills and Wan animates them, which is a whole film, for about 30 GB.

### Stills: Z-Image Turbo — about 20 s per 1080p still

| File | Size | Folder |
|------|------|--------|
| `z_image_turbo_int8_convrot.safetensors` | 5.8 GB | `diffusion_models/` |
| `qwen_3_4b.safetensors` | 7.5 GB | `text_encoders/` |
| `ae.safetensors` | 0.3 GB | `vae/` |

### Motion: Wan 2.2 TI2V 5B — about 0.74 s per frame at 10 steps

From [Comfy-Org/Wan_2.2_ComfyUI_Repackaged](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged),
under `split_files/`.

| File | Size | Folder |
|------|------|--------|
| `wan2.2_ti2v_5B_fp16.safetensors` | 9.3 GB | `diffusion_models/` |
| `umt5_xxl_fp8_e4m3fn_scaled.safetensors` | 6.3 GB | `text_encoders/` |
| `wan2.2_vae.safetensors` | 1.3 GB | `vae/` |

Measured against MiniMax H3 on the same start frame, same size, same machine:
H3 turbo at 8 steps took 1.78 s per frame, Wan at 10 steps took 0.74 s — about
2.4x faster. Ten steps was indistinguishable from twenty here. Wan also makes
picture alone, where H3 loads a second VAE and decodes a soundtrack this
pipeline throws away, since a narrated film is rendered voice-only.

Wan also took direction H3 ignored: told to stay seated, it stayed seated,
where H3 on the same frame stood the character up and walked him at the camera.

### Keeping a character the same: Qwen-Image-Edit 2511 Lightning — about 36 s

A reference-conditioned edit, used to draw the same character in a new shot
from an approved master image. Needs ComfyUI-GGUF for the `.gguf` loader.

| File | Size | Folder |
|------|------|--------|
| `qwen-image-edit-2511-Q4_K_M.gguf` | 12.3 GB | `unet/` |
| `Qwen-Image-Edit-2511-Lightning-4steps-V1.0-bf16.safetensors` | 0.8 GB | `loras/` |
| `qwen_2.5_vl_7b_fp8_scaled.safetensors` | 8.7 GB | `text_encoders/` |
| `qwen_image_vae.safetensors` | 0.2 GB | `vae/` |

### Optional: MiniMax H3 image-to-video — 1.78 s per frame

Slower than Wan and generates audio nothing here uses, but it is the only one
of these that takes a **last frame**, so a clip can be made to land on an
already-approved still. See [The frame a clip has to land on](#the-frame-a-clip-has-to-land-on).
From [Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3).

| File | Size | Folder |
|------|------|--------|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` | 19.5 GB | `diffusion_models/` |
| `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` | 1.8 GB | `loras/` |
| `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 14.6 GB | `text_encoders/` |
| `minimax_h3_video_vae_fp16.safetensors` | 4.9 GB | `vae/` |
| `minimax_h3_audio_vae_fp32.safetensors` | 0.6 GB | `vae/` |

### Optional: Boogu-Image-0.1-Edit

| File | Size | Folder |
|------|------|--------|
| `boogu_image_edit_int8_convrot.safetensors` | 10.6 GB | `diffusion_models/` |
| `qwen3vl_8b_fp8_scaled.safetensors` | 9.9 GB | `text_encoders/` |
| `ae.safetensors` | 0.3 GB | `vae/` |

A workflow naming a file you do not have is not a silent failure: **Validate
against the graph** on the Workflows page checks every mapped field against the
live ComfyUI and says which model is missing. If your copy of a file is named
differently, change the name in the graph rather than renaming the model, and
record why -- `workflows/derived/*.provenance.json` shows the shape of that.

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

Every variable is optional. An empty `.env` runs the whole application on mock
providers.

**ComfyUI — local image and video generation**

| Variable           | Default                 | Description                                                          |
|--------------------|-------------------------|----------------------------------------------------------------------|
| `COMFYUI_PROVIDER` | `mock`                  | `mock` for deterministic placeholders, `real` to drive a live ComfyUI |
| `COMFYUI_URL`      | `http://127.0.0.1:8000` | ComfyUI instance URL, used when the provider is `real`                |

**OpenAI — story authoring, hosted stills, narration**

Without a key, story generation falls back to a deterministic local author,
hosted stills are refused with an explanation rather than silently mocked, and
narration uses the system voice. Nothing here selects a paid provider on its
own: the Generate page shows the estimated total and the paid shot count
before the run starts.

| Variable                     | Default                     | Description                                                                   |
|------------------------------|-----------------------------|-------------------------------------------------------------------------------|
| `OPENAI_API_KEY`             | unset                       | Enables hosted authoring, the Images API and hosted voices                     |
| `OPENAI_MODEL`               | provider default            | Text model for briefs, scenes, shots and prompts; built against `gpt-4.1`      |
| `OPENAI_IMAGE_MODEL`         | `gpt-image-1-mini`          | Image model for paid stills                                                    |
| `OPENAI_IMAGE_QUALITY`       | `medium`                    | `low`, `medium` or `high`                                                      |
| `OPENAI_BASE_URL`            | `https://api.openai.com/v1` | Point at an Azure, proxy or compatible endpoint                                |
| `OPENAI_ORG_ID`              | unset                       | Only if the key belongs to more than one organization                          |
| `CAS_AI_PROVIDER`            | unset                       | Pin one text provider machine-wide. A pinned provider that is not configured fails loudly instead of quietly writing placeholder text into a storyboard |
| `CAS_OPENAI_IMAGE_PRICE_USD` | built-in table              | Override the USD-per-image rate used to estimate what a run will cost          |

**Storage and development switches**

| Variable               | Default        | Description                                                                 |
|------------------------|----------------|-----------------------------------------------------------------------------|
| `CAS_DATA_DIR`         | `backend/data` | Database, workflows, snapshots, media and exports. Prefer an absolute path  |
| `CAS_DISABLE_QUEUE`    | unset          | Set to `1` to run the API without the background generation worker          |
| `CAS_MOCK_QUEUED_SEC`  | `1.0`          | Seconds a mock job stays Queued (lower it to speed up the e2e run)          |
| `CAS_MOCK_RUNNING_SEC` | `2.0`          | Seconds a mock job stays Running                                            |
| `CAS_DISABLE_DOTENV`   | unset          | Ignore `.env` entirely. The test suite sets this so a real key can never reach a test |

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

### 3. Register a workflow before anything else

A shot cannot be generated without a mapped workflow, so a fresh install has
nothing to generate with. Open **Workflows** in the left rail and:

1. Export the graph from ComfyUI with **Workflow -> Export (API)**. The editor
   format cannot be executed; the page flags a graph imported in that format
   rather than failing later at submission.
2. Register it with a name and a purpose (`image`, `text-to-video`,
   `image-to-video`).
3. Bind each logical field - `positivePrompt`, `seed`, `frames`,
   `referenceImage`, and the rest - to a node id and input name. This is the
   only place in the application where node ids appear.
4. Say what frame rate the graph renders at. A clip's length is asked for in
   frames, so a graph that renders 24 fps while the project assumes 30 makes
   every clip a quarter longer than the shot asked for. `0` means it has not
   said, and the project's rate is used as an estimate.
5. Optionally give it fixed settings as JSON (`{"samplerCfg": 9.0}`) - values
   this workflow fixes rather than a shot deciding. A shot's own value still
   wins, and a constant naming a field that is not mapped is refused.
6. **Validate against the graph** checks every mapped field reaches a node that
   exists.

Three shot-level decisions live in the storyboard's shot editor: which workflow
generates it (blank means the project's), whether it is **included in the cut**
(turn this off for a key image that exists only so a later clip can animate from
it - left on, it plays as a still and lengthens the film), and its own negative
prompt, which is added to the style's negatives rather than replacing them.

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

### Browser walk-through (Playwright)

Everything else here tests the application through its API or through a
rendered component. This one drives the real pages in a real browser and types
every value into a field a creator can see - a workflow registered from its
JSON export and mapped, a project, a scene, a shot, preflight, generation,
approval, the cut, and the export that the typed sentence comes back out of.

```bash
cd frontend && npm install     # once
python scripts/e2e_browser.py  # from the repository root
python scripts/e2e_browser.py --headed   # watch it happen
```

The script starts a backend of its own on port 8011 with mock providers and a
database at `backend/data/e2e-browser` that it wipes before each run, so a
walk-through cannot touch the real one, cannot reach a paid provider, and
cannot leave a half-finished project behind. What it generates is a
deterministic placeholder: this proves the pages work, not that a picture is
good.

Playwright uses the Chrome already installed on the machine
(`channel: "chrome"`), because downloading its own browser is blocked here.
`npx playwright install chromium` would remove that dependency where the
download works.

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

### Character continuity end-to-end (requires the backend and a live ComfyUI)

Walks the identity and hand-off chain once against real generation: character
set -> generated canonical views -> approved version -> bound to two shots ->
reference-conditioned scene image -> approved take -> image-to-video ->
approved clip -> extracted end frame -> bound as the next shot's continuity
source -> that shot generated -> timeline -> render -> exports.

It asserts what reached the provider, not only that each call returned 200:
that a canonical view was really submitted, that withdrawing the source take's
approval really blocks the dependent shot, and that the job's lineage names the
exact frame bytes it was conditioned on. Every response is written to
`backend/data/e2e_evidence/character-continuity/`.

```bash
# Start the backend with the real provider first:
COMFYUI_PROVIDER=real COMFYUI_URL=http://127.0.0.1:8000   python -m uvicorn app.main:app --port 8001

python scripts/e2e_character_continuity.py
```

The registered workflow ids default to this workstation's; override them with
`CAS_E2E_WF_T2I`, `CAS_E2E_WF_EDIT` and `CAS_E2E_WF_I2V`. A full run drives the
GPU for roughly 20 minutes.

### Two references in one render (requires the backend and a live ComfyUI)

Drives the two-slot path: an establishing shot conditioned on its canonical
character view alone, then a continuation shot that carries both the hand-off
frame and that same canonical view into one render. It asserts that both
images physically reached the provider, that each landed on its own node
input, and that a shot with only one image is refused on a two-slot workflow
rather than letting the empty input keep the graph's exported default.

```bash
python scripts/e2e_two_reference.py
```

Needs a workflow mapping both `referenceImage` and `referenceImage2`; it finds
one by mapping, or takes `CAS_E2E_WF_EDIT2`. A run takes about 8 minutes.

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
16. **Character Set Generator** -- Define a character's identity, proportions, wardrobe and palette once, then generate a versioned canonical sheet (front, three-quarter, side, back, full body, expression). Each version records its provider, model, workflow, seed and per-view SHA-256. Exactly one version is explicitly approved as canonical, and editing the identity text marks that version out of date rather than silently regenerating it -- regenerating a sheet costs time and money, so it stays the user's decision. Only a text-to-image workflow can produce a sheet: a reference-conditioned graph would keep whichever image was baked into its export and condition every canonical view on a stranger, so those workflows are excluded from the picker and refused by the backend.
17. **Canonical Conditioning and Shot Continuity** -- Bind approved character sets to individual shots, so the canonical views reach the provider as real reference inputs, not as words in a prompt. A shot can additionally continue from an explicitly chosen source: an approved scene image, or the true end frame extracted with FFmpeg from a previous approved video take. Nothing is ever chained automatically. The bound frame's timestamp, dimensions, SHA-256 and source take are stored and shown, and the frame can be re-extracted or cleared. Job and take lineage records both the character-set hashes and the continuity frame hash, so preflight and generation refuse a shot whose source has lost approval or gone stale, naming what to do about it. Where a workflow accepts only one reference image, the run says which image it actually submitted and why, instead of implying it used them all. A clip is its own shot rather than a mode toggle, because a shot cannot continue from its own take: the image an image-to-video shot animates is always one an earlier shot produced and someone approved. That start frame is never inferred -- a canonical view is a studio portrait on a plain backdrop, so animating it would deliver a clip of the character sheet instead of the scene while every hash and lineage entry still checked out, and an image-to-video shot with nothing but a character set bound is refused until a start frame is chosen.
18. **Reference Capacity From the Workflow** -- How many reference images a run may use is read off the mapping of the graph that will actually execute, not fixed in code. The same ComfyUI serves a text-to-image workflow that binds none, an edit workflow that binds one, and a reference-to-video workflow that binds nine, so the number belongs to the workflow. Slots are counted as the contiguous run starting at the first, because a mapping with a gap would otherwise promise an input nothing is wired to. The first slot keeps the name `referenceImage`, so mappings and jobs created before this keep their meaning; later slots are `referenceImage2`, `referenceImage3` and so on. Every bound slot must receive an image: parameter injection overwrites values but does not clear inputs, so a reference input nothing was sent to would keep the filename baked into the graph at export time -- and on a machine where that file exists, the render succeeds while conditioned on a picture from someone else's project. Where a shot resolves more images than the workflow has slots, the run fills them in resolved order and records what it left out, except when a hand-attached plate would be the thing dropped, which is refused instead: someone chose that picture for that shot.

### Deriving a multi-reference workflow

`TextEncodeBooguEdit` accepts up to sixteen reference images through an
autogrow input, but an exported graph wires only the slots that were connected
in the editor. `scripts/derive_two_reference_workflow.py` adds one loader and
binds it to the next slot, leaving the model, sampler, VAE and text encoder
untouched:

```bash
python scripts/derive_two_reference_workflow.py path/to/edit_workflow.json
```

It prints the mapping to apply after importing the result. With two slots a
continuation shot carries its hand-off frame *and* its canonical character
view: the frame holds pose, framing and light while the canonical view holds
the face and wardrobe. An establishing shot, which has only its identity to go
on, stays on the one-slot workflow -- routing is per shot, so both fit in one
project.

### Reference-to-video (MiniMax H3 R2V)

Image-to-video animates a picture it is given. Reference-to-video is a
different thing: it is told *who is in the clip* and composes the shot itself,
so a character can appear in a scene no still of them exists for yet. That is
the shape a character set was made for.

It needs two files beyond the image-to-video set, both from
[Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3):

| File | Size | Folder |
|------|------|--------|
| `minimax_h3_ref2va_pruned_int8_convrot.safetensors` | 19.5 GiB | `models/diffusion_models/` |
| `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` | 1.8 GiB | `models/loras/` |

The text encoder and both VAEs are the ones the image-to-video workflow already
uses. The `MiniMaxH3ReferenceToVideo` node takes up to nine reference images,
so the workflow's mapping decides how many a shot may bind.

ComfyUI ships the workflow as a template (`video_minimax_h3_r2v`); export it as
API format and map:

| Logical field | Node | Input |
|---------------|------|-------|
| `positivePrompt` | the prompt primitive feeding the node | `value` |
| `seed` | `RandomNoise` | `noise_seed` |
| `width` / `height` / `frames` | `MiniMaxH3ReferenceToVideo` | `width` / `height` / `length` |
| `referenceImage` | first `LoadImage` | `image` |
| `referenceImage2` | second `LoadImage` | `image` |
| `outputPrefix` | `SaveVideo` | `filename_prefix` |

Set such a shot's `generation_mode` to **`video`**, not `image-to-video`. The
start-frame rule is right about image-to-video and would be wrong here: an R2V
shot has no first frame to animate, and refusing it for lacking one would block
the case the model exists to serve.

Loading a 19.5 GiB model needs the memory to be there. On a 16 GB card with
other models resident, the first attempt failed inside the reference node with
`HostBuffer.read_file_slice failed`; the same graph ran unchanged after
ComfyUI's `/free` released what it was holding.

### The frame a clip has to land on

Continuity so far has been about where a shot *starts*. That leaves the other
end unconstrained, so each clip drifts and the shot after it inherits the
drift. When both ends are already approved -- one still opens the shot, another
opens the next one -- a shot can say so, and the model interpolates between two
fixed frames instead of guessing where to finish.

`MiniMaxH3ImageToVideo` has always taken a `last_frame`; the exported graph
never wired one. `scripts/derive_end_frame_workflow.py` adds the loader:

```bash
python scripts/derive_end_frame_workflow.py path/to/i2v_workflow.json
```

Map its output to **`endFrameImage`**, never to `referenceImage2`. Reference
slots are positional and the resolver fills them with canonical character
views; sending one of those to `last_frame` would end every clip on a studio
portrait, with correct hashes and correct lineage throughout. `endFrameImage`
is a separate logical field for that reason, is not counted as reference
capacity, and a shot that binds an end frame on a workflow with no
`endFrameImage` mapping is refused rather than run without it.

Bind it under Explicit shot continuity, beside the start frame. The two ends
are separate decisions -- a shot often continues from one clip and has to meet
a different one -- so they are bound, cleared and blocked independently, though
both follow the same rule: a source whose approval is withdrawn stops the run.

Verified against a live ComfyUI. Given a still of the character at the left
edge of a rooftop and another at the right edge, the generated clip's first
frame scored 4.70 against the opening still and 36.41 against the landing;
its final frame scored 3.60 against the landing and 33.32 against the opening
(mean absolute luma difference, 0 identical). It starts and ends where it was
told.


### UX Layout

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

[MIT](LICENSE). Use it, change it, ship it; keep the copyright notice.

The licence covers this application's own code. The models, the ComfyUI
workflows you export, and anything you generate with them carry their own
terms -- check the licence of each model you download before publishing what
it makes.
