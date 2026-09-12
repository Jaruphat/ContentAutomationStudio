# Release evidence

Each directory here is the record of one verification run: the screenshots,
contact sheets, job records, ffprobe output and loudness measurements that a
claim in the main [README](../../README.md) rests on. They are kept so that
"verified working" can be checked rather than taken on trust.

Two things to know when reading them.

**Absolute paths are redacted.** These files were written by the application,
so they carry the full path of everything they touched on the workstation that
produced them. Before this repository was published, the repository root was
replaced with `<REPO>` and any remaining home directory with
`C:\Users\<user>`, uniformly, across every text record. Nothing else was
changed: the hashes, durations, measurements and filenames are as they were
recorded.

**They describe one machine.** Every timing was measured on an RTX 5080 (16 GB)
running ComfyUI 0.34.0 on Windows. A different card will produce different
numbers; the point of the record is what ran and what came out, not that your
run will take the same time.
