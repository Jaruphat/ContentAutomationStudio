import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * MELLO EP002 — "The Name That Outlived The Plant", 16:9, English.
 *
 * The first Mello episode told this story in two minutes and twenty-four
 * shots, which was enough for the shape of it and not enough for the story.
 * This one starts before anybody was involved - with a salt marsh and a plant
 * that heals - and follows the sweet through Greek and Roman medicine, the
 * monastery gardens, the famine years, the French confectioners who beat air
 * into the root's own gel, the gelatin that quietly replaced the plant, the
 * pipe that decided its shape, and the fire.
 *
 * Everything the previous seven episodes settled applies. Three things matter
 * more here than usual.
 *
 * The character is a marshmallow and the story is full of marshmallows, so
 * every prop of his own kind is spelled out as having no face, no limbs and no
 * scarf. An identity reference plus "a marshmallow on a board" is how a film
 * grows twins.
 *
 * The master is generated at the delivery resolution, so nothing is cropped -
 * EP001 was drawn square and cropped to widescreen at the render.
 *
 * And the holds are planned at the rate this narrator actually reads, not the
 * rate it is asked to read at, then measured and re-cut from the recording.
 */

const CHANNEL = "Mello";
const EPISODE = "MELLO EP002 — The Name That Outlived The Plant";
const MASTER_SHEET = "MELLO master";
const MASTER_SEED = "4821";
const DELIVERY = "1024x576";
const NARRATOR_VOICE = "sage";

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
  + "with a toasted golden brown top, two round glossy black eyes, pink "
  + "blush cheeks, a small open smiling mouth, a dark red knitted scarf with "
  + "hanging ends, a small brown leather backpack, long thin tan wooden arms "
  + "with mitten hands and long thin tan wooden legs in chunky tan boots. "
  + "Never redraw him as a person, an animal, a snowman or a flat drawing. ";

/** One world for the whole film, repeated in every prompt. */
const STYLE =
  " Rendered as a soft cute 3D illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and shallow depth of field, warm "
  + "palette of cream white, toasted gold, brown, deep red and butter yellow. "
  + "No text, no letters, no numbers, no signage, no logos, no flat line art. "
  + "Wide landscape composition with room around him.";

/** The same world with nobody in it. */
const STYLE_PLATE =
  " Rendered as a soft cute 3D illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and shallow depth of field, warm "
  + "palette of cream white, toasted gold, brown, deep red and butter yellow. "
  + "No text, no letters, no numbers, no signage, no logos, no flat line art. "
  + "No people, no characters, no creatures and no faces anywhere in the "
  + "frame. Wide landscape composition.";

/**
 * Said in every shot where marshmallows appear as objects.
 *
 * He is a marshmallow. "A marshmallow on a board" beside an attached identity
 * reference is read as another one of him - the onigiri episode grew twins in
 * five frames that way before the cause was found.
 */
const PROPS_HAVE_NO_FACE =
  " Every other marshmallow in the frame is a plain white block with no face, "
  + "no limbs and no scarf. Exactly ONE character in the frame.";

const NEGATIVE =
  "text, letters, numbers, signage, watermark, logo, flat 2d, line art, "
  + "sketch, anime, human face, nose, ears, hair, fingers, teeth, snowman, "
  + "multiple identical characters, cluttered background, harsh contrast";

const NEGATIVE_PLATE =
  "person, people, character, figure, face, mascot, marshmallow, animal, "
  + NEGATIVE;

const VOICE_DIRECTION =
  "Speak as a small, cheerful young character telling his own story. Light "
  + "and bright, a little curious, warm and friendly. Unhurried and never "
  + "breathless; let each sentence finish and land before the next one "
  + "begins. Slightly warmer and slower on the closing lines.";

/**
 * How long a shot is held: as long as its line takes to say, plus air.
 *
 * 125 words per minute, because that is near the rate this narrator was
 * measured reading - 130 - rather than the 140 it was asked for and the 150
 * the fit check assumes. Planning at a rate the voice does not use is what put
 * forty-one lines of the last episode on top of the line after them. This is
 * still only a starting point: the render measures every line, and the cut is
 * re-timed from the recording afterwards.
 */
const PLANNING_WPM = 125;
const AIR_SEC = 1.0;

