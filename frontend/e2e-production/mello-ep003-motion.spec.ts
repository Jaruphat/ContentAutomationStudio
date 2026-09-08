import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * MELLO EP003 — "Marshmallow, Moving", 16:9, English, every shot a clip.
 *
 * The same history as EP002, cut to three minutes, and animated: each shot is
 * drawn as a still, approved, then handed to image-to-video as its own start
 * frame. It exists to answer one question - whether generated motion is usable
 * for this channel - against an episode of the same story that is not moving.
 *
 * Two measurements decided the shape of it, both taken before a word was
 * written.
 *
 * A 124-frame clip took 220-230 seconds on this machine: about 45 seconds of
 * GPU for every second of finished film. Three minutes is what fits in an
 * afternoon; nine, like EP002, would be most of a day.
 *
 * And the character survived. Image-to-video destroyed the ink stick figure -
 * it lost limbs, the model redrew the frame, and three attempts came back
 * near-static - so this was expected to fail. In this register it does not:
 * the body, face, scarf, backpack and limbs held for the whole clip.
 *
 * The one thing that has not changed is that the model does not take
 * instructions about what not to do. Told to stay seated - explicitly, twice -
 * the character stood up and walked out of frame. So every shot here is
 * written as a thing that happens. There are no prohibitions in the motion
 * prompts, because they do not work and their presence suggests they do.
 */

const CHANNEL = "Mello";
const EPISODE = "MELLO EP003 — Marshmallow, Moving";
const MASTER_SHEET = "MELLO master";
const MASTER_SEED = "4821";
const DELIVERY = "1024x576";
const NARRATOR_VOICE = "sage";
const IMAGE_WORKFLOW = "Qwen-Image-Edit 2511 Lightning 4-step (1 ref)";
const VIDEO_WORKFLOW = "H3 I2V turbo 1024x576 (16:9)";

const MASTER_PROMPT =
  "ONE character, full body, front view, standing in the centre of a wide "
  + "landscape frame. The character is a cute little marshmallow. His head and "
  + "body are ONE single soft rounded white marshmallow cube with a lightly "
  + "toasted golden brown top. On the front of the cube, a simple friendly "
  + "face: two large round glossy black eyes, two soft pink blush cheeks, and "
  + "one small open smiling mouth. No nose, no ears, no hair, no eyebrows. "
  + "LIMBS: two long thin straight tan wooden arms held clearly out and away "
  + "from the body, ending in small rounded mitten hands, and two long thin "
  + "straight tan wooden legs, well apart, ending in chunky rounded tan boots "
  + "- slender wooden sticks like a small artist mannequin, never short nubs. "
  + "A soft dark red knitted scarf around his neck with two ends hanging down "
  + "the front, and a small brown leather backpack with buckles on his back. "
  + "Rendered as a soft cute 3D character illustration with clay-like matte "
  + "surfaces, gentle warm lighting, soft shadows and a shallow depth of "
  + "field. Warm palette of cream white, toasted gold, brown leather, deep red "
  + "and butter yellow. BACKGROUND: plain soft warm off-white studio backdrop, "
  + "evenly lit, no scene, no props, no other characters, no lettering.";

const MASTER_NEGATIVE =
  "pear shape, blob, sphere, snowman, short stubby limbs, nubs for arms, "
  + "armless, eyebrows, moustache, text, letters, numbers, watermark, human "
  + "face, nose, ears, hair, fingers, multiple characters";

const IDENTITY =
  "Use the attached image as the authoritative character identity reference. "
  + "Keep the exact same character: one soft rounded white marshmallow body "
  + "with a toasted golden brown top, two round glossy black eyes, pink blush "
  + "cheeks, a small open smiling mouth, a dark red knitted scarf with hanging "
  + "ends, a small brown leather backpack, long thin tan wooden arms with "
  + "mitten hands and long thin tan wooden legs in chunky tan boots. Never "
  + "redraw him as a person, an animal, a snowman or a flat drawing. ";

