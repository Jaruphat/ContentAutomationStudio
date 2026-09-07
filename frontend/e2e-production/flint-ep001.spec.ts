import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * FLINT EP001 — "เปลวเล็ก", one minute, vertical.
 *
 * Produced from the character sheet: a walking matchstick with a burnt head, a
 * small flame, dot eyes, thin charcoal limbs and a brown messenger satchel,
 * drawn as a pencil-and-ink sketch on warm cream paper. The sheet's own line -
 * that it is all right to be a small flame - is the story.
 *
 * Everything the previous four episodes settled applies here: one ground for
 * the whole episode, the master attached to every shot, no text generated, and
 * stills rather than clips.
 */

const EPISODE = "FLINT EP001 — เปลวเล็ก";
const MASTER_SHEET = "FLINT master";
const MASTER_SEED = "5150";

const MASTER_PROMPT =
  "ONE character, full body, front view, standing, centred with generous "
  + "empty margins in a tall vertical frame. The character is a walking "
  + "matchstick: the head is a pale tan wooden match shaft with a rounded "
  + "top, the upper part burnt to charcoal black with a small warm orange "
  + "flame burning above it. Two simple black dot eyes and a small curved "
  + "smiling mouth are drawn on the pale wooden face. No nose, no ears, no "
  + "hair. The body is a thin dark charcoal stick figure: single-line torso, "
  + "thin single-line arms and legs, small dark rounded hands and feet, "
  + "slightly gangly. A small brown leather messenger satchel hangs across "
  + "the chest on a thin strap. Drawn as a hand-made pencil and ink sketch "
  + "with visible pencil hatching and a slightly rough contour, warm limited "
  + "palette of tan, burnt orange, charcoal and beige. BACKGROUND: plain warm "
  + "cream paper #F3EEE4, evenly filled edge to edge, no scene, no props, no "
  + "other characters, no lettering.";

const IDENTITY =
  "Use the attached image as the authoritative character identity reference. "
  + "Keep the exact same character: pale tan wooden matchstick body with a "
  + "burnt charcoal head, a small orange flame above it, two dot eyes and a "
  + "small mouth on the wooden face, thin charcoal single-line arms and legs, "
  + "small rounded hands and feet, and the brown leather satchel on its "
  + "strap. Never redraw him as a person or give him a wide body. ";

/** One world: pencil and ink on warm cream paper, lit only by flames. */
const STYLE =
  " Drawn as a hand-made pencil and ink sketch on warm cream paper #F3EEE4 "
  + "with visible hatching and a slightly rough contour, warm limited palette "
  + "of tan, burnt orange, charcoal and beige, the only light coming from the "
  + "flames themselves. No gradients, no photographic lighting, no text, no "
  + "letters, no numbers. Tall vertical composition with room around him.";

const NEGATIVE =
  "text, letters, numbers, watermark, photorealistic, 3d render, anime, human "
  + "face, nose, ears, hair, fingers, wide body, filled body, colour "
  + "background, gradients, neon, multiple identical characters";

