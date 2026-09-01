# Product Requirements Document (PRD)

## Content Automation Studio

| รายการ | รายละเอียด |
|---|---|
| ประเภทผลิตภัณฑ์ | AI-assisted Storyboard, Image/Video Generation and Automated Editing Platform |
| เวอร์ชันเอกสาร | 0.1 — Concept and MVP Draft |
| สถานะ | Draft for Review |
| ผู้ใช้เป้าหมาย | Content creator, creative producer, video editor และทีมสื่อขนาดเล็ก |
| ระบบสร้างสื่อหลัก | ComfyUI ผ่าน Workflow JSON โดยเริ่มรองรับ Workflow H3 |
| รูปแบบติดตั้งเป้าหมาย | Local-first web application; ขยายเป็นทีม/เซิร์ฟเวอร์ได้ในอนาคต |

> **ข้อสมมติ:** “H3” หมายถึง ComfyUI workflow ที่ผู้ใช้มีและสามารถ export เป็น API-format JSON ได้ ทั้ง workflow สร้างภาพและสร้างวิดีโอ ยังไม่ได้รับไฟล์ JSON จริง จึงออกแบบระบบ mapping ให้รองรับ workflow ที่เปลี่ยน node และ parameter ได้โดยไม่ hardcode

---

## 1. Executive Summary

**Content Automation Studio** เป็นระบบผลิตคอนเทนต์แบบครบสายงาน ตั้งแต่รับแนวคิดหรือ plot จากผู้ใช้ แตกเรื่องเป็น scene และ shot สร้าง storyboard พร้อม prompt รายฉาก ส่งงานไปสร้างภาพหรือวิดีโอผ่าน ComfyUI Workflow H3 ตรวจผลและสร้างใหม่เฉพาะฉากที่ไม่ผ่าน จากนั้นนำ asset ที่อนุมัติแล้วมาประกอบเป็นวิดีโอโดยอัตโนมัติ พร้อมเสียง คำบรรยาย transition และไฟล์ส่งออก

ระบบต้องมีลักษณะ **human-in-the-loop**: ผู้ใช้สามารถแก้ plot, scene, shot, prompt, seed, reference image และผลลัพธ์ได้ทุกขั้น ไม่ควรเป็น black box ที่กดครั้งเดียวแล้วแก้ไม่ได้ จุดสำคัญคือการรักษาความต่อเนื่องของตัวละคร ฉาก และสไตล์ ตลอดจนการตรวจสอบที่มาของไฟล์ พารามิเตอร์ และ workflow version เพื่อให้สร้างซ้ำได้

MVP จะรองรับโครงการหนึ่งเรื่อง แบ่งเป็น scenes/shots สร้างภาพนิ่งหรือวิดีโอจาก ComfyUI จัดคิวงาน ตรวจผล เลือก take และประกอบวิดีโอด้วย FFmpeg โดยไม่รวมระบบทีมขั้นสูง การชำระเงิน หรือระบบเผยแพร่หลายแพลตฟอร์ม

---

## 2. Product Vision

> “เปลี่ยน plot หนึ่งเรื่องให้กลายเป็น storyboard, generated assets และวิดีโอฉบับร่างที่ตรวจสอบและสร้างซ้ำได้จากระบบเดียว”

### 2.1 คุณค่าหลัก

1. **Structured Creativity:** เปลี่ยนความคิดอิสระเป็นโครงสร้าง Project → Scene → Shot → Asset → Timeline
2. **Workflow Reuse:** ใช้ ComfyUI workflow เดิมซ้ำผ่าน template และ parameter mapping
3. **Creative Control:** แก้ได้ทุกขั้น และล็อกข้อมูลที่ไม่ต้องการให้ AI เปลี่ยน
4. **Consistency:** มี Character Bible, Location Bible และ Style Bible เป็น context กลาง
5. **Traceability:** ทุก asset ระบุ prompt, seed, model, workflow version, source และสถานะอนุมัติ
6. **Selective Regeneration:** สร้างใหม่เฉพาะ shot หรือ asset ที่ไม่ผ่าน
7. **Automated Assembly:** ประกอบวิดีโอ draft โดยไม่ต้องลากไฟล์เองทุกครั้ง