const STYLE =
  " Rendered as a soft cute 3D illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and shallow depth of field, warm "
  + "palette of cream white, toasted gold, brown, deep red and butter yellow. "
  + "No text, no letters, no numbers, no signage, no logos, no flat line art. "
  + "Wide landscape composition with room around him.";

/** He is a marshmallow, so a marshmallow prop needs saying to be a prop. */
const PROPS_HAVE_NO_FACE =
  " Every other marshmallow in the frame is a plain white block with no face, "
  + "no limbs and no scarf. Exactly ONE character in the frame.";

const NEGATIVE =
  "text, letters, numbers, signage, watermark, logo, flat 2d, line art, "
  + "sketch, anime, human face, nose, ears, hair, fingers, teeth, snowman, "
  + "multiple identical characters, cluttered background, harsh contrast";

const VOICE_DIRECTION =
  "Speak as a small, cheerful young character telling his own story. Light "
  + "and bright, a little curious, warm and friendly. Unhurried and never "
  + "breathless; let each sentence finish and land before the next one "
  + "begins. Slightly warmer and slower on the closing lines.";

/**
 * The hold, and therefore the clip.
 *
 * The application works the frame count out from this and the graph's own
 * rate, so a hold is not only how long the picture stays up - it is how much
 * GPU the shot costs. 125 words per minute is the rate this narrator was
 * measured reading.
 */
const PLANNING_WPM = 125;
const AIR_SEC = 1.0;

export function holdSeconds(line: string): number {
  const words = line.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(3.0, Math.round(((words / PLANNING_WPM) * 60 + AIR_SEC) * 2) / 2);
}

/** `t` is spoken, `d` draws the start frame, `m` says what then happens. */
type Beat = { t: string; d: string; m: string; props?: true };

