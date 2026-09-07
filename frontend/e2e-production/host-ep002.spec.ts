import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * ก้าง EP002 — "นอนครบ 8 ชั่วโมง แล้วทำไมยังเพลีย", five minutes, 16:9.
 *
 * The format is the long-form explainer the reference video is made in: a
 * black ink stick figure living in fully coloured pastel scenes, one drawing a
 * beat, carried by narration.
 *
 * The character took two attempts and the second one is the finding. Asked for
 * a stick body in a soft cartoon hand, the model draws a pear - twice, past a
 * negative prompt naming filled body, wide body and thick torso. Asked for the
 * same figure in ink it draws a true stick figure immediately. So the master
 * is drawn in ink and the colour lives in the scene around it, which is also
 * how the reference video reads: a plain line character on a painted world.
 */

const EPISODE = "ก้าง EP002 — นอนครบแปดชั่วโมง แล้วทำไมยังเพลีย";
const MASTER_SHEET = "ก้าง — ink master";
const MASTER_SEED = "4501";

const MASTER_PROMPT =
  "ONE classic stick figure, full body, front view, neutral standing pose, "
  + "standing on the left third of a wide landscape frame with empty space to "
  + "the right. Minimal flat 2D ink illustration with smooth uniform black "
  + "#171717 strokes and rounded line caps. A circular white-filled head "
  + "outlined in black, two small black dot eyes, two short curved eyebrows "
  + "and a tiny curved mouth. No nose, ears or hair. THE BODY IS DRAWN WITH "
  + "SINGLE PEN STROKES: one thin vertical line for the spine, one thin line "
  + "per arm, one thin line per leg, rounded tips instead of hands, small "
  + "black oval feet. The torso has no width and no fill. BACKGROUND: solid "
  + "pure white #FFFFFF, evenly filled edge to edge. No lettering, watermark, "
  + "borders, other characters.";

const IDENTITY =
  "Use the attached image as the authoritative character identity reference. "
  + "Keep the exact same stick figure: circular white head with a black "
  + "outline, dot eyes, curved eyebrows, small mouth, single-line torso, "
  + "single-line arms and legs, small oval feet. The body stays a stick drawn "
  + "in single strokes - never a filled or widened body. ";

/** One world for the whole episode: the character in ink, the scene in paint. */
const STYLE =
  " The character keeps its plain black ink lines. The scene around it is "
  + "drawn in soft flat pastel colours with thin dark outlines and one gentle "
  + "shading tone, warm and calm, no gradients, no harsh shadows, no text, no "
  + "letters, no numbers. Wide landscape composition with room around the "
  + "figure.";

const NEGATIVE =
  "filled body, wide body, chubby, thick torso, clothing, tunic, text, "
  + "letters, numbers, watermark, photorealistic, 3d render, anime, nose, "
  + "ears, hair, fingers, gradients, harsh shadows";