export function holdSeconds(line: string): number {
  const words = line.trim().split(/\s+/).filter(Boolean).length;
  return Math.max(3.0, Math.round(((words / PLANNING_WPM) * 60 + AIR_SEC) * 2) / 2);
}

type Beat = { t: string; d: string; plate?: true; props?: true };

/** Eighty-three beats. One sentence, one picture, one hold. */
const BEATS: Beat[] = [
  // — Who is talking ——————————————————————————————————————————————
  { t: "I am a marshmallow.",
    d: "Mello standing in the middle of a plain warm off-white backdrop, one mitten hand raised in a small wave, soft shadow under him." },
  { t: "Sugar, air, and a little gelatin. That is all I am now.",
    d: "Mello standing on a plain warm backdrop with both mitten hands held open in front of him, palms up." },
  { t: "But my name is older than my recipe. Much older.",
    d: "Mello standing small at the bottom of a wide empty warm frame, looking up into the open space above him." },
  { t: "It is the name of a plant, and the plant is not in me any more.",
    d: "Mello standing on a plain warm backdrop holding one pale pink five-petalled flower up in both mitten hands, looking at it." },
  { t: "To find it you have to go back to the water.",
    d: "Wide misty salt marsh at dawn, still water and pale reeds, Mello standing small on the low earth bank." },
  { t: "Not the sea, and not a river. The ground in between.",
    d: "A wide flat salt marsh at dawn, channels of still water winding between low reed beds, pale sky, mist lying on the water, nothing else in the frame.",
    plate: true },
  { t: "Salty, waterlogged, and almost nothing will grow there.",
    d: "Mello standing ankle-deep in shallow grey-green water among sparse thin reeds, flat empty horizon behind him." },
  { t: "Almost.",
    d: "Mello looking down at one tall plant with pale pink flowers growing out of the shallow water beside his boots." },

  // — The plant ——————————————————————————————————————————————————
  { t: "This is the marsh mallow. A tall plant with soft grey-green leaves.",
    d: "Close view of a tall plant with velvety grey-green leaves and pale pink flowers, Mello standing beside it looking at the leaves." },
  { t: "Five pale pink petals, and a stem that can stand as tall as a person.",
    d: "Mello standing very small at the foot of the tall flowering plant, looking up the length of its stem." },
  { t: "It belongs to the same family as the hollyhock and the hibiscus.",
    d: "Mello walking along a garden bed with three different tall flowering plants growing in a row behind him, warm afternoon light." },
  { t: "The Greeks called it althaia, from a word that means to heal.",
    d: "Mello standing in a sunlit stone courtyard beside two terracotta pots holding the same pale pink flowering plant." },
  { t: "That is still its botanical name. The plant is literally called the healer.",
    d: "Mello holding one whole stem of the plant across both mitten hands, standing on a plain warm backdrop." },
  { t: "All of that is because of the root.",
    d: "Mello crouching low beside the base of the plant with one mitten hand resting on the dark soil." },
  { t: "Pull one up and cut it, and it does not run like sap.",
    d: "Close view of a thick pale root lying cut in half on dark soil, Mello crouching beside it looking down." },
  { t: "It stretches. A clear, slippery gel that pulls out into a thread.",
    d: "Close view of two halves of a pale root with a clear glistening thread stretching between them, Mello holding one half up." },
  { t: "The gel is mucilage, and the root is about a third made of it.",
    d: "Mello standing beside a shallow glass dish of clear gel on a worn wooden table, warm light through the dish." },
  { t: "It coats whatever it touches, and that is the reason for everything that follows.",
    d: "Mello holding the shallow glass dish of clear gel up in both mitten hands with warm light shining through it." },

  // — Medicine ————————————————————————————————————————————————————
  { t: "So the first thing anybody made from it was not a sweet. It was a medicine.",
    d: "Mello standing in a dim stone room lined with shelves of small clay jars, one warm lamp burning." },
  { t: "A sore throat is a raw surface, and mucilage lies over it.",
    d: "Mello sitting wrapped in his red scarf holding a warm clay cup close to his face, small wisps of steam rising." },
  { t: "Greek and Roman physicians wrote it down.",
    d: "Mello standing beside a low wooden table holding rolled blank scrolls and a stone mortar, warm lamplight, no writing visible anywhere." },
  { t: "Dioscorides listed it for coughs, and for wounds that would not close.",
    d: "Mello standing beside a wooden rack with bunches of pale dried roots hanging from it in a warm dim room." },
  { t: "Pliny the Elder claimed a spoonful of mallow a day would keep every illness away.",
    d: "Mello holding a small wooden spoon of pale clear gel up in front of him with both mitten hands, eyes wide." },
  { t: "He was wrong. But he was not making it up out of nothing.",
    d: "Mello sitting on a warm stone step with the small wooden spoon resting on his lap, looking down at it." },
  { t: "The root was a poultice too. Boiled soft, wrapped in cloth, laid on a swelling.",
    d: "Mello holding a folded pale cloth bundle in both mitten hands with a little steam rising from it." },
  { t: "In medieval Europe it grew in monastery gardens, in neat beds with the other useful plants.",
    d: "Wide view of a walled garden with low hedged beds and stone arches, Mello walking along the gravel path." },
  { t: "It was also food when there was no food.",
    d: "Mello standing alone in a bare harvested field under a flat grey sky, stubble and dry soil around him." },
  { t: "When the harvest failed, people dug the roots and ate them.",
    d: "Mello crouching in dry cracked soil holding a pale root in both mitten hands." },
  { t: "That is in the oldest writing we have about it. A plant for the destitute.",
    d: "Mello sitting alone on a low stone wall at dusk holding the pale root, cool blue light behind him." },
  { t: "For most of its history, that is what my name meant. Not a treat. A last resort.",
    d: "Mello standing quietly on a plain warm backdrop, head tilted down, arms at his sides." },

  // — The story that may not be true ————————————————————————————————
  { t: "There is one story that is always told about the beginning.",
    d: "Mello standing on a plain warm backdrop with one mitten hand raised, as if asking you to wait." },
  { t: "That in ancient Egypt, four thousand years ago, the root gel was mixed with honey and nuts.",
    d: "Mello standing in a warm sandstone room with painted columns, beside a low table holding a honey jar and a shallow bowl of nuts." },
  { t: "Into a small, pale, sticky sweet.",
    d: "Close view of one small honey-coloured sweet on a shallow stone dish on a low table, Mello leaning in to look at it." },
  { t: "And that it was kept for the gods, and for pharaohs.",
    d: "Mello standing at the foot of wide sandstone steps looking up toward a tall golden doorway in warm evening light." },
  { t: "It is repeated everywhere. The evidence for it is thin.",
    d: "Mello standing on a plain warm backdrop with both mitten hands turned palm up in a small shrug." },
  { t: "Nobody can point to a surviving Egyptian recipe for it.",
    d: "Mello standing beside a single empty stone plinth in a quiet warmly lit gallery." },
  { t: "So: probably. Not certainly. I would rather say that than tell you a better story.",
    d: "Mello standing square on to us in the middle of a plain warm backdrop, calm and still." },

  // — France —————————————————————————————————————————————————————
  { t: "What is certain begins in France, about two hundred years ago.",
    d: "Mello standing on a wet cobbled street at dusk in front of a small warmly lit confectionery shop window." },
  { t: "Confectioners took the same root gel and did something nobody had done with it.",
    d: "Mello standing on a wooden stool at a marble counter beside a large copper bowl." },
  { t: "They beat air into it.",
    d: "Close view of a whisk standing in a copper bowl of pale foam, Mello holding the whisk handle with both mitten hands." },
  { t: "Sugar, egg white, and the root's own gel, whipped until it held its shape.",
    d: "Mello standing on the stool looking down into the copper bowl at a thick white foam." },
  { t: "The gel held the bubbles. That is the whole trick, and it is what mucilage does.",
    d: "Close view of stiff white foam holding soft peaks in a copper bowl, warm light across it." },
  { t: "They called it pâte de guimauve. Guimauve is simply their word for the plant.",
    d: "Mello standing beside a marble slab spread with soft white paste dusted with fine powder." },
  { t: "It was poured into trays of starch and left to set.",
    d: "Mello standing beside shallow wooden trays filled with white powder, rows of small moulded hollows pressed into it." },
  { t: "For a day. Sometimes two.",
    d: "Mello sitting on a stool beside the trays with his chin resting on both mitten hands, a small hourglass on the bench." },
  { t: "Then cut, dusted, and sold.",
    d: "Mello standing at a counter beside a paper-lined tray of soft white squares dusted with fine white powder.",
    props: true },
  { t: "Sold, at first, as a lozenge for a sore throat.",
    d: "Mello holding one soft white square up beside his cheek in both mitten hands.",
    props: true },
  { t: "A sweet that happened to be a medicine, or a medicine that happened to be a sweet.",
    d: "Mello standing between two low pedestals, a small glass apothecary jar on one and a folded paper sweet bag on the other." },
  { t: "Every piece was made by hand, and it took days.",
    d: "Mello standing alone in a quiet workshop at night with one lamp lit above the bench." },
  { t: "So it was expensive, and most people never ate one.",
    d: "A single soft white square on a small pedestal inside a glass shop case, Mello standing outside the glass looking in.",
    props: true },

  // — The plant is taken out ————————————————————————————————————————
  { t: "Then the plant was taken out.",
    d: "Mello standing on a plain warm backdrop looking to one side, a single pale root lying on the ground behind him." },
  { t: "Root gel is slow. It has to be dug, washed, soaked and strained.",
    d: "Mello standing beside a wooden tub of cloudy water with pale roots soaking in it." },
  { t: "Gelatin does the same job and arrives ready to use.",
    d: "Mello standing beside a small clear bowl of pale set jelly on a wooden table." },
  { t: "It holds more air, it sets harder, and it keeps.",
    d: "Mello pressing a plain soft white block gently between both mitten hands so that it springs back.",
    props: true },
  { t: "Egg white and gum arabic took over the rest of the work.",
    d: "Mello standing behind a counter with three small bowls of different pale ingredients set out in a row." },
  { t: "By the end of the eighteen hundreds, the marsh mallow was gone from the marshmallow.",
    d: "Mello standing on a plain warm backdrop holding a pale pink flower in one mitten hand and a plain white block in the other, held apart.",
    props: true },
  { t: "The recipe kept nothing of the plant except its name.",
    d: "Close view of one pale pink flower and one plain white block sitting side by side on a wooden board, Mello standing behind them.",
    props: true },
  { t: "Which is the strangest thing about me, and almost nobody notices it.",
    d: "Mello standing quietly front on in the middle of a plain warm backdrop, arms at his sides." },

  // — Industry ———————————————————————————————————————————————————
  { t: "What happened next was all about speed.",
    d: "Mello standing in a bright open workshop beside a long empty wooden bench." },
  { t: "The starch trays became a machine called a mogul.",
    d: "Mello standing beside a large warm cream-coloured machine feeding a long belt of shallow white powder trays." },
  { t: "It printed rows of hollows into the starch, filled them, and moved on.",
    d: "Close view of rows of small hollows in white powder being filled with pale syrup, Mello watching from the side of the belt." },
  { t: "Thousands an hour, instead of dozens a day.",
    d: "Wide view of long trays of white powder receding into the distance under warm lamps, Mello standing small beside them." },
  { t: "But every piece still had to sit in the starch until it set.",
    d: "Mello sitting on a wooden crate beside the trays with his chin on his hands, waiting." },
  { t: "In nineteen forty-eight, an American confectioner named Alex Doumak changed that.",
    d: "Mello standing beside a clean cream-coloured machine with pipes and dials in a bright room." },
  { t: "He pumped the whipped mixture through long tubes.",
    d: "Close view of a long soft white rope coming out of a nozzle onto a moving belt, Mello standing beside the belt." },
  { t: "It came out as a rope, and the rope was cut into pieces.",
    d: "The soft white rope being cut into even cylinders on a moving belt, Mello watching from the side.",
    props: true },
  { t: "Then tumbled in starch and sugar so they would not stick to each other.",
    d: "Plain white cylinders tumbling inside a slowly turning drum of white powder, Mello standing beside the drum.",
    props: true },
  { t: "No moulds. No drying room. No waiting.",
    d: "Wide bright factory line with plain white cylinders moving past on a belt, Mello standing at the rail watching them go.",
    props: true },
  { t: "That is why the marshmallow in your hand is a cylinder and not a square.",
    d: "Mello holding one plain white cylinder up in both mitten hands on a plain warm backdrop.",
    props: true },
  { t: "A shape decided by a pipe.",
    d: "Close view of a single plain white cylinder resting on a worn wooden board, Mello standing behind the board.",
    props: true },

  // — The fire ————————————————————————————————————————————————————
  { t: "And then it met the fire.",
    d: "Mello sitting on a log beside a small campfire at dusk in a pine forest, holding a long thin stick toward the flames." },
  { t: "Sugar on the outside browns. That is not burning, it is chemistry.",
    d: "Close view of a plain white block on the end of a stick turning golden over low flames, warm orange light.",
    props: true },
  { t: "The surface caramelises into a thin shell.",
    d: "Very close view of a deep golden crisp shell on a toasted white block held over the fire.",
    props: true },
  { t: "Inside, the gelatin melts at about the temperature of your own body.",
    d: "Mello holding a toasted golden block in both mitten hands close to his face, firelight on him.",
    props: true },
  { t: "So the middle turns liquid while the outside stays whole.",
    d: "Close view of a toasted block pulled into two halves with a soft white thread stretching between them.",
    props: true },
  { t: "The recipe for that was printed in a scouting handbook in nineteen twenty-seven.",
    d: "Mello sitting on a log holding a small round wooden plate, firelight warm on him, forest dark behind." },
  { t: "Two biscuits, a piece of chocolate, and one of me.",
    d: "Close view of a small stacked sandwich of two pale biscuits and dark chocolate on a wooden plate, Mello sitting behind it.",
    props: true },
  { t: "Meanwhile the plant went quietly back to being a medicine.",
    d: "Mello standing in a quiet warm room beside a shelf of small glass bottles and bundles of dried pale root." },
  { t: "You can still buy the root, dried, for a cough. It works the way it always did.",
    d: "Mello holding a small open cloth bag of pale dried root pieces in both mitten hands." },
  { t: "So there are two of us now. A plant that heals, and a sweet that does not.",
    d: "Mello standing between the tall pink-flowered plant on one side and a single plain white block on a low stand on the other.",
    props: true },
  { t: "And only one of us kept the name.",
    d: "Mello standing alone front on in the middle of a plain warm backdrop, quiet and still." },
  { t: "A marsh, a flower, and a root that soothed a sore throat.",
    d: "Wide view of the misty salt marsh at dawn again with pale pink flowers among the reeds, Mello standing small on the bank with his back to us." },
  { t: "None of it is in the bag. The name is all that survived.",
    d: "Wide golden hour view of Mello walking away along the edge of the marsh toward the low sun, small in a big warm landscape." },
];