const BEATS: Beat[] = [
  { t: "I am a marshmallow. Sugar, air and gelatin. But my name is far older.",
    d: "Mello standing in the middle of a plain warm off-white backdrop, one mitten hand raised in a small wave.",
    m: "The little marshmallow character waves his raised wooden arm slowly and rocks gently on his feet. The camera holds still." },
  { t: "It is the name of a plant, and the plant is not in me any more.",
    d: "Mello standing on a plain warm backdrop holding one pale pink five-petalled flower up in both mitten hands, looking at it.",
    m: "He turns the pale pink flower slowly in both hands and tilts his head to look at it. The camera holds still." },
  { t: "To find it, go back to the water. A salt marsh, at first light.",
    d: "Wide misty salt marsh at dawn, still water and pale reeds, Mello standing small on the low earth bank.",
    m: "Mist drifts slowly across the still water and the pale reeds sway in the wind while the light warms. The camera holds still." },
  { t: "Almost nothing grows in ground that salty. This does.",
    d: "Mello standing ankle-deep in shallow water beside one tall plant with pale pink flowers and grey-green leaves.",
    m: "The tall flowering plant sways gently in the breeze and he looks up along its stem. The water ripples around his boots." },
  { t: "The Greeks called it althaia, the healer, and the name stuck.",
    d: "Mello standing in a sunlit stone courtyard beside a row of terracotta pots holding the same pale pink flowering plant.",
    m: "He walks slowly along the row of pots from left to right while the sunlight shifts across the stone wall behind him." },
  { t: "Everything comes from the root. Cut it, and it does not run like sap.",
    d: "Close view of one thick pale root cut into two halves on a dark wooden board, Mello standing behind the board.",
    m: "He reaches down and lifts one half of the pale root off the board and holds it up. The camera pushes in slowly." },
  { t: "It stretches. A clear gel that pulls out into a long thread.",
    d: "Close view of two halves of a pale root with a clear glistening thread stretching between them, Mello holding one half up.",
    m: "The clear thread stretches longer and sags slowly as he raises his hand higher. The camera holds still." },
  { t: "That gel is mucilage. The root is about a third made of it.",
    d: "Mello standing beside a shallow glass dish of clear gel on a worn wooden table, warm light through the dish.",
    m: "He tilts the shallow dish with both hands and the clear gel slides slowly across it, catching the warm light." },
  { t: "So the first thing anybody made from it was medicine, not sweets.",
    d: "Mello standing in a dim stone room lined with shelves of small clay jars, one warm lamp burning.",
    m: "He walks slowly along the shelf of clay jars while the lamp flame flickers and the shadows move across the stone wall." },
  { t: "A sore throat is a raw surface, and mucilage lies over it.",
    d: "Mello sitting wrapped in his red scarf holding a warm clay cup close to his face, small wisps of steam rising.",
    m: "Steam rises and curls from the cup as he lifts it slowly toward his face. The camera pushes in gently." },
  { t: "Greek and Roman doctors wrote it down. Dioscorides listed it for coughs.",
    d: "Mello standing beside a low wooden table holding a stone mortar and pestle and blank rolled scrolls, warm lamplight.",
    m: "He grinds slowly with the pestle in the stone mortar, turning it round, while the lamp flame flickers behind him." },
  { t: "Pliny promised a spoonful a day would keep every illness away. He was wrong.",
    d: "Mello holding a small wooden spoon of pale clear gel up in front of him with both mitten hands, eyes wide.",
    m: "He tilts the wooden spoon slowly and the pale gel slides toward the edge and hangs there. The camera holds still." },
  { t: "In monastery gardens it grew in neat beds with the other useful plants.",
    d: "Wide view of a walled garden with low hedged beds and stone arches, Mello walking along the gravel path.",
    m: "He walks slowly away from the camera along the gravel path between the hedged beds. The leaves move in the breeze." },
  { t: "When harvests failed, people dug the roots and ate them. A last resort.",
    d: "Mello crouching in a bare harvested field under a flat grey sky, holding a pale root in both mitten hands.",
    m: "He rises slowly to standing while holding the pale root, and the dry stubble around him moves in the wind." },
  { t: "Then France, two hundred years ago, where confectioners did something new.",
    d: "Mello standing on a wet cobbled street at dusk in front of a small warmly lit confectionery shop window.",
    m: "He walks slowly toward the glowing shop window and the warm light spreads across the wet cobbles. The camera follows him in." },
  { t: "They beat air into the root's own gel.",
    d: "Close view of a whisk standing in a copper bowl of pale foam, Mello holding the whisk handle with both mitten hands.",
    m: "He whisks steadily in the copper bowl and the pale foam thickens and rises up the sides. The camera holds still." },
  { t: "Sugar, egg white and mucilage, whipped until it held its own shape.",
    d: "Mello on a wooden stool at a marble counter looking down into a copper bowl of thick white foam.",
    m: "He lifts the whisk out of the bowl and a soft white peak rises with it and slowly folds back down." },
  { t: "They called it pâte de guimauve. Guimauve is simply their word for the plant.",
    d: "Mello standing beside a marble slab spread with soft white paste dusted with fine powder.",
    m: "He spreads the soft white paste slowly across the marble slab with a wooden spatula. The camera drifts along the slab." },
  { t: "It set overnight in trays of starch, then was cut and sold as a throat lozenge.",
    d: "Mello standing beside shallow wooden trays of white powder with rows of small moulded hollows pressed into it.",
    m: "He pours pale syrup slowly into the row of hollows in the white powder. The camera drifts along the tray." },
  { t: "Then the plant was taken out. Gelatin was cheaper and arrived ready to use.",
    d: "Mello standing beside a small clear bowl of pale set jelly on a wooden table.",
    m: "He presses the pale jelly with one mitten hand and it wobbles and settles slowly back into shape." },
  { t: "It holds more air, it sets harder, and it keeps.",
    d: "Mello pressing a plain soft white block gently between both mitten hands so that it springs back.",
    m: "He squeezes the plain white block between both hands and it slowly springs back out to its full shape.",
    props: true },
  { t: "By the end of that century, the marsh mallow was gone from the marshmallow.",
    d: "Mello standing on a plain warm backdrop holding a pale pink flower in one mitten hand and a plain white block in the other.",
    m: "He looks slowly from the flower in one hand across to the plain white block in the other, turning his head.",
    props: true },
  { t: "The recipe kept nothing of the plant except its name.",
    d: "Close view of one pale pink flower and one plain white block side by side on a wooden board, Mello standing behind them.",
    m: "The camera pushes in slowly on the flower and the plain white block while he stands quietly behind the board.",
    props: true },
  { t: "Then machines. In nineteen forty-eight the mixture was pumped through pipes.",
    d: "Mello standing beside a cream-coloured machine as a long soft white rope comes out of a nozzle onto a moving belt.",
    m: "The long white rope extrudes steadily from the nozzle onto the belt and travels away while he watches it go past." },
  { t: "It came out as a rope, cut into cylinders, and tumbled in starch.",
    d: "Plain white cylinders tumbling inside a slowly turning drum of white powder, Mello standing beside the drum.",
    m: "The drum turns steadily and the plain white cylinders tumble over each other through the white powder.",
    props: true },
  { t: "That is why a marshmallow is a cylinder. A shape decided by a pipe.",
    d: "Mello standing on a plain warm backdrop holding up one small plain white cylinder in both mitten hands.",
    m: "He turns the plain white cylinder slowly in both hands, looking at it. The camera pushes in gently.",
    props: true },
  { t: "And then it met the fire. The sugar browns and the middle turns to liquid.",
    d: "Mello sitting on a log by a small campfire at dusk holding a long stick with a plain white block on the end over the flames.",
    m: "The flames flicker and rise while the plain white block on the stick slowly turns golden brown at the edges.",
    props: true },
  { t: "A marsh, a flower, a root that soothed a throat. None of it is in the bag.",
    d: "Wide golden hour view of Mello walking away from us along the edge of the misty marsh toward the low sun.",
    m: "He walks slowly away from the camera down the path toward the low sun and grows smaller, while the reeds sway and the mist drifts." },
];