/** Fifty-four beats. Sixteen minutes of GPU, five minutes of film. */
const BEATS = [
  // -- the problem ---------------------------------------------------------
  { s: "5", t: "เจ็ดโมงเช้า นาฬิกาปลุกดัง เขาลืมตาขึ้นมา",
    d: "The stick figure sits up in bed in a pale morning bedroom, one hand rubbing an eye, a round alarm clock on the bedside table." },
  { s: "5", t: "เมื่อคืนเขาเข้านอนตั้งแต่สามทุ่มครึ่ง",
    d: "The same bedroom at night, the stick figure lying under a blue blanket, eyes closed, a round wall clock behind him." },
  { s: "5", t: "นอนไปแปดชั่วโมงเต็ม ตามที่ทุกคนบอกว่าควรนอน",
    d: "A simple pale wall with one large round clock, and beside it the stick figure standing and pointing up at it." },
  { s: "5", t: "แต่ตื่นมาเหมือนไม่ได้นอนเลย",
    d: "The stick figure stands slouched in a warm cream kitchen, shoulders down, holding a mug, eyes half closed." },
  { s: "5", t: "หลายคนสรุปว่าปัญหาคือนอนไม่พอ",
    d: "The stick figure sits at a small table with a laptop, head resting on one hand, a mug beside him, pale office wall behind." },
  { s: "5", t: "เลยพยายามนอนให้นานขึ้น เก้าชั่วโมง สิบชั่วโมง",
    d: "The stick figure lying in bed with the blanket pulled up, the bedroom darker, a clock on the wall showing a late hour." },
  { s: "5", t: "แล้วก็ยังตื่นมาเพลียเหมือนเดิม",
    d: "The stick figure sits on the edge of the bed in the morning, feet on the floor, head lowered, sunlight from the window." },
  { s: "6", t: "เพราะจำนวนชั่วโมง เป็นแค่หนึ่งในสามอย่าง ที่ตัดสินว่าเราจะตื่นมาสดชื่นไหม",
    d: "The stick figure stands on the left of a plain pastel wall, one arm raised, with three simple empty circles floating in a row to his right." },

  // -- cause one: the cycle ------------------------------------------------
  { s: "5", t: "เรื่องแรก การนอนของเราไม่ได้ราบเรียบตลอดคืน",
    d: "The stick figure lies asleep in bed seen from the side, in a calm night bedroom with a window showing stars." },
  { s: "5", t: "มันเป็นวงจร ที่วนซ้ำไปเรื่อย ๆ",
    d: "A pastel wall with one large simple circular arrow loop drawn on it, and the stick figure standing beside it looking at the loop." },
  { s: "5", t: "หนึ่งวงจรยาวประมาณเก้าสิบนาที",
    d: "The stick figure stands beside a large round wall clock, one arm pointing at it, in a calm pastel room." },
  { s: "5", t: "เริ่มจากหลับตื้น",
    d: "The stick figure lies in bed near the surface of a wide pale blue band that fills the lower half of the frame, like the surface of water." },
  { s: "5", t: "ลงไปหลับลึก ช่วงที่ร่างกายซ่อมแซมตัวเอง",
    d: "The stick figure floating deep inside a dark blue band that fills most of the frame, curled and calm, small bubbles around him." },
  { s: "5", t: "แล้วลอยขึ้นมาที่ช่วงฝัน",
    d: "The stick figure floating in a soft lavender band with a few simple cloud shapes and a crescent moon around him." },
  { s: "5", t: "แล้ววนกลับไปหลับตื้นอีกครั้ง",
    d: "The stick figure near the top of a pale blue band again, with a simple curved arrow looping down and back up beside him." },
  { s: "5", t: "คืนหนึ่ง เราวนแบบนี้ประมาณสี่ถึงหกรอบ",
    d: "A wide pastel wall with a simple gentle wave line drawn across it from left to right, dipping and rising several times, the stick figure standing small at the left end." },
  { s: "5", t: "ทีนี้ลองคิดว่า นาฬิกาปลุกดังตอนไหนของวงจร",
    d: "The stick figure asleep in bed on the right, a round alarm clock on the bedside table on the left, mid-ring with small motion marks." },
  { s: "5", t: "ถ้ามันดังตอนหลับตื้น เราตื่นง่าย",
    d: "The stick figure sitting up in bed awake and alert, eyebrows raised, morning light through the window." },
  { s: "5", t: "แต่ถ้ามันดังตอนหลับลึก",
    d: "The stick figure deep inside a dark blue band, still asleep, with a small alarm clock far above at the surface." },
  { s: "5", t: "สมองต้องถูกดึงขึ้นมาจากที่ลึกที่สุด",
    d: "The stick figure being pulled upward through a dark blue band toward a pale surface, arms above his head, eyes still closed." },
  { s: "6", t: "อาการมึนงงหลังตื่นแบบนั้น มีชื่อเรียกว่า sleep inertia",
    d: "The stick figure standing in a pale bedroom with his head tilted and eyes half closed, small spiral marks floating above his head." },
  { s: "6", t: "และมันอยู่กับเราได้ ตั้งแต่สิบห้านาที ไปจนถึงเป็นชั่วโมง",
    d: "The stick figure sitting slumped on the edge of the bed, a round clock on the wall behind him, long morning shadows on the floor." },
  { s: "6", t: "แปลว่าคนที่นอนเจ็ดชั่วโมงครึ่ง อาจตื่นมาสดกว่าคนที่นอนแปดชั่วโมง",
    d: "Two stick figures standing side by side on a plain pastel wall: the one on the left upright with eyebrows raised, the one on the right slouched with half-closed eyes." },
  { s: "6", t: "เพราะเขาบังเอิญตื่นตรงรอยต่อของวงจรพอดี",
    d: "A wide pastel wall with a gentle wave line across it, and the stick figure standing at a high point of the wave with one arm raised." },

  // -- cause two: the timing ----------------------------------------------
  { s: "5", t: "เรื่องที่สอง คือเวลา ไม่ใช่จำนวนชั่วโมง",
    d: "The stick figure stands between two large round wall clocks on a pastel wall, looking from one to the other." },
  { s: "5", t: "ร่างกายเรามีนาฬิกาของตัวเองอยู่ข้างใน",
    d: "The stick figure standing on a plain pastel wall with one large simple clock face drawn inside his chest area as a thin outline." },
  { s: "6", t: "มันไม่ได้สนใจว่าเรานอนกี่ชั่วโมง แต่สนใจว่าเรานอนและตื่นตอนไหน",
    d: "The stick figure asleep in bed on the left of the frame and standing awake on the right, with a round clock between them." },
  { s: "5", t: "วันธรรมดา เรานอนห้าทุ่ม ตื่นเจ็ดโมง",
    d: "A calm night bedroom, the stick figure getting into bed, a round clock on the wall showing a late evening hour." },
  { s: "5", t: "พอเสาร์อาทิตย์ เรานอนตีสอง ตื่นสิบเอ็ดโมง",
    d: "The same bedroom in bright late morning light, the stick figure still asleep under the blanket, the curtains open." },
  { s: "6", t: "สำหรับร่างกาย นั่นเหมือนบินข้ามสามโซนเวลา ทุกสัปดาห์",
    d: "The stick figure sitting in a simple aeroplane seat beside a small round window with clouds outside, holding the armrests." },
  { s: "5", t: "เขาเรียกมันว่า social jet lag",
    d: "The stick figure standing between three round clocks on a pastel wall, each showing a different time, looking confused." },
  { s: "5", t: "พอถึงเช้าวันจันทร์ นาฬิกาในตัวยังไม่กลับมา",
    d: "The stick figure standing in a pale kitchen in the morning, holding a mug, eyes half closed, a clock on the wall behind him." },
  { s: "6", t: "เราเลยง่วงตอนที่ควรตื่น และตื่นตอนที่ควรง่วง",
    d: "The stick figure sitting at a desk with a laptop, head on one hand, and beside him the same figure lying in bed with eyes wide open at night." },
  { s: "5", t: "ต่อให้คืนนั้นเราจะนอนครบแปดชั่วโมงก็ตาม",
    d: "The stick figure asleep in bed under a blanket, a round clock on the wall, the room calm and dim." },

  // -- cause three: what goes in -------------------------------------------
  { s: "5", t: "เรื่องที่สาม คือสิ่งที่เราใส่เข้าไปก่อนนอน",
    d: "The stick figure standing at a kitchen counter with a mug of coffee and a phone lying beside it, warm afternoon light." },
  { s: "5", t: "กาแฟแก้วบ่ายสาม ที่เราคิดว่าไม่เป็นไร",
    d: "The stick figure raising a mug toward his mouth in a warm café corner, a small round clock on the wall behind showing mid afternoon." },
  { s: "6", t: "คาเฟอีนมีครึ่งชีวิตประมาณห้าถึงหกชั่วโมง",
    d: "A pastel wall with a large simple mug drawn on it, half of the mug shaded and half empty, and the stick figure standing beside it pointing." },
  { s: "6", t: "แปลว่าตอนสามทุ่ม ครึ่งหนึ่งของมันยังอยู่ในตัวเรา",
    d: "The stick figure sitting on a sofa at night, a small half-shaded mug shape floating beside his head, a lamp glowing warm." },
  { s: "5", t: "เราหลับได้ก็จริง",
    d: "The stick figure lying in bed with eyes closed, blanket up, the room dim and calm." },
  { s: "5", t: "แต่หลับลึกได้น้อยลงกว่าที่ควรจะเป็น",
    d: "The stick figure floating just below the surface of a pale blue band, not deep, with the darker deep band far below him." },
  { s: "5", t: "แสงจากจอ ก็ทำงานคล้าย ๆ กัน",
    d: "The stick figure lying in bed in a dark room holding a glowing phone above his face, the glow lighting his head." },
  { s: "5", t: "มันบอกสมองว่า ตอนนี้ยังเป็นกลางวัน",
    d: "The stick figure standing in a dark bedroom with a bright simple sun shape drawn glowing on the wall beside him." },
  { s: "6", t: "ร่างกายเลยเลื่อนเวลาปล่อยเมลาโทนินออกไป",
    d: "The stick figure standing beside a large round clock on a pastel wall, one arm pushing the clock's hand forward." },
  { s: "6", t: "เราเข้านอนตรงเวลา แต่ร่างกายยังไม่พร้อมจะนอน",
    d: "The stick figure lying in bed with eyes wide open in a dark room, the ceiling above him plain and pale." },

  // -- the turn and what to do ---------------------------------------------
  { s: "6", t: "เพราะงั้น คำถามที่ถูก จึงไม่ใช่ว่านอนกี่ชั่วโมง",
    d: "The stick figure standing on a plain pastel wall beside a large round clock, shaking his head, one hand raised." },
  { s: "6", t: "แต่คือ เรานอนตอนไหน และหลับได้ลึกแค่ไหน",
    d: "The stick figure standing between a round clock on his left and a deep blue band below his right, looking at both." },
  { s: "5", t: "สามอย่างที่ทำได้ตั้งแต่คืนนี้",
    d: "The stick figure standing on the left of a plain pastel wall with three simple empty circles in a row beside him." },
  { s: "6", t: "หนึ่ง ตื่นเวลาเดิมทุกวัน แม้แต่วันหยุด",
    d: "The stick figure standing beside a round alarm clock on a bedside table, giving it a thumbs-up-style raised arm, morning light." },
  { s: "6", t: "สอง หยุดคาเฟอีนตั้งแต่บ่ายสอง",
    d: "The stick figure standing beside a kitchen counter, one arm out flat refusing a mug of coffee that sits on the counter." },
  { s: "6", t: "สาม ปิดจอสักครึ่งชั่วโมงก่อนเข้านอน",
    d: "The stick figure placing a phone face down on a bedside table in a dim bedroom, a small lamp glowing warm." },
  { s: "5", t: "ไม่ต้องทำครบทั้งสามข้อในคืนเดียว",
    d: "The stick figure standing on a plain pastel wall with three simple circles beside him, one of them shaded in." },
  { s: "6", t: "เลือกข้อที่ง่ายที่สุดสำหรับคุณ แล้วทำมันสองสัปดาห์",
    d: "The stick figure standing beside a simple wall calendar with a grid of plain squares, marking one square with a raised arm." },
  { s: "6", t: "เพราะร่างกายเรา ไม่ได้นับชั่วโมงที่เรานอน",
    d: "The stick figure standing on a plain pastel wall beside a large round clock, looking away from it." },
  { s: "6", t: "มันนับความสม่ำเสมอ ที่เราให้มันต่างหาก",
    d: "The stick figure standing calm in a warm morning bedroom, curtains open, sunlight across the floor, a made bed behind him." },
];

