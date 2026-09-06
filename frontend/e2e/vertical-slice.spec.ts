import { expect, test, type Page } from "@playwright/test";
import path from "node:path";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/**
 * One episode, typed into the pages by hand.
 *
 * Both delivered episodes were produced by posting to the API from Python.
 * That proves the backend and proves nothing about whether a person can use
 * the application, which is a different claim and the one this makes: every
 * value below is typed into a field or chosen from a control that a creator
 * can see, in the order a creator would meet them.
 *
 * The one thing it cannot claim is picture quality. The backend it drives
 * generates deterministic placeholders, because a walk-through that needs a
 * GPU is a walk-through nobody runs.
 */

const GRAPH = path.resolve(
  HERE, "..", "..", "workflows", "source", "api",
  "image_z_image_turbo_int8.api.json",
);

/** Node ids read out of that graph, typed the way a person reads them off
 *  ComfyUI: which node input each logical field is written to. */
const MAPPING: Array<[string, string, string]> = [
  ["positivePrompt", "57:27", "text"],
  ["seed", "57:3", "seed"],
  ["width", "57:13", "width"],
  ["height", "57:13", "height"],
  ["outputPrefix", "9", "filename_prefix"],
];

const WORKFLOW_NAME = "Z-Image Turbo (browser walk-through)";
const PROJECT_TITLE = "The Locked Stairwell";

async function stage(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Production stages" })
    .getByRole("button", { name, exact: true })
    .click();
}

test.describe.configure({ mode: "serial" });

test("a creator can take an episode from nothing to an export", async ({ page }) => {
  await page.goto("/story");

  // ── 1. A graph to generate with ───────────────────────────────────────
  // Nothing can be generated until one is registered, so this is where a
  // person actually has to start.
  await stage(page, "Workflows");
  await expect(page.getByText("until a workflow is registered")).toBeVisible();

  await page.getByLabel("Workflow name").fill(WORKFLOW_NAME);
  await page.getByLabel("Workflow purpose").selectOption("image");
  await page.locator('input[type="file"]').setInputFiles(GRAPH);
  await page.getByRole("button", { name: "Register" }).click();

  const card = page.locator("article", { hasText: WORKFLOW_NAME });
  await expect(card).toBeVisible();

  for (const [field, nodeId, input] of MAPPING) {
    await card.getByLabel(`${field} node id`).fill(nodeId);
    await card.getByLabel(`${field} input name`).fill(input);
  }
  await card.getByLabel("Workflow constants").fill('{"seed": 12345}');
  await card.getByRole("button", { name: "Save mapping" }).click();
  await card.getByRole("button", { name: "Validate against the graph" }).click();
  await expect(
    card.getByText("Every mapped field reaches a node in this graph."),
  ).toBeVisible();

  // ── 2. The brief ──────────────────────────────────────────────────────
  await stage(page, "Story");
  await page.getByRole("button", { name: "New" }).click();
  await page.getByLabel("Project Title").fill(PROJECT_TITLE);
  await page.getByLabel("Objective").fill(
    "A short film about a stairwell that gains a floor overnight.",
  );
  await page.getByLabel("Creative Brief").fill(
    "A two-minute unease piece for a late-night channel. No gore, no jump "
    + "scares, nothing explained.",
  );
  await page.getByLabel("Plot / Narrative").fill(
    "A caretaker counts the landings on his round. Tonight there is one more.",
  );
  await page.getByLabel("Frame Rate (fps)").fill("30");
  await page.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  // ── 3. A scene and a shot ─────────────────────────────────────────────
  await stage(page, "Storyboard");
  await page.getByRole("button", { name: "Add Scene" }).click();

  // A scene arrives called "Scene 1" and everything about it used to be
  // read-only. Two of these fields reach the compiled prompt.
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("The upstairs hall");
  await page.getByLabel("Scene time of day").fill("night");
  await page.getByLabel("Scene summary").fill(
    "He counts the landings and finds one more.",
  );
  await page.getByLabel("Scene planned duration in seconds").fill("12");
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("The upstairs hall")).toBeVisible();

  await page.getByRole("button", { name: "Add Shot" }).click();

  // The camera icon opens the inline editor on the shot row.
  await page.locator("tbody tr").first()
    .getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Shot workflow").selectOption({ label: WORKFLOW_NAME });
  await page.getByLabel("Shot negative prompt").fill("no text, no lettering");
  await page.getByLabel("Shot subject").fill("A caretaker on a concrete landing");
  await page.getByLabel("Shot action").fill("counting the doors under a failing light");
  await page.getByLabel("Planned duration in seconds").fill("6");
  await page.getByLabel("Image prompt").fill(
    "A caretaker stands on a concrete stairwell landing at night, counting "
    + "doors under a failing fluorescent tube.",
  );
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("A caretaker on a concrete landing")).toBeVisible();

  // A second shot, so order is something that can be got wrong. The storyboard
  // used to draw a drag handle that did not drag, and appending was the only
  // way a shot could arrive.
  await page.getByRole("button", { name: "Add Shot" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(2);
  const second = page.locator("tbody tr").nth(1);
  await second.getByRole("button", { name: /earlier$/ }).click();
  await expect(
    page.locator("tbody tr").first().getByText("A caretaker on a concrete landing"),
  ).toHaveCount(0);
  await page.locator("tbody tr").first().getByRole("button", { name: /later$/ }).click();
  await expect(
    page.locator("tbody tr").first().getByText("A caretaker on a concrete landing"),
  ).toBeVisible();

  // The second shot is a key image: generated like any other, and kept out of
  // the cut because it exists only for a later clip to animate from. This is
  // the control that stops a 32-second film quietly becoming 48.
  await page.locator("tbody tr").nth(1)
    .getByRole("button", { name: /^Edit shot / }).click();
  await page.getByLabel("Shot workflow").selectOption({ label: WORKFLOW_NAME });
  await page.getByLabel("Include this shot in the cut").uncheck();
  await page.getByLabel("Image prompt").fill(
    "The same landing, empty, lit only by the failing tube.",
  );
  await page.getByRole("button", { name: "Save" }).click();

  // ── 4. Generate ───────────────────────────────────────────────────────
  // The shot names its own workflow, so no project default is needed. What
  // the page must do is refuse until the shot is actually ready, and say why.
  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText("All 2 shot(s) ready to generate")).toBeVisible();
  await expect(page.getByText("0 blocking issues")).toBeVisible();

  // Mock generation is gated behind an explicit acknowledgement that what
  // comes out is a placeholder, which is the whole point of the gate.
  await page.getByRole("checkbox", { name: /Simulation Mode/ }).check();
  const generate = page.getByTestId("generate-button");
  await expect(generate).toBeEnabled();
  await generate.click();

  // ── 5. Review ─────────────────────────────────────────────────────────
  // The take has to arrive on its own: the queue runs in the background and
  // the page finds out by polling, exactly as it would for a real render.
  await stage(page, "Review");
  const approve = page.getByRole("button", { name: "Approve", exact: true });
  await expect(approve.first()).toBeVisible({ timeout: 60_000 });
  await expect(approve).toHaveCount(2, { timeout: 60_000 });
  await approve.first().click();
  await approve.first().click();
  // Approve is only offered on a Pending take, so its disappearance is the
  // decision having been recorded rather than a badge that says so.
  await expect(approve).toHaveCount(0);

  // ── 6. The cut ────────────────────────────────────────────────────────
  await stage(page, "Timeline");
  await page.getByRole("button", { name: "Build Timeline" }).click();
  // One item, not two: both shots generated and both were approved, and the
  // key image stayed out because its "include in the cut" was cleared. Six
  // seconds because that is what was typed into the shot, not a default.
  await expect(page.getByText(/1 item .* 6\.0s/)).toBeVisible();

  // Where a clip starts and stops inside its take is an editing decision, and
  // the only way to make it used to be rewriting the manifest through the API.
  await page.getByLabel("Clip 1 ends at").fill("4");
  await page.getByLabel("Clip 1 ends at").blur();
  await expect(page.getByText(/1 item .* 4\.0s/)).toBeVisible();

  // ── 7. Export ─────────────────────────────────────────────────────────
  // The strongest thing this can assert: the sentence typed into the shot
  // editor in step 3 comes back out of the far end of the pipeline.
  await stage(page, "Export");
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByTestId("export-storyboard_json").click(),
  ]);
  const file = await download.path();
  const exported = JSON.parse(readFileSync(file!, "utf-8"));
  expect(JSON.stringify(exported)).toContain("failing fluorescent tube");
});

