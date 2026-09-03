# รายงาน QC อิสระ — 3-scene mixed-media render

- Project: `5df52248-ce4b-4a76-8c81-a436b21b6b46`
- Render: `backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4`
- ตรวจเมื่อ: 2026-09-02
- ผลรวม: **WARN** — ภาพ/ไทม์ไลน์/ไฟล์ส่งมอบใช้งานได้และ segment 3 ถูก take แต่เสียงเบามาก, aspect ratio ที่ประกาศไม่ตรง pixel DAR, color tags หาย, และมีข้อสังเกตด้านภาพ/continuity

## ผลตามหัวข้อ

### 1) ความสมบูรณ์ของไฟล์และสเปก — PASS/WARN

**PASS**
- SHA-256 render: `9dd5a119b2f654d6bc0182a5b5d421f679020de28917abdb718fc69d051e5948` ตรงกับ media-phase/provenance
- Decode ทั้ง final และ approved T2V สำเร็จ: `exit=0`, ไม่มี decoder error
- Final video: H.264 High, `yuv420p`, `864x480`, progressive, SAR `1:1`, `24/1` nominal, average `274432/11435 = 23.99930039352864 fps`, 268 frames, video duration `11.166992 s`
- Final audio: AAC-LC, `48000 Hz`, stereo, `90534 b/s`; container duration `11.188333 s`; file `530358` bytes; container bitrate `379222 b/s`
- Segment durations/frames: S1 `3.000000 s / 72`, S2 `5.166667 s / 124`, S3 `3.000000 s / 72`; รวม video `11.166992 s` เทียบ timeline `11.167 s` ต่าง `-0.008 ms`
- PTS video 268 เฟรมเพิ่มขึ้นอย่างเคร่งครัด; step `0.041666–0.041992 s`

**WARN**
- Pixel DAR คือ `9:5 = 1.8`, แต่ provenance ประกาศ `16:9 = 1.777777...`; กว้างกว่า 16:9 `1.25%`. ไม่เห็นการยืดภาพภายใน render เพราะ source และ output ใช้ 864x480 เหมือนกัน แต่ declaration ไม่ตรง bytes จริง
- Final video ไม่ระบุ `color_range/color_space/color_transfer/color_primaries`; approved T2V source ระบุ `tv / bt709 / iec61966-2-1 / bt709`. ภาพที่ตรวจไม่พบ color corruption แต่ playback ข้ามอุปกรณ์อาจตีความต่างกัน

หลักฐาน: `00_tools_files_hashes.txt`, `01_ffprobe_review.json`, `02_ffprobe_t2v.json`, `13_probe_segments.txt`, `14_decode_integrity.txt`, `18_technical_timestamps_leakage_summary.json`

### 2) Segment boundaries — PASS

- Cut 1: เฟรมก่อน cut ที่ `2.917/2.958 s` เป็น scene 1; ตัวอย่างที่ request `3.000/3.042 s` เป็น scene 2. PTS เฟรม scene 2 แรกจริง `3.020996 s` (ทั้ง video track offset `+20.996 ms`)
- Cut 2: `8.083/8.125 s` เป็น scene 2; `8.167/8.208 s` เป็น scene 3. PTS เฟรม scene 3 แรกจริง `8.187988 s`
- ไม่พบ black/blank/corrupt frame, blended transition หรือ flash ที่ cut; เป็น hard cuts ตาม manifest
- Frame-difference spikes ใหญ่สุดเกิดเฉพาะ cut: MAE `93.1162` รอบ cut 1 และ `68.3570` รอบ cut 2; T2V ภายในมี MAE สูงสุดเพียง `3.7100`

หลักฐาน: `08_segment_boundaries_contact_sheet.png`, `11_visual_temporal_leakage_metrics.json`, `18_technical_timestamps_leakage_summary.json`

### 3) Black/frozen/temporal — PASS/WARN

**PASS**
- `blackdetect=d=0.04:pix_th=0.10` ไม่รายงาน `black_start` ทั้ง final, T2V และแต่ละ segment
- `freezedetect=n=-50dB:d=0.20`: S1 และ S3 freeze ตั้งแต่ต้นตามคาด เพราะเป็น still-image segments; approved T2V ไม่มี freeze event
- Approved T2V: 124 frames, ไม่มี exact duplicate transition; frame-difference MAE ต่อเฟรม `min 2.2056`, `median 3.1397`, `p95 3.6211`, `max 3.7100`; ไม่พบ objective jump/frozen run

