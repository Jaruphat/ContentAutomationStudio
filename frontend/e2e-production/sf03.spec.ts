import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * SF03, "Tomorrow's Newspaper", produced by typing it into the pages.
 *
 * SF01 and SF02 were both produced by a Python file posting to the API. This
 * episode is the same pipeline driven the other way: every value below is
 * typed into a field or chosen from a control that a creator can see, against
 * the real backend, the real database and the real ComfyUI. What comes out is
 * a real project, not a fixture.
 *
 * The premise is the one thing in the slate this pipeline is measured as bad
 * at. SF01 failed its publish gate on a garbled headline - a model asked for
 * newsprint writes a plausible smear, and there is no negative prompt for
 * "spell correctly". So this episode is written so that no headline is ever
 * held: the paper is seen at an angle or at a distance where its type is
 * texture, and the reveal is a photograph and a spoken line rather than
 * anything the audience has to read.
 *
 * Run with scripts/sf03_via_browser.py, which checks the backend and ComfyUI
 * are up first. Phases are separate tests so a failure in generation does not
 * make the typing happen twice:
 *
 *   --grep "types SF03"     the brief, the scenes, the shots
 *   --grep "generates"      preflight and the queue, watched to completion
 *   --grep "assembles"      approve, cut, render
 */

const EPISODE = "Tomorrow's Newspaper";
// Kept for the plate pass: the key images are conditioned on an approved
// plate of the place, and a plate is generated text-to-image.
const PLATE_WORKFLOW = "Z-Image Turbo T2I (Local API)";

const SHOT_WORKFLOW = "Boogu Edit INT8 (1 ref, guidance 9)";
const CLIP_WORKFLOW = "H3 Video - I2V (API)";

/** What the narrator says, one line per shot, in the order they are cut. */
const SHOTS = [
  {
    subject: "an empty city street corner before dawn",
    action: "a delivery van pulls away, leaving a bundle of newspapers on the wet pavement",
    environment: "corner of a narrow street, closed shopfronts, one working streetlamp, 4:40 in the morning",
    lens: "wide, 24mm, deep focus",
    prompt:
      "Wide shot of an empty city street corner before dawn. A white delivery "
      + "van is pulling away at the far end, tail lights red on wet asphalt. A "
      + "bundle of newspapers sits tied on the pavement under a single working "
      + "streetlamp. Closed shutters, no people. Cold blue light, film grain.",
    motion: "The van recedes and turns out of frame; rain haze drifts through the lamplight.",
    camera: "Locked off.",
    audio: "Wet tyres receding, distant traffic, light rain on pavement.",
    seconds: "4",
    narration: "Every morning at 4:40, a van drops the papers at the corner of Vine and Third.",
  },
  {
    subject: "the bundle of newspapers under the kiosk light",
    action: "rain beads on the plastic wrap",
    environment: "the pavement beside a shuttered newspaper kiosk",
    lens: "low angle, 35mm, shallow depth",
    prompt:
      "Low angle close shot of a tied bundle of newspapers on wet pavement "
      + "beside a shuttered newspaper kiosk. Rain beads on the plastic wrap. "
      + "The type on the top sheet is soft and out of focus, unreadable. Cold "
      + "streetlight from above, film grain.",
    motion: "Rain lands on the wrapping; the light flickers once.",
    camera: "Slow push in, a hand's width.",
    audio: "Rain on plastic, the hum of a failing streetlight.",
    seconds: "3.5",
    narration: "The vendor cuts the twine. He has done it for nineteen years.",
  },
  {
    subject: "a pair of weathered hands with a pocket knife",
    action: "cutting the twine on the bundle",
    environment: "inside the opened kiosk, warm bulb overhead",
    lens: "close, 50mm, shallow depth",
    prompt:
      "Close shot of weathered hands cutting the twine on a newspaper bundle "
      + "with a small pocket knife. Warm bulb overhead, cold street behind. No "
      + "face in frame. The newsprint is soft and out of focus. Film grain.",
    motion: "The twine parts and the bundle relaxes open.",
    camera: "Locked off.",
    audio: "Twine snapping, paper settling, a kettle somewhere behind.",
    seconds: "3.5",
    narration: "Last Tuesday, the front page carried a story about a fire on Bell Street.",
  },
  {
    subject: "the top newspaper of the stack",
    action: "seen from directly above at a steep angle as the stack settles",
    environment: "the kiosk counter under a warm bulb",
    lens: "overhead, 35mm, steep angle",
    prompt:
      "Overhead shot at a steep raking angle of the top newspaper on a stack, "
      + "on a kiosk counter under a warm bulb. The page is seen edge-on enough "
      + "that the type reads only as grey texture. A dark photograph occupies "
      + "the upper half. Film grain, no legible words.",
    motion: "The stack settles a few millimetres; the page corner lifts in a draught.",
    camera: "Locked off.",
    audio: "Paper shifting, a draught through the kiosk hatch.",
    seconds: "3.5",
    narration: "The fire started at 6:15 that evening.",
  },
  {
    subject: "the vendor's silhouette",
    action: "standing still in the kiosk hatch, looking out at the street",
    environment: "the kiosk from outside, warm interior against the blue street",
    lens: "medium wide, 35mm",
    prompt:
      "Medium wide shot from the street of a newspaper kiosk at dawn. A man's "
      + "silhouette stands motionless in the lit hatch, seen from behind and "
      + "to the side, face not visible. Warm interior against cold blue "
      + "street. Film grain.",
    motion: "He does not move; a bus passes behind the camera and its light crosses him.",
    camera: "Locked off.",
    audio: "A bus passing, the kiosk radio low and indistinct.",
    seconds: "3.5",
    narration: "He didn't say anything. Who would believe him.",
  },
  {
    subject: "a stack of kept newspapers in a back room",
    action: "tied in bundles, standing against a wall",
    environment: "a small storeroom behind the kiosk, one bare bulb",
    lens: "medium, 35mm, deep focus",
    prompt:
      "Medium shot of forty tied bundles of newspapers stacked against the "
      + "wall of a small storeroom, one bare bulb overhead. Dust in the air. "
      + "The papers are seen edge-on; no page faces the camera. Film grain.",
    motion: "Dust drifts through the bulb light; nothing else moves.",
    camera: "Very slow push in.",
    audio: "A bulb ticking, muffled street outside.",
    seconds: "3.5",
    narration: "So he started keeping them.",
  },
  {
    subject: "the cut edges of the stacked papers",
    action: "held still, dates visible only as rhythm not as text",
    environment: "the storeroom wall, raking light",
    lens: "macro, 85mm, very shallow depth",
    prompt:
      "Extreme close shot along the cut edges of stacked newspapers in raking "
      + "light. The printed dates appear only as a rhythm of grey marks, far "
      + "too small and soft to read. Dust, film grain.",
    motion: "The focus drifts a few millimetres along the edges.",
    camera: "Slow lateral drift.",
    audio: "Room tone, paper dry and close.",
    seconds: "3.5",
    narration: "Forty-one editions, each one printed a day early.",
  },
  {
    subject: "a front page held at an angle",
    action: "a hand tilts it toward the bulb, showing the photograph on it",
    environment: "the storeroom, bulb behind",
    lens: "close, 50mm, shallow depth",
    prompt:
      "Close shot of a newspaper front page held at a steep angle toward a "
      + "bare bulb. The photograph on the page shows an empty street corner "
      + "at dawn with a single streetlamp. The surrounding type is angled away "
      + "and reads as grey texture only. Film grain.",
    motion: "The page tilts a few degrees further into the light.",
    camera: "Locked off.",
    audio: "Paper flexing, the bulb ticking.",
    seconds: "4",
    narration: "Yesterday's paper carried a photograph of the corner of Vine and Third.",
  },
  {
    subject: "the same street corner",
    action: "empty, with the first grey light coming",
    environment: "corner of Vine and Third, the streetlamp still on",
    lens: "wide, 24mm, deep focus",
    prompt:
      "Wide shot of the same empty street corner at first light, the "
      + "streetlamp still burning, wet asphalt, no people, no van. The framing "
      + "matches the photograph exactly. Cold grey dawn, film grain.",
    motion: "The streetlamp goes out; nothing else moves.",
    camera: "Locked off.",
    audio: "Birds beginning, a distant shutter rolling up.",
    seconds: "3.5",
    narration: "Taken tomorrow.",
  },
];

