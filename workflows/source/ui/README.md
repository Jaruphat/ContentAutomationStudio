# Imported ComfyUI Workflow Sources

These files were copied from the user's running ComfyUI workspace on 2026-09-01. They are preserved as read-only source inputs for adapter analysis.

| File | Original path | SHA-256 | Format |
|---|---|---|---|
| `video_minimax_h3_t2v.ui.json` | `C:\AI\ComfyFile\user\default\workflows\video_minimax_h3_t2v.json` | `187ce4b96e2a09fb222f6b5581f5aa42cd16cb3a70dcb89855ce352e2fe96fc0` | ComfyUI UI workflow |
| `video_minimax_h3_i2v.ui.json` | `C:\AI\ComfyFile\user\default\workflows\video_minimax_h3_i2v.json` | `b4d6c319533aec6e37eb14aea44a6a40d006c82d548a9d8f7b42111e8267c2b6` | ComfyUI UI workflow |
| `image_boogu_image_0_1_edit_int8.ui.json` | `C:\AI\ComfyFile\user\default\workflows\image_boogu_image_0_1_edit_int8.json` | `dc68c0ac18cca39f46108dfd2b40d3f48e148c34d0d385dbe6afcca9d45361b9` | ComfyUI UI workflow |

## Important

These are graph/UI workflow JSON files (`nodes` + `links`), not ComfyUI API-format prompt JSON. They must not be submitted directly to `/prompt`. Keep them unchanged for provenance. Export API-format copies from ComfyUI or produce a validated conversion before real generation.

## Analysis (2026-09-01)

Analysed against the live instance (ComfyUI 0.34.0, 1800 registered node
classes) via `GET /api/workflows/{id}/analysis`.

| File | Subgraph | Node classes | Models | Dependencies |
|---|---|---:|---:|---|
| `image_boogu_image_0_1_edit_int8.ui.json` | Image Edit (Boogu Image Edit) | 15 | 3 | all present |
| `video_minimax_h3_t2v.ui.json` | Image to Video (MiniMax H3) | 20 | 5 | all present |
| `video_minimax_h3_i2v.ui.json` | Image to Video (MiniMax H3) | 23 | 5 | all present |

No custom node and no model file is missing. The only blocker is the format:
all three are editor graphs, so `POST /prompt` cannot execute them.

Each one puts its generation nodes inside a subgraph, whose node ids ComfyUI
renumbers during API export. Candidate logical mappings therefore name a node
class and input rather than a node id, and no mapping is auto-applied.

See `docs/ComfyUI_Workflow_Integration.md` for the per-workflow candidate
mappings and the export steps.
