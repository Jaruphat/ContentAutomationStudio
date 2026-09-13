# Development

Installing, running and testing the application in detail. The [README](../README.md) has the short version.

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