/** Click a shot row until the inspector is showing *that* shot.
 *
 * Two things make this less obvious than it looks. The row is re-rendered
 * when the save that preceded it lands, so a single click can be delivered to
 * a node on its way out and select nothing. And the inspector keeps showing
 * the previously selected shot until the new one arrives - so waiting for the
 * direction control to be visible proves nothing, because it was already
 * visible. The first run of this file wrote three beats' directions onto one
 * shot that way.
 *
 * A shot that has not been written yet has an empty direction and an empty
 * spoken line, so that is the condition worth waiting for.
 */
async function selectShot(page: Page, row: Locator) {
  const motion = page.getByLabel("What happens in the frame");
  const line = page.getByLabel("Spoken line");
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await row.click();
    try {
      await expect(motion).toHaveValue("", { timeout: 4000 });
      await expect(line).toHaveValue("", { timeout: 4000 });
      return;
    } catch {
      // Still showing the shot before this one. Click again.
    }
  }
  throw new Error("The inspector never followed the row that was clicked.");
}

/** Click a row and wait until the inspector is showing a shot with a
 *  direction control - used where the shot already has one written. */
async function selectShotByRow(page: Page, row: Locator) {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    await row.click();
    try {
      await page
        .getByLabel("What happens in the frame")
        .waitFor({ state: "visible", timeout: 4000 });
      return;
    } catch {
      // Not this one yet.
    }
  }
  throw new Error("The inspector never showed a clip for the row clicked.");
}

async function stage(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Production stages" })
    .getByRole("button", { name, exact: true })
    .click();
}

/** Open the episode by name, whichever project the app happened to select. */
async function selectEpisode(page: Page) {
  await page.goto("/story");
  await page
    .getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
}

test("types SF03 in from the channel down to the last shot", async ({ page }) => {
  // Typing is the phase that gets re-run while the wording is being settled,
  // so it starts clean rather than adding a second half-finished episode
  // beside the first. Deleting is a control now, so it is done the same way
  // as everything else here.
  await page.goto("/story");
  const switcher = page.getByRole("combobox", { name: "Switch project" });
  if ((await switcher.locator(`option`).allTextContents()).includes(EPISODE)) {
    await switcher.selectOption({ label: EPISODE });
    await page.getByRole("button", { name: "Delete this project" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(switcher).not.toContainText(EPISODE);
  }

  // A creator starts at the channel, because that is what carries the house
  // look, the voice and the canvas this episode has to match.
  await page.goto("/channel");
  // The premise board above has its own pillar, hook and premise controls, so
  // the episode form is the last of each on the page.
  await page.getByRole("textbox", { name: "Episode title" }).fill(EPISODE);
  await page.getByRole("combobox", { name: "Pillar" }).last()
    .selectOption("strange_files");
  await page.getByRole("combobox", { name: "Hook" }).last().selectOption("H01");
  await page.getByRole("textbox", { name: "Premise" }).last().fill(
    "A newspaper vendor notices that the edition delivered each morning "
    + "carries the day that has not happened yet.",
  );
  await page.getByRole("button", { name: "Start episode" }).click();

  await selectEpisode(page);
  await expect(page.getByLabel("Project Title")).toHaveValue(EPISODE);
  await page.getByLabel("Creative Brief").fill(
    "Strange Files, episode three. One impossible fact, stated plainly and "
    + "never explained. No gore, no jump scares, no music stings. The paper is "
    + "never held close enough for a headline to be read - the reveal is a "
    + "photograph and a spoken line, because a model asked for newsprint "
    + "writes a plausible smear and that is what gave the last episode away.",
  );
  await page.getByLabel("Plot / Narrative").fill(
    SHOTS.map((shot) => shot.narration).join(" "),
  );
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  // Three scenes: the delivery, the paper, and what it turns out to be a
  // photograph of. A plate belongs to a scene rather than to an episode.
  const scenes = [
    { title: "The corner before dawn", time: "4:40 in the morning, wet street",
      summary: "A van leaves a bundle of papers under one working streetlamp.",
      seconds: "11" },
    { title: "The kiosk", time: "first light, kiosk bulb on",
      summary: "The vendor cuts the twine and the top page settles open.",
      seconds: "10.5" },
    { title: "The storeroom", time: "dawn, one bare bulb",
      summary: "Forty-one kept editions, and a photograph of the corner outside.",
      seconds: "11" },
  ];

  await stage(page, "Storyboard");
  for (const scene of scenes) {
    await page.getByRole("button", { name: "Add Scene" }).click();
  }
  const cards = page.locator("article, div").filter({ hasText: /^Scene /  });

  for (const [index, scene] of scenes.entries()) {
    const edit = page.getByRole("button", { name: /^Edit scene / }).nth(index);
    await edit.click();
    await page.getByLabel("Scene title").fill(scene.title);
    await page.getByLabel("Scene time of day").fill(scene.time);
    await page.getByLabel("Scene summary").fill(scene.summary);
    await page.getByLabel("Scene planned duration in seconds").fill(scene.seconds);
    await page.getByRole("button", { name: "Save scene" }).click();
    await expect(page.getByText(scene.title)).toBeVisible();
  }
  expect(await cards.count()).toBeGreaterThan(0);

  // Each beat is two shots, which is how both delivered episodes were made:
  // a key image that establishes the frame, and a clip animated from it. The
  // key image is not part of the cut - it exists so the clip has somewhere to
  // start - and leaving that box ticked is what once turned 32 seconds of
  // film into 48.
  const negatives =
    "legible text, headline, masthead, readable words, lettering, watermark, "
    + "faces in focus, modern smartphones";

  for (const [index, shot] of SHOTS.entries()) {
    const sceneIndex = Math.floor(index / 3);
    const beat = index % 3;
    const addShot = page.getByRole("button", { name: "Add Shot" }).nth(sceneIndex);
    const rows = page.locator("tbody").nth(sceneIndex).locator("tr");

    // -- the key image ----------------------------------------------------
    await addShot.click();
    await expect(rows).toHaveCount(beat * 2 + 1);
    const keyRow = rows.nth(beat * 2);
    await keyRow.getByRole("button", { name: /^Edit shot / }).click();
    await page.getByLabel("Shot type").fill(shot.lens.split(",")[0]);
    await page.getByLabel("Lens and framing").fill(shot.lens);
    await page.getByLabel("Shot subject").fill(`${shot.subject} (key image)`);
    await page.getByLabel("Shot action").fill(shot.action);
    await page.getByLabel("Shot environment").fill(shot.environment);
    await page.getByLabel("Planned duration in seconds").fill(shot.seconds);
    await page.getByLabel("Image prompt").fill(shot.prompt);
    await page.getByLabel("Shot negative prompt").fill(negatives);
    await page.getByLabel("Shot workflow").selectOption({ label: SHOT_WORKFLOW });
    await page.getByLabel("Include this shot in the cut").uncheck();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText(`${shot.subject} (key image)`)).toBeVisible();

    // -- the clip ---------------------------------------------------------
    await addShot.click();
    await expect(rows).toHaveCount(beat * 2 + 2);
    const clipRow = rows.nth(beat * 2 + 1);
    await clipRow.getByRole("button", { name: /^Edit shot / }).click();
    await page.getByLabel("Generation mode").selectOption("image-to-video");
    await page.getByLabel("Shot type").fill(shot.lens.split(",")[0]);
    await page.getByLabel("Lens and framing").fill(shot.lens);
    await page.getByLabel("Shot subject").fill(shot.subject);
    await page.getByLabel("Shot action").fill(shot.action);
    await page.getByLabel("Shot environment").fill(shot.environment);
    await page.getByLabel("Planned duration in seconds").fill(shot.seconds);
    await page.getByLabel("Image prompt").fill(shot.prompt);
    await page.getByLabel("Shot negative prompt").fill(negatives);
    await page.getByLabel("Shot workflow").selectOption({ label: CLIP_WORKFLOW });
    await page.getByRole("button", { name: "Save", exact: true }).click();

    // The direction and the spoken line live in the inspector, beside the
    // compiled prompt, because that is where a clip is read. The direction
    // control appears only on a shot that actually makes a clip.
    await selectShot(page, clipRow);
    await page.getByLabel("What happens in the frame").fill(shot.motion);
    await page.getByLabel("How the camera behaves").fill(shot.camera);
    await page.getByLabel("What it sounds like").fill(shot.audio);
    await page.getByRole("button", { name: "Save direction" }).click();
    await expect(page.getByText("Saved. Generate this shot again")).toBeVisible();

    await page.getByLabel("Spoken line").fill(shot.narration);
    await page.getByRole("button", { name: "Save captions" }).click();
    await expect(page.getByText("Saved. Render again")).toBeVisible();
  }
});

/** One plate per scene: the place, established once, generated text-to-image.
 *
 * Both delivered episodes were held together this way. The key images are then
 * edits of the plate rather than nine separate inventions of the same street,
 * which is what keeps three shots of a kiosk in one kiosk.
 */
const PLATES = [
  {
    name: "SF03 — the corner before dawn",
    prompt:
      "Vertical 9:16 cinematic documentary photograph. An empty city street "
      + "corner before dawn: closed shutters, wet asphalt, one working "
      + "streetlamp, a shuttered newspaper kiosk on the near corner. Cold blue "
      + "light, weak tungsten from the lamp, 35mm film grain. No people, no "
      + "text, no signage.",
  },
  {
    name: "SF03 — the kiosk interior",
    prompt:
      "Vertical 9:16 cinematic documentary photograph. The inside of a small "
      + "newspaper kiosk before opening: a worn wooden counter, stacked "
      + "newspapers seen edge-on, a warm bare bulb overhead, the cold blue "
      + "street through the hatch. 35mm film grain. No people, no readable "
      + "text.",
  },
  {
    name: "SF03 — the storeroom",
    prompt:
      "Vertical 9:16 cinematic documentary photograph. A narrow storeroom "
      + "behind a kiosk: tied bundles of newspapers stacked against a damp "
      + "wall, one bare bulb, dust in the air, a wooden stool. 35mm film "
      + "grain. No people, no readable text.",
  },
];

test("generates the plates each scene is built on", async ({ page }) => {
  await selectEpisode(page);

  // Start from no plates. A re-run otherwise leaves the sheet it half-made
  // beside the new one, and a shot conditioned on the empty one generates
  // whatever the workflow was exported with.
  //
  // The list has to have arrived before it can be emptied: counting while the
  // query was still in flight found nothing to delete and then added a fourth
  // sheet to the three that were already there.
  await expect(page.getByRole("button", { name: "Add sheet" })).toBeVisible();
  const generators = page.getByRole("button", { name: "Generate canonical image" });
  await expect
    .poll(async () => generators.count(), { timeout: 30_000, intervals: [500] })
    .toBe(await (async () => {
      await page.waitForTimeout(2000);
      return generators.count();
    })());

  const stale = page.getByRole("button", { name: /^Delete SF03 / });
  for (let count = await stale.count(); count > 0; count = await stale.count()) {
    await stale.first().click();
    await expect(stale).toHaveCount(count - 1);
  }
  await expect(generators).toHaveCount(0);

  for (const plate of PLATES) {
    await page.getByRole("combobox", { name: "Reference kind" }).selectOption("location");
    await page.getByRole("textbox", { name: "Reference name" }).fill(plate.name);
    await page.getByRole("button", { name: "Add sheet" }).click();

    // A generator that has been opened stays open, so the only unopened one on
    // the page is the sheet just added.
    const opener = page.getByRole("button", { name: "Generate canonical image" });
    await expect(opener).toHaveCount(1);
    await opener.click();

    // A generator that has already run stays open, so every field here is the
    // last of its kind on the page - this sheet's.
    await page.getByLabel("Plate prompt").last().fill(plate.prompt);
    await page.getByLabel("Plate workflow").last()
      .selectOption({ label: PLATE_WORKFLOW });
    // A fixed seed, so a plate that has to be re-made comes back the same and
    // a change in the picture is a change somebody made on purpose.
    await page.getByLabel("Plate seed").last()
      .fill(String(120_003 + PLATES.indexOf(plate)));
    // The rail's own Generate stage answers to the same name.
    const run = page
      .getByRole("region", { name: "Visual Reference Bible" })
      .getByRole("button", { name: "Generate", exact: true })
      .last();
    const attached = page.getByRole("button", { name: /^Detach image / });
    const before = await attached.count();
    await run.click();

    // Real generation on the local card - seconds for a still, where a clip is
    // minutes. Waiting for the button to be enabled again proves nothing: it
    // is enabled until the request is in flight and enabled again the instant
    // it fails. What says the plate exists is the sheet gaining an image.
    await expect(attached).toHaveCount(before + 1, { timeout: 5 * 60_000 });
    await expect(page.getByRole("alert")).toHaveCount(0);
  }
});

test("generates the key images each clip starts from", async ({ page }) => {
  await selectEpisode(page);
  await stage(page, "Storyboard");

  // Every shot in a scene is conditioned on that scene's plate. This is what
  // keeps three shots of one kiosk in one kiosk: they are edits of the same
  // approved image rather than three separate inventions of it.
  for (let sceneIndex = 0; sceneIndex < PLATES.length; sceneIndex += 1) {
    const rows = page.locator("tbody").nth(sceneIndex).locator("tr");
    await expect(rows).toHaveCount(6);

    for (let rowIndex = 0; rowIndex < 6; rowIndex += 1) {
      const row = rows.nth(rowIndex);
      await row.getByRole("button", { name: /^Edit shot / }).click();
      const attach = page.getByRole("combobox", { name: "Attach reference" });
      const options = await attach.locator("option").allTextContents();
      const plate = options.find((text) => text.includes(PLATES[sceneIndex].name));
      if (plate) await attach.selectOption({ label: plate });
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.getByRole("button", { name: "Save", exact: true }))
        .toHaveCount(0);
    }
  }

  // Preflight has to clear before anything is queued: an unmapped field or a
  // shot with no reference is a render that produces whatever the graph was
  // exported with, which is worse than a refusal.
  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText("All 18 shot(s) ready to generate")).toBeVisible();

  await page.getByTestId("generate-button").click();

  // Nine stills on the local card, then nine clips. This waits for the queue
  // to empty rather than for a fixed time, and reports what it saw.
  const queueEmpty = page.getByText(/No jobs in this view|0 queued/);
  await expect(queueEmpty.first()).toBeVisible({ timeout: 40 * 60_000 });
});

