# Real Boogu image-edit visual QC

- Transport/integration gate: **PASS**. The application uploaded the selected project-scoped canonical image, injected the returned ComfyUI-relative filename into `LoadImage`, received real prompt ID `d20aad31-2648-4f62-b193-08f1dcc6dbef`, and persisted a nonblank RGB PNG take.
- Output integrity: **PASS**. Reference is PNG RGB24 at 864×480; output is PNG RGB24 at 512×512.
- Recurring prop count/color: **PASS for this smoke**. The output contains exactly one medium-blue folded paper boat and no duplicate boat.
- Broad scene retention: **PARTIAL**. Pond, mist, sunset direction and the boat motif remain recognizable.
- Character/composition retention: **FAIL as a content-continuity proof**. The child in the blue raincoat was removed and the framing changed from a wide landscape with the child at frame right to a square boat-only composition.

This bounded run proves the real reference-conditioned application path, not full character-identity preservation. Character continuity requires a stronger canonical character reference/prompt or multi-reference conditioning and must remain a separate content gate.