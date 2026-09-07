import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * A stick-figure story told in stills, as a channel format.
 *
 * The two channels this is modelled on tell a whole story in flat black
 * figures on paper, one drawing per beat, carried by narration. Nothing moves.
 * That matters here for a reason SF03 measured the hard way: the video model
 * is where this pipeline's tells come from - it redraws what it is given and
 * writes on anything that looks like paper. A film made of stills cannot do
 * either.
 *
 * It also costs almost nothing. A stick drawing is about twenty seconds on
 * this card where a clip is two to seven minutes, so twenty beats is a few
 * minutes of GPU rather than an evening.
 *
 * The style is one string, repeated on every beat. Consistency in this format
 * is not a plate or a character sheet - it is the same six words about brush,
 * paper and empty space, every time.
 */

const EPISODE = "The Man With No Shadow";

const STYLE =
  "Simple stick figure illustration drawn with a thick black brush marker on "
  + "off-white paper. Bold flat black shapes, round head with no face, props "
  + "drawn in a few strokes, plenty of empty paper around the subject, "
  + "vertical composition.";

const NEGATIVE =
  "text, letters, words, numbers, watermark, signature, photorealistic, "
  + "detailed face, 3d render, colour, shading, crosshatching";

/** Twenty beats. Each one is a drawing and a line. */
const BEATS = [
  { draw: "A stick man walking home under a single streetlamp at night, a long shadow stretching behind him on the ground.",
    line: "Every night he walked home the same way." },
  { draw: "The same stick man standing still, but his shadow on the ground is a few steps ahead of him, still walking.",
    line: "One night, his shadow kept going." },
  { draw: "A stick man's shadow turning a corner around a building, alone, the man watching from behind.",
    line: "It turned the corner without him." },
  { draw: "A stick man running after a shadow down a narrow alley between two simple buildings.",
    line: "So he followed it." },
  { draw: "A shadow on the ground waiting beside a plain door set in a blank wall at the end of an alley.",
    line: "It was waiting by a door." },
  { draw: "Close view of a plain rectangular door in a blank wall, with no handle and no keyhole.",
    line: "A door with no handle." },
  { draw: "A shadow flattening and sliding underneath the gap beneath a closed door.",
    line: "The shadow went under it." },
  { draw: "A stick man knocking on a closed door with his fist, standing alone in the dark alley.",
    line: "He knocked until his hand hurt." },
  { draw: "A stick man sitting up in a simple bed in the morning, bright light from a window, and there is no shadow on the floor.",
    line: "In the morning, his shadow was gone." },
  { draw: "Several stick figures at desks in an office, one of them standing, nobody looking at him.",
    line: "Nobody at work noticed." },
  { draw: "A stick man standing alone in bright sunlight in an empty square, the ground beneath him completely blank.",
    line: "He stood in the sun to be sure." },
  { draw: "A stick man walking back into a narrow dark alley at night, small in the frame.",
    line: "That night he went back to the alley." },
  { draw: "A plain door in a blank wall, open a crack, with light spilling out onto the alley floor.",
    line: "The door was open a crack." },
  { draw: "Rows and rows of black stick figure shadows standing in lines inside a large empty room, seen from the doorway.",
    line: "Inside were hundreds of them. Standing in rows." },
  { draw: "One shadow stepping forward out of a crowd of identical shadows, toward the viewer.",
    line: "His own stepped forward." },
  { draw: "A single shadow figure raising one arm and pointing straight at the viewer.",
    line: "And pointed at him." },
  { draw: "A crowd of shadow figures all turning their round heads to face the same direction, toward the viewer.",
    line: "Every shadow in the room turned." },
  { draw: "A stick man running away down a long alley, seen from behind, arms out, moving fast.",
    line: "He ran." },
  { draw: "A plain door in a blank wall, closed, with a thin line of light gone from underneath it.",
    line: "Behind him, the door shut." },
  { draw: "A shadow of a walking man on the ground under a streetlamp at night, with no person casting it.",
    line: "Under the streetlamp, his shadow walked home. Alone." },
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

test("types the stickman story in", async ({ page }) => {
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
    "A stick-figure story told in stills, one drawing per beat, carried by "
    + "narration. Nothing moves, on purpose.",
  );
  await page.getByLabel("Aspect Ratio").selectOption("9:16");
  await page.getByLabel("Duration (sec)").fill("50");
  await page.getByLabel("Frame Rate (fps)").fill("30");
  await page.getByLabel("Delivery Resolution").fill("576x1024");
  await page.getByLabel("Creative Brief").fill(
    "Flat black stick figures on paper. One drawing a beat, held two and a "
    + "half seconds. No colour, no faces, no writing anywhere in frame - the "
    + "story is carried by the narration and by what the drawing withholds.",
  );
  await page.getByLabel("Plot / Narrative").fill(
    BEATS.map((beat) => beat.line).join(" "),
  );
  await page.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  await stage(page, "Storyboard");
  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("The shadow that left");
  await page.getByLabel("Scene time of day").fill("night, then morning, then night");
  await page.getByLabel("Scene summary").fill(
    "A man's shadow walks away from him, and he follows it to where the "
    + "shadows are kept.",
  );
  await page.getByLabel("Scene planned duration in seconds").fill("50");
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("The shadow that left")).toBeVisible();

  const rows = page.locator("tbody").first().locator("tr");
  for (const [index, beat] of BEATS.entries()) {
    await page.getByRole("button", { name: "Add Shot" }).first().click();
    await expect(rows).toHaveCount(index + 1);
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();
    await page.getByLabel("Shot subject").fill(beat.draw.slice(0, 60));
    await page.getByLabel("Planned duration in seconds").fill("2.5");
    await page.getByLabel("Image prompt").fill(`${beat.draw} ${STYLE}`);
    await page.getByLabel("Shot negative prompt").fill(NEGATIVE);
    await page.getByLabel("Shot workflow")
      .selectOption({ label: "Z-Image Turbo T2I (Local API)" });
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true }))
      .toHaveCount(0);

    await selectShot(page, row);
    await page.getByLabel("Spoken line").fill(beat.line);
    await page.getByRole("button", { name: "Save captions" }).click();
    await expect(page.getByText("Saved. Render again")).toBeVisible();
  }
});