test("stops the clips that would start from the wrong frame", async ({ page }) => {
  // A correction, not a step. Attaching the scene's plate to every shot made
  // preflight pass, and it also gave the three clips in a scene the same start
  // frame: all three would animate the wide plate instead of their own key
  // image, so a scene would be three versions of one shot. The stills are
  // wanted; the clips have to wait until each one can start from its own.
  await selectEpisode(page);
  const project = page.url();
  void project;

  const scenes = await (await page.request.get("/api/projects")).json();
  const pid = scenes.find((p: { title: string }) => p.title === EPISODE).id;
  const sceneRows = await (await page.request.get(`/api/projects/${pid}/scenes`)).json();
  const clipIds: string[] = [];
  for (const scene of sceneRows) {
    const shots = await (
      await page.request.get(`/api/projects/${pid}/scenes/${scene.id}/shots`)
    ).json();
    for (const shot of shots) {
      if (shot.generation_mode !== "image") clipIds.push(shot.id.slice(0, 8));
    }
  }

  await stage(page, "Generate");
  for (const id of clipIds) {
    const row = page.locator("tr").filter({ hasText: id });
    const cancel = row.getByTitle("Cancel");
    if (await cancel.count()) await cancel.first().click();
  }
});

test("pins the edit graph to the size it was tuned for", async ({ page }) => {
  // Found by watching the first pass: a key image took forty-five minutes and
  // was still at step 8 of 25. The shot asks for the project's delivery canvas
  // - 1080x1920 - and this graph was built and measured at 576x1024, which is
  // the same 9:16 with a third of the pixels. At the larger size the card is
  // thrashing rather than rendering.
  //
  // The size a graph renders at is a property of the graph, not of the shot,
  // which is what the fixed settings on a workflow are for. The delivery
  // canvas is applied when the film is assembled.
  await page.goto("/workflows");
  const card = page.locator("article", {
    hasText: "Boogu Edit INT8 (1 ref, guidance 9)",
  });
  await card.getByLabel("Workflow constants").fill(
    '{"samplerCfg": 9.0, "width": 576, "height": 1024}',
  );
  await card.getByRole("button", { name: "Save mapping" }).click();
  await expect(card.getByRole("alert")).toHaveCount(0);
  await card.getByRole("button", { name: "Validate against the graph" }).click();
  await expect(
    card.getByText("Every mapped field reaches a node in this graph."),
  ).toBeVisible();
});

test("rejects what the first pass made before the graph was pinned", async ({ page }) => {
  // Two takes exist from the first attempt: a still rendered at the delivery
  // canvas, which took forty-five minutes and was abandoned, and a clip that
  // animated the scene's plate instead of its own key image. Both are wrong,
  // and a shot with a take awaiting review is a shot the queue refuses to
  // touch - correctly, because regenerating over an unreviewed take throws
  // away the thing somebody was about to look at.
  await selectEpisode(page);
  await stage(page, "Review");

  const reject = page.getByRole("button", { name: "Reject", exact: true });
  for (let count = await reject.count(); count > 0; count = await reject.count()) {
    await reject.first().click();
    await expect(reject).toHaveCount(count - 1);
  }
});

test("re-makes the one key image that was left marked stale", async ({ page }) => {
  // The way out of a state the first pass left behind. A shot whose take was
  // rejected keeps the mark of what it produced, so preflight calls it stale
  // and refuses it - and the way to clear a stale shot is to make it again,
  // which is what Regenerate is for. It works on a rejected take, which is
  // the point: the rejection is the reason to make another one.
  await selectEpisode(page);
  await stage(page, "Review");

  // The innermost element that carries both this take's name and a regenerate
  // button is the card for it. Filtering on the text alone matches every
  // wrapper up to the page.
  const card = page
    .locator("div")
    .filter({ has: page.getByRole("button", { name: "Regenerate" }) })
    .filter({ hasText: "The corner before dawn · Shot 1" })
    .last();
  await card.getByRole("button", { name: "Regenerate" }).click();

  // The new take arrives from the local card in under a minute at the size the
  // graph is now pinned to, where the first attempt was still at step 8 of 25
  // after forty-five minutes on the delivery canvas.
  await expect(page.getByRole("button", { name: "Approve", exact: true }))
    .toHaveCount(1, { timeout: 10 * 60_000 });
});