**WARN (visual)**
- เด็ก/เสื้อกันฝน/สระ/ต้นไม้คงรูปดีโดยรวม ไม่มี identity swap หรือ gross anatomy failure
- เรือเคลื่อนขวาต่อเนื่อง แต่ทรง/สีเรือเปลี่ยนเล็กน้อยช่วงประมาณ `0.833–1.667 s` (ขอบ/ฐานมืดและรูปพับดู morph ก่อนคงรูปชัดขึ้น); มือใกล้เรือดูรวมกับวัตถุบางเฟรม
- กล้องดูเกือบคงที่มากกว่าการ “slowly tracks the boat” อย่างชัดเจน จึงตรง motion prompt เพียงบางส่วน
- ไม่พบ text/logo/watermark ในเฟรมตัวอย่าง

หลักฐาน: `05_black_freeze_review.txt`, `06_black_freeze_t2v.txt`, `09_t2v_multiframe_contact_sheet.png`, `17_black_freeze_segments.txt`, `11_visual_temporal_leakage_metrics.json`

### 4) Composition/style/subject continuity — WARN

- Style photorealistic cinematic, misty pond, blue raincoat, short dark hair และ dawn palette สอดคล้องทั้ง 3 scenes
- S1→S2: identity/wardrobe/shoreline ต่อเนื่องดี; framing เปลี่ยนจาก medium close-up เป็น medium crouch ตาม action
- S3: wide shot และเด็กยืนขวาตาม storyboard; แต่เรือดูสีน้ำเงิน/เทาเข้มมากกว่าสีขาว และโทนโดยรวมเย็นลง แม้มีแถบแสงอาทิตย์
- Screen geography กระโดดที่ cut 2: scene 2 วางเด็กซ้าย/เรือขวา แต่ scene 3 วางเรือซ้าย/เด็กขวา; อ่านเรื่องได้แต่ continuity เชิงทิศทางไม่ลื่น
- S1 อาจอ่านได้ว่าเห็นเรือพับแล้วหนึ่งลำมุมล่างซ้าย ขณะที่เด็กกำลังพับอีกชิ้น ซึ่งเสี่ยงขัด negative prompt “extra boats”
- ไม่พบ cropping, stretch, watermark หรือ on-screen text ที่ไม่ตั้งใจ

หลักฐาน: `07_storyboard_to_render_contact_sheet.png`, `08_segment_boundaries_contact_sheet.png`, `09_t2v_multiframe_contact_sheet.png`

### 5) Audio/loudness/A-V alignment — WARN

- Full render loudness: integrated `-52.74 LUFS`, true peak `-29.21 dBTP`, LRA `8.10 LU`
- Active scene 2 only: `-52.14 LUFS`, true peak `-29.21 dBTP`, LRA `0.40 LU`; source T2V `-52.46 LUFS`, `-29.17 dBTP`. เสียงแทบไม่ได้ถูกเพิ่มระดับหลัง conform และเบามากสำหรับ delivery ทั่วไป
- Silence ตามเจตนาของ still scenes: `0–3.053167 s` และ `8.139417–11.196333 s`
- Audio stream เริ่ม `0.000000 s`, video เริ่ม `0.020996 s` (audio lead `20.996 ms`); ปลาย audio ช้ากว่าปลาย video `0.345 ms`
- เสียง active เริ่มหลัง video scene 2 frame แรก `32.171 ms` และจบก่อน scene 3 frameแรก `48.571 ms`; อยู่ราว 1 เฟรมและไม่มี dialogue/lip-sync event ให้ทดสอบ offset เชิงปาก จึงไม่พบ A/V sync defect ที่มีนัย แต่ loudness เป็นข้อเตือนหลัก

หลักฐาน: `03_loudnorm_review.txt`, `04_audio_analysis_review.txt`, `15_loudnorm_t2v_source.txt`, `16_loudnorm_render_active_scene.txt`, `18_technical_timestamps_leakage_summary.json`

### 6) Delivery leakage — PASS สำหรับ MP4 / WARN สำหรับ sidecar หากส่งภายนอก