/** Fifteen beats, four seconds each. */
const BEATS = [
  { s: "4", t: "เปลวของฟลินท์เล็กกว่าของคนอื่นเสมอ",
    d: "Flint stands alone in a wide dark open place at night, his small flame the only light, his shadow thin on the ground." },
  { s: "4", t: "ไม้ขีดตัวอื่นเปลวใหญ่ เดินผ่านเขาไป",
    d: "Three other matchstick figures with tall bright flames walk past Flint in a line, their light spilling across the ground, Flint small at the edge of the frame." },
  { s: "4", t: "พวกเขาบอกว่า แค่นี้ไปไม่ถึงหรอก",
    d: "A tall matchstick figure with a big flame stands over Flint and points away into the distance, Flint looking up at him." },
  { s: "4", t: "ฟลินท์มองเปลวของตัวเอง",
    d: "Close view of Flint alone, looking upward at his own small flame above his burnt head, hands at his sides." },
  { s: "4", t: "ตรงหน้าคือปากถ้ำที่ไม่มีใครเข้าไป",
    d: "Flint stands small at the bottom of the frame in front of a large dark cave mouth in a rock face, the darkness inside completely black." },
  { s: "4", t: "เขากางแผนที่ อ่านด้วยแสงของตัวเอง",
    d: "Flint holds an open folded map in both hands, his small flame lighting the paper from above, everything beyond the map dark." },
  { s: "4", t: "ก้าวแรก แสงส่องไปได้แค่ก้าวเดียว",
    d: "Flint takes one step into the dark cave, a small circle of warm light around his feet, blackness beyond it." },
  { s: "4", t: "เขาก้าวต่อ ความมืดปิดลงข้างหลัง",
    d: "Flint walking deeper inside the dark cave, seen from behind, only his flame and a small ring of light visible in the blackness." },
  { s: "4", t: "กลางทาง เขาเจอไม้ขีดอีกอันนั่งอยู่ ไฟดับ",
    d: "Flint's small light reveals another matchstick figure sitting on the cave floor with its head unlit and no flame, knees drawn up." },
  { s: "4", t: "ฟลินท์ก้มลงไปใกล้ ๆ",
    d: "Flint leans down close to the unlit matchstick figure, his flame almost touching its burnt head, both faces lit warm." },
  { s: "4", t: "ไฟติด กลายเป็นสองเปลว",
    d: "The second matchstick figure now has its own small flame alight, both figures standing side by side, the cave around them visibly brighter." },
  { s: "4", t: "เดินต่อ แล้วเจออีกอัน แล้วอีกอัน",
    d: "Flint and his companion walking together through the cave, passing two more unlit matchstick figures sitting in the dark ahead of them." },
  { s: "4", t: "ทุกเปลวใหม่ จุดเปลวถัดไป",
    d: "A row of four matchstick figures, each leaning toward the next one, flames passing along the line from left to right." },
  { s: "4", t: "จนแถวไฟยาวทะลุความมืดทั้งถ้ำ",
    d: "A wide view of the cave from a distance with a long line of small flames curving away into the depth, the rock walls warm with light." },
  { s: "4", t: "เปลวของฟลินท์ยังเท่าเดิม แต่ความมืดหายไปแล้ว",
    d: "Flint stands at the mouth of the cave looking back inside at the line of lights, his own small flame unchanged above his head." },
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

test("sets Flint up", async ({ page }) => {
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
    "เรื่องหนึ่งนาทีของไม้ขีดเปลวเล็ก ภาพนิ่งวาดมือ ตัวละครเดิมทุกช็อต",
  );
  await page.getByLabel("Aspect Ratio").selectOption("9:16");
  await page.getByLabel("Duration (sec)").fill("60");
  await page.getByLabel("Frame Rate (fps)").fill("30");
  await page.getByLabel("Delivery Resolution").fill("576x1024");
  await page.getByLabel("Creative Brief").fill(
    "ฟลินท์คือไม้ขีดเปลวเล็ก กล้า อยากรู้ และเก้ ๆ กัง ๆ นิดหน่อย "
    + "โลกของเรื่องเป็นลายเส้นดินสอบนกระดาษครีม แสงมาจากเปลวไฟเท่านั้น",
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

test("types the fifteen beats in", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("เปลวเล็กในถ้ำมืด");
  await page.getByLabel("Scene planned duration in seconds").fill("60");
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("เปลวเล็กในถ้ำมืด")).toBeVisible();

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

test("draws Flint's minute", async ({ page }) => {
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
  await expect(generate).toBeEnabled({ timeout: 120_000 });
});

test("cuts and renders Flint's minute", async ({ page }) => {
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
  await expect(page.getByText(/15 items/)).toBeVisible({ timeout: 60_000 });

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
  await expect(render).toBeEnabled({ timeout: 20 * 60_000 });
});