async function stage(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Production stages" })
    .getByRole("button", { name, exact: true })
    .click();
}

async function selectShot(page: Page, row: Locator) {
  const line = page.getByLabel("Spoken line");
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await row.click();
    try {
      await expect(line).toHaveValue("", { timeout: 4000 });
      return;
    } catch {
      // Still the shot before this one.
    }
  }
  throw new Error("The inspector never followed the row that was clicked.");
}

test("sets up the episode and its master", async ({ page }) => {
  await page.goto("/story");
  const switcher = page.getByRole("combobox", { name: "Switch project" });
  await expect(switcher).toBeVisible({ timeout: 30_000 });
  if ((await switcher.locator("option").allTextContents()).includes(EPISODE)) {
    await switcher.selectOption({ label: EPISODE });
    await page.getByRole("button", { name: "Delete this project" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(switcher).not.toContainText(EPISODE);
  }

  await page.getByRole("button", { name: "New" }).click();
  await page.getByLabel("Project Title").fill(EPISODE);
  await page.getByLabel("Objective").fill(
    "คลิปความรู้ยาวห้านาที ตัวละครเส้นหมึกในโลกสีพาสเทล หนึ่งภาพต่อหนึ่งประโยค",
  );
  await page.getByLabel("Aspect Ratio").selectOption("16:9");
  await page.getByLabel("Duration (sec)").fill("300");
  await page.getByLabel("Frame Rate (fps)").fill("30");
  await page.getByLabel("Delivery Resolution").fill("1024x576");
  await page.getByLabel("Creative Brief").fill(
    "อธิบายว่าทำไมนอนครบแปดชั่วโมงแล้วยังเพลีย ด้วยเหตุและผลสามข้อ "
    + "จบด้วยสิ่งที่ทำได้จริงสามอย่าง ตัวหนังสือทุกตัวใส่ตอนตัดต่อ",
  );
  await page.getByLabel("Plot / Narrative").fill(BEATS.map((b) => b.t).join(" "));
  await page.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  await expect(page.getByRole("button", { name: "Add sheet" })).toBeVisible();
  await page.getByRole("combobox", { name: "Reference kind" }).selectOption("character");
  await page.getByRole("textbox", { name: "Reference name" }).fill(MASTER_SHEET);
  await page.getByRole("button", { name: "Add sheet" }).click();

  const opener = page.getByRole("button", { name: "Generate canonical image" });
  await expect(opener).toHaveCount(1);
  await opener.click();
  await page.getByLabel("Plate prompt").fill(MASTER_PROMPT);
  await page.getByLabel("Plate workflow")
    .selectOption({ label: "Z-Image Turbo T2I (Local API)" });
  await page.getByLabel("Plate seed").fill(MASTER_SEED);
  const run = page
    .getByRole("region", { name: "Visual Reference Bible" })
    .getByRole("button", { name: "Generate", exact: true })
    .last();
  await run.click();
  await expect(page.getByRole("button", { name: /^Detach image / }))
    .toHaveCount(1, { timeout: 5 * 60_000 });
});

test("types the fifty-four beats in", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("ทำไมนอนครบแล้วยังเพลีย");
  await page.getByLabel("Scene planned duration in seconds").fill("300");
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("ทำไมนอนครบแล้วยังเพลีย")).toBeVisible();

  const rows = page.locator("tbody").first().locator("tr");
  for (const [index, beat] of BEATS.entries()) {
    await page.getByRole("button", { name: "Add Shot" }).first().click();
    await expect(rows).toHaveCount(index + 1);
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();

    await page.getByLabel("Shot subject").fill(beat.d.slice(0, 56));
    await page.getByLabel("Planned duration in seconds").fill(beat.s);
    await page.getByLabel("Image prompt").fill(IDENTITY + beat.d + STYLE);
    await page.getByLabel("Shot negative prompt").fill(NEGATIVE);
    await page.getByLabel("Shot workflow")
      .selectOption({ label: "Qwen-Image-Edit 2511 Lightning 4-step (1 ref)" });

    const attach = page.getByRole("combobox", { name: "Attach reference" });
    const options = await attach.locator("option").allTextContents();
    const master = options.find((text) => text.includes(MASTER_SHEET));
    if (master) await attach.selectOption({ label: master });

    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true }))
      .toHaveCount(0);

    await selectShot(page, row);
    await page.getByLabel("Spoken line").fill(beat.t);
    await page.getByRole("button", { name: "Save captions" }).click();
    await expect(page.getByText("Saved. Render again")).toBeVisible();
  }
});

