import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * ก้าง EP001 — "เสียงที่ไม่ใช่เสียงเรา", produced from the shot script.
 *
 * The shape comes from the channel research: open on a problem, explain it as
 * cause and effect, end on an answer that turns the problem over. Sixteen
 * stills, fifty seconds, one recurring character.
 *
 * Two things are settled before this runs and are worth stating, because they
 * are what the previous three episodes cost to learn:
 *
 * * **Nothing moves.** The video model is where this pipeline's tells come
 *   from - it redraws what it is given and writes on anything resembling
 *   paper. Stills cannot do either, and a stick figure animated by an
 *   image-to-video model loses its limbs.
 * * **The character is attached, not described.** Every shot carries the
 *   approved master as a reference and Qwen-Image-Edit as the graph. Measured
 *   against the alternative: the same three poses through Boogu Edit kept the
 *   identity and lost the proportions, the scale, and one pose's legs.
 *
 * Text is never generated. Every word on screen is a burned-in caption.
 */

const EPISODE = "ก้าง EP001 — เสียงที่ไม่ใช่เสียงเรา";

/** The master, regenerated here at the seed that produced the approved one:
 *  references are project-scoped, so the character has to exist in this
 *  project rather than be borrowed from the one it was designed in. */
const MASTER_SEED = "4501";
const MASTER_SHEET = "NARRATOR_01 — ก้าง";
const MASTER_PROMPT =
  "Create ONE original stick figure narrator, full body, front view, neutral "
  + "standing pose, centered with generous empty margins. Minimal flat 2D "
  + "digital ink illustration with smooth uniform black #171717 strokes and "
  + "rounded line caps. A circular white-filled head outlined in black. Total "
  + "standing height approximately 4.5 head diameters. Two small black dot "
  + "eyes, a tiny curved mouth, no nose, ears or hair. A single black stick "
  + "torso, thin stick arms and legs, rounded hand ends without fingers, and "
  + "small black oval feet. One small cyan #28B8D5 neckerchief with a short "
  + "triangular tip centered on the upper torso. This is the only colored "
  + "character feature. BACKGROUND: solid neutral pure white #FFFFFF, evenly "
  + "filled edge to edge. Flat solid colors. No scene lighting, gradients, "
  + "shadows or texture. No lettering, labels, watermark, borders, other "
  + "characters or objects.";

/** Prefixed to every shot: the identity is attached and named, never assumed. */
const IDENTITY =
  "Use the attached image as the authoritative character identity reference. "
  + "Keep the exact same character: circular white-filled head, dot eyes, "
  + "stroke thickness, limb proportions, oval feet, cyan neckerchief. ";

const NEGATIVE =
  "text, letters, numbers, watermark, gradients, 3d render, photorealistic, "
  + "hair, nose, ears, extra limbs, sepia, paper texture, warm color cast";

const CLOSING =
  " BACKGROUND: solid light gray #F1F3F5, evenly filled edge to edge, with a "
  + "single thin darker floor line low in the frame. Flat 2D line art, flat "
  + "solid fills, no gradients, no shadows, no texture, no text.";