---

## 3. Goals and Non-Goals

### 3.1 เป้าหมาย MVP

- รับ plot ที่ผู้ใช้เขียนเอง หรือสร้าง plot จาก brief
- แตก plot เป็น scene และ shot อย่างเป็นโครงสร้าง
- สร้าง storyboard table และ prompt สำหรับภาพ/วิดีโอราย shot
- Import และ validate ComfyUI API-format workflow JSON
- Mapping field เช่น prompt, negative prompt, seed, width, height, frames และ output prefix ไปยัง node ของ H3
- ส่งงานไป ComfyUI, ตรวจสถานะ, ดาวน์โหลด/จัดเก็บผลลัพธ์ และ retry เมื่อผิดพลาด
- สร้างภาพนิ่งและวิดีโอ โดยเลือก workflow ตามประเภท shot
- รองรับ reference image และข้อมูล consistency
- ให้ผู้ใช้ approve/reject/regenerate take
- ประกอบ take ที่อนุมัติแล้วเป็นวิดีโอ draft ด้วย FFmpeg
- บันทึก project state เพื่อกลับมาทำงานต่อได้
- Export storyboard, prompt package, generation manifest และ final video

### 3.2 สิ่งที่ไม่รวมใน MVP

- ระบบ social publishing อัตโนมัติ
- Multi-tenant SaaS และ billing
- Marketplace สำหรับ workflow/model
- Real-time collaborative editing
- Training/fine-tuning model ภายในระบบ
- Automatic lip-sync ขั้นสูง
- ระบบจัดการลิขสิทธิ์อัตโนมัติเต็มรูปแบบ
- การรับประกันความถูกต้องของเนื้อหาที่ AI สร้าง

---

## 4. Target Users and Roles

| Role | ความต้องการหลัก |
|---|---|
| Creator | ใส่ไอเดีย สร้าง storyboard และได้วิดีโอ draft เร็ว |
| Creative Producer | ควบคุมเรื่อง โทน ตัวละคร และอนุมัติแต่ละ scene |
| Prompt Designer | แก้ prompt และ workflow parameters ราย shot |
| Video Editor | ปรับ timeline, duration, transition, audio และ export |
| Technical Operator | ดูแล ComfyUI, model, queue, VRAM และ workflow version |

MVP อาจใช้ผู้ใช้คนเดียวทำทุก role แต่โครงสร้างข้อมูลควรรองรับการแยก role ในอนาคต

---

## 5. End-to-End Workflow

1. **Create Project** — ตั้งชื่อ project, format, aspect ratio, duration และสไตล์
2. **Story Intake** — ใส่ plot เองหรือสร้างจาก brief
3. **Story Planning** — สร้าง synopsis, acts/beats, characters, locations และ style bible
4. **Scene Breakdown** — แตกเป็น scenes โดยกำหนดวัตถุประสงค์ เหตุการณ์ ตัวละคร สถานที่ และ duration
5. **Shot Planning** — แตก scene เป็น shots พร้อม shot type, camera, action, dialogue และ duration
6. **Storyboard Review** — ผู้ใช้แก้ไข ล็อก และอนุมัติ shot list
7. **Prompt Compilation** — รวม shot prompt กับ character/location/style constraints
8. **Generation Planning** — เลือก image/video workflow, preset, seed policy และ reference assets
9. **Queue Execution** — ส่ง jobs ไป ComfyUI และติดตามสถานะ
10. **Take Review** — แสดง outputs หลาย take ให้ approve/reject/regenerate
11. **Timeline Assembly** — นำ approved takes เรียงตาม shot order
12. **Audio/Subtitles** — เพิ่ม voice, ambience, music, captions ตามที่มี
13. **Automated Edit** — trim, scale, crop, transition, loudness และ encode
14. **QC Review** — ตรวจ missing shot, duration, aspect ratio, black frame, audio และ subtitle
15. **Export** — video, storyboard, prompt manifest และ project archive