test("draws the fifty-four beats", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText(/shot\(s\) ready/)).toBeVisible({ timeout: 60_000 });
  const generate = page.getByTestId("generate-button");
  await expect(generate).toBeEnabled({ timeout: 30_000 });
  await generate.click();
  await expect(generate).toBeDisabled({ timeout: 30_000 });
  await expect(generate).toBeEnabled({ timeout: 180_000 });
});

test("cuts and renders the five minutes", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });

  await stage(page, "Review");
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  await expect(approve.first()).toBeVisible({ timeout: 30_000 });
  for (let count = await approve.count(); count > 0; count = await approve.count()) {
    await approve.first().click();
    await expect(approve).toHaveCount(count - 1, { timeout: 30_000 });
  }

  await stage(page, "Timeline");
  await page.getByRole("button", { name: "Build Timeline" }).click();
  await expect(page.getByText(/54 items/)).toBeVisible({ timeout: 60_000 });

  await page.getByLabel("Subtitle mode").selectOption("burn_in");
  await page.getByLabel("Style preset").selectOption("thai_friendly");
  await page.getByRole("button", { name: /Save settings/ }).click();
  await expect(page.getByText(/Saved|saved/).first()).toBeVisible({ timeout: 30_000 });

  await page.getByText("Narrate", { exact: true }).click();
  await page.getByRole("combobox").filter({ hasText: "OpenAI voice" }).first()
    .selectOption("openai");
  const render = page.getByRole("button", { name: "Render Review" });
  await render.click();
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 30 * 60_000 });
});
