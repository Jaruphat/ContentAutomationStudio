from __future__ import annotations
import json, re, subprocess
from fractions import Fraction
from pathlib import Path

ROOT=Path(r"<REPO>")
AUDIT=ROOT/r"docs\release_evidence\2026-09-02\full-system-multiscene-e2e\audit"
RENDER=ROOT/r"backend\data\exports\5df52248-ce4b-4a76-8c81-a436b21b6b46\review.mp4"
T2V=ROOT/r"backend\data\generated\87f6aff0-a2ef-46e9-8956-7418d9fa26a0_5df52248_9b56cb9b_00001_.mp4"
PROV=ROOT/r"backend\data\exports\5df52248-ce4b-4a76-8c81-a436b21b6b46\review.provenance.json"
MEDIA=ROOT/r"backend\data\release_checks\full-system-multiscene-e2e\media-phase.json"

def probe(path, args):
    p=subprocess.run(["ffprobe","-v","error",*args,"-of","json",str(path)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)

pr=probe(RENDER,["-show_streams","-show_format"])
frames=probe(RENDER,["-select_streams","v:0","-show_frames","-show_entries","frame=best_effort_timestamp_time,pkt_duration_time,pict_type"])["frames"]
pts=[float(x["best_effort_timestamp_time"]) for x in frames]
steps=[b-a for a,b in zip(pts,pts[1:])]
v=next(s for s in pr["streams"] if s["codec_type"]=="video")
a=next(s for s in pr["streams"] if s["codec_type"]=="audio")
vs=float(v["start_time"]); vd=float(v["duration"]); ast=float(a["start_time"]); ad=float(a["duration"])
fmt=float(pr["format"]["duration"])
avg=float(Fraction(v["avg_frame_rate"]))
expected=11.167
# silencedetect results measured separately: active final audio is 3.053167..8.139417.
active_audio_start=3.053167; active_audio_end=8.139417
scene2_start=3.0; scene2_end=8.167
actual_scene2_first_pts=min(p for p in pts if p >= scene2_start)
actual_scene3_first_pts=min(p for p in pts if p >= scene2_end)

# Metadata and byte-leakage scans on source/final/sidecar.
def printable_and_hits(path):
    data=path.read_bytes(); low=data.lower()
    terms=[b"prompt",b"workflow",b"comfyui",b"c:\\users\\",b"c:/users/",b"contentautomationstudio",b"backend\\data",b"backend/data",b".safetensors",b".ckpt",b"negative_prompt"]
    return {"size_bytes":len(data),"raw_case_insensitive_hits":{t.decode():low.count(t) for t in terms if low.count(t)}}

meta_tags={
 "format":pr["format"].get("tags",{}),
 "streams":[s.get("tags",{}) for s in pr["streams"]],
}
summary={
 "render":{
  "codec":v["codec_name"],"profile":v.get("profile"),"pixel_format":v["pix_fmt"],"width":v["width"],"height":v["height"],
  "sample_aspect_ratio":v.get("sample_aspect_ratio"),"display_aspect_ratio":v.get("display_aspect_ratio"),
  "declared_project_aspect_ratio":"16:9","pixel_aspect_ratio_decimal":v["width"]/v["height"],"sixteen_nine_decimal":16/9,
  "relative_width_excess_vs_16_9_percent":((v["width"]/v["height"])/(16/9)-1)*100,
  "r_frame_rate":v["r_frame_rate"],"avg_frame_rate":v["avg_frame_rate"],"avg_frame_rate_decimal":avg,"nb_frames":int(v["nb_frames"]),
  "video_start_sec":vs,"video_duration_sec":vd,"video_end_sec":vs+vd,"audio_start_sec":ast,"audio_duration_sec":ad,"audio_end_sec":ast+ad,
  "format_duration_sec":fmt,"timeline_expected_duration_sec":expected,"format_minus_timeline_ms":(fmt-expected)*1000,"video_duration_minus_timeline_ms":(vd-expected)*1000,
  "audio_leads_video_start_ms":(vs-ast)*1000,"audio_minus_video_end_ms":((ast+ad)-(vs+vd))*1000,
  "video_bitrate":int(v["bit_rate"]),"audio_codec":a["codec_name"],"audio_sample_rate":int(a["sample_rate"]),"audio_channels":a["channels"],"audio_bitrate":int(a["bit_rate"]),"container_bitrate":int(pr["format"]["bit_rate"]),"size_bytes":int(pr["format"]["size"]),
  "color_range":v.get("color_range"),"color_space":v.get("color_space"),"color_transfer":v.get("color_transfer"),"color_primaries":v.get("color_primaries"),
  "embedded_metadata":meta_tags,
 },
 "frame_timestamps":{
  "decoded_frame_count":len(pts),"first_pts_sec":pts[0],"last_pts_sec":pts[-1],"strictly_increasing":all(b>a for a,b in zip(pts,pts[1:])),
  "step_min_sec":min(steps),"step_max_sec":max(steps),"unique_rounded_steps_sec":sorted(set(round(x,6) for x in steps)),
  "frames_near_boundary_3s":[{"index":i,"pts":p} for i,p in enumerate(pts) if 2.90<=p<=3.10],
  "frames_near_boundary_8_167s":[{"index":i,"pts":p} for i,p in enumerate(pts) if 8.05<=p<=8.30],
 },
 "av_alignment":{
  "method":"stream start/end plus silencedetect at -50 dB; no dialogue/lip-sync event exists",
  "active_audio_start_sec":active_audio_start,"scene2_timeline_start_sec":scene2_start,"scene2_actual_first_video_pts_sec":actual_scene2_first_pts,
  "active_audio_lag_vs_timeline_ms":(active_audio_start-scene2_start)*1000,"active_audio_lag_vs_actual_video_ms":(active_audio_start-actual_scene2_first_pts)*1000,
  "active_audio_end_sec":active_audio_end,"scene3_timeline_start_sec":scene2_end,"scene3_actual_first_video_pts_sec":actual_scene3_first_pts,
  "active_audio_lead_vs_timeline_cut_ms":(scene2_end-active_audio_end)*1000,"active_audio_lead_vs_actual_scene3_frame_ms":(actual_scene3_first_pts-active_audio_end)*1000,
 },
 "leakage":{
  "final_mp4":printable_and_hits(RENDER),"source_t2v_mp4":printable_and_hits(T2V),"provenance_sidecar":printable_and_hits(PROV),"media_phase_json":printable_and_hits(MEDIA),
  "note":"ffprobe filename is supplied by the command and is not embedded metadata; embedded tags are listed separately"
 }
}
(AUDIT/"18_technical_timestamps_leakage_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