**PASS — `review.mp4`**
- ffprobe embedded tags มีเพียง `major_brand`, `minor_version`, `compatible_brands`, `encoder`, `language`, `handler_name`
- Raw case-insensitive byte scan ของ 530358 bytes ไม่พบ: `prompt`, `workflow`, `comfyui`, `C:\Users\`, `C:/Users/`, `ContentAutomationStudio`, `backend/data`, `backend\\data`, `.safetensors`, `.ckpt`, `negative_prompt`
- เปรียบเทียบ source T2V พบ `prompt` 2, `comfyui` 1, `.safetensors` 5 แต่ final เป็นศูนย์ ยืนยันว่าการ strip metadata ทำงาน

**WARN — sidecars ไม่ใช่ไฟล์ public-safe โดยอัตโนมัติ**
- `review.provenance.json` มี `prompt` 14, `workflow` 10, `comfyui` 3, `contentautomationstudio` 7, `negative_prompt` 3 และมี source/workflow snapshot paths โดยเจตนา
- `media-phase.json` ก็มี prompt/workflow/provider/internal path data. เก็บเป็น internal audit provenance; อย่าแนบเป็น public delivery หากนโยบายห้ามเปิดเผย

หลักฐาน: `01_ffprobe_review.json`, `02_ffprobe_t2v.json`, `11_visual_temporal_leakage_metrics.json`, `18_technical_timestamps_leakage_summary.json`

### 7) Segment 3 regenerated approved take — PASS

- Timeline order 2 ใช้ take `19ccc0f0-41ad-433e-8cbc-09dcabc7f76d` ซึ่ง media phase ระบุเป็น `approved_regenerated_take_id`
- Provenance segment index 2 ใช้ source `32c1fc90-9a42-426a-97cc-9f205a1897e1_5df52248_fef81802_00002_.png`, SHA-256 `9d23ca02badfb7e6a1e36d33a625d09728f6f7763eea95a23348f1adb33a35d6`
- Rejected take คือ `7bcdcf55-5efe-42c8-9dba-43d8aa456cc4`, source `9dd9a330-..._00001_.png`, SHA-256 `841ebf7cd1174f86c42f58839a79c1e140615125447d07eb97f228f66689d97e`
- Final S3 และ `seg_0002` เทียบ approved regenerated: PSNR `38.8911 dB`, global SSIM `0.998974`, MAE `2.08316`
- เทียบ rejected: PSNR `15.7810 dB`, global SSIM `0.758903`, MAE `31.2521`
- ลักษณะภาพ final/approved ตรงกัน: เรืออยู่ซ้ายกลาง, เด็กชิดฝั่งขวา, ต้นไม้ใหญ่กลางขวา; rejected มีดวงอาทิตย์/เรือกลางภาพเด่นและเด็กชิดขอบขวาต่างชัดเจน

หลักฐาน: `10_segment3_take_verification.png`, `11_visual_temporal_leakage_metrics.json`, `00_tools_files_hashes.txt`

## คำสั่งหลักที่ใช้ (exact)

```bash
sha256sum "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4" "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/generated/e909fb3a-00b8-490b-aaa0-a9bab4f8873a_5df52248_add1126f_00001_.png" "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/generated/87f6aff0-a2ef-46e9-8956-7418d9fa26a0_5df52248_9b56cb9b_00001_.mp4" "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/generated/32c1fc90-9a42-426a-97cc-9f205a1897e1_5df52248_fef81802_00002_.png" "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/generated/9dd9a330-2ff8-4c91-93c3-2b1e76a08e54_5df52248_fef81802_00001_.png"

ffprobe -v error -show_format -show_streams -show_programs -show_chapters -print_format json "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4"

ffprobe -v error -count_frames -count_packets -show_entries format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,pix_fmt,r_frame_rate,avg_frame_rate,start_time,duration,nb_frames,nb_read_frames,nb_read_packets,sample_rate,channels,channel_layout -of default=noprint_wrappers=1 "<review-or-segment-path>"

ffmpeg -v error -xerror -i "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4" -map 0 -f null -

ffmpeg -hide_banner -nostats -i "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4" -af loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json -f null -

ffmpeg -hide_banner -nostats -i "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4" -af "silencedetect=noise=-50dB:d=0.25,astats=metadata=1:reset=0" -f null -

ffmpeg -hide_banner -nostats -i "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/backend/data/exports/5df52248-ce4b-4a76-8c81-a436b21b6b46/review.mp4" -vf "blackdetect=d=0.04:pix_th=0.10,freezedetect=n=-50dB:d=0.20" -an -f null -

python "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/docs/release_evidence/2026-09-02/full-system-multiscene-e2e/audit/qc_visual_analysis.py"
python "C:/Users/jongp/Desktop/Thinkpad_and_PC_Sync/ContentAutomationStudio/docs/release_evidence/2026-09-02/full-system-multiscene-e2e/audit/qc_technical_analysis.py"
```

หมายเหตุ: คำสั่งเต็มพร้อม path/redirect และ stdout/stderr จริงอยู่ในไฟล์หลักฐานหมายเลข `00–19`; scripts บันทึก exact ffmpeg/ffprobe subprocess arguments และสร้างหลักฐานเฉพาะใต้โฟลเดอร์ audit นี้เท่านั้น