const TOTAL_SEC = BEATS.reduce((sum, beat) => sum + holdSeconds(beat.t), 0);

function stillPrompt(beat: Beat): string {
  return IDENTITY + beat.d + (beat.props ? PROPS_HAVE_NO_FACE : "") + STYLE;
}

/**
 * What the clip does.
 *
 * The identity block is repeated because the clip is a fresh generation that
 * happens to start from a picture, and the style block is repeated for the
 * same reason the stills repeat it: one world, stated every time.
 */
function motionPrompt(beat: Beat): string {
  return (
    "The scene begins exactly on the attached image and stays in it. "
    + beat.m
    + " The character is a small soft white marshmallow with a toasted golden "
    + "top, black dot eyes, pink blush cheeks, a dark red scarf, a small brown "
    + "leather backpack and thin wooden arms and legs, and he keeps that exact "
    + "shape and those exact colours throughout. Soft cute 3D animation, "
    + "clay-like matte surfaces, gentle warm lighting, shallow depth of field."
  );
}

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

async function openChannel(page: Page): Promise<Locator> {
  const expander = page.getByRole("button", { name: `Expand ${CHANNEL}` });
  if (await expander.count()) await expander.first().click();
  const card = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: CHANNEL, exact: true }),
  }).first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

async function saveChannel(page: Page, card: Locator) {
  const direction = await card.getByLabel("Voice direction").inputValue();
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.request().method() === "PUT"
        && response.url().includes("/channels/")
        && response.status() === 200,
      { timeout: 30_000 },
    ),
    card.getByRole("button", { name: "Save channel bibles" }).click(),
  ]);
  await page.reload();
  const reopened = await openChannel(page);
  await expect(reopened.getByLabel("Voice direction"))
    .toHaveValue(direction, { timeout: 30_000 });
}