test("sets the canvas the graphs were tuned for", async ({ page }) => {
  // The size a shot asks for comes from the project, not from the workflow: a
  // shot's own value wins over a graph's fixed setting, by design, and the
  // shot's width and height are the project's delivery canvas. So pinning the
  // graph did nothing, and the first key image came back 1080x1920 after four
  // and a half minutes.
  //
  // 576x1024 is the same 9:16 with a third of the pixels, and it is what both
  // delivered episodes were made at. Delivery scales up at the end; generation
  // happens where the models were measured.
  await selectEpisode(page);
  // Wait for the project to be in the form before typing into it, the way a
  // person waits for a page to settle.
  await expect(page.getByLabel("Project Title")).toHaveValue(EPISODE);
  await page.getByLabel("Delivery Resolution").fill("576x1024");
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();
});

test("approves what is waiting and generates the rest of the key images", async ({ page }) => {
  await selectEpisode(page);

  // Approve anything already made and waiting. A shot with a take under review
  // is a shot the queue refuses, and this is the decision that clears it - the
  // one the reviewer is there to make.
  await stage(page, "Review");
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  for (let count = await approve.count(); count > 0; count = await approve.count()) {
    await approve.first().click();
    await expect(approve).toHaveCount(count - 1);
  }

  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText(/shot\(s\) ready to generate/)).toBeVisible();
  await expect(page.getByText("0 blocking issues")).toBeVisible();
  await page.getByTestId("generate-button").click();

  // Only the stills are wanted from this pass: the clips still have the plate
  // as their start frame, and each one has to start from its own key image.
  // They are cancelled by the phase that runs next.
  await expect(page.getByText(/Queued|Running/).first()).toBeVisible();
});

test("binds the first clip to its own key image and makes it", async ({ page }) => {
  // The shape both delivered episodes were made in, done here through the
  // pages: approve the key image, bind it as the clip's start frame, and
  // animate that. Until it is bound the clip starts from the scene's plate,
  // which is a picture of the place rather than of this shot.
  await selectEpisode(page);
  await stage(page, "Review");

  // Takes are listed newest first, and the one still waiting is the older
  // attempt at the wrong canvas. Rejecting a take whose shot has moved on is
  // the only thing that can be done with it: approving it is refused, and
  // says so - "the shot changed after it was generated".
  const pending = page.getByRole("button", { name: "Reject", exact: true });
  for (let count = await pending.count(); count > 0; count = await pending.count()) {
    await pending.first().click();
    await expect(pending).toHaveCount(count - 1, { timeout: 30_000 });
  }

  // Bind it as the clip's start frame, in the shot that will be animated.
  await stage(page, "Storyboard");
  const clip = page.locator("tbody").first().locator("tr").nth(1);
  await clip.getByRole("button", { name: /^Edit shot / }).click();
  const picker = page.getByRole("combobox", {
    name: "Choose an approved scene image take",
  });
  // The candidates are fetched when the editor opens; reading the options
  // before they arrive finds only the placeholder.
  await expect(page.getByText("Loading continuity candidates")).toHaveCount(0);
  await expect.poll(async () => picker.locator("option").count(), {
    timeout: 30_000,
  }).toBeGreaterThan(1);
  const options = await picker.locator("option").allTextContents();
  const first = options.find((text) => text.includes("Shot 1"));
  expect(first, "the approved key image should be offered").toBeTruthy();
  await picker.selectOption({ label: first as string });
  await page
    .getByRole("button", { name: "Use approved scene image as start frame" })
    .click();
  // Assert the binding, not the button that offers it: the first version of
  // this checked for the words "start frame" and passed while nothing had
  // been bound at all, because those words are on the button.
  await expect(
    page.getByText(/Bound to|Start frame:|capture/i).first(),
  ).toBeVisible({ timeout: 60_000 });
});

test("remakes the clip whose first take was thrown away", async ({ page }) => {
  // The clip for beat one was generated from the scene's plate before its own
  // key image existed, so it was rejected. On the server this project runs
  // against, a shot whose takes are all rejected keeps the mark of what it
  // produced and is refused as stale for ever - the fix for that is committed
  // but not yet running here. The way out with the pages alone is to make the
  // shot again: delete it, type it back, and move it to where it belongs.
  const beat = SHOTS[0];
  await selectEpisode(page);
  await stage(page, "Storyboard");

  const rows = page.locator("tbody").first().locator("tr");
  await expect(rows).toHaveCount(6);
  await rows.nth(1).getByRole("button", { name: /^Delete shot / }).click();
  await expect(rows).toHaveCount(5);

  await page.getByRole("button", { name: "Add Shot" }).first().click();
  await expect(rows).toHaveCount(6);
  const fresh = rows.nth(5);
  await fresh.getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Generation mode").selectOption("image-to-video");
  await page.getByLabel("Shot type").fill(beat.lens.split(",")[0]);
  await page.getByLabel("Lens and framing").fill(beat.lens);
  await page.getByLabel("Shot subject").fill(beat.subject);
  await page.getByLabel("Shot action").fill(beat.action);
  await page.getByLabel("Shot environment").fill(beat.environment);
  await page.getByLabel("Planned duration in seconds").fill(beat.seconds);
  await page.getByLabel("Image prompt").fill(beat.prompt);
  await page.getByLabel("Shot negative prompt").fill(
    "legible text, headline, masthead, readable words, lettering, watermark, "
    + "faces in focus, modern smartphones",
  );
  await page.getByLabel("Shot workflow").selectOption({ label: CLIP_WORKFLOW });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByText(beat.subject).first()).toBeVisible();

  await selectShot(page, rows.nth(5));
  await page.getByLabel("What happens in the frame").fill(beat.motion);
  await page.getByLabel("How the camera behaves").fill(beat.camera);
  await page.getByLabel("What it sounds like").fill(beat.audio);
  await page.getByRole("button", { name: "Save direction" }).click();
  await expect(page.getByText("Saved. Generate this shot again")).toBeVisible();
  await page.getByLabel("Spoken line").fill(beat.narration);
  await page.getByRole("button", { name: "Save captions" }).click();
  await expect(page.getByText("Saved. Render again")).toBeVisible();

  // Back to second place, where the cut needs it: a clip belongs beside the
  // key image it was animated from.
  for (let step = 0; step < 4; step += 1) {
    await rows.last().getByRole("button", { name: /earlier$/ }).click();
    await page.waitForTimeout(400);
  }
});