---

## 6. Information Architecture

```text
Workspace
└─ Project
   ├─ Brief and Plot
   ├─ Story Bible
   │  ├─ Characters
   │  ├─ Locations
   │  └─ Visual Style
   ├─ Scenes
   │  └─ Shots
   │     ├─ Prompt Package
   │     ├─ Generation Jobs
   │     ├─ Takes
   │     └─ Approved Asset
   ├─ Audio
   ├─ Timeline
   ├─ Exports
   └─ Logs and Manifests
```

---

## 7. Core Data Model

### 7.1 Project

- projectId
- title
- objective
- audience
- contentType
- aspectRatio
- targetResolution
- targetDuration
- frameRate
- language
- defaultImageWorkflowId
- defaultVideoWorkflowId
- status
- createdAt / updatedAt

### 7.2 Story Bible

**Character**
- characterId, name, role, age range, appearance, clothing, color palette
- personality, expression set, prohibited changes
- reference images, LoRA/model references, prompt tokens

**Location**
- locationId, name, description, geography/layout, time of day
- palette, lighting, props, reference images, prohibited changes

**Style**
- styleId, medium, genre, visual keywords, camera language
- palette, lighting rules, texture, negative constraints
- model/checkpoint/LoRA recommendations

### 7.3 Scene

- sceneId, order, title, purpose, summary
- characters, location, time, emotional beat
- plannedDuration, continuityIn, continuityOut
- status: Draft / Reviewed / Locked / Generated / Approved

### 7.4 Shot

- shotId, sceneId, order
- shotType, cameraAngle, cameraMovement, lens/framing
- subject, action, environment, dialogue/voiceover
- plannedDuration, generationMode: image / video / image-to-video
- imagePrompt, videoPrompt, negativePrompt
- referenceAssetIds
- workflowPresetId, seedPolicy, status

### 7.5 Generation Job

- jobId, shotId, workflowId, workflowVersion
- workflowSnapshotPath
- parameterMap, seed, model identifiers
- submittedAt, startedAt, completedAt
- ComfyUI promptId
- status: Queued / Running / Completed / Failed / Cancelled
- attempts, errorCode, errorMessage, outputs

### 7.6 Take

- takeId, shotId, jobId, filePath, thumbnailPath
- duration, width, height, frameRate, codec
- reviewStatus, rating, notes, approvedAt
- provenance manifest

---

## 8. Story and Storyboard Module

### 8.1 Story Input Modes

1. **Manual Plot:** ผู้ใช้วาง plot เต็มเรื่อง
2. **Guided Brief:** ผู้ใช้กรอก genre, audience, message, duration, characters และ ending
3. **AI Draft:** ระบบเสนอ plot จาก brief โดยผู้ใช้ต้อง approve ก่อนแตก scene
4. **Import:** รับ Markdown/JSON จากระบบภายนอก

### 8.2 Scene Breakdown Output

แต่ละ scene ต้องตอบให้ได้:

- เกิดอะไรขึ้น
- ทำไม scene นี้จำเป็นต่อเรื่อง
- ใครอยู่ใน scene
- สถานที่และเวลา
- จุดเริ่มและจุดจบด้าน continuity
- ความยาวเป้าหมาย
- จำนวน shots ที่เหมาะสม

### 8.3 Storyboard View

แสดงเป็นตารางหรือ cards:

| Shot | Preview | Duration | Camera | Action | Prompt | Workflow | Status |
|---|---|---:|---|---|---|---|---|

รองรับ:

- reorder ด้วย drag-and-drop
- duplicate shot
- split/merge shot
- lock scene/shot
- bulk edit style tokens
- compare prompt versions
- export Markdown, CSV และ JSON

---

## 9. Prompt System

### 9.1 Prompt Layers

Final prompt ประกอบจาก:

1. Global style prompt
2. Character constraints
3. Location constraints
4. Scene context
5. Shot camera/framing
6. Action and expression
7. Technical generation tokens
8. Negative prompt

### 9.2 Prompt Template Example

