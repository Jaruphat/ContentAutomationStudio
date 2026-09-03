# Post-reference release media QC

- Result: **PASS** for delivery-media technical gates.
- Delivery: `review.mp4`
- SHA-256: `2f649feed2855529cb9252c9852c4e7801bbc77b44450156847442a97df4397d`
- Video: H.264 High, yuv420p, 864×480, 24 fps, 268 frames, 11.196 s container duration.
- Aspect: stored and probed as **9:5** (`864×480`, SAR 1:1).
- Audio: AAC-LC, stereo, 48 kHz. Video starts at 0.020020 s and audio at 0.000000 s (20.020 ms delta).
- Loudness: source −52.74 LUFS; delivered −16.67 LUFS; true peak −2.01 dBTP; target achieved is recorded as `true` against −16 LUFS / −1.5 dBTP limits.
- Decode: full decode completed with no errors.
- Black-frame scan: no `black_start`/`black_end` events at 0.25 s / 10% threshold.
- Delivery metadata: only generic ISO container/handler/encoder tags; no prompt, workflow, model filename, or internal source path embedded. Detailed lineage stays in `review.provenance.json`.

The older visual-content audit remains historical evidence for the pre-reference run; the new Visual Reference Bible and real Boogu/H3 reference-conditioned smokes are captured in sibling evidence directories.