const TOTAL_SEC = BEATS.reduce((sum, beat) => sum + holdSeconds(beat.t), 0);

function promptFor(beat: Beat): string {
  if (beat.plate) return beat.d + STYLE_PLATE;
  return IDENTITY + beat.d + (beat.props ? PROPS_HAVE_NO_FACE : "") + STYLE;
}

/**
 * What the first pass got wrong.
 *
 * Two grew a second Mello - one at the foot of the tall plant, and, worst of
 * all, the closing shot, where two of him walked into the sunset together. The
 * prop rule stops a marshmallow becoming a twin; it does not stop a wide empty
 * landscape from being filled with company, so those say how many characters
 * the frame may hold.
 *
 * The other three asked for a thing stretching or being held and got the thing
 * beside him at the wrong scale instead. They name the board and the size.
 */
const REWORK: { n: number; d: string; props?: true }[] = [
  { n: 10,
    d: "Mello standing very small at the foot of one tall plant with pale pink flowers, looking up the length of its stem. Exactly ONE character in the entire frame and nothing else alive in it." },
  { n: 16,
    d: "Close view of one thick pale root cut into two halves lying on a dark wooden board, a single clear glistening thread of gel stretching between the two cut faces. Mello standing behind the board looking down at it. Exactly ONE character in the frame." },
  { n: 70, props: true,
    d: "Mello standing on a plain warm backdrop holding up one small plain white cylinder about the size of his own mitten hand, in both hands, close to his face." },
  { n: 75, props: true,
    d: "Close view of one toasted golden block pulled into two halves on a wooden board with a soft molten white thread stretching between them, Mello standing behind the board looking at it." },
  { n: 83,
    d: "Wide golden hour view of Mello walking away from us along the edge of the misty marsh toward the low sun, seen from behind, small in a big warm landscape. Exactly ONE character in the entire frame and nobody walking with him." },
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

/**
 * Open this channel's card and return it.
 *
 * The channel page collapses each channel behind an expander, so its fields do
 * not exist in the document until it is opened - and it closes again on every
 * reload. Tolerant of the expander not being there at all, because this page
 * is being redesigned around us.
 */
async function openChannel(page: Page): Promise<Locator> {
  const expander = page.getByRole("button", { name: `Expand ${CHANNEL}` });
  if (await expander.count()) await expander.first().click();
  const card = page.getByRole("article").filter({
    has: page.getByRole("heading", { name: CHANNEL, exact: true }),
  }).first();
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

/** Save a channel and wait for the server to have it before moving on. */
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

/** Reject what a shot produced, rewrite it, and re-make it. */
async function redraw(
  page: Page,
  items: { n: number; d: string; negative?: string; plate?: true; props?: true }[],
) {
  const cardFor = (n: number) =>
    page.getByRole("button", { name: /^Select take / })
      .filter({ hasText: new RegExp(`Shot ${n}\\b`) }).first();

  for (const item of items) {
    await page.goto("/review");
    await expect(cardFor(item.n)).toBeVisible({ timeout: 30_000 });
    const reject = cardFor(item.n)
      .getByRole("button", { name: "Reject", exact: true });
    if (await reject.count()) {
      await reject.click();
      await expect(reject).toHaveCount(0, { timeout: 30_000 });
    }
  }

  await stage(page, "Storyboard");
  const rows = page.locator("tbody").first().locator("tr");
  await expect(rows).toHaveCount(BEATS.length, { timeout: 60_000 });
  for (const item of items) {
    const row = rows.nth(item.n - 1);
    await row.getByRole("button", { name: /^Edit shot / }).click();
    await page.getByLabel("Image prompt").fill(promptFor(item as Beat));
    await page.getByLabel("Shot negative prompt")
      .fill(item.negative ?? (item.plate ? NEGATIVE_PLATE : NEGATIVE));
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true }))
      .toHaveCount(0);
  }

  for (const item of items) {
    await page.goto("/review");
    await expect(cardFor(item.n)).toBeVisible({ timeout: 30_000 });
    const again = cardFor(item.n)
      .getByRole("button", { name: "Regenerate", exact: true });
    await again.click();
    await expect(again).toBeEnabled({ timeout: 120_000 });
  }
}