```text
[STYLE]
[CHARACTER_APPEARANCE]
[LOCATION_AND_TIME]
[SHOT_TYPE], [CAMERA_ANGLE], [CAMERA_MOVEMENT]
[ACTION], [EXPRESSION], [COMPOSITION]
[LIGHTING], [COLOR_PALETTE]
[TECHNICAL_TOKENS]
```

### 9.3 Prompt Versioning

- เก็บ promptVersion ทุกครั้งที่แก้
- แยก user-authored text จาก AI-generated text
- แสดง diff ระหว่าง version
- regenerate ต้องอ้างอิง prompt version ที่แน่นอน
- ห้ามแก้ locked tokens ของ character/location โดยไม่เตือน

### 9.4 Consistency Controls

- fixed or controlled seed policy
- shared character references
- reusable style preset
- model/checkpoint/LoRA lock ต่อ sequence
- prompt tokens ที่ห้ามเปลี่ยน
- continuity note ระหว่าง shot ก่อนหน้าและถัดไป

---

## 10. ComfyUI Workflow Integration

### 10.1 Workflow Registry

ระบบเก็บ workflow เป็น template record:

- workflowId และชื่อแสดง
- purpose: image / text-to-video / image-to-video
- source JSON path
- SHA-256 hash
- version
- required models/custom nodes
- parameter mapping
- output node mapping
- tested ComfyUI version
- validation status

### 10.2 H3 Adapter

ห้าม hardcode node ID ของ H3 ลง business logic โดยตรง ให้สร้าง adapter/preset เช่น:

```json
{
  "workflowId": "h3-image-v1",
  "inputs": {
    "positivePrompt": {"nodeId": "6", "field": "text"},
    "negativePrompt": {"nodeId": "7", "field": "text"},
    "seed": {"nodeId": "3", "field": "seed"},
    "width": {"nodeId": "5", "field": "width"},
    "height": {"nodeId": "5", "field": "height"},
    "referenceImage": {"nodeId": "12", "field": "image"}
  },
  "outputs": [{"nodeId": "18", "type": "image"}]
}
```

เมื่อ import workflow ใหม่ ระบบต้องตรวจว่า node/field ที่ mapping ยังมีอยู่

### 10.3 Preflight Validation

ก่อนส่ง job:

- JSON parse ได้
- node mapping ครบ
- required models/checkpoints/LoRA มีอยู่
- custom nodes พร้อม
- input files เข้าถึงได้
- output path ถูกต้อง
- width/height/frame count อยู่ใน preset ที่รองรับ
- ComfyUI online และ queue ตอบสนอง

### 10.4 Queue and Execution

- ส่ง job ทีละรายการหรือ batch
- concurrency กำหนดตาม GPU/VRAM profile
- pause/resume/cancel queue
- retry เฉพาะ transient error
- exponential backoff สำหรับการเชื่อมต่อ
- เก็บ workflow snapshot ต่อ job เพื่อ reproducibility
- ไม่เปลี่ยน workflow กลาง batch โดยไม่สร้าง version ใหม่

### 10.5 Error Categories

- ConnectionError
- WorkflowValidationError
- MissingModelError
- MissingCustomNodeError
- OutOfMemoryError
- GenerationTimeout
- OutputMissingError
- MediaValidationError

ระบบต้องเสนอ action ที่เหมาะสม ไม่ retry OOM แบบไม่จำกัด

---

## 11. Image and Video Generation

### 11.1 Image Modes

- Text-to-image storyboard frame
- Character reference generation
- Location reference generation
- Shot keyframe
- Variation from approved take
- Inpainting/outpainting หลัง MVP

### 11.2 Video Modes

- Text-to-video
- Image-to-video จาก approved keyframe
- Start/end-frame guided video หาก workflow รองรับ
- Motion preset เช่น static, pan, push-in, orbit, character action

### 11.3 Take Strategy

