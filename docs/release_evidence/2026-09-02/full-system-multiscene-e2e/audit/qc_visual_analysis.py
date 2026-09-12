from __future__ import annotations
import hashlib, json, math, os, re, subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(r"<REPO>")
AUDIT = ROOT / r"docs\release_evidence\2026-09-02\full-system-multiscene-e2e\audit"
FRAMES = AUDIT / "frames"
FRAMES.mkdir(parents=True, exist_ok=True)
RENDER = ROOT / r"backend\data\exports\5df52248-ce4b-4a76-8c81-a436b21b6b46\review.mp4"
T2V = ROOT / r"backend\data\generated\87f6aff0-a2ef-46e9-8956-7418d9fa26a0_5df52248_9b56cb9b_00001_.mp4"
S1 = ROOT / r"backend\data\generated\e909fb3a-00b8-490b-aaa0-a9bab4f8873a_5df52248_add1126f_00001_.png"
S3_APPROVED = ROOT / r"backend\data\generated\32c1fc90-9a42-426a-97cc-9f205a1897e1_5df52248_fef81802_00002_.png"
S3_REJECTED = ROOT / r"backend\data\generated\9dd9a330-2ff8-4c91-93c3-2b1e76a08e54_5df52248_fef81802_00001_.png"
SEG3 = ROOT / r"backend\data\exports\5df52248-ce4b-4a76-8c81-a436b21b6b46\segments\seg_0002.mp4"
FONT = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 22)
FONT_SMALL = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 18)

def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)

def extract(src: Path, t: float, name: str) -> Path:
    out = FRAMES / name
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.6f}", "-i", str(src), "-frames:v", "1", "-y", str(out)])
    return out

