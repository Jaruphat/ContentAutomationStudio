# Content Automation Studio — Claude Code Context

## Mission
Build the MVP described in `docs/PRD_Content_Automation_Studio_v0.2.md`: a local-first application that turns a creative brief/plot into scenes, shots, compiled prompts, mockable ComfyUI generation jobs, reviewed takes, a Timeline Manifest and an automated review render.

## Current Constraint
ComfyUI is reachable at `http://127.0.0.1:8000` and has been verified through `/system_stats` and `/object_info` (ComfyUI 0.34.0, RTX 5080). The application backend uses port `8001` to avoid a conflict. The real H3 image/video API-format JSON files, required models and custom-node inventory have not been provided. Do not fabricate a successful H3 integration. Keep deterministic mock generation available until the real H3 workflows are supplied. Real H3 end-to-end verification remains blocked until those workflow files and dependencies are available.

## Source of Truth
- `docs/PRD_Content_Automation_Studio_v0.2.md`
- Preserve versioned PRD files unchanged.

## First Build Target
A runnable vertical slice:
1. Create/edit a Creative Brief and plot.
2. Create/edit 3 scenes and 9–15 shots.
3. Compile layered prompts from Story Bible + scene + shot data.
4. Register/import a workflow JSON and map logical fields without hardcoding H3 node IDs in business logic.
5. Preflight validation.
6. Persistent queue with deterministic mock image/video jobs and resumable states.
7. Take review: approve/reject/regenerate.
8. Timeline Manifest using approved takes only.
9. Generate a lightweight review output or validated render plan; use FFmpeg only when installed and real media exists.
10. Export project/storyboard/prompts/manifests.

## Technical Direction
- Prefer React + TypeScript for frontend and Python FastAPI for backend.
- SQLite for MVP metadata.
- Keep modules separated: project/story, prompt compiler, workflow registry/adapter, orchestration, assets, timeline/render.
- Use schemas and migrations; avoid hardcoded sample logic in core services.
- Must run on Windows with paths containing spaces and Unicode.
- Store generated runtime data under project-local ignored directories.

## UX Direction
Production cockpit:
- Left: stage rail `Story → Storyboard → Generate → Review → Timeline → Export`
- Center: storyboard/timeline grid
- Right: inspector for prompt, camera, references, seed, workflow and take
- States: Draft / Ready / Generating / Needs Review / Approved / Failed
- Approval gates before Generate and Final Render

## Quality Gates
Before claiming completion:
- Install dependencies reproducibly.
- Run backend and frontend tests.
- Run lint/typecheck and production build.
- Start the app and exercise the vertical-slice flow.
- Verify persistence after restart/reload.
- Verify mock queue resume/reconcile behavior.
- Verify exports exist and parse.
- Record blockers honestly; never invent ComfyUI responses or generated media.
- Update README with exact setup/run/test commands and current H3 blocker.

## Working Rules
- Work only inside this project folder.
- Do not commit secrets or local model paths.
- Do not alter or delete versioned PRDs.
- Make incremental git commits with clear messages after verified milestones.
