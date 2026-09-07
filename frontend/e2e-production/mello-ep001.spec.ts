import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * MELLO EP001 — "ชื่อที่รอดมาจากต้นไม้", two minutes, 16:9.
 *
 * Produced from the supplied character sheet: a soft 3D toasted marshmallow
 * with dot eyes, blush cheeks, a red scarf, a leather backpack and wooden
 * mannequin limbs. The episode is the real history of the sweet he is made of
 * - the marsh mallow plant, the Egyptian confection, the French pâte de
 * guimauve, gelatin replacing the root, the extrusion machine, and the
 * campfire - ending on the fact that carries the whole story: the name
 * outlived the plant that gave it.
 *
 * Everything the previous five episodes settled applies: one world stated in
 * every prompt, the master attached to every shot, no generated text, stills
 * rather than clips. The only new thing is the register - this world is a soft
 * 3D render rather than ink or flat colour, so the style line says so.
 */

const EPISODE = "MELLO EP001 — ชื่อที่รอดมาจากต้นไม้";
const MASTER_SHEET = "MELLO master";
const MASTER_SEED = "6120";

const MASTER_PROMPT =
  "ONE character, full body, front view, standing, placed on the left third "
  + "of a wide landscape frame with empty space to the right. The character is "
  + "a cute little marshmallow: the head and body are a single soft rounded "
  + "white marshmallow cube with a lightly toasted golden brown top. On the "
  + "front of the cube, a simple friendly face: two large glossy black oval "
  + "eyes, two soft pink blush cheeks, and a small open smiling mouth. No "
  + "nose, no ears, no hair. Slim smooth wooden tan limbs like a small artist "
  + "mannequin: thin arms with rounded mitten hands, thin legs with chunky "
  + "rounded tan boots. A soft dark red knitted scarf around the neck with the "
  + "ends hanging, and a small brown leather backpack on the back. Rendered as "
  + "a soft cute 3D character illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and a shallow depth of field. Warm "
  + "palette of cream white, toasted gold, brown leather, deep red and butter "
  + "yellow. BACKGROUND: plain soft warm off-white studio backdrop, evenly "
  + "lit, no scene, no props, no other characters, no lettering.";

const IDENTITY =
  "Use the attached image as the authoritative character identity reference. "
  + "Keep the exact same character: a soft white marshmallow cube body with a "
  + "toasted golden top, two glossy black oval eyes, pink blush cheeks, a "
  + "small smiling mouth, a dark red knitted scarf, a small brown leather "
  + "backpack, thin wooden tan arms with mitten hands and chunky tan boots. "
  + "Never redraw him as a person, an animal or a flat drawing. ";

/** One world for the whole film: soft 3D, warm light, shallow depth. */
const STYLE =
  " Rendered as a soft cute 3D illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and shallow depth of field, warm "
  + "palette of cream, toasted gold, brown, deep red and butter yellow. No "
  + "text, no letters, no numbers, no logos, no flat line art, no harsh "
  + "contrast. Wide landscape composition with room around him.";

const NEGATIVE =
  "text, letters, numbers, watermark, logo, flat 2d, line art, sketch, anime, "
  + "human face, nose, ears, hair, fingers, creepy, realistic food photograph, "
  + "multiple identical characters, cluttered background";