const BEATS = [
  { sec: "2.5", line: "กดฟังคลิปตัวเองครั้งแรก แล้วสะดุ้ง",
    draw: "The character holds a phone up near his face and recoils slightly, eyes wide, mouth a small open circle. Plain light gray #F1F3F5 wall behind, floor line visible. Full body, centered, generous margin." },
  { sec: "2.5", line: "นี่เสียงเราจริงเหรอ",
    draw: "A large phone seen straight on, filling the middle of the frame, held by the same flat stick-figure hand - a plain black line ending in a rounded tip, drawn exactly like the character, never a realistic hand. On the phone screen, a simple waveform of flat black bars. No letters or numbers anywhere." },
  { sec: "3", line: "เสียงในคลิปมันบางกว่า สูงกว่า และไม่ใช่เสียงที่เราคุ้น",
    draw: "The character tilts his head, looking at the phone in his hand with a puzzled expression, mouth a small flat line. Plain light gray wall, floor line. Full body." },
  { sec: "3", line: "ตอนเราพูด เสียงเดินทางถึงหูเราสองทาง",
    draw: "The character stands facing forward with his mouth open as if speaking. Empty pale background with clear space on both sides of his head. Full body, centered." },
  { sec: "3", line: "ทางแรก ออกจากปาก ลอยผ่านอากาศ แล้ววกกลับเข้าหูเรา",
    draw: "The character faces forward, speaking. A single curved cyan #28B8D5 arrow leaves his mouth, arcs outward through the air and curves back to the side of his head. Only one arrow. Pale background." },
  { sec: "3", line: "ทางที่สอง สั่นผ่านกระดูกในหัวเราตรง ๆ",
    draw: "The character faces forward, speaking, with a curved cyan arrow arcing from his mouth back to his ear. Add one short straight red #D64545 arrow running from his throat directly up through the inside of his head. Two arrows total. Pale background." },
  { sec: "3", line: "และกระดูกพาเสียงต่ำได้ดีกว่าอากาศมาก",
    draw: "A diagram with no people in it at all. Two wave shapes side by side, drawn as flat black outlines: on the left a large slow wave with tall rounded humps, on the right a small tight wave with short quick humps. No figures, no hands, no faces, nothing else in the frame." },
  { sec: "3", line: "เสียงที่เราได้ยินตอนพูด เลยทุ้มกว่าความจริงเสมอ",
    draw: "The character stands speaking, with a soft rounded cyan ring drawn around his head as a simple flat outline. Pale background. Full body visible." },
  { sec: "3", line: "แต่ไมโครโฟนได้ยินแค่ทางเดียว",
    draw: "The character stands speaking on the right. On the left, a simple microphone on a small stand in the same flat style. One cyan curved arrow travels from his mouth to the microphone. No red arrow. Pale background." },
  { sec: "3", line: "มันบันทึกเฉพาะเสียงที่ลอยผ่านอากาศ",
    draw: "The character speaking on the right, a microphone on a stand on the left, one cyan arrow from mouth to microphone. Inside his head, a faint dashed gray outline where a red arrow used to be. Pale background." },
  { sec: "3", line: "เสียงต่ำที่เคยมี เลยหายไปทั้งหมด",
    draw: "A diagram with no people in it at all. Two wave shapes side by side: the large slow wave on the left drawn as a faint dashed gray outline, the small tight wave on the right solid black. No figures, no hands, no faces, nothing else in the frame." },
  { sec: "3", line: "สิ่งที่เหลืออยู่ คือเสียงเราที่ไม่มีกระดูกช่วย",
    draw: "The character stands still, looking down at the phone in his hand, mouth a small flat line, shoulders lowered. Plain light gray wall. Full body." },
  { sec: "3.5", line: "เราเลยรู้สึกว่า มันไม่ใช่เรา",
    draw: "The character points at the phone lying in his other hand and turns his head away slightly, mouth a small flat line. Plain light gray wall, floor line. Full body." },
  { sec: "3.5", line: "แต่คนอื่น ได้ยินเสียงเราแบบนั้นมาตั้งแต่แรก",
    draw: "Wide shot: the character stands on the left, speaking. Two other simple stick figures without neckerchiefs stand on the right, facing him and listening. One cyan curved arrow travels from his mouth toward them. Plain light gray wall, floor line." },
  { sec: "4", line: "เสียงในคลิป ไม่ใช่เสียงที่ผิด",
    draw: "Medium shot: the character holds a phone out flat on his palm. Two other simple stick figures lean in slightly and nod, mouths small curved smiles. Plain light gray wall." },
  { sec: "4", line: "มันคือเสียงที่โลกได้ยิน ตั้งแต่แรก",
    draw: "The character stands holding a phone at his side, looking straight ahead with a small curved smile, calm. Plain light gray wall, floor line, generous empty space above his head. Full body, centered." },
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
      // Still showing the shot before this one.
    }
  }
  throw new Error("The inspector never followed the row that was clicked.");
}

test("draws the master this episode is built on", async ({ page }) => {
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
    "หนึ่งคำถามที่คนดูเคยสงสัย เล่าด้วยเหตุและผล จบด้วยคำตอบที่พลิกความเข้าใจ",
  );
  await page.getByLabel("Aspect Ratio").selectOption("9:16");
  await page.getByLabel("Duration (sec)").fill("50");
  await page.getByLabel("Frame Rate (fps)").fill("30");
  await page.getByLabel("Delivery Resolution").fill("576x1024");
  await page.getByLabel("Creative Brief").fill(
    "ช่องมนุษย์ก้างเล่าเรื่องชวนสงสัย ภาพนิ่งล้วน ตัวละครเดิมทุกตอน "
    + "ตัวหนังสือทุกตัวใส่ตอนตัดต่อ ไม่ให้โมเดลวาด",
  );
  await page.getByLabel("Plot / Narrative").fill(
    BEATS.map((beat) => beat.line).join(" "),
  );
  await page.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  // The character has to exist in this project: references are project-scoped,
  // so the master is made again at the seed that produced the approved one.
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
  const attached = page.getByRole("button", { name: /^Detach image / });
  const run = page
    .getByRole("region", { name: "Visual Reference Bible" })
    .getByRole("button", { name: "Generate", exact: true })
    .last();
  await run.click();
  await expect(attached).toHaveCount(1, { timeout: 5 * 60_000 });
});

