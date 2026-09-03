# Independent Visual QC — DaVinci

Date: 2026-09-02
Evidence reviewed:
- `07_storyboard_to_render_contact_sheet.png`
- `08_segment_boundaries_contact_sheet.png`
- `09_t2v_multiframe_contact_sheet.png`

## Gate Result: FAIL — selective regeneration required

## Passes
- The three-scene sequence reads clearly as: folding/preparing a paper boat → placing/releasing it → watching it travel toward the light.
- The child remains visually recognizable across all three scenes: similar age, dark hair, blue raincoat, and outdoor pond setting.
- Overall photographic style, cool blue clothing accent, shallow atmospheric mist, and natural cinematic lighting are coherent.
- Approved source frames and final render midpoints match in all three scenes.
- T2V composition is stable. No obvious frame-to-frame flicker, severe subject deformation, tearing, or unwanted camera drift is visible in the sampled frames.
- Segment boundaries are clean hard cuts with no black flash, scaling error, padding, or aspect-ratio jump.

## Blocking continuity defects
1. **Scene 1 contains two paper boats**: one being handled by the child and another already floating at lower left. This conflicts with the intended single recurring boat.
2. **Recurring boat identity changes**: the boat is light/white in Scene 1, dark navy/black in Scene 2, then saturated blue in Scene 3. Shape and color do not read as the same hero prop.

## Recommended selective repair
- Regenerate Scene 1 with an explicit invariant: exactly one paper boat; no second boat in foreground, background, reflection, or water.
- Preserve the selected recurring-boat design across all scenes with a concrete color/material descriptor and image reference where supported.
- Prefer keeping Scene 2 if it remains the approved T2V take, then align Scene 1 and Scene 3 to its boat design; otherwise establish the approved Scene 1 boat as the reference and regenerate the downstream takes.
- Do not regenerate unaffected scenes merely to repair the prop unless the chosen reference direction requires it.

## Re-check acceptance
- Exactly one boat appears in Scene 1.
- Boat color, fold silhouette, and scale progression plausibly represent one recurring object across all scenes.
- Final render still matches approved replacement takes and contains no transition/aspect defects.
- Updated manifest and lineage identify the regenerated shot revision.
