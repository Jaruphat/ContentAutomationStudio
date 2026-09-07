# คู่มือเริ่มช่องมนุษย์ก้างเล่าเรื่อง

จัดทำ 7 กันยายน 2026 — ข้อเสนอสำหรับเริ่มผลิต ไม่ใช่การยืนยันว่าสองช่องอ้างอิงใช้วิธีนี้

ช่องอ้างอิง: [เล่าไปเรื่อย by มนุษย์ก้าง](https://www.youtube.com/@stickmanstory34) และ [นักเล่าล้านปี](https://www.youtube.com/@นักเล่าล้านปี) การค้นหาพบข้อมูลช่อง แต่ไม่สามารถเปิดดูคลิปโดยตรงเพื่อวิเคราะห์ภาพ จังหวะ หรือเครื่องมือที่ใช้ได้

## หลักที่แก้ปัญหาได้ตรงที่สุด

อย่าสั่งสร้างตัวละครใหม่จากข้อความทุกช็อต ให้มีภาพต้นแบบที่ผ่านการเลือกแล้ว และแยกตัวละคร ฉาก พร็อพ ข้อความเป็นคนละเลเยอร์ การแนบ reference ช่วยลดความเปลี่ยนแปลง แต่ไม่รับประกันว่าจะเหมือนเดิมทุกพิกเซล หากต้องการเหมือนเดิมจริง ให้ใช้ชิ้นส่วนตัวละครเดิมมาขยับหรือทำ rig

ชื่อ NARRATOR_01 เป็นรหัสจัดการไฟล์ ไม่ใช่คำที่ทำให้โมเดลรู้จักตัวละครโดยอัตโนมัติ ต้องมีภาพและรายละเอียดประกอบเสมอ Seed เดิมก็ไม่ใช่ระบบล็อกตัวละคร เมื่อเปลี่ยนพรอมป์ต์ภาพยังเปลี่ยนได้

## 1. กำหนดรายการก่อนเริ่มผลิต

- เลือกแนวหลักหนึ่งอย่างในช่วงทดลอง เช่น ความรู้ใกล้ตัว ประวัติศาสตร์ หรือเรื่องแต่งหักมุม
- เขียนคำสัญญาช่องหนึ่งประโยค เช่น “เรื่องแปลกของมนุษย์ เล่าให้เข้าใจด้วยมนุษย์ก้าง”
- ทดลองตอน 45–60 วินาทีก่อน และตัดสินจากเสียงพากย์จริง ไม่ใช้จำนวนคำภาษาไทยเป็นตัวจับเวลา
- คลิปแนวตั้งใช้พื้นที่ทำงาน 1080×1920; แนวนอนใช้ 1920×1080 เลือกก่อนจัดองค์ประกอบ
- สำหรับสารคดี: เก็บแหล่งอ้างอิงของข้อเท็จจริง แยกหลักฐาน สมมติฐาน และมุกประกอบ ไม่เสนอเรื่องแต่งเป็นประวัติศาสตร์จริง

## 2. Character Bible — ตัวละครตั้งต้น

ตัวละครตัวอย่างชื่อเล่น “ก้าง” รหัส NARRATOR_01 สามารถเปลี่ยนชื่อได้โดยไม่เปลี่ยนรูปลักษณ์

| ส่วน | ข้อกำหนดคงที่ |
|---|---|
| ภาพรวม | มนุษย์ก้าง 2D เรียบ เส้นสะอาด ปลายเส้นมน |
| หัว | วงกลม ภายในสีขาวทึบ ขอบสี #171717 |
| สัดส่วนเป้าหมาย | ความสูงรวมหัวถึงเท้าประมาณ 4.5 เท่าของเส้นผ่านศูนย์กลางหัว |
| ใบหน้า | ตาจุดดำสองจุด ไม่มีจมูก หู หรือผม ปากเส้นสั้น |
| ลำตัว | เส้นตั้งหนึ่งเส้น แขนขาเป็นเส้น ไม่ใช่คนรูปร่างเต็ม |
| มือและเท้า | มือปลายเส้นมน ไม่มีนิ้ว เท้าวงรีดำเล็ก |
| เอกลักษณ์ | ผ้าผูกคอสีฟ้า #28B8D5 ปลายสามเหลี่ยมสั้นกลางอก |
| ความหนาเส้น | เป้าหมายประมาณ 3% ของเส้นผ่านศูนย์กลางหัว ใช้เป็นเกณฑ์ตรวจ ไม่ใช่ความแม่นยำที่ AI รับประกัน |
| เปลี่ยนได้ | ท่า สีหน้าตาและปาก ตำแหน่ง ขนาดในเฟรม พร็อพ |
| ไม่เปลี่ยน | รูปหัว สัดส่วนหลัก รูปแบบเส้น สีผ้าผูกคอ จำนวนแขนขา |

เมื่อเลือก master แล้ว ให้ยึดรูปนั้นเป็นมาตรฐานจริง หากรูปไม่ตรงสัดส่วนเป้าหมายให้ปรับก่อนผลิตท่าอื่น อย่าสลับใช้ master หลายแบบ

### Prompt สร้างภาพต้นแบบ

```text
Create ONE original stick figure narrator, full body, front view,
neutral standing pose, centered with generous empty margins.

CHARACTER ID: NARRATOR_01. This is a production label, not visible text.
Minimal flat 2D digital ink illustration with smooth uniform black
#171717 strokes and rounded line caps.
A circular white-filled head outlined in black.
Total standing height approximately 4.5 head diameters.
Two small black dot eyes, a tiny curved mouth, no nose, ears or hair.
A single black stick torso, thin stick arms and legs, rounded hand ends
without fingers, and small black oval feet.
One small cyan #28B8D5 neckerchief with a short triangular tip centered
on the upper torso. This is the only colored character feature.

BACKGROUND: solid neutral pure white #FFFFFF, evenly filled edge to edge.
Flat solid colors. No scene lighting, gradients, shadows or texture.
No lettering, labels, watermark, borders, other characters or objects.
Avoid yellow, ivory, cream, beige, sepia, parchment and warm color grading.
```

ภาพที่มีพื้นขาวยังไม่ใช่ PNG โปร่งใส การลบพื้นต้องทำ mask เฉพาะฉากหลัง อย่าลบสีขาวทั้งหมดเพราะหน้าจะกลายเป็นรูโปร่ง ตรวจ alpha ด้วยการวางภาพบนพื้นเข้ม

## 3. สร้างคลังท่าและสีหน้า

เริ่มด้วยท่ายืน เล่าเรื่อง ชี้ซ้าย ชี้ขวา คิด ตกใจ ดีใจ และเดิน รวม 8 ท่า ท่าที่มีทิศให้ระบุว่าเป็นด้านของตัวละครหรือด้านของภาพให้ชัดเจน

ทำมุมหน้า 3/4 ข้าง และหลังเมื่อจำเป็นต่อเรื่อง เริ่มจากภาพละหนึ่งท่าเพื่อให้ง่ายต่อการตรวจและนำไปใช้ จากนั้นจึงรวมเป็น character sheet สำหรับดูมาตรฐานร่วมกัน

แนบ master เดิมในการสร้างทุกรูป ไม่ใช้รูปที่เพิ่งสร้างต่อกันเป็นทอด ๆ เพราะความผิดเพี้ยนอาจสะสม

### Prompt เปลี่ยนท่า — ต้องแนบ master

```text
Use the attached image as the authoritative character identity reference.
Create ONE full-body image of the exact same NARRATOR_01 character.
Preserve the circular head, facial feature style, limb proportions,
stroke thickness, oval feet and the same cyan neckerchief.
Change ONLY the pose and expression described below.

POSE: pointing toward the empty space on the viewer's right.
EXPRESSION: curious, with a small open mouth.

Keep the entire body visible. Plain neutral pure white #FFFFFF background.
Flat 2D line art, no lighting, texture, shadows, text or new accessories.
```

คำว่า “same character” โดยไม่มีภาพอ้างอิงไม่เพียงพอ ถ้าสร้างรูปเดียวจากหลาย reference ให้บอกหน้าที่แยก: ภาพ A ล็อกตัวละคร ภาพ B ล็อกท่า ภาพ C ล็อกฉากและสี

## 4. ระบบสีและฉาก

| การใช้งาน | สีตั้งต้น |
|---|---|
| พื้นว่าง/อธิบาย | #FFFFFF |
| เส้นตัวละคร/วัตถุหลัก | #171717 |
| สีประจำตัวละคร | #28B8D5 |
| ฉากกลางแจ้งสว่าง | #EAF5FA |
| ผนังห้อง | #F1F3F5 |
| พืชและธรรมชาติ | #DDEFE4 |
| จุดเน้น/อันตราย | #E85D5D |

นี่เป็นข้อเสนอด้านการออกแบบ ไม่ใช่สีที่วัดจากช่องอ้างอิง รหัส HEX ในพรอมป์ต์เป็นเป้าหมาย โมเดลอาจสร้างคลาดเคลื่อน ถ้าต้องการสีตรงให้ตั้งพื้นและสีเลเยอร์ในโปรแกรมกราฟิกหรือตัดต่อโดยตรง

สร้างฉากซ้ำได้ 5 แบบ: พื้นขาวโล่ง ห้องเรียบ ถนน ป่า/ทุ่ง และถ้ำ แต่ละฉากใช้วัตถุเด่น 2–4 ชิ้น เส้นฉากบางกว่าเส้นตัวละคร และเว้นพื้นที่สำหรับตัวละครกับซับ

### Prompt ฉาก — สร้างแยกจากตัวละคร

```text
BACKGROUND ONLY. No people, stick figures, faces or text.
Minimal flat 2D digital illustration matching a simple stick figure series.
SCENE: a sparse prehistoric cave interior with one stone and a simple
cave opening. Clean geometric shapes and restrained thin dark outlines.
Neutral light gray #F1F3F5 rock surfaces and a pale blue #EAF5FA exterior.
Flat solid fills. No paper texture, gradients, realistic lighting,
yellow color cast, beige wash, sepia or vintage treatment.
Leave the lower central area uncluttered for a separately composited figure.
Vertical 9:16 composition.
```

กลางคืนหรือถ้ำมืดต้องตรวจว่าแขนขาดำยังอ่านออก อาจใช้แผ่นพื้นที่สว่างหลังตัวละครโดยรักษาสีประจำตัวละครเดิม

## 5. แก้พื้นหลังเหลืองอย่างเป็นระบบ

ยังไม่เห็น prompt ภาพ และ workflow ที่เกิดปัญหา จึงระบุสาเหตุจริงไม่ได้ ให้ทดสอบทีละตัวแปร:

1. ตรวจคำที่ชวนไปโทนอุ่น เช่น vintage, parchment, old paper, warm light, sepia รวมถึงคำที่ระบบ prompt enhancer เติมให้
2. ทดสอบ “minimal flat digital line art on solid pure white background” โดยเอาคำเกี่ยวกับยุคโบราณออกก่อน ถ้าหายจึงเติมเนื้อหากลับทีละส่วน
3. ใช้ master พื้นขาวหรือโปร่งใส ภาพอ้างอิงพื้นเหลืองอาจส่งอิทธิพลสีมาด้วย
4. ถ้าใช้ ComfyUI ทดสอบปิด style LoRA และลดอิทธิพล style reference ทีละอย่าง ไม่เปลี่ยนทุกอย่างพร้อมกัน
5. ตรวจ preview ก่อนเข้าโปรแกรมตัดต่อ ถ้าขาวก่อนตัดต่อแต่เหลืองหลังตัดต่อ ให้ตรวจ filter/LUT/temperature แทนการแก้ prompt
6. วิธีควบคุมพื้นได้แน่นอนที่สุด: สร้างตัวละครแยก ลบพื้นอย่างถูกต้อง แล้ววางบน solid background ที่ตั้งสีเอง

### Negative prompt — เฉพาะ workflow ที่รองรับและใช้งานจริง

```text
yellow background, yellow tint, beige background, cream background,
ivory, sepia, parchment, aged paper, warm color cast, paper texture,
watercolor, gradients, volumetric lighting, 3d render, realistic anatomy,
thick muscular body, extra limbs, extra fingers, hair, nose, ears,
outfit change, character redesign, text, watermark
```

ไม่ใช่ทุกโมเดลใช้ negative prompt ได้เหมือนกัน หากระบบไม่มีช่องนี้ให้เขียนข้อจำกัดในคำสั่งหลัก อย่าใส่คำห้ามสีเหลืองถ้าในช็อตนั้นตั้งใจให้มีพร็อพสีเหลือง ให้จำกัดเฉพาะสีพื้นและ color cast

## 6. เลือกวิธีผลิต

| วิธี | เหมาะเมื่อ | ข้อจำกัด |
|---|---|---|
| ใช้ PNG ท่าเดิม + keyframe | เริ่มผลิตเร็วและตัวละครเหมือนเดิม | ท่าซ้ำได้ ต้องใช้จังหวะเล่าและพร็อพช่วย |
| ทำตัวละครแบบแยกชิ้น/rig | ผลิตซีรีส์ต่อเนื่อง ต้องการเส้นและสัดส่วนแน่นอน | ต้องเตรียมชิ้นส่วนและจุดหมุนก่อน |
| AI edit/reference รายช็อต | ต้องการท่าหรือสถานการณ์หลากหลาย | ต้องตรวจหน้าตา สัดส่วน และสีทุกภาพ |
| AI image-to-video | ช็อตที่ต้องเคลื่อนไหวซับซ้อน | เส้น หน้า และแขนขาอาจเปลี่ยนระหว่างเฟรม |

เริ่มด้วย PNG + keyframe ให้เลื่อนตัวละคร เปลี่ยนท่า ซูมภาพ ใส่พร็อพและเอฟเฟกต์เสียง ช็อตละประมาณ 3–6 วินาทีเป็นจุดเริ่มทดลอง ปรับตามเสียงจริง ไม่ใช่สูตรตายตัว สำหรับการขยับแขนเฉพาะส่วนต้องแยกแขนเป็นเลเยอร์หรือใช้ rig

### กรณี ComfyUI

ComfyUI เป็นระบบต่อ workflow ส่วนการทำ reference และ negative conditioning ขึ้นกับโมเดลที่เลือก

- Reference image/edit: ใช้เส้นทางที่โมเดลรองรับ สำหรับ SD1.5/SDXL มี IPAdapter เป็นทางเลือก ต้องจับคู่ weights และ image encoder ให้ตรงรุ่น ไม่ย้ายไฟล์ข้ามตระกูลโดยเดา
- Pose/structure: ControlNet ใช้ภาพควบคุมท่าหรือโครงสร้าง เลือกตัวที่เข้ากันกับ base model ไม่ได้ล็อกตัวตนแทน reference
- มนุษย์ก้างอาจตรวจ skeleton อัตโนมัติได้ไม่ครบ ถ้า detector ไม่ได้ผลให้ใช้ pose ที่เตรียมเอง หรือทดสอบ line art/ขอบภาพกับตัวควบคุมที่รองรับ
- Seed: คงไว้เมื่อต้องการเปรียบเทียบการปรับค่า ไม่ใช่ตัวรับประกัน identity
- img2img denoise: ค่าต่ำมักรักษาภาพต้นทางมากขึ้น แต่เปลี่ยนท่ายากขึ้น ค่าสูงเปิดให้เปลี่ยนภาพมากขึ้น ไม่มีเลขเดียวที่ใช้ได้ทุกโมเดล
- เก็บ workflow JSON, model/version, seed, prompts, sampler/scheduler, steps, guidance และ reference ที่ใช้ คู่กับภาพที่ผ่านการเลือก
- ไม่จำเป็นต้องฝึก LoRA ตั้งแต่วันแรก พิจารณาหลังมีภาพตัวละครที่คัดแล้วหลายท่าและ workflow เดิมยังรักษารูปลักษณ์ไม่ได้ตามต้องการ

เอกสาร: [ControlNet](https://docs.comfy.org/tutorials/controlnet/controlnet), [Pose ControlNet](https://docs.comfy.org/tutorials/controlnet/pose-controlnet-2-pass), [KSampler](https://docs.comfy.org/built-in-nodes/sampling/ksampler), [IPAdapter implementation](https://github.com/cubiq/ComfyUI_IPAdapter_plus) โครงการ IPAdapter นี้ระบุสถานะ maintenance only จึงควรตรวจความเข้ากันได้ก่อนติดตั้ง

## 7. ขั้นตอนผลิตหนึ่งตอน

1. เลือกหัวข้อและประเด็นเดียวที่คนดูควรจำ
2. หาข้อมูลหากเป็นเรื่องจริง เก็บลิงก์และบันทึกข้อที่ยังไม่แน่ใจ
3. เขียน hook → ตั้งสถานการณ์ → เหตุ/ผลหรือเหตุการณ์ 2–3 จังหวะ → payoff → ปิดเรื่อง
4. อัดเสียงหรือสร้างเสียงชั่วคราว ฟังให้จบและจับเวลาจริง แก้ประโยคยาวก่อนสร้างภาพ
5. แบ่งตามเสียงเป็น shot list ประมาณ 10–14 ช็อตสำหรับตัวอย่าง 60 วินาที เพิ่มหรือลดตามจังหวะ
6. ระบุช็อตละ: เวลา, narration, character ID, pose ID, background ID, prop, framing, motion, caption, SFX
7. ใช้ asset เดิมก่อน สร้างใหม่เฉพาะที่ขาด แยกฉากกับตัวละคร
8. ตรวจภาพนิ่งทั้งหมดเทียบกับ master ก่อนทำ motion
9. ตัดต่อเสียงก่อน แล้วประกอบภาพ ใส่ keyframe หรือ animation เท่าที่ช่วยเล่าเรื่อง
10. ใส่ซับภายหลัง ใช้บรรทัดสั้น อ่านง่าย และตรวจบนหน้าจอโทรศัพท์ อย่าให้ AI วาดซับลงในภาพ
11. วางเพลงและ SFX ให้เสียงพูดชัดตลอด ตรวจเสียงด้วยหูฟังและลำโพงโทรศัพท์
12. ตรวจทั้งคลิป: สัดส่วน/สีเดิม แขนขาครบ หน้าขาวไม่โปร่ง ไม่มีขอบพื้นตกค้าง ข้อความไม่ถูก UI บัง และตอนจบไม่ขาด
13. Export MP4 H.264 แนวตั้ง 1080×1920 ที่ 30 fps เป็นค่าตั้งต้น รักษา fps ของโปรเจกต์ให้สม่ำเสมอ
14. เตรียม title ที่บอกประเด็นจริง description สั้น แหล่งข้อมูลเมื่อเกี่ยวข้อง hashtags ที่เกี่ยวข้อง และเฟรมปกที่อ่านออก
15. หลังเผยแพร่ ใช้ข้อมูลจริงของช่องดูว่าคนหลุดช่วงใดและเลือกดูหรือเลื่อนผ่านอย่างไร แล้วปรับ hook/ช่วงช้าในตอนถัดไป อย่าคาดผลจากตอนเดียว

### Prompt ช่วยเขียน shot list

```text
ช่วยทำสคริปต์และ shot list ภาษาไทยสำหรับคลิปมนุษย์ก้างเล่าเรื่อง
หัวข้อ: [หัวข้อ]
ประเภท: [สารคดี/เรื่องแต่ง]
กลุ่มผู้ชม: [กลุ่ม]
ความยาวเป้าหมาย: 60 วินาที โดยต้องตรวจเวลากับเสียงจริงอีกครั้ง
ตัวละครประจำ: NARRATOR_01 ตาม Character Bible ที่แนบ
โครงสร้าง: hook, setup, development, payoff, ending
หนึ่งตอนมีหนึ่งประเด็นหลัก ใช้ประโยคพูดที่เป็นธรรมชาติ
หากเป็นเรื่องจริง ใช้ข้อมูลจากแหล่งที่แนบและระบุส่วนที่ยังไม่มีหลักฐาน
ห้ามแต่งข้อเท็จจริงให้ดูเป็นข้อมูลจริง
ส่งตาราง: shot_id, duration, narration, character_id, pose,
background, props, framing, motion, caption, SFX
ใช้ฉากและท่าที่มีอยู่ซ้ำได้ สร้างใหม่เท่าที่จำเป็น
แยก prompt ตัวละครและ background ต่อช็อต
อย่าเปลี่ยน character bible หรือเติม warm/sepia/parchment style
```

## 8. ตัวอย่างทดสอบกระบวนการ 60 วินาที

เรื่องแต่งสำหรับทดสอบภาพและจังหวะ: “ปุ่มข้ามวันจันทร์” ไม่ใช่ข้อเสนอว่าช่องต้องเล่าเรื่องแต่ง

| เวลาเป้าหมาย | เหตุการณ์/เสียง | ภาพ |
|---|---|---|
| 0–4 | “ถ้ามีปุ่มข้ามวันจันทร์ คุณจะกดไหม?” | ก้างชี้ปุ่ม พื้นขาว |
| 4–9 | เช้าวันจันทร์ ก้างยังไม่อยากเริ่มงาน | ห้อง โต๊ะ นาฬิกา |
| 9–14 | เขาเจอปุ่มที่เขียนว่า ข้ามวันนี้ | ซูมปุ่ม ใส่ข้อความในโปรแกรมตัดต่อ |
| 14–19 | กดหนึ่งครั้ง กลายเป็นวันอังคาร | ท่ากด เปลี่ยนการ์ดวัน |
| 19–24 | งานวันจันทร์ยังอยู่ | พร็อพกองงานเดิม |
| 24–29 | แถมงานวันอังคารเข้ามาอีก | เพิ่มกองงาน |
| 29–34 | งั้นข้ามอีกวันก็แล้วกัน | ก้างกดปุ่มซ้ำ |
| 34–39 | ปฏิทินเปลี่ยนอย่างรวดเร็ว | สลับการ์ดวัน |
| 39–45 | กองงานสูงจนบังตัว | เพิ่มและเลื่อนพร็อพ |
| 45–51 | เขาหยุดกด แล้วหยิบงานชิ้นแรก | ท่าคิด → หยิบ |
| 51–56 | “ข้ามวันได้…แต่ข้ามสิ่งที่ต้องทำไม่ได้” | ลดกองงานหนึ่งชิ้น |
| 56–60 | เขาวางปุ่มไว้ แล้วเริ่มทำงาน | จบมุกด้วยปุ่มสั่นเล็กน้อย |

เวลาเป็นกรอบจัดภาพ ต้องเขียนเสียงเต็มและอัดจริงก่อนล็อก ไม่จำเป็นต้อง gen video 12 ช็อต ตัวอย่างนี้ใช้การ์ดวัน กองงาน และท่าตัวละครซ้ำได้เป็นส่วนใหญ่

## 9. รูปแบบการเก็บ asset

- character/NARRATOR_01/master_front_v01.png
- character/NARRATOR_01/pose_point_right_v01.png
- character/NARRATOR_01/pose_surprised_v01.png
- backgrounds/BG_ROOM_v01.png
- props/PROP_BUTTON_v01.png
- episodes/EP001/script.md
- episodes/EP001/shotlist.csv
- episodes/EP001/audio/
- episodes/EP001/workflows/
- episodes/EP001/export/

รายการด้านบนเป็นตัวอย่างชื่อไฟล์ที่ควรใช้ ไม่ใช่รายการไฟล์ที่สร้างครบแล้วในชุดนี้

ข้อมูลที่จำเป็นสำหรับทำ workflow ให้ตรงเครื่อง: ชื่อโมเดลภาพ, ใช้ text-to-image หรือ image edit, prompt ปัจจุบัน, ภาพที่ติดเหลือง และถ้าใช้ ComfyUI ให้มี screenshot หรือ workflow JSON