test("types the sixteen beats in", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("ทำไมเสียงในคลิปถึงไม่เหมือนเรา");
  await page.getByLabel("Scene summary").fill(
    "เสียงตัวเองเดินทางถึงหูเราสองทาง ไมโครโฟนได้ยินทางเดียว",
  );
  await page.getByLabel("Scene planned duration in seconds").fill("50");
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("ทำไมเสียงในคลิปถึงไม่เหมือนเรา")).toBeVisible();

  const rows = page.locator("tbody").first().locator("tr");
  for (const [index, beat] of BEATS.entries()) {
    await page.getByRole("button", { name: "Add Shot" }).first().click();
    await expect(rows).toHaveCount(index + 1);
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();

    await page.getByLabel("Shot subject").fill(beat.draw.slice(0, 58));
    await page.getByLabel("Planned duration in seconds").fill(beat.sec);
    await page.getByLabel("Image prompt").fill(IDENTITY + beat.draw + CLOSING);
    await page.getByLabel("Shot negative prompt").fill(NEGATIVE);
    // One character, one reference. The two-slot graph wanted the same master
    // attached twice and the editor will not offer an image already assigned,
    // so this episode uses a one-reference derivation of the same graph.
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
    await page.getByLabel("Spoken line").fill(beat.line);
    await page.getByRole("button", { name: "Save captions" }).click();
    await expect(page.getByText("Saved. Render again")).toBeVisible();
  }
});

test("draws the sixteen beats", async ({ page }) => {
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

test("takes the character out of the two diagram beats", async ({ page }) => {
  // Both diagram shots came back with the character standing in front of the
  // waves, twice, however plainly the prompt said "no people in it at all".
  // An attached identity reference is not a suggestion: the edit model puts
  // that character in every frame it is given. A beat with no character in it
  // therefore cannot use the edit model - it is a text-to-image shot.
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");
  const rows = page.locator("tbody").first().locator("tr");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });

  for (const index of [6, 10]) {
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();

    const attached = page.getByRole("button", { name: /^Detach / });
    for (let n = await attached.count(); n > 0; n = await attached.count()) {
      await attached.first().click();
      await expect(attached).toHaveCount(n - 1);
    }
    await page.getByLabel("Shot workflow")
      .selectOption({ label: "Z-Image Turbo T2I (Local API)" });
    await page.getByLabel("Image prompt").fill(
      (index === 6
        ? "Two sound waves side by side, drawn as flat black outlines on a "
          + "solid light gray #F1F3F5 field: on the left one large slow wave "
          + "with tall rounded humps, on the right one small tight wave with "
          + "short quick humps."
        : "Two sound waves side by side on a solid light gray #F1F3F5 field: "
          + "the large slow wave on the left drawn as a faint dashed gray "
          + "outline, the small tight wave on the right solid black.")
      + " Minimal flat 2D line art in the same hand as a simple stick figure "
      + "series. No people, no figures, no hands, no faces, no text, no "
      + "letters, no numbers, no gradients, no shadows.",
    );
    await page.getByLabel("Shot negative prompt").fill(
      "person, people, stick figure, character, face, hand, arm, body, text, "
      + "letters, numbers, watermark, gradients, 3d render, photorealistic",
    );
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true }))
      .toHaveCount(0);
  }
});

test("cuts and renders the episode", async ({ page }) => {
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
  await expect(page.getByText(/16 items/)).toBeVisible({ timeout: 60_000 });

  // Thai captions need a font with Thai glyphs, which is what this preset is.
  await page.getByLabel("Subtitle mode").selectOption("burn_in");
  await page.getByLabel("Style preset").selectOption("thai_friendly");
  await page.getByRole("button", { name: /Save settings/ }).click();
  await expect(page.getByText(/Saved|saved/).first()).toBeVisible({ timeout: 30_000 });

  // The metered narrator: this machine has no Thai voice of its own, and this
  // one reads the channel's voice direction. About a cent for the script.
  await page.getByText("Narrate", { exact: true }).click();
  await page.getByRole("combobox").filter({ hasText: "OpenAI voice" }).first()
    .selectOption("openai");
  const render = page.getByRole("button", { name: "Render Review" });
  await render.click();
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 20 * 60_000 });
});