test("puts the remade clip in its place and gives it a start frame", async ({ page }) => {
  const beat = SHOTS[0];
  await selectEpisode(page);
  await stage(page, "Storyboard");
  const rows = page.locator("tbody").first().locator("tr");

  // The clip, not the key image: both carry the same subject, and only one of
  // them says so.
  const clip = () =>
    rows.filter({ hasText: beat.subject }).filter({ hasNotText: "(key image)" });

  // Second place, beside the key image it is animated from. Moving "the last
  // row" four times moved four different rows; this moves this one.
  for (let step = 0; step < 5; step += 1) {
    const up = clip().getByRole("button", { name: /earlier$/ });
    if (!(await up.count()) || !(await up.first().isEnabled())) break;
    const before = await rows.allInnerTexts();
    await up.first().click();
    await expect.poll(async () => (await rows.allInnerTexts()).join("|"), {
      timeout: 15_000,
    }).not.toBe(before.join("|"));
    if ((await rows.nth(1).innerText()).includes(beat.subject)) break;
  }

  // The start frame: this clip's own key image, approved a moment ago.
  await clip().getByRole("button", { name: /^Edit shot / }).click();
  const picker = page.getByRole("combobox", {
    name: "Choose an approved scene image take",
  });
  await expect(page.getByText("Loading continuity candidates")).toHaveCount(0);
  await expect
    .poll(async () => picker.locator("option").count(), { timeout: 30_000 })
    .toBeGreaterThan(1);
  const options = await picker.locator("option").allTextContents();
  const source = options.find((text) => text.includes("Shot"));
  expect(source, "an approved key image should be offered").toBeTruthy();
  await picker.selectOption({ label: source as string });
  await page
    .getByRole("button", { name: "Use approved scene image as start frame" })
    .click();
  await expect(
    page.getByRole("button", { name: /Clear continuity/ }),
  ).toBeVisible({ timeout: 60_000 });
});

test("runs the shots that are ready", async ({ page }) => {
  // The button now says what the endpoint does: it queues the shots whose
  // status makes them eligible and leaves the approved one alone.
  await selectEpisode(page);
  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText(/shot\(s\) ready/)).toBeVisible();
  const generate = page.getByTestId("generate-button");
  await expect(generate).toBeEnabled({ timeout: 30_000 });
  await generate.click();
  // The request is in flight when the click returns, and the page already has
  // old jobs on it - so looking for the words "Queued" or "Running" finds
  // yesterday's and proves nothing. The button disabling itself is the run
  // actually starting.
  await expect(generate).toBeDisabled({ timeout: 30_000 });
  await expect(generate).toBeEnabled({ timeout: 120_000 });
});

test("approves the key images and gives every clip its own start frame", async ({ page }) => {
  await selectEpisode(page);

  // Approve every still that is waiting. These are the frames the clips will
  // be animated from, so this is the decision that has to be made first.
  await stage(page, "Review");
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  for (let count = await approve.count(); count > 0; count = await approve.count()) {
    await approve.first().click();
    await expect(approve).toHaveCount(count - 1, { timeout: 30_000 });
  }

  await stage(page, "Storyboard");
  // Wait for the storyboard to arrive. Counting rows before it does finds
  // none, and a loop over none is a pass that bound nothing.
  await expect(page.locator("tbody").first().locator("tr").first())
    .toBeVisible({ timeout: 30_000 });
  await expect
    .poll(async () => page.locator("tbody").count(), { timeout: 30_000 })
    .toBe(3);

  for (let sceneIndex = 0; sceneIndex < 3; sceneIndex += 1) {
    const rows = page.locator("tbody").nth(sceneIndex).locator("tr");
    await expect.poll(async () => rows.count(), { timeout: 30_000 })
      .toBeGreaterThan(0);
    const total = await rows.count();
    for (let rowIndex = 0; rowIndex < total; rowIndex += 1) {
      const row = rows.nth(rowIndex);
      const order = (await row.locator("td").first().innerText()).trim().split("\n")[0];
      await row.getByRole("button", { name: /^Edit shot / }).click();

      const mode = page.getByLabel("Generation mode");
      if ((await mode.inputValue()) === "image") {
        await page.getByRole("button", { name: "Cancel" }).first().click();
        continue;
      }
      // The candidates load after the editor opens, and "already bound" is
      // only knowable once they have: checking too early found nothing bound
      // and tried to bind a clip that already had its frame.
      await expect(page.getByText("Loading continuity candidates"))
        .toHaveCount(0, { timeout: 30_000 });
      if (await page.getByRole("button", { name: /Clear continuity/ }).count()) {
        await page.getByRole("button", { name: "Cancel" }).first().click();
        continue;
      }

      // The plate comes off first. It was attached to every shot so preflight
      // would pass before any key image existed; now the clip has a frame of
      // its own to start from, and this graph takes one image. Leaving both
      // on means the one that reaches the model is whichever the resolver
      // happens to pick.
      const attached = page.getByRole("button", { name: /^Detach / });
      for (let n = await attached.count(); n > 0; n = await attached.count()) {
        await attached.first().click();
        await expect(attached).toHaveCount(n - 1);
      }

      // The key image for this beat is the shot immediately before it.
      const previous = String(Number(order) - 1);
      const picker = page.getByRole("combobox", {
        name: "Choose an approved scene image take",
      });
      await expect(page.getByText("Loading continuity candidates")).toHaveCount(0);
      await expect
        .poll(async () => picker.locator("option").count(), { timeout: 30_000 })
        .toBeGreaterThan(1);
      const options = await picker.locator("option").allTextContents();
      const own = options.find((text) => text.includes(`Shot ${previous} `));
      expect(own, `shot ${order} should be offered shot ${previous}`).toBeTruthy();
      await picker.selectOption({ label: own as string });
      await page
        .getByRole("button", { name: "Use approved scene image as start frame" })
        .click();
      await expect(
        page.getByRole("button", { name: /Clear continuity/ }),
      ).toBeVisible({ timeout: 60_000 });
      // Binding is saved by the control itself; detaching the plate is part of
      // the shot form, so it needs the form's own Save.
      await page.getByRole("button", { name: "Save", exact: true }).click();
      await expect(page.getByRole("button", { name: "Save", exact: true }))
        .toHaveCount(0);
    }
  }
});

/**
 * The one still that had to go back.
 *
 * Every shot in this episode carries a negative prompt that names legible
 * text, headlines and lettering, and the edit model wrote three of them
 * anyway: the kiosk's overhead shot came back with pages pinned behind the
 * counter reading "NEAYII STR" and "WECRNA LANCR UTS". That is the exact tell
 * SF01 failed its publish gate on, and it confirms what was written there -
 * there is no negative prompt for "spell correctly". The prompt has to remove
 * the *surface*, not ask for the writing on it to be unreadable.
 */