test("sets the Mello channel up", async ({ page }) => {
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
  // Counting before the list has rendered reads zero and makes a duplicate.
  // Each channel is a collapsed section, so the expander is what proves the
  // list arrived, not the card.
  const expander = page.getByRole("button", { name: `Expand ${CHANNEL}` });
  await expect(
    page.getByRole("button", { name: /^Expand / }).first()
      .or(page.getByText("No channels yet")),
  ).toBeVisible({ timeout: 30_000 });

  if ((await expander.count()) === 0) {
    await page.getByLabel("New channel").fill(CHANNEL);
    // The stage rail now has a "Create" button of its own, so this one is
    // taken from the page body rather than from the whole document.
    await page.getByRole("main")
      .getByRole("button", { name: "Create", exact: true }).click();
    await expect(expander).toHaveCount(1, { timeout: 30_000 });
  }
  const card = await openChannel(page);

  await card.getByLabel("Tagline").fill("Sweet things, long histories.");
  await card.getByLabel("Audience").fill(
    "English-speaking viewers who like short factual history told by a "
    + "character. No prior knowledge assumed.",
  );
  await card.getByLabel("Voice direction").fill(VOICE_DIRECTION);
  await card.getByLabel("Visual bible").fill(
    "Soft cute 3D illustration, clay-like matte surfaces, gentle warm "
    + "lighting, soft shadows, shallow depth of field. Warm palette of cream "
    + "white, toasted gold, brown, deep red and butter yellow. Every word on "
    + "screen is composited at the edit; nothing in frame is ever lettered.",
  );
  await card.getByLabel("Negative prompt").fill(NEGATIVE);
  await card.getByLabel("Camera language").fill(
    "Still frames. Wide establishing shots for places, close shots for the "
    + "making of things. No motion generated; movement is added in the edit.",
  );
  await card.getByLabel("Sound direction").fill(
    "Narration only, no music bed. Delivered at -16 LUFS integrated.",
  );
  await card.getByLabel("Aspect").fill("16:9");
  await card.getByLabel("Resolution").fill(DELIVERY);
  await card.getByLabel("FPS").fill("30");
  await card.getByLabel("Length (sec)").fill(String(Math.round(TOTAL_SEC)));
  await saveChannel(page, card);

  const episodes = card.locator("section").filter({
    has: page.getByRole("heading", { name: "Episodes", exact: true }),
  });
  await episodes.getByLabel("Episode title").fill(EPISODE);
  await episodes.getByLabel("Premise").fill(
    "Mello tells the real history of the sweet he is made of, from the salt "
    + "marsh and the healing root to the pipe that decided his shape, ending "
    + "on the fact that the name is the only part of the plant that survived.",
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

test("types the eighty-three beats in", async ({ page }) => {
  test.setTimeout(60 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("From a salt marsh to a campfire");
  await page.getByLabel("Scene planned duration in seconds")
    .fill(String(Math.round(TOTAL_SEC)));
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("From a salt marsh to a campfire")).toBeVisible();

  const rows = page.locator("tbody").first().locator("tr");
  for (const [index, beat] of BEATS.entries()) {
    await page.getByRole("button", { name: "Add Shot" }).first().click();
    await expect(rows).toHaveCount(index + 1);
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();

    await page.getByLabel("Shot subject").fill(beat.d.slice(0, 56));
    await page.getByLabel("Planned duration in seconds")
      .fill(holdSeconds(beat.t).toFixed(1));
    await page.getByLabel("Image prompt").fill(promptFor(beat));
    await page.getByLabel("Shot negative prompt")
      .fill(beat.plate ? NEGATIVE_PLATE : NEGATIVE);
    await page.getByLabel("Shot workflow").selectOption({
      label: beat.plate
        ? "Z-Image Turbo T2I (Local API)"
        : "Qwen-Image-Edit 2511 Lightning 4-step (1 ref)",
    });

    if (!beat.plate) {
      const attach = page.getByRole("combobox", { name: "Attach reference" });
      const options = await attach.locator("option").allTextContents();
      const master = options.find((text) => text.includes(MASTER_SHEET));
      if (master) await attach.selectOption({ label: master });
    }

    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByRole("button", { name: "Save", exact: true }))
      .toHaveCount(0);

    await selectShot(page, row);
    await page.getByLabel("Spoken line").fill(beat.t);
    await page.getByRole("button", { name: "Save captions" }).click();
    await expect(page.getByText("Saved. Render again")).toBeVisible();
  }
});

test("draws Mello's history", async ({ page }) => {
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

test("re-draws the Mello frames that failed", async ({ page }) => {
  test.setTimeout(90 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await redraw(page, REWORK);
});

/**
 * Five shots this episode never had a problem with, rejected by accident.
 *
 * A --grep for "re-draws the five frames that failed" matched a test of the
 * same shape in another episode's spec, which ran against whichever project
 * was selected and threw away Mello's shots 6, 44, 55, 59 and 68 before
 * failing on the shot count. Their prompts were never touched, so they only
 * need making again. Both tests are named for their episode now.
 */
test("re-runs the Mello frames a stray grep rejected", async ({ page }) => {
  test.setTimeout(60 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Generate");
  await page.getByRole("button", { name: "Run preflight" }).click();
  await expect(page.getByText(/shot\(s\) ready/)).toBeVisible({ timeout: 60_000 });
  // Only Draft, Ready and Failed shots are eligible, and a shot whose every
  // take was rejected is Ready - so this picks up exactly those five and
  // steps over the seventy-eight that are waiting on review.
  const generate = page.getByTestId("generate-button");
  await expect(generate).toBeEnabled({ timeout: 30_000 });
  await generate.click();
  await expect(generate).toBeDisabled({ timeout: 30_000 });
  await expect(generate).toBeEnabled({ timeout: 300_000 });
});

test("cuts and renders Mello's history", async ({ page }) => {
  test.setTimeout(120 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });

  await stage(page, "Review");
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