- ค่าเริ่มต้น 2–4 takes ต่อ shot สำหรับภาพ
- วิดีโอเริ่ม 1–2 takes เนื่องจากต้นทุนสูง
- ผู้ใช้กำหนด generation budget ต่อ project/scene
- เก็บทุก take แต่เลือกเพียงหนึ่ง approved take ต่อตำแหน่ง timeline

---

## 12. Review and Approval

### 12.1 Review States

Draft → Ready to Generate → Generating → Generated → Needs Review → Approved / Rejected

### 12.2 Review Tools

- side-by-side take comparison
- mark preferred take
- notes และ reason code
- regenerate with same seed / new seed / edited prompt
- replace asset from local file
- lock approved asset
- batch approve เฉพาะเมื่อผ่าน validation

### 12.3 Suggested QC Checks

- subject count ถูกต้อง
- character identity/wardrobe ต่อเนื่อง
- location and time continuity
- anatomy/visual artifact
- text artifact
- camera direction consistency
- frame dimensions/duration/frame rate
- NSFW/safety check ตามนโยบายที่กำหนด

---

## 13. Automated Video Assembly

### 13.1 Timeline Model

แต่ละ timeline item เก็บ:

- shotId และ takeId
- in/out point
- duration
- scale/crop/position
- transitionIn/transitionOut
- dialogue/voice/music/ambience references
- subtitle cue

### 13.2 Assembly Rules

- ใช้ approved take เท่านั้น
- normalize resolution, pixel format และ frame rate ก่อน concat
- still image ใช้ hold + optional Ken Burns motion
- video trim ตาม shot duration
- transition ค่าเริ่มต้นเป็น cut; dissolve ใช้ตาม rule เท่านั้น
- audio normalize ตาม target profile
- missing shot ให้หยุด export หรือสร้าง placeholder ตาม setting

### 13.3 FFmpeg Pipeline

1. Probe media
2. Generate per-shot normalized intermediates/proxies
3. Trim/scale/crop/pad
4. Add motion to stills
5. Mix dialogue, ambience, SFX และ music
6. Burn-in หรือ attach subtitles
7. Concatenate timeline
8. Loudness normalization
9. Encode master และ review proxy
10. Run automated QC

### 13.4 Export Presets

- Master: MP4 H.264/H.265, configurable quality
- Review: MP4 H.264 1080p
- Vertical: 1080×1920
- Landscape: 1920×1080
- Square: 1080×1080
- Project archive: JSON + manifests + prompts + selected assets

---

## 14. User Interface

### 14.1 Main Navigation

- Dashboard
- Story
- Story Bible
- Storyboard
- Generate
- Review
- Timeline
- Export
- Workflows
- Settings / System Health

### 14.2 Key Screens

1. **Project Wizard** — brief, format, ratio, duration, style
2. **Story Editor** — plot and beat outline
3. **Scene/Shot Board** — cards/table with lock and status
4. **Prompt Inspector** — layered prompt with source labels
5. **Workflow Mapper** — JSON import, node preview and field mapping
6. **Generation Queue** — jobs, progress, errors and GPU profile
7. **Take Review** — compare and approve
8. **Timeline** — sequence with basic edit controls
9. **Export/QC** — profile, warnings and outputs

### 14.3 Usability Principles

- แสดงสถานะทุกขั้นชัดเจน
- autosave พร้อม undo/version history
- ไม่เริ่ม batch ค่าใช้จ่ายสูงโดยไม่มี summary
- คำสั่ง destructive ต้องยืนยัน
- เปิดไฟล์/โฟลเดอร์ผลลัพธ์ได้โดยตรง
- แสดง provenance ของ asset ได้จากหน้า review

---

## 15. System Architecture

### 15.1 Recommended Components

```text
Web UI
  └─ Application API
      ├─ Project/Story Service
      ├─ Prompt Compiler
      ├─ Workflow Registry + H3 Adapter
      ├─ Generation Orchestrator
      │   └─ ComfyUI Client
      ├─ Asset/Metadata Service
      ├─ Timeline/Render Service
      │   └─ FFmpeg
      └─ Job Queue + Event Log

Storage
  ├─ SQLite/PostgreSQL metadata
  └─ Local project filesystem / object storage
```