test("sets the moving episode up", async ({ page }) => {
  test.setTimeout(30 * 60_000);
  await page.goto("/story");
  const switcher = page.getByRole("combobox", { name: "Switch project" });
  await expect(switcher).toBeVisible({ timeout: 30_000 });
  while ((await switcher.locator("option").allTextContents()).includes(EPISODE)) {
    await switcher.selectOption({ label: EPISODE });
    await page.getByRole("button", { name: "Delete this project" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(switcher).not.toContainText(EPISODE, { timeout: 30_000 });
  }

  await page.goto("/channel");
  await expect(
    page.getByRole("button", { name: /^Expand / }).first()
      .or(page.getByText("No channels yet")),
  ).toBeVisible({ timeout: 30_000 });
  const card = await openChannel(page);
  await card.getByLabel("Voice direction").fill(VOICE_DIRECTION);
  await card.getByLabel("Length (sec)").fill(String(Math.round(TOTAL_SEC)));
  await saveChannel(page, card);

  const episodes = card.locator("section").filter({
    has: page.getByRole("heading", { name: "Episodes", exact: true }),
  });
  await episodes.getByLabel("Episode title").fill(EPISODE);
  await episodes.getByLabel("Premise").fill(
    "The same history as EP002, cut to three minutes and animated: every shot "
    + "is a still that was approved and then handed to image-to-video as its "
    + "own start frame.",
  );
  await episodes.getByRole("button", { name: "Start episode" }).click();
  await expect(episodes.getByText(EPISODE)).toBeVisible({ timeout: 30_000 });

  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await expect(page.getByRole("button", { name: "Add sheet" })).toBeVisible();
  await page.getByRole("combobox", { name: "Reference kind" }).selectOption("character");
  await page.getByRole("textbox", { name: "Reference name" }).fill(MASTER_SHEET);
  await page.getByRole("button", { name: "Add sheet" }).click();
  await page.getByLabel("Negative identity tokens").fill(MASTER_NEGATIVE);
  await page.getByRole("button", { name: "Save sheet" }).click();

  const opener = page.getByRole("button", { name: "Generate canonical image" });
  await expect(opener).toHaveCount(1);
  await opener.click();
  await page.getByLabel("Plate prompt").fill(MASTER_PROMPT);
  await page.getByLabel("Plate workflow")
    .selectOption({ label: "Z-Image Turbo T2I (Local API)" });
  await page.getByLabel("Plate size").fill(DELIVERY);
  await page.getByLabel("Plate seed").fill(MASTER_SEED);
  await page
    .getByRole("region", { name: "Visual Reference Bible" })
    .getByRole("button", { name: "Generate", exact: true })
    .last()
    .click();
  await expect(page.getByRole("button", { name: /^Detach image / }))
    .toHaveCount(1, { timeout: 5 * 60_000 });
});

test("types the twenty-eight moving beats in", async ({ page }) => {
  test.setTimeout(60 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  // Named, not matched by prefix: a re-run after a failure part way through
  // leaves a scene behind, and two of them make the prefix ambiguous.
  await page.getByRole("button", { name: "Edit scene 1", exact: true }).click();
  await page.getByLabel("Scene title").fill("Marshmallow, moving");
  await page.getByLabel("Scene planned duration in seconds")
    .fill(String(Math.round(TOTAL_SEC)));
  await page.getByRole("button", { name: "Save scene" }).click();
  // The episode title contains the scene title, so the project switcher's
  // hidden <option> matches it too. The scene's own row is the evidence.
  await expect(page.getByRole("button", { name: /^Scene 1/ }))
    .toBeVisible({ timeout: 30_000 });

  const rows = page.locator("tbody").first().locator("tr");
  for (const [index, beat] of BEATS.entries()) {
    await page.getByRole("button", { name: "Add Shot" }).first().click();
    await expect(rows).toHaveCount(index + 1);
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();

    await page.getByLabel("Shot subject").fill(beat.d.slice(0, 56));
    await page.getByLabel("Planned duration in seconds")
      .fill(holdSeconds(beat.t).toFixed(1));
    await page.getByLabel("Image prompt").fill(stillPrompt(beat));
    // The video prompt is written in the animate pass, not here: the field
    // only exists where a clip is made, which is deliberate - on a still it
    // would be a prompt that reaches nothing.
    await page.getByLabel("Shot negative prompt").fill(NEGATIVE);
    await page.getByLabel("Shot workflow").selectOption({ label: IMAGE_WORKFLOW });

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

test("draws the twenty-eight start frames", async ({ page }) => {
  test.setTimeout(120 * 60_000);
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
  await expect(generate).toBeEnabled({ timeout: 300_000 });
});

test("approves the start frames", async ({ page }) => {
  test.setTimeout(60 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Review");
  await expect(page.getByRole("button", { name: /^Select take / }).first())
    .toBeVisible({ timeout: 60_000 });

  const batch = page.getByRole("button", { name: /^Approve all \d+ pending/ });
  if (await batch.count()) {
    await batch.click();
    await expect(batch).toHaveCount(0, { timeout: 180_000 });
  }
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  for (let count = await approve.count(); count > 0; count = await approve.count()) {
    await approve.first().click();
    await expect(approve).toHaveCount(count - 1, { timeout: 30_000 });
  }
  await expect(approve).toHaveCount(0, { timeout: 60_000 });
});

test("hands each approved still to image-to-video", async ({ page }) => {
  test.setTimeout(90 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");
  const rows = page.locator("tbody").first().locator("tr");
  await expect(rows).toHaveCount(BEATS.length, { timeout: 60_000 });

  for (let index = 0; index < BEATS.length; index += 1) {
    const row = rows.nth(index);
    await selectShot(page, row);

    // Bind this shot's own approved still as the frame the clip starts on.
    // Nothing is chained automatically, and that is the point: the picture a
    // clip begins from is a decision, not an inference from shot order.
    const picker = page.getByLabel("Choose an approved scene image take");
    await expect(picker).toBeVisible({ timeout: 30_000 });
    const own = (await picker.locator("option").allTextContents())
      .find((text) => text.includes(`Shot ${index + 1} `)
        || text.includes(`Shot ${index + 1}·`)
        || text.includes(`Shot ${index + 1}·`));
    await picker.selectOption(own ? { label: own } : { index: 1 });
    await page.getByRole("button", { name: "Use approved scene image as start frame" })
      .click();
    await expect(page.getByText(/Exact approved scene image/))
      .toBeVisible({ timeout: 60_000 });

    // Only now does it become a video shot: changing the mode first would
    // make the still it is about to start from a take of the wrong kind.
    await row.getByRole("button", { name: /^Edit shot / }).click();
    await page.getByLabel("Generation mode").selectOption("image-to-video");
    await page.getByLabel("Shot workflow").selectOption({ label: VIDEO_WORKFLOW });
    // The video prompt field appears with the mode that uses it.
    await page.getByLabel("Video prompt").fill(motionPrompt(BEATS[index]));
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true }))
      .toHaveCount(0);
  }
});

test("generates the twenty-eight clips", async ({ page }) => {
  test.setTimeout(240 * 60_000);
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
  await expect(generate).toBeEnabled({ timeout: 600_000 });
});

test("cuts and renders the moving episode", async ({ page }) => {
  test.setTimeout(120 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });

  await stage(page, "Review");
  await expect(page.getByRole("button", { name: /^Select take / }).first())
    .toBeVisible({ timeout: 60_000 });
  const batch = page.getByRole("button", { name: /^Approve all \d+ pending/ });
  if (await batch.count()) {
    await batch.click();
    await expect(batch).toHaveCount(0, { timeout: 180_000 });
  }
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  for (let count = await approve.count(); count > 0; count = await approve.count()) {
    await approve.first().click();
    await expect(approve).toHaveCount(count - 1, { timeout: 30_000 });
  }

  await stage(page, "Timeline");
  await page.getByRole("button", { name: "Build Timeline" }).click();
  await expect(page.getByText(new RegExp(`${BEATS.length} items`)))
    .toBeVisible({ timeout: 60_000 });

  await page.getByLabel("Subtitle mode").selectOption("burn_in");
  await page.getByLabel("Style preset").selectOption("clean");
  await page.getByRole("button", { name: /Save settings/ }).click();
  await expect(page.getByText(/Saved|saved/).first()).toBeVisible({ timeout: 30_000 });

  await page.getByText("Narrate", { exact: true }).click();
  await page.getByRole("combobox").filter({ hasText: "OpenAI voice" }).first()
    .selectOption("openai");
  await page.getByLabel("Narrator voice").selectOption(NARRATOR_VOICE);
  const render = page.getByRole("button", { name: "Render Review" });
  await render.click();
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 60 * 60_000 });
});