def fitted(path: Path, size=(432,240)) -> Image.Image:
    im = Image.open(path).convert("RGB")
    im.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, "black")
    canvas.paste(im, ((size[0]-im.width)//2, (size[1]-im.height)//2))
    return canvas

def sheet(panels, out: Path, cols: int, title: str):
    cell_w, image_h, label_h = 432, 240, 48
    rows = math.ceil(len(panels)/cols)
    canvas = Image.new("RGB", (cell_w*cols, 58 + (image_h+label_h)*rows), (28,28,28))
    d = ImageDraw.Draw(canvas)
    d.text((15,14), title, font=FONT, fill="white")
    for i,(path,label) in enumerate(panels):
        x=(i%cols)*cell_w; y=58+(i//cols)*(image_h+label_h)
        canvas.paste(fitted(path),(x,y))
        d.rectangle((x,y+image_h,x+cell_w,y+image_h+label_h), fill=(15,15,15))
        d.text((x+8,y+image_h+6),label,font=FONT_SMALL,fill="white")
    canvas.save(out)

# Extract storyboard/render representatives and boundary/T2V samples.
src2_mid = extract(T2V, 2.583333, "source_scene2_t2v_mid.png")
render_samples = {
    "s1_mid": extract(RENDER, 1.500000, "render_scene1_mid_1.500.png"),
    "s2_mid": extract(RENDER, 5.583333, "render_scene2_mid_5.583.png"),
    "s3_mid": extract(RENDER, 9.667000, "render_scene3_mid_9.667.png"),
}
boundary_times = [2.916667,2.958333,3.000000,3.041667,8.083333,8.125000,8.166667,8.208333]
boundary_paths=[]
for t in boundary_times:
    boundary_paths.append((extract(RENDER,t,f"boundary_{t:.6f}.png"),f"render t={t:.3f}s"))
t2v_times=[0.000000,0.833333,1.666667,2.583333,3.416667,4.250000,5.083333]
t2v_paths=[]
for t in t2v_times:
    t2v_paths.append((extract(T2V,t,f"t2v_{t:.6f}.png"),f"T2V t={t:.3f}s"))
seg3_frame=extract(SEG3,1.500000,"seg3_mid_1.500.png")

sheet([
    (S1,"Storyboard/source S1 approved"),(src2_mid,"Storyboard/source S2 T2V mid"),(S3_APPROVED,"Storyboard/source S3 regenerated"),
    (render_samples["s1_mid"],"Render S1 t=1.500s"),(render_samples["s2_mid"],"Render S2 t=5.583s"),(render_samples["s3_mid"],"Render S3 t=9.667s"),
], AUDIT/"07_storyboard_to_render_contact_sheet.png", 3, "Storyboard approved sources -> final render midpoints")
sheet(boundary_paths,AUDIT/"08_segment_boundaries_contact_sheet.png",4,"Boundary frames around 3.000s and 8.167s")
sheet(t2v_paths,AUDIT/"09_t2v_multiframe_contact_sheet.png",4,"Approved T2V take: temporal samples")
sheet([(S3_APPROVED,"Approved regenerated source"),(render_samples["s3_mid"],"Final render segment 3"),(seg3_frame,"Encoded seg_0002 midpoint"),(S3_REJECTED,"Rejected prior source")],AUDIT/"10_segment3_take_verification.png",4,"Segment 3 approved-vs-render-vs-rejected")

def metric(a_path: Path,b_path: Path):
    a=np.asarray(Image.open(a_path).convert("RGB"),dtype=np.float64)
    b=np.asarray(Image.open(b_path).convert("RGB").resize((a.shape[1],a.shape[0]),Image.Resampling.LANCZOS),dtype=np.float64)
    mse=float(np.mean((a-b)**2)); mae=float(np.mean(np.abs(a-b)))
    psnr=float("inf") if mse==0 else 10*math.log10(255*255/mse)
    # Global RGB SSIM; sufficient here to distinguish the two candidate still takes.
    mux=a.mean(axis=(0,1)); muy=b.mean(axis=(0,1)); vx=a.var(axis=(0,1)); vy=b.var(axis=(0,1)); cov=((a-mux)*(b-muy)).mean(axis=(0,1))
    c1=(0.01*255)**2; c2=(0.03*255)**2
    ssim=np.mean(((2*mux*muy+c1)*(2*cov+c2))/((mux*mux+muy*muy+c1)*(vx+vy+c2)))
    return {"mse":mse,"mae":mae,"psnr_db":psnr,"global_ssim":float(ssim)}

metrics={
 "render_s1_vs_approved_source":metric(render_samples["s1_mid"],S1),
 "render_s2_mid_vs_t2v_source_mid":metric(render_samples["s2_mid"],src2_mid),
 "render_s3_vs_approved_regenerated":metric(render_samples["s3_mid"],S3_APPROVED),
 "render_s3_vs_rejected":metric(render_samples["s3_mid"],S3_REJECTED),
 "seg3_vs_approved_regenerated":metric(seg3_frame,S3_APPROVED),
 "seg3_vs_rejected":metric(seg3_frame,S3_REJECTED),
}

def frame_diffs(src: Path, fps=24.0):
    p=subprocess.Popen(["ffmpeg","-hide_banner","-loglevel","error","-i",str(src),"-vf","scale=216:120,format=gray","-fps_mode","passthrough","-f","rawvideo","-pix_fmt","gray","-"],stdout=subprocess.PIPE)
    frame_bytes=216*120; prev=None; diffs=[]; hashes=[]; idx=0
    while True:
        data=p.stdout.read(frame_bytes)
        if not data: break
        if len(data)!=frame_bytes: raise RuntimeError(f"short frame {len(data)}")
        arr=np.frombuffer(data,dtype=np.uint8).astype(np.int16)
        hashes.append(hashlib.sha256(data).hexdigest())
        if prev is not None:
            diffs.append({"from_frame":idx-1,"to_frame":idx,"time_sec":idx/fps,"mae":float(np.mean(np.abs(arr-prev))),"max_abs":int(np.max(np.abs(arr-prev)))})
        prev=arr; idx+=1
    rc=p.wait()
    if rc: raise RuntimeError(f"ffmpeg decode rc={rc}")
    vals=np.array([x["mae"] for x in diffs])
    ranked=sorted(diffs,key=lambda x:x["mae"],reverse=True)[:12]
    return {"frame_count":idx,"transition_count":len(diffs),"exact_duplicate_transitions":sum(hashes[i]==hashes[i-1] for i in range(1,len(hashes))),"mae_min":float(vals.min()),"mae_p05":float(np.percentile(vals,5)),"mae_median":float(np.median(vals)),"mae_p95":float(np.percentile(vals,95)),"mae_max":float(vals.max()),"largest_transitions":ranked,"around_3s":[x for x in diffs if 2.85<=x["time_sec"]<=3.15],"around_8_167s":[x for x in diffs if 8.0<=x["time_sec"]<=8.3]}

temporal={"final_render":frame_diffs(RENDER),"approved_t2v":frame_diffs(T2V)}

# Delivery byte scan: printable ASCII/UTF-16LE strings plus direct case-insensitive keyword/path scans.
data=RENDER.read_bytes()
ascii_strings=[m.group().decode("ascii","replace") for m in re.finditer(rb"[ -~]{4,}",data)]
utf16_strings=[m.group().decode("utf-16le","replace") for m in re.finditer(rb"(?:[ -~]\x00){4,}",data)]
terms=["prompt","workflow","comfyui","users\\","users/","contentautomationstudio","backend\\data","backend/data",".safetensors",".ckpt","negative_prompt","dawn pond","child's hand"]
term_hits={t:[] for t in terms}
for s in ascii_strings+utf16_strings:
    low=s.lower()
    for t in terms:
        if t in low: term_hits[t].append(s[:500])
term_hits={k:v for k,v in term_hits.items() if v}

report={
 "files_created":[str(p) for p in sorted(AUDIT.glob("*.png"))]+[str(FRAMES)],
 "source_render_similarity":metrics,
 "temporal_frame_diff":temporal,
 "delivery_scan":{"size_bytes":len(data),"ascii_string_count":len(ascii_strings),"utf16le_string_count":len(utf16_strings),"suspicious_term_hits":term_hits,"all_printable_strings":ascii_strings+utf16_strings},
}
(AUDIT/"11_visual_temporal_leakage_metrics.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps({"contact_sheets":[str(AUDIT/f) for f in ["07_storyboard_to_render_contact_sheet.png","08_segment_boundaries_contact_sheet.png","09_t2v_multiframe_contact_sheet.png","10_segment3_take_verification.png"]],"metrics":metrics,"temporal_summary":{k:{kk:vv for kk,vv in v.items() if kk not in ("largest_transitions","around_3s","around_8_167s")} for k,v in temporal.items()},"delivery_suspicious_term_hits":term_hits},indent=2))