### 15.2 Suggested Technology Direction

- Frontend: React + TypeScript
- Backend: Python FastAPI หรือ Node.js TypeScript; Python เหมาะกับ media/AI integration
- Database MVP: SQLite
- Job queue MVP: persistent local queue; Redis/RQ/Celery หลัง MVP
- ComfyUI: HTTP/WebSocket API adapter
- Media: FFmpeg/ffprobe
- File watcher: ตรวจ outputs และ workflow changes
- Packaging: local web service หรือ desktop wrapper ใน phase ถัดไป

> Stack ต้องยืนยันหลังทำ technical spike กับ H3 JSON และ ComfyUI instance จริง

### 15.3 Project Folder Layout

```text
ContentAutomationStudio/
├─ app/
├─ workflows/
│  ├─ source/
│  ├─ mappings/
│  └─ snapshots/
├─ projects/
│  └─ <project-id>/
│     ├─ project.json
│     ├─ story/
│     ├─ prompts/
│     ├─ inputs/
│     ├─ generated/
│     ├─ approved/
│     ├─ timeline/
│     ├─ exports/
│     └─ logs/
├─ docs/
└─ tests/
```

---

## 16. Functional Requirements

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | สร้างและบันทึก project จาก wizard ได้ | Must |
| FR-02 | รับ plot แบบ manual หรือสร้างจาก brief ได้ | Must |
| FR-03 | สร้าง/แก้ scene และ shot hierarchy ได้ | Must |
| FR-04 | สร้าง storyboard และ prompt package ราย shot ได้ | Must |
| FR-05 | เก็บ Character/Location/Style Bible และ lock constraint ได้ | Must |
| FR-06 | Import ComfyUI API-format workflow JSON ได้ | Must |
| FR-07 | Mapping logical field ไปยัง workflow node/field ได้ | Must |
| FR-08 | Validate workflow และ dependencies ก่อนรันได้ | Must |
| FR-09 | ส่งงาน image/video ไป ComfyUI และติดตามสถานะได้ | Must |
| FR-10 | Queue, pause, cancel และ retry job ได้ | Must |
| FR-11 | เก็บ prompt, seed, workflow snapshot และ output provenance ได้ | Must |
| FR-12 | Compare, approve, reject และ regenerate take ได้ | Must |
| FR-13 | ประกอบ approved takes เป็น timeline ได้ | Must |
| FR-14 | Render video ด้วย FFmpeg และ export preset ได้ | Must |
| FR-15 | Export storyboard/prompt/generation manifest ได้ | Must |
| FR-16 | Autosave และ resume project ได้ | Must |
| FR-17 | แสดง system health ของ ComfyUI/FFmpeg/storage ได้ | Should |
| FR-18 | Import local image/video เพื่อแทน generated take ได้ | Should |
| FR-19 | รองรับ subtitle และ audio tracks ขั้นพื้นฐาน | Should |
| FR-20 | Duplicate project/preset/workflow mapping ได้ | Should |

---

## 17. Non-Functional Requirements

| ID | Requirement |
|---|---|
| NFR-01 | งานและ metadata ต้องไม่สูญหายเมื่อ app ปิดหรือ restart |
| NFR-02 | ทุก generation job ต้อง reproducible เท่าที่ model/runtime อนุญาต |
| NFR-03 | UI ยังตอบสนองได้ระหว่าง generation/render งานยาว |
| NFR-04 | รองรับ project ที่มีอย่างน้อย 100 shots โดยไม่ช้าผิดปกติ |
| NFR-05 | Secrets และ credentials ไม่ถูกเก็บใน project export |
| NFR-06 | Path/file name รองรับ Windows และ Unicode |
| NFR-07 | การเขียนไฟล์ใช้ atomic write หรือ temp-and-rename เมื่อเหมาะสม |
| NFR-08 | Log มี timestamp, jobId, shotId และ error category |
| NFR-09 | Render ที่ล้มเหลวไม่ทำลาย approved assets หรือ project state |
| NFR-10 | Workflow/version ที่ใช้ต้องตรวจสอบย้อนหลังได้ |