const REJECTED: string[] = [
  // Nothing to send back this pass. The list is only ever true of the pass it
  // was written for: leaving a name here once rejected the remade take too.
];

test("reviews the key images one at a time", async ({ page }) => {
  await selectEpisode(page);
  await stage(page, "Review");

  // Wait for the takes to arrive before counting them: an empty list a moment
  // after the page opens is indistinguishable from nothing left to review, and
  // the loop below would report a finished review having done nothing.
  await expect(
    page.getByRole("button", { name: "Approve", exact: true }).first(),
  ).toBeVisible({ timeout: 30_000 });

  const decided = new Set<string>();

  // One take at a time, reading the card each decision belongs to. Filtering
  // for "a div that contains an Approve button" matches every wrapper up to
  // the page, so the count never settles and the loop stops after one click -
  // which is how the first version of this reviewed exactly one take and
  // reported success.
  for (let guard = 0; guard < 24; guard += 1) {
    const approve = page.getByRole("button", { name: "Approve", exact: true });
    const remaining = await approve.count();
    if (remaining === 0) break;

    const first = approve.first();
    const label = await first.evaluate((el) => {
      const card = el.closest("[class*='rounded-lg']") as HTMLElement | null;
      return card?.innerText ?? "";
    });
    // Two attempts at one shot can both be waiting - a regenerate that was
    // clicked twice. The newest is first in the list, so the first card for a
    // shot is the one to keep and any later card for the same shot is the
    // older attempt.
    const shot = (label.split(String.fromCharCode(10))[0] ?? label).trim();
    const duplicate = decided.has(shot);
    decided.add(shot);
    const bad = duplicate || REJECTED.some((name) => label.includes(name));
    if (bad) {
      await first.locator("xpath=following-sibling::button[1]").click();
    } else {
      await first.click();
    }
    await expect(approve).toHaveCount(remaining - 1, { timeout: 30_000 });
  }
});



test("reworks the two shots that came back wrong", async ({ page }) => {
  await selectEpisode(page);
  await stage(page, "Storyboard");

  // 1. The kiosk overhead. The negative prompt named legible text, headlines
  //    and lettering, and the model wrote three headlines anyway on pages
  //    pinned behind the counter. The fix is not a stronger negative - it is
  //    removing the surface: no pages on display, nothing pinned up, and the
  //    one page in frame seen edge-on.
  const kiosk = page.locator("tbody").nth(1).locator("tr").first();
  await kiosk.getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Image prompt").fill(
    "Overhead shot at a steep raking angle of the top newspaper on a stack, "
    + "on a bare wooden kiosk counter under a warm bulb. The page is seen "
    + "almost edge-on, so its printing is only a grey rhythm. Nothing is "
    + "pinned up, no pages on display, no boards, no posters - bare timber and "
    + "glass behind. Film grain.",
  );
  await page.getByLabel("Shot negative prompt").fill(
    "pages pinned up, display boards, posters, notices, front pages facing "
    + "the camera, legible text, headline, masthead, lettering, watermark",
  );
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);

  // 2. The last beat is the street corner at first light, and it came back as
  //    the storeroom again: it sits in the storeroom scene, so it was
  //    conditioned on the storeroom plate, and the plate decides where a shot
  //    happens. It needs the corner.
  const corner = page.locator("tbody").nth(2).locator("tr").nth(4);
  await corner.getByRole("button", { name: /^Edit shot / }).click();
  const attached = page.getByRole("button", { name: /^Detach / });
  for (let count = await attached.count(); count > 0; count = await attached.count()) {
    await attached.first().click();
    await expect(attached).toHaveCount(count - 1);
  }
  const attach = page.getByRole("combobox", { name: "Attach reference" });
  const options = await attach.locator("option").allTextContents();
  const plate = options.find((text) => text.includes(PLATES[0].name));
  expect(plate, "the corner plate should be offered").toBeTruthy();
  await attach.selectOption({ label: plate as string });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

test("makes the two reworked shots again", async ({ page }) => {
  // Their takes were rejected, so the shots cannot be picked up by the queue
  // on this server - the fix that gives a shot back when its last take is
  // thrown away is committed but not running here. Regenerate works on a
  // rejected take, which is the point of it: the rejection is the reason to
  // make another one.
  await selectEpisode(page);
  await stage(page, "Review");

  // Whichever shots were reworked since the last pass. Like REJECTED above,
  // this is only true of the pass it is written for.
  for (const name of ["The corner before dawn · Shot 1"]) {
    // A shot that already has a take waiting has been made again: leave it.
    const waiting = await page
      .getByRole("button", { name: "Approve", exact: true })
      .evaluateAll((buttons, shot) =>
        buttons.some((el) => {
          const card = el.closest("[class*='rounded-lg']") as HTMLElement | null;
          return (card?.innerText ?? "").includes(shot);
        }), name);
    if (waiting) continue;

    const buttons = page.getByRole("button", { name: "Regenerate" });
    await expect(buttons.first()).toBeVisible({ timeout: 30_000 });
    const count = await buttons.count();
    let found = false;
    for (let index = 0; index < count; index += 1) {
      const button = buttons.nth(index);
      const label = await button.evaluate((el) => {
        const card = el.closest("[class*='rounded-lg']") as HTMLElement | null;
        return card?.innerText ?? "";
      });
      if (label.includes(name)) {
        await button.click();
        found = true;
        break;
      }
    }
    expect(found, `${name} should be on the review page`).toBe(true);
    // Regenerate fetches a fresh price before it submits anything, so the
    // request is still in flight when the click returns. Ending the test here
    // tore the page down before it was sent, and nothing was ever queued.
    // What proves it landed is a take appearing for that shot: the card gains
    // the Approve button a pending take carries.
    await expect
      .poll(async () => page.getByRole("button", { name: "Approve", exact: true }).count(),
        { timeout: 10 * 60_000, intervals: [2000] })
      .toBeGreaterThan(0);
  }

  // Proof the queue actually took them, rather than the page having said so.
  await stage(page, "Generate");
  await expect(page.getByText(/Queued|Running/).first()).toBeVisible({
    timeout: 60_000,
  });
});

