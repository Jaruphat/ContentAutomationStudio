# ComfyUI API-Format Workflow Handoff

Place workflows exported through **ComfyUI → File → Export Workflow (API)** in this directory.

Expected filenames:

- `video_minimax_h3_t2v.api.json` — received; SHA-256 `06392e8508554ce7b9cbefc8ae1ebc59e12e7019c3d04d372ad11a4864030088`
- `video_minimax_h3_i2v.api.json` — received; SHA-256 `a742c6de241bd77d540767cf0ec2ce4bc084d701eeae85faf925ec79ccf75601`
- `image_boogu_image_0_1_edit_int8.api.json`

The two H3 files were supplied by the user at the project root on 2026-09-01 and moved here after verification. Both are valid API-format root node mappings (not UI graphs). Their node classes were checked against live ComfyUI 0.34.0 at `http://127.0.0.1:8000/object_info`: T2V has 23 nodes / 20 class types and I2V has 26 nodes / 23 class types, with no missing class types.

For every file:

1. Preserve the matching UI workflow under `../ui/`.
2. Record SHA-256 and original export path/date.
3. Validate that the root is an API prompt mapping keyed by node ID, not a UI graph containing top-level `nodes` and `links`.
4. Validate mapped inputs against live `http://127.0.0.1:8000/object_info`.
5. Run one low-resolution shot and inspect the output before enabling batch generation.
6. Never edit an exported source file in place; create a new version and mapping record.