---

## 18. Security, Privacy and Rights

- เก็บ API key ใน environment/secret store ไม่ใส่ใน JSON project
- sanitize file paths และชื่อ output
- จำกัดชนิดไฟล์ upload
- ไม่ execute custom node/workflow ที่ไม่เชื่อถือโดยอัตโนมัติ
- แสดงรายการ model, LoRA, reference และ source asset ใน manifest
- ให้ผู้ใช้ยืนยันว่ามีสิทธิใช้ภาพ เสียง และ likeness ที่นำเข้า
- แยก generated output จาก source/reference ชัดเจน
- เก็บ prompt และ provenance เพื่อรองรับการตรวจสอบภายหลัง

---

## 19. Observability and Operations

### 19.1 Dashboard

- ComfyUI online/offline
- current queue length
- active job and elapsed time
- success/failure count
- disk usage
- output directory availability
- last workflow validation

### 19.2 Logs

- application log
- generation event log
- FFmpeg command/result log
- workflow validation report
- project activity/history

### 19.3 Recovery

- resume interrupted queue
- mark unknown state jobs and reconcile with ComfyUI history
- rebuild thumbnails/proxies
- regenerate timeline from manifest
- project backup and restore

---

## 20. MVP Scope

### 20.1 MVP Vertical Slice

- 1 project
- plot ประมาณ 3–5 นาที
- 3 scenes
- 9–15 shots
- 1 image workflow H3
- 1 video workflow H3
- Character Bible 1–2 ตัวละคร
- Location Bible 2–3 สถานที่
- image/video queue
- take review
- basic timeline
- FFmpeg export 1080p
- Markdown/CSV/JSON storyboard export

### 20.2 MVP Definition of Done

1. ผู้ใช้ใส่ plot และได้ scene/shot storyboard ที่แก้ไขได้
2. แต่ละ shot มี prompt และ workflow mapping ที่ตรวจสอบได้
3. ระบบส่ง image และ video job ผ่าน H3 ได้จริง
4. Job status/error/retry แสดงถูกต้อง
5. ผู้ใช้เลือก approved take ต่อ shot ได้
6. ระบบประกอบ approved takes เป็นวิดีโอ review ได้
7. ปิดและเปิดระบบใหม่แล้ว project/queue state หลักยังอยู่
8. Export มี video, storyboard, prompt manifest และ provenance
9. มี automated test ของ data model, mapping และ queue state
10. ผ่าน end-to-end test อย่างน้อยหนึ่ง project โดยไม่แก้ไฟล์มือระหว่างทาง

---

## 21. Delivery Phases

### Phase 0 — Technical Spike

- รับ H3 image/video API JSON จริง
- ตรวจ node mapping และ output retrieval
- ส่ง prompt/seed/reference แล้วรับไฟล์กลับ
- ทดสอบ FFmpeg assembly 3 shots
- สรุป ComfyUI/custom node/model dependencies

### Phase 1 — Workflow MVP

- project/story/scene/shot data
- prompt compiler
- workflow registry/mapping
- queue and generation
- take review
- basic timeline/export

### Phase 2 — Creative Consistency

- Character/Location/Style Bible tools
- prompt diff/versioning
- reference asset management
- continuity checker
- improved review and regeneration

### Phase 3 — Production Automation

- voice/audio/subtitle pipeline
- advanced edit presets
- batch generation budget
- proxy workflow
- project templates and reusable scene patterns

### Phase 4 — Team and Scale

- multi-user roles and approvals
- remote workers/GPU pool
- cloud/object storage
- audit trail and reporting

---