test("the queue refuses a shot that has nothing to draw, and says which", async ({ page }) => {
  // The gate is the part worth proving. A queue that accepts an empty shot
  // spends a GPU minute to produce a picture of nothing, and the first place
  // anyone would find out is Review.
  await page.goto("/story");
  await page.getByRole("button", { name: "New" }).click();
  await page.getByLabel("Project Title").fill("An episode with a hole in it");
  await page.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  await stage(page, "Storyboard");
  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: "Add Shot" }).click();

  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText("Missing image prompt")).toBeVisible();
  await expect(page.getByText("1 blocking issue")).toBeVisible();
  await expect(page.getByTestId("generate-button")).toBeDisabled();
});

test("an episode can be named for upload, and a project thrown away", async ({ page }) => {
  // The last two things a creator does that used to need an HTTP client: type
  // the text that goes in the upload form, and get rid of a project that went
  // nowhere.
  await page.goto("/story");
  await page.getByRole("button", { name: "New" }).click();
  await page.getByLabel("Project Title").fill("A试 project — ตั้งชื่อ");
  await page.getByRole("button", { name: "Create Project" }).click();
  await expect(page.getByText("Project saved successfully.")).toBeVisible();

  await stage(page, "Export");
  await page.getByLabel("Published title").fill("The Extra Room");
  await page.getByLabel("Series label").fill("Strange Floors");
  await page.getByLabel("Published description").fill(
    "A caretaker counts the landings on his round.",
  );
  await page.getByLabel("Published hashtags").fill("#shorts #liminal");
  await page.getByRole("button", { name: "Save publication copy" }).click();

  // Saved, not just typed: the page is reloaded and the text is still there.
  await page.reload();
  await expect(page.getByLabel("Published title")).toHaveValue("The Extra Room");
  await expect(page.getByLabel("Published hashtags")).toHaveValue("#shorts #liminal");

  // The learning loop's other half. The channel page compares episodes and
  // refuses to rank fewer than three per pillar; the numbers it compares had
  // no page to be typed into.
  await page.getByLabel("Views (24h)").fill("1840");
  await page.getByLabel("Average viewed (%)").fill("62.5");
  await page.getByLabel("Analytics notes").fill("posted late");
  await page.getByRole("button", { name: "Record capture" }).click();
  await expect(page.getByText("Capture recorded.")).toBeVisible();

  // A project with a non-ASCII title, because this runs on Windows and the
  // paths under it are the ones that break.
  await page.getByRole("button", { name: "Delete this project" }).click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Switch project" }),
  ).not.toContainText("A试 project");
});