/** Twenty-four beats, five seconds each: two minutes. */
const BEATS = [
  { s: "5", t: "ก่อนจะเป็นขนมนุ่ม ๆ ที่เราปิ้งกินกัน มาร์ชแมลโลว์เคยเป็นต้นไม้",
    d: "Mello stands on the left of a wide misty marshland at golden hour, tall pale green reed-like plants with soft pink flowers around him, water and grass." },
  { s: "5", t: "ต้นมาโลว์ ขึ้นตามที่ลุ่มน้ำเค็ม",
    d: "A close view of the pale pink mallow flowers and their leaves growing out of shallow water, Mello standing small among them looking up." },
  { s: "5", t: "ภาษาอังกฤษเรียกที่ลุ่มแบบนั้นว่า marsh และเรียกต้นไม้ชนิดนี้ว่า mallow",
    d: "A wide calm marsh landscape at dawn with reeds and still water, Mello standing on a small wooden walkway looking out over it." },
  { s: "5", t: "สองคำนี้รวมกันเป็นชื่อของขนมที่เรารู้จัก",
    d: "Mello standing on a plain warm backdrop, one wooden hand held out flat with a single soft mallow flower resting on it." },
  { s: "5", t: "ความพิเศษของมันอยู่ที่ราก",
    d: "Mello crouching beside a pulled-up plant, its thick pale root exposed on the soil, examining it with both hands." },
  { s: "5", t: "รากมียางเหนียวใส ที่เอามาทำอะไรได้หลายอย่าง",
    d: "A close view of a cut pale root with a clear sticky sap stretching between the two halves, Mello holding one half up to the light." },
  { s: "5", t: "เมื่อราวสี่พันปีก่อน ชาวอียิปต์โบราณเอายางนั้นมาผสมน้ำผึ้งและถั่ว",
    d: "Mello standing in a warm sandstone Egyptian room with painted columns, beside a low table holding a honey jar and a bowl of nuts." },
  { s: "5", t: "ได้ขนมหวานชิ้นเล็ก ๆ ที่มีค่ามาก",
    d: "A small honey-coloured sweet resting on a shallow stone dish on a low table, lit warmly, Mello leaning in to look at it closely." },
  { s: "5", t: "เชื่อกันว่าสงวนไว้สำหรับชนชั้นสูงและใช้ในพิธี",
    d: "Mello standing at the foot of wide sandstone steps looking up toward a golden ceremonial doorway, warm evening light." },
  { s: "5", t: "แต่ตอนนั้นมันไม่ได้เป็นแค่ของหวาน",
    d: "Mello sitting on a stone bench holding a small clay cup with both mitten hands, warm light from a window behind." },
  { s: "5", t: "ยางจากรากถูกใช้เป็นยาแก้เจ็บคอกับอาการไอด้วย",
    d: "Mello sitting wrapped in his red scarf holding a warm cup near his face, small wisps of steam rising, a soft blanket around him." },
  { s: "5", t: "ข้ามมาศตวรรษที่สิบเก้า ที่ฝรั่งเศส",
    d: "Mello standing on a cobbled European street in the evening in front of a warmly lit little confectionery shop window." },
  { s: "5", t: "ร้านขนมเอายางรากไปตีรวมกับไข่ขาวและน้ำตาล",
    d: "Mello standing on a wooden stool at a marble counter beside a large copper bowl, holding a whisk in a fluffy white mixture." },
  { s: "5", t: "จนได้เนื้อฟูเบา ที่เรียกว่า ปาต เดอ กีมูฟว์",
    d: "A tray of soft white square sweets dusted with fine powder cooling on a marble counter, Mello looking at them with wide eyes." },
  { s: "5", t: "ทุกขั้นตอนทำด้วยมือ และต้องรอให้เซ็ตตัวหลายวัน",
    d: "Mello sitting on a stool beside the counter with his chin on his hands, waiting, an hourglass and cooling trays nearby, warm lamplight." },
  { s: "5", t: "มันเลยเป็นของแพง ที่คนทั่วไปไม่ค่อยได้กิน",
    d: "A single white sweet displayed alone on a small pedestal inside a glass shop case, Mello standing outside the glass looking in." },
  { s: "5", t: "ต่อมาเจลาตินเข้ามาแทนที่รากมาโลว์",
    d: "Mello standing between two low pedestals: on the left a pale plant root, on the right a small bowl of clear jelly, looking from one to the other." },
  { s: "5", t: "เพราะถูกกว่า และทำให้เนื้อขนมอยู่ตัวกว่า",
    d: "Mello holding a soft white marshmallow cube in both hands and pressing it gently so it springs back, close warm lighting." },
  { s: "5", t: "แปลว่ามาร์ชแมลโลว์ที่เรากินทุกวันนี้ ไม่มีต้นมาร์ชแมลโลว์อยู่ในนั้นแล้ว",
    d: "Mello standing on a plain warm backdrop looking at a soft marshmallow in one hand and a mallow flower in the other, the two held apart." },
  { s: "5", t: "ปี 1948 มีคนคิดวิธีบีบส่วนผสมออกมาเป็นเส้นยาว แล้วตัดเป็นชิ้น",
    d: "Mello standing beside a warm cream-coloured machine in a bright factory, a long white rope of marshmallow coming out of it onto a belt." },
  { s: "5", t: "จากขนมหายาก กลายเป็นถุงที่ใครก็ซื้อได้",
    d: "Rows of soft white marshmallow cubes moving along a conveyor belt into an open bag, Mello standing beside the belt watching them pass." },
  { s: "5", t: "แล้วมันก็ไปเจอกับกองไฟ",
    d: "Mello sitting on a log beside a small campfire at dusk in a pine forest, holding a long stick with a marshmallow on the end toward the flames." },
  { s: "5", t: "ผิวนอกไหม้เป็นสีทอง ข้างในละลายจนนุ่ม",
    d: "Close view of a marshmallow on a stick turning golden brown over the fire, warm orange light on Mello's face as he watches it." },
  { s: "5", t: "ชื่อของมันยังเป็นชื่อของต้นไม้ ที่ไม่ได้อยู่ในนั้นอีกแล้ว",
    d: "Wide view at night: Mello sitting alone by the small campfire under stars, holding his toasted marshmallow, a single mallow flower tucked into his backpack strap." },
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

test("sets Mello up", async ({ page }) => {
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
    "เล่าที่มาของมาร์ชแมลโลว์จริง ๆ ตั้งแต่ต้นไม้ในที่ลุ่ม จนถึงกองไฟ",
  );
  await page.getByLabel("Aspect Ratio").selectOption("16:9");
  await page.getByLabel("Duration (sec)").fill("120");
  await page.getByLabel("Frame Rate (fps)").fill("30");
  await page.getByLabel("Delivery Resolution").fill("1024x576");
  await page.getByLabel("Creative Brief").fill(
    "โลกของเรื่องเป็น 3D นุ่ม ๆ แสงอุ่น ตัวละครเดิมทุกช็อต "
    + "เนื้อหาเป็นประวัติจริงของมาร์ชแมลโลว์ ไม่แต่งข้อเท็จจริง "
    + "ตัวหนังสือทุกตัวใส่ตอนตัดต่อ",
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
  await page
    .getByRole("region", { name: "Visual Reference Bible" })
    .getByRole("button", { name: "Generate", exact: true })
    .last()
    .click();
  await expect(page.getByRole("button", { name: /^Detach image / }))
    .toHaveCount(1, { timeout: 5 * 60_000 });
});

test("types the twenty-four beats in", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("จากต้นไม้ในที่ลุ่ม ถึงกองไฟ");
  await page.getByLabel("Scene planned duration in seconds").fill("120");
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("จากต้นไม้ในที่ลุ่ม ถึงกองไฟ")).toBeVisible();

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

test("draws Mello's two minutes", async ({ page }) => {
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

test("cuts and renders Mello's two minutes", async ({ page }) => {
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
  await expect(page.getByText(/24 items/)).toBeVisible({ timeout: 60_000 });

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
  await expect(render).toBeEnabled({ timeout: 25 * 60_000 });
});