test("draws the twenty beats", async ({ page }) => {
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

test("approves the drawings and cuts the English version", async ({ page }) => {
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
  await expect(page.getByText(/20 items/)).toBeVisible({ timeout: 60_000 });

  // The machine's own voice for the English pass: free, and the point here is
  // the format rather than the reading.
  await page.getByText("Narrate", { exact: true }).click();
  const render = page.getByRole("button", { name: "Render Review" });
  await render.click();
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 20 * 60_000 });
});

/** The same twenty lines in Thai, which is the language this format is told in
 *  on the channels it is modelled on. */
const THAI = [
  "ทุกคืน เขาเดินกลับบ้านทางเดิม",
  "คืนหนึ่ง เงาของเขาเดินต่อไปเอง",
  "มันเลี้ยวหัวมุมไปโดยไม่มีเขา",
  "เขาจึงเดินตามมันไป",
  "มันยืนรออยู่ข้างประตูบานหนึ่ง",
  "ประตูที่ไม่มีลูกบิด",
  "เงาลอดใต้ประตูเข้าไป",
  "เขาเคาะจนมือชา",
  "เช้าวันรุ่งขึ้น เงาของเขาหายไป",
  "ที่ทำงาน ไม่มีใครสังเกตเลย",
  "เขาออกไปยืนกลางแดดเพื่อให้แน่ใจ",
  "คืนนั้นเขากลับไปที่ซอยเดิม",
  "ประตูแง้มอยู่นิดเดียว",
  "ข้างในมีเงาเป็นร้อย ยืนเรียงกันเป็นแถว",
  "เงาของเขาก้าวออกมา",
  "แล้วชี้มาที่เขา",
  "เงาทุกตัวในห้องหันมามอง",
  "เขาวิ่ง",
  "ข้างหลังเขา ประตูปิดลง",
  "ใต้เสาไฟ เงาของเขาเดินกลับบ้าน ตัวคนเดียว",
];

test("tells the same story in Thai", async ({ page }) => {
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");
  const rows = page.locator("tbody").first().locator("tr");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });

  for (const [index, line] of THAI.entries()) {
    const row = rows.nth(index);
    for (let attempt = 0; attempt < 5; attempt += 1) {
      await row.click();
      const box = page.getByLabel("Spoken line");
      const current = await box.inputValue().catch(() => null);
      if (current !== null && current !== line) {
        await box.fill(line);
        await page.getByRole("button", { name: "Save captions" }).click();
        await expect(page.getByText("Saved. Render again")).toBeVisible();
        break;
      }
    }
  }

  // Thai needs a font that has Thai glyphs, which is what this preset is for.
  // The style controls are disabled until subtitles are switched on - captions
  // that are off have no style to set.
  await stage(page, "Timeline");
  await page.getByLabel("Subtitle mode").selectOption("burn_in");
  await page.getByLabel("Style preset").selectOption("thai_friendly");
  await page.getByRole("button", { name: /Save settings/ }).click();
  await expect(page.getByText(/Saved|saved/).first()).toBeVisible({ timeout: 30_000 });
});

test("renders the Thai version with the metered narrator", async ({ page }) => {
  // The metered voice, chosen deliberately: it is the one that reads the
  // channel's voice direction, and this machine has no Thai voice of its own.
  // About a cent for this script, and confirmed before it was spent.
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Timeline");
  await expect(page.getByText(/20 items/)).toBeVisible({ timeout: 30_000 });

  await page.getByText("Narrate", { exact: true }).click();
  await page.getByRole("combobox").filter({ hasText: "OpenAI voice" }).first()
    .selectOption("openai");
  const render = page.getByRole("button", { name: "Render Review" });
  await render.click();
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 20 * 60_000 });
});