test("puts scene one back in the order the story is told in", async ({ page }) => {
  // The first beat's clip was remade, and a remade shot is appended: it sat at
  // the end of its scene, so the film would have opened with the second beat
  // and ended the scene on the first. Order is what the cut follows.
  const beat = SHOTS[0];
  await selectEpisode(page);
  await stage(page, "Storyboard");
  const rows = page.locator("tbody").first().locator("tr");
  await expect(rows.first()).toBeVisible({ timeout: 30_000 });

  const clip = () =>
    rows.filter({ hasText: beat.subject }).filter({ hasNotText: "(key image)" });

  for (let step = 0; step < 6; step += 1) {
    const second = await rows.nth(1).innerText();
    if (second.includes(beat.subject) && !second.includes("(key image)")) break;
    const up = clip().getByRole("button", { name: /earlier$/ }).first();
    if (!(await up.isEnabled())) break;
    const before = (await rows.allInnerTexts()).join("|");
    await up.click();
    await expect
      .poll(async () => (await rows.allInnerTexts()).join("|"), { timeout: 15_000 })
      .not.toBe(before);
  }

  const second = await rows.nth(1).innerText();
  expect(second).toContain(beat.subject);
  expect(second).not.toContain("(key image)");
});

test("re-directs the dead opening and makes the reveal a held frame", async ({ page }) => {
  await selectEpisode(page);
  await stage(page, "Storyboard");
  await expect(page.locator("tbody").first().locator("tr").first())
    .toBeVisible({ timeout: 30_000 });

  // 1. The opening clip did not move. The direction described the van
  //    receding, but the frame it starts from already has the van at the far
  //    end of the street - so there was nothing left to recede. Say what
  //    moves in the frame that exists.
  const opening = page.locator("tbody").first().locator("tr").nth(1);
  await selectShotByRow(page, opening);
  await page.getByLabel("What happens in the frame").fill(
    "The van's tail lights slide left and shrink as it turns the corner. "
    + "Rain falls steadily through the cone of lamplight and darkens the "
    + "pavement.",
  );
  await page.getByRole("button", { name: "Save direction" }).click();
  await expect(page.getByText("Saved. Generate this shot again")).toBeVisible();

  // 2. The reveal is a held frame. Its key image is clean and its clip was
  //    not: animating a page that is being handled makes the model redraw the
  //    page, and it writes on it. The blueprint's own rule is that critical
  //    text is composited in post rather than generated - a still is where
  //    that holds. So the key image joins the cut and the clip leaves it.
  const storeroom = page.locator("tbody").nth(2).locator("tr");
  await storeroom.nth(2).getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Include this shot in the cut").check();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);

  await storeroom.nth(3).getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Include this shot in the cut").uncheck();
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

test("gives the opening clip a graph with more to work with", async ({ page }) => {
  // Twice now the opening has come back with a mean luma change of 0.32 and
  // every sample near-static: the turbo graph, at eight steps, finds nothing
  // to move in a still night street. Re-writing the direction did not change
  // that, so the next thing to change is the graph - which is what a workflow
  // per shot is for.
  await selectEpisode(page);
  await stage(page, "Storyboard");
  const opening = page.locator("tbody").first().locator("tr").nth(1);
  await expect(opening).toBeVisible({ timeout: 30_000 });
  await opening.getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Shot workflow")
    .selectOption({ label: "H3 I2V probe full 576x1024" });
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

test("re-makes the opening frame so there is something in it to move", async ({ page }) => {
  // Three attempts at the opening clip, three dead ones: 0.33 mean luma
  // change and every sample near-static, on the turbo graph and on the full
  // one, with the direction rewritten in between. The graph is not the
  // problem and neither is the wording - the frame is. A distant van on an
  // empty street at night gives an image-to-video model nothing to move.
  //
  // So the key image is remade with the movement already implied: the van
  // close and lit, rain visible in the lamplight, the pavement wet enough to
  // carry a reflection that can shift.
  await selectEpisode(page);
  await stage(page, "Storyboard");
  const key = page.locator("tbody").first().locator("tr").first();
  await expect(key).toBeVisible({ timeout: 30_000 });
  await key.getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Image prompt").fill(
    "Wide shot of an empty city street corner before dawn in heavy rain. A "
    + "white delivery van is close, half in frame at the kerb, its brake "
    + "lights burning red on the wet asphalt and its exhaust visible in the "
    + "cold air. A bundle of newspapers has just been dropped on the pavement "
    + "under a single working streetlamp, rain streaking through the light. "
    + "Closed shutters, no people. Film grain.",
  );
  await page.getByRole("button", { name: "Save", exact: true }).click();
  await expect(page.getByRole("button", { name: "Save", exact: true })).toHaveCount(0);
});

test("re-points the opening clip at the frame that was just remade", async ({ page }) => {
  // The binding names a take, not a shot, so remaking the key image leaves the
  // clip pointing at the picture that was thrown away.
  await selectEpisode(page);
  await stage(page, "Storyboard");
  const clip = page.locator("tbody").first().locator("tr").nth(1);
  await expect(clip).toBeVisible({ timeout: 30_000 });
  await clip.getByRole("button", { name: /^Edit shot / }).click();
  await expect(page.getByText("Loading continuity candidates")).toHaveCount(0, {
    timeout: 30_000,
  });
  const clear = page.getByRole("button", { name: /Clear continuity/ });
  if (await clear.count()) {
    await clear.first().click();
    await expect(clear).toHaveCount(0, { timeout: 30_000 });
  }
  const picker = page.getByRole("combobox", {
    name: "Choose an approved scene image take",
  });
  await expect.poll(async () => picker.locator("option").count(), { timeout: 30_000 })
    .toBeGreaterThan(1);
  const options = await picker.locator("option").allTextContents();
  const own = options.find((text) => text.includes("Shot 0 "));
  expect(own, "the remade opening frame should be offered").toBeTruthy();
  await picker.selectOption({ label: own as string });
  await page.getByRole("button", { name: "Use approved scene image as start frame" }).click();
  await expect(page.getByRole("button", { name: /Clear continuity/ }))
    .toBeVisible({ timeout: 60_000 });
});

test("builds the cut and renders the film", async ({ page }) => {
  await selectEpisode(page);
  await stage(page, "Timeline");
  await page.getByRole("button", { name: "Build Timeline" }).click();
  // Nine items: eight clips and one held frame - the reveal, which is a still
  // because animating a page being handled makes the model write on it.
  await expect(page.getByText(/9 items/)).toBeVisible({ timeout: 60_000 });

  // Narrated with this machine's own voice: free, and it cannot be directed.
  // The channel's voice direction is only read by the metered narrator, and
  // spending on one is a decision for whoever owns the account, not for a
  // production run to make on their behalf.
  await page.getByText("Narrate", { exact: true }).click();
  const render = page.getByRole("button", { name: "Render Review" });
  await expect(render).toBeEnabled();
  await render.click();

  // FFmpeg, locally: a 32-second cut with narration and burned captions takes
  // minutes rather than seconds. The button disabling itself is the render
  // starting - the words "Finished Film" are on the page before it does.
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 20 * 60_000 });
});