## 22. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| H3 node IDs เปลี่ยนเมื่อ export ใหม่ | สูง | ใช้ workflow registry + mapping validation + version/hash |
| Character/scene ไม่ต่อเนื่อง | สูง | Bible, references, locked tokens และ review gate |
| GPU OOM/งานค้าง | สูง | preflight, concurrency profile, timeout และ categorized retry |
| สร้างทุก shot แล้วพบว่าเรื่องไม่ดี | สูง | storyboard approval ก่อน generation |
| งานวิดีโอใช้เวลานาน/แพง | สูง | generation budget, keyframe-first และ low-res preview |
| ไฟล์จำนวนมากกระจัดกระจาย | สูง | project folder schema + manifest + approved directory |
| Workflow/custom node ไม่ปลอดภัย | สูง | allowlist, manual install และไม่ execute unknown workflow |
| AI เปลี่ยน prompt ที่ผู้ใช้ล็อก | กลาง | immutable locked fields และ prompt diff |
| Export ผิด resolution/audio | กลาง | preset, ffprobe validation และ automated QC |
| ลิขสิทธิ์/likeness ไม่ชัดเจน | สูง | source declaration, rights checklist และ provenance manifest |

---

## 23. Open Decisions

| ID | Decision Required | Recommendation |
|---|---|---|
| OD-01 | H3 image/video JSON รูปแบบใด | ขอ API-format JSON จริงทั้งสอง workflow ก่อนเริ่ม adapter |
| OD-02 | Local web app หรือ desktop app | เริ่ม local web app; พิจารณา desktop wrapper ภายหลัง |
| OD-03 | Backend language | แนะนำ Python FastAPI สำหรับ ComfyUI/FFmpeg integration |
| OD-04 | Story AI provider | ทำ provider interface; อย่าผูกกับ model เดียว |
| OD-05 | Database | SQLite สำหรับ MVP |
| OD-06 | Output storage | local project folder ใน MVP |
| OD-07 | Video duration policy | กำหนดระดับ project/scene/shot และตรวจยอดรวม |
| OD-08 | Human approval gates | บังคับก่อน generation batch และก่อน final export |
| OD-09 | Audio scope | เริ่ม optional tracks; voice generation หลัง image/video flow เสถียร |
| OD-10 | Safety policy | กำหนดตามกลุ่มผู้ใช้และ model ที่เชื่อมต่อ |

---

## 24. Recommended Next Actions

1. ส่งไฟล์ H3 image workflow และ H3 video workflow ใน **API-format JSON**
2. ระบุ ComfyUI URL, เวอร์ชัน, custom nodes, model/checkpoint/LoRA ที่ workflow ต้องใช้
3. เตรียม sample plot หนึ่งเรื่อง ความยาว 1–3 นาที สำหรับ vertical slice
4. ทำ technical spike: 3 shots จาก storyboard → ComfyUI → approved takes → FFmpeg export
5. ล็อก data schema และ project folder structure จากผล spike
6. ทดสอบ workflow mapping เมื่อมีการ export H3 version ใหม่
7. เริ่ม MVP หลังพิสูจน์ end-to-end path แล้วเท่านั้น

---

## Appendix A — Example Shot Record

```json
{
  "shotId": "SC01-SH03",
  "sceneId": "SC01",
  "order": 3,
  "generationMode": "image-to-video",
  "plannedDurationSec": 4,
  "camera": {
    "shotType": "medium shot",
    "angle": "eye level",
    "movement": "slow push-in"
  },
  "subject": "Mira enters the abandoned greenhouse",
  "imagePrompt": "...",
  "videoPrompt": "slow cautious movement, leaves moving gently...",
  "negativePrompt": "identity change, extra limbs, text, logo...",
  "referenceAssetIds": ["CHAR-MIRA-REF-01", "LOC-GREENHOUSE-REF-01"],
  "workflowPresetId": "h3-i2v-preview-v1",
  "seedPolicy": "inherit-scene-base",
  "status": "ReadyToGenerate"
}
```

## Appendix B — Required H3 Handoff Package

```text
h3-handoff/
├─ h3-image-api.json
├─ h3-video-api.json
├─ README.md
├─ required-models.txt
├─ required-custom-nodes.txt
├─ sample-inputs/
├─ expected-outputs/
└─ parameter-notes.md
```

README ควรระบุ positive/negative prompt node, seed, dimensions, frames/duration, reference image, model selectors และ output node อย่างชัดเจน
