import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * NORI EP001 — "The Rice Ball Is Older Than The Seaweed", 16:9, English.
 *
 * Produced from the supplied character sheet: a soft 3D onigiri with a dark
 * green nori band, dot eyes, blush cheeks, a red scarf, a leather backpack and
 * wooden mannequin limbs. The episode is the real history of the thing he is
 * made of — rice arriving in the islands, the burned lumps dug up in Ishikawa,
 * the hand that gave him his name, the mountain that gave him his shape, the
 * court, the wars, and the fact the whole film turns on: the flat sheet of
 * seaweed everybody recognises him by is roughly three hundred years old, and
 * the rice ball under it is two thousand.
 *
 * Three things are different from the six episodes before it.
 *
 * The narration is English, so the subtitle preset is the plain one.
 *
 * The episode belongs to a *channel*, because the channel is the only place
 * that carries a voice direction, and the narrator was the part of the last
 * cut that did not work.
 *
 * And the shots are not a fixed five seconds each. Each one is as long as its
 * own line needs, plus air. Fitting the picture to the read rather than the
 * read to the picture is the whole of the pacing fix that was available
 * without new machinery.
 */

const CHANNEL = "Nori";
const EPISODE = "NORI EP001 — The Rice Ball Is Older Than The Seaweed";
const MASTER_SHEET = "NORI master";
const MASTER_SEED = "2841";
const DELIVERY = "1024x576";

const MASTER_PROMPT =
  "ONE character, full body, front view, standing in the centre of a wide "
  + "landscape frame. The character is a cute little onigiri rice ball. His "
  + "head and body are ONE single crisp TRIANGLE: two long straight sloping "
  + "sides meeting at a soft rounded point on top, and a wide flat base. The "
  + "triangle is made of white steamed rice with a soft bumpy rice-grain "
  + "texture. The silhouette is a clean triangle, NOT a dome, NOT an egg and "
  + "NOT a pear. Across the lower part of the triangle, one wide flat "
  + "rectangular patch of very dark green nori seaweed with straight "
  + "horizontal top and bottom edges, like a belt. Above it, a simple friendly "
  + "face: two large round glossy black eyes, two soft pink blush cheeks, and "
  + "one small open smiling mouth. No nose, no ears, no hair, no eyebrows, no "
  + "moustache. LIMBS: two long thin straight tan wooden arms held clearly out "
  + "and away from the body, each about as long as the triangle is tall, "
  + "ending in small rounded mitten hands; two long thin straight tan wooden "
  + "legs, well apart, clearly visible below the triangle, ending in chunky "
  + "rounded tan boots. The arms and legs are slender wooden sticks like a "
  + "small artist mannequin, never short nubs. A soft dark red knitted scarf "
  + "around the narrow upper part of the triangle with two ends hanging down "
  + "the front, and a small brown leather backpack with buckles on his back. "
  + "Rendered as a soft cute 3D character illustration with clay-like matte "
  + "surfaces, gentle warm lighting, soft shadows and a shallow depth of "
  + "field. Warm palette of cream white, tan, brown leather, deep red, amber "
  + "and dark green. BACKGROUND: plain soft warm off-white studio backdrop, "
  + "evenly lit, no scene, no props, no other characters, no lettering.";

/**
 * The sheet's Nori is a crisp triangle with long stick limbs. The first master
 * came back a dome with nubs for arms - the same failure the ink stickman had,
 * in a different medium - so the silhouette is stated three ways in the prompt
 * above, and the shapes it must not be are refused here. Seed chosen from four.
 */
const MASTER_NEGATIVE =
  "pear shape, round blob, egg shape, dome, ball, sphere, short stubby limbs, "
  + "thick legs, nubs for arms, armless, moustache, eyebrows, text, letters, "
  + "numbers, watermark, human face, nose, ears, hair, fingers, sushi roll, "
  + "multiple characters";

const IDENTITY =
  "Use the attached image as the authoritative character identity reference. "
  + "Keep the exact same character: one crisp white triangular rice-ball body "
  + "with bumpy rice-grain texture, a wide dark green nori seaweed patch "
  + "across the lower front, two round glossy black eyes, pink blush cheeks, a "
  + "small open smiling mouth, a dark red knitted scarf with hanging ends, a "
  + "small brown leather backpack, long thin tan wooden arms with rounded "
  + "mitten hands and long thin tan wooden legs in chunky tan boots. Never "
  + "redraw him as a person, an animal, a dome, a pear or a piece of sushi. ";

/** One world for the whole film, repeated in every prompt. */
const STYLE =
  " Rendered as a soft cute 3D illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and shallow depth of field, warm "
  + "palette of cream white, tan, brown, deep red, amber and dark green. No "
  + "text, no letters, no numbers, no signage, no logos, no flat line art. "
  + "Wide landscape composition with room around him.";

/** The same world with the character taken out of it. See the plate rule. */
const STYLE_PLATE =
  " Rendered as a soft cute 3D illustration with clay-like matte surfaces, "
  + "gentle warm lighting, soft shadows and shallow depth of field, warm "
  + "palette of cream white, tan, brown, deep red, amber and dark green. No "
  + "text, no letters, no numbers, no signage, no logos, no flat line art. No "
  + "people, no characters, no creatures and no faces anywhere in the frame. "
  + "Wide landscape composition.";

const NEGATIVE =
  "text, letters, numbers, signage, watermark, logo, flat 2d, line art, "
  + "sketch, anime, human face, nose, ears, hair, fingers, teeth, sushi roll, "
  + "pyramid, cone, ice cream, multiple identical characters, cluttered "
  + "background, harsh contrast";

const NEGATIVE_PLATE =
  "person, people, character, figure, face, mascot, onigiri, rice ball, "
  + "animal, " + NEGATIVE;

const VOICE_DIRECTION =
  "A calm, warm male documentary narrator reading English at about 140 words "
  + "per minute. Unhurried and level; never bright, never salesy. Let each "
  + "sentence finish and land before the next one begins. Slightly warmer and "
  + "slower on the closing lines.";

/**
 * How long a shot is held: as long as its line takes to say, plus air.
 *
 * 135 words per minute rather than the 150 the fit check assumes, because a
 * hosted narrator reads slower than an estimate more often than faster, and an
 * overrun costs more than a held beat. The extra second and a bit is the pause
 * between one sentence and the next - the thing a flat five-second slot either
 * swallows or stretches into silence.
 */
const PLANNING_WPM = 135;
const AIR_SEC = 1.2;

export function holdSeconds(line: string): number {
  const words = line.trim().split(/\s+/).filter(Boolean).length;
  const spoken = (words / PLANNING_WPM) * 60;
  return Math.max(3.5, Math.round((spoken + AIR_SEC) * 2) / 2);
}

type Beat = { t: string; d: string; plate?: true };

/** Seventy-nine beats. One sentence, one picture, one hold. */
const BEATS: Beat[] = [
  // — Who is talking ——————————————————————————————————————————————
  { t: "I am a rice ball.",
    d: "Nori standing in the middle of a plain warm off-white backdrop, one mitten hand raised in a small wave, soft shadow under him." },
  { t: "Rice, salt, and somebody's hands. That is the whole recipe, and it has not changed in two thousand years.",
    d: "Nori standing on a plain warm backdrop with both mitten hands held open in front of him, palms up." },
  { t: "I am older than sushi. I am older than the samurai. I am older than the country I come from.",
    d: "Nori standing small at the bottom of a wide empty warm frame, looking up into the open space above him." },
  { t: "And the part of me everybody recognises, this dark green band, is the newest thing about me.",
    d: "Close view of Nori looking down at the dark green band across his front, one wooden hand resting on it." },
  { t: "Let me start where it started. In the water.",
    d: "Wide view of a flooded rice paddy at dawn, still water reflecting a pale sky, Nori standing small on the narrow earth bank." },

  // — Rice arrives ————————————————————————————————————————————————
  { t: "Rice did not begin in Japan.",
    d: "A wide misty river valley at dawn with terraced flooded paddies stepping down the hillside, low cloud, still water, no living thing in sight.",
    plate: true },
  { t: "It was carried across from the Asian mainland, and about two thousand three hundred years ago it took root in the islands.",
    d: "Nori standing on a grey pebble beach at dawn beside a small wooden boat pulled up on the stones, bundles of green rice seedlings in the boat." },
  { t: "Wet paddy farming came with it, and it rearranged everything about how people lived.",
    d: "Wide view of flooded paddy fields with low thatched wooden houses along the far bank, Nori standing on a raised bank in the foreground." },
  { t: "Rice can be dried and stored. Food that keeps means a village that stays put.",
    d: "Nori standing beside a small raised wooden storehouse on stilts with a thick straw roof, warm morning light." },
  { t: "It also means surplus, and surplus means somebody has to count it.",
    d: "Nori standing at the foot of a tall stack of straw rice bales, looking up at them, holding his small notebook closed under one arm." },
  { t: "But long before the granaries and the taxes, somebody was hungry, and had cooked rice, and no bowl.",
    d: "Nori sitting on a woven straw mat beside a round clay pot of steaming white rice, looking down into it." },

  // — The hand ————————————————————————————————————————————————————
  { t: "So they used what they had.",
    d: "Close view of Nori's two rounded wooden mitten hands cupped together and empty, warm light from the side." },
  { t: "They pressed the rice between their palms until it held its own shape.",
    d: "Close view of Nori pressing his two mitten hands together with a small ball of white rice between them." },
  { t: "The word for that is nigiru. To grasp. To squeeze in the hand.",
    d: "Nori on a plain warm backdrop holding a small white rice ball up in one hand, turning it toward the light." },
  { t: "Which is why I am called onigiri. I am not named after the rice. I am named after the hand.",
    d: "Nori standing on a plain warm backdrop with both arms opened wide, presenting himself, small proud smile." },
  { t: "No plate. No chopsticks. No second fire.",
    d: "Three plain white rice balls sitting in a row on a worn wooden board, Nori standing beside the board looking at them." },
  { t: "Just food you could carry, in the only shape a pair of hands can make.",
    d: "Nori walking along a dirt path between green fields with his leather backpack on, warm late morning light." },

  // — The oldest one ——————————————————————————————————————————————
  { t: "In nineteen eighty-seven, on the west coast, archaeologists opened a hillside site in Ishikawa.",
    d: "Wide view of a terraced hillside excavation in soft mist, cut earth steps, string lines and wooden pegs, Nori standing at the edge of it." },
  { t: "In the soil they found lumps of rice, burned black, about two thousand years old.",
    d: "Nori crouching low on the dark soil, holding a small charred black lump of rice carefully in both mitten hands." },
  { t: "And the lumps were not round. They had been shaped by fingers.",
    d: "Very close view of a small charred black lump of rice lying on a pale cloth, its surface dented with shallow finger marks." },
  { t: "They are usually called the oldest rice balls in Japan.",
    d: "The charred black lump resting on a small pale stand under a warm museum spotlight, Nori standing beside the stand looking up at it." },
  { t: "Though the people who study them are careful about it.",
    d: "Nori sitting on a low wooden bench with his chin resting on both hands, thinking, the small stand beside him." },
  { t: "They may have been chimaki, rice steamed inside a leaf. They may never have been lunch at all.",
    d: "A small parcel of rice wrapped in a broad green bamboo leaf and tied with pale cord, resting on a wooden stand, Nori leaning in to look at it." },
  { t: "They may have been an offering. Food made for something that does not get hungry.",
    d: "Wide misty dawn: Nori standing small at the foot of a simple weathered wooden shrine gate on a green hillside, a leaf-wrapped parcel on a flat stone before it." },

  // — Mountain and knot ———————————————————————————————————————————
  { t: "Which would fit, because of the shape.",
    d: "Nori standing on a high ridge at sunrise looking out at layered blue mountain peaks, his own triangular outline echoing them." },
  { t: "There is another name for me. Omusubi.",
    d: "Nori on a plain warm backdrop, head tilted slightly, one mitten hand lifted as if presenting the word." },
  { t: "It comes from musubu, which means to tie. To bind. To join two things into one.",
    d: "Close view of two wooden mitten hands pulling a simple knot tight in a soft red cord, warm side light." },
  { t: "It is also the name of an old kind of god. The power that brings things into being.",
    d: "A misty forest of tall dark trunks with gold light coming through, a thick straw rope with folded paper streamers tied around one old tree, Nori standing small beneath it." },
  { t: "And the mountains were where those gods were said to live.",
    d: "Wide dawn landscape of layered mountain ridges fading into mist, Nori standing tiny on a foreground rock with his back to us." },
  { t: "So the rice was pressed into a mountain.",
    d: "Close view of Nori's two mitten hands cupped around a small white rice ball, shaping its three flat sides, warm light." },
  { t: "Eat a small mountain, and a little of that travels with you.",
    d: "Nori holding a triangular white rice ball in both hands close to his face, eyes closed, warm golden light on him." },
  { t: "That is a belief, not a fact. But it is the reason I am this shape and not a sphere.",
    d: "Nori standing on a plain warm backdrop turned to three-quarter view, showing his triangular profile against the empty ground." },

  // — Salt and distance ———————————————————————————————————————————
  { t: "The second ingredient did the practical work.",
    d: "Close view of a small shallow wooden dish of coarse white salt on a worn board, Nori's mitten hand dipping into it." },
  { t: "Salt on the outside seasons the rice, and slows down whatever would spoil it.",
    d: "Nori rubbing his two mitten hands together above a white rice ball on a board, fine salt falling through the warm light." },
  { t: "Put a sour pickled plum in the middle, and it keeps longer still.",
    d: "Nori holding a single dark red wrinkled pickled plum up between both mitten hands, a white rice ball on the board beside him." },
  { t: "Rice that keeps is not just a meal. It is a distance.",
    d: "Wide view of Nori walking away from us along a stony mountain road at midday, small against a big open landscape." },
  { t: "It is how far you can go before you have to stop.",
    d: "Wide view of a pale path winding away over green hills toward distant blue peaks, Nori a small figure partway along it." },
  { t: "For most of my history, that was the entire point of me.",
    d: "Nori sitting on a flat rock at a bend in the road, untying the cord on his small cloth lunch pouch." },

  // — The court —————————————————————————————————————————————————
  { t: "A thousand years ago, at the imperial court, I had a place.",
    d: "Nori standing in a long wooden palace corridor with paper screens and a polished dark floor, warm lamplight at the far end." },
  { t: "Not on the high tables.",
    d: "A low black lacquer banquet table set with small fine dishes and glowing paper lamps, Nori standing beside it at floor level, looking up at the table top." },
  { t: "In the records they are called tonjiki. Rice pressed into plain oval lumps.",
    d: "A shallow woven tray holding five plain oval white rice lumps in a row, Nori standing beside the tray." },
  { t: "They were handed out to the guards and the lower attendants, outside, while the banquet went on inside.",
    d: "Nori sitting on a wooden step outside a warmly lit doorway at night, holding an oval white rice lump in both hands." },
  { t: "Which tells you exactly what I have always been.",
    d: "Nori sitting on the wooden step looking down at the rice lump in his hands, warm light spilling past him from the doorway." },
  { t: "Not the feast. The thing you hand to somebody who still has work to do.",
    d: "Close view of two wooden mitten hands holding out a white rice lump toward the edge of the frame, warm night light." },

  // — Four hundred years of walking ————————————————————————————————
  { t: "Then came four hundred years of people fighting each other.",
    d: "Wide dusk landscape of dark hills with rows of plain red and black cloth banners on tall poles along a distant ridge, Nori standing on a rock in the foreground." },
  { t: "Armies do not move on courage. They move on lunch.",
    d: "Nori standing at dawn beside a stack of straw bales and rough wooden crates in a quiet camp clearing." },
  { t: "Soldiers carried rice balls wrapped in leaves, and dried rice they could soak back to life with water.",
    d: "Nori pouring a little pale dried rice from a small cloth bag into a wooden cup, sitting on a log." },
  { t: "A rice ball is a ration you can eat with one hand, standing up, in the rain.",
    d: "Nori standing in light rain under a wide woven straw hat, holding a white rice ball, grey-green hills behind him." },
  { t: "It needs no bowl, no heat, and no fire to show anyone where you are.",
    d: "Nori crouching low behind a mossy rock at dusk in deep blue light, eating quietly, hills dark behind him." },
  { t: "For hundreds of years I fed the people doing the hardest walking.",
    d: "Wide dawn view of a muddy road with a long line of footprints stretching away, Nori walking along it with his pack." },
  { t: "And in all that time, the thing I wear now did not exist.",
    d: "Nori standing on a plain warm backdrop holding a single flat rectangular dark green sheet up in both mitten hands, looking at it." },

  // — The sheet —————————————————————————————————————————————————
  { t: "Seaweed itself is old. People had gathered it off the rocks for as long as they had been standing on them.",
    d: "Wide rocky shoreline at low tide, dark wet seaweed spread across the rocks, shallow pools, Nori standing among them." },
  { t: "By the year seven hundred and one it was valuable enough to be accepted as tax.",
    d: "Nori standing on a wooden dock in the morning mist beside a large woven basket heaped with dark wet seaweed." },
  { t: "But it was a paste, or a dried clump. It was not a sheet.",
    d: "A shallow wooden bowl of dark green seaweed paste sitting on a plank, Nori leaning over the rim to peer into it." },
  { t: "The sheet was borrowed from paper.",
    d: "A wooden papermaking screen being lifted out of a vat, a thin even layer of pale pulp draining across it, water running off, warm workshop light, nobody in the frame.",
    plate: true },
  { t: "In Edo, in the seventeen hundreds, somebody spread seaweed slurry onto a papermaker's screen and dried it in the sun.",
    d: "Nori standing in a bright open yard beside a row of leaning wooden drying screens, each holding one thin dark green sheet." },
  { t: "Flat. Even. Thin enough to fold, strong enough to hold.",
    d: "Nori holding a single dark green sheet up against the low sun so the light glows through it, close view." },
  { t: "They named it after the part of the city that made it.",
    d: "Wide view of a canal lined with low wooden buildings and drying racks, small boats moored along the bank, Nori standing on the towpath." },
  { t: "Only then could anyone wrap a rice ball in it.",
    d: "Close view of two wooden mitten hands folding a dark green sheet around a plain white triangular rice ball on a wooden board." },
  { t: "So the rice in me is two thousand years old. This green band is about three hundred.",
    d: "Nori standing on a plain warm backdrop with both mitten hands resting on the dark green band across his front, looking down at it." },
  { t: "I am wearing something much younger than I am.",
    d: "Nori standing on a plain warm backdrop in three-quarter view, quiet expression, soft shadow beneath him." },

  // — Trains, shelves, machines ————————————————————————————————————
  { t: "In eighteen eighty-five the railway reached a town called Utsunomiya.",
    d: "Wide view of a small wooden country railway platform at dusk with hanging paper lanterns and an empty track, Nori standing on the platform." },
  { t: "The story usually told is that a shop there sold the first station lunch in Japan.",
    d: "Nori standing beside a small wooden platform stall with a plain cloth awning, warm lantern light, no writing anywhere." },
  { t: "It was two rice balls and a slice of pickled radish, wrapped in a bamboo leaf.",
    d: "Close view of an opened broad green bamboo leaf on a wooden bench holding two white rice balls and one pale yellow pickle slice." },
  { t: "Travel food again. The same job, on a faster road.",
    d: "Nori sitting by a train window at golden hour with the leaf parcel open on his lap, blurred green landscape sliding past outside." },
  { t: "Then, in the nineteen seventies, came a problem nobody had needed to solve before.",
    d: "Nori standing on a plain warm backdrop with a limp dull dark green sheet drooping over one outstretched mitten hand." },
  { t: "Wrap seaweed around wet rice and within an hour it goes soft. It stops being crisp. It stops being good.",
    d: "Close view of a wrapped white rice ball on a board with its green sheet visibly limp, dull and clinging." },
  { t: "The answer was a wrapper in two parts, holding the sheet away from the rice until you pull the tab.",
    d: "Nori pulling open a plain blank white wrapper so a crisp dark green sheet folds down onto a white rice ball, no printing of any kind on the wrapper." },
  { t: "Convenience stores took it up in nineteen seventy-eight, and I became something you could buy at two in the morning.",
    d: "Nori standing in front of a brightly lit shelf of plain blank white wrapped triangles at night, everything else dark." },
  { t: "Japan now eats billions of them a year.",
    d: "Wide view of a long lit shelf receding into the distance stacked with plain blank white wrapped triangles, Nori very small in front of it." },
  { t: "Machines press most of them now, at a speed no pair of hands could reach.",
    d: "Nori standing beside a warm cream-coloured machine in a bright room, plain white triangles moving along a short belt." },

  // — What did not change —————————————————————————————————————————
  { t: "But look at what the machines were built to make.",
    d: "Close view of one plain white triangular rice ball sitting alone on a worn wooden board in warm light, Nori's hand resting on the board edge." },
  { t: "Not a cube. Not a brick. A triangle.",
    d: "Nori standing in profile on a plain warm backdrop beside a single white triangular rice ball on a low stand, both shapes matching." },
  { t: "Two thousand years later, the machine is still copying a mountain.",
    d: "Nori standing on a ridge at sunrise with the layered mountain range behind him repeating his own outline." },
  { t: "There are onigiri counters now in cities that never grew a grain of rice.",
    d: "Evening view of a small warmly lit shop front on a wet cobbled European street, Nori standing outside it looking in." },
  { t: "The fillings change everywhere they go. Tuna. Salmon. Things nobody at that Heian banquet would recognise.",
    d: "Nori standing behind a worn wooden counter with a row of small bowls of different coloured fillings laid out in front of him." },
  { t: "The shape does not change.",
    d: "Nori standing square on to us in the middle of a plain warm backdrop, arms at his sides, calm and still." },
  { t: "Because the shape was never a design. It is the print of a pair of hands, closed around something warm.",
    d: "Close view of two wooden mitten hands cupped together holding one small white rice ball, warm light from above." },
  { t: "Made for somebody who has somewhere to go.",
    d: "Wide golden hour view of Nori walking away down a long path toward distant blue mountains with his leather backpack on, small in a big warm landscape." },
];

const TOTAL_SEC = BEATS.reduce((sum, beat) => sum + holdSeconds(beat.t), 0);

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

test("sets the Nori channel up", async ({ page }) => {
  await page.goto("/story");
  const switcher = page.getByRole("combobox", { name: "Switch project" });
  await expect(switcher).toBeVisible({ timeout: 30_000 });
  if ((await switcher.locator("option").allTextContents()).includes(EPISODE)) {
    await switcher.selectOption({ label: EPISODE });
    await page.getByRole("button", { name: "Delete this project" }).click();
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await expect(switcher).not.toContainText(EPISODE);
  }

  await page.goto("/channel");
  // Counting before the list has rendered reads zero and makes a second channel
  // with the same name - which is exactly what an earlier run did. An absent
  // spinner does not prove the list arrived; a rendered card or the empty
  // state does.
  await expect(
    page.getByRole("article").first().or(page.getByText("No channels yet")),
  ).toBeVisible({ timeout: 30_000 });

  const heading = page.getByRole("heading", { name: CHANNEL, exact: true });
  const cards = page.getByRole("article").filter({ has: heading });
  if ((await cards.count()) === 0) {
    await page.getByLabel("New channel").fill(CHANNEL);
    await page.getByRole("button", { name: "Create", exact: true }).click();
    await expect(cards).toHaveCount(1, { timeout: 30_000 });
  }

  // Every field below exists once per channel on this page, so everything is
  // scoped to this channel's own card rather than to the page.
  const card = cards.first();

  // The channel is what carries the reading direction: the render has no field
  // for it, and it is the only lever on the narrator this pipeline has.
  await card.getByLabel("Tagline").fill("Small food. Long history.");
  await card.getByLabel("Audience").fill(
    "English-speaking viewers who like short factual history told by a "
    + "character. No prior knowledge of Japan assumed.",
  );
  await card.getByLabel("Voice direction").fill(VOICE_DIRECTION);
  await card.getByLabel("Visual bible").fill(
    "Soft cute 3D illustration, clay-like matte surfaces, gentle warm "
    + "lighting, soft shadows, shallow depth of field. Warm palette of cream "
    + "white, tan, brown, deep red, amber and dark green. Every word on screen "
    + "is composited at the edit; nothing in frame is ever lettered.",
  );
  await card.getByLabel("Negative prompt").fill(NEGATIVE);
  await card.getByLabel("Camera language").fill(
    "Still frames. Wide establishing shots for places, close two-hand shots "
    + "for the making of things. No motion generated; movement is added in the "
    + "edit.",
  );
  await card.getByLabel("Sound direction").fill(
    "Narration only, no music bed. Delivered at -16 LUFS integrated.",
  );
  await card.getByLabel("Aspect").fill("16:9");
  await card.getByLabel("Resolution").fill(DELIVERY);
  await card.getByLabel("FPS").fill("30");
  await card.getByLabel("Length (sec)").fill(String(Math.round(TOTAL_SEC)));
  await card.getByRole("button", { name: "Save channel bibles" }).click();

  // The premise board on the same card has a Premise field of its own.
  const episodes = card.locator("section").filter({
    has: page.getByRole("heading", { name: "Episodes", exact: true }),
  });
  await episodes.getByLabel("Episode title").fill(EPISODE);
  await episodes.getByLabel("Premise").fill(
    "Nori tells the real history of the onigiri he is, ending on the fact "
    + "that the seaweed everybody knows him by is about three hundred years "
    + "old and the rice ball under it is two thousand.",
  );
  await episodes.getByRole("button", { name: "Start episode" }).click();
  // In the channel's own episode list: the project switcher carries the same
  // words in a hidden <option>, which is not evidence of anything.
  await expect(episodes.getByText(EPISODE)).toBeVisible({ timeout: 30_000 });

  // The master. Its size is the episode's size, because every edited shot
  // downstream inherits the shape of the image it is handed.
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await expect(page.getByRole("button", { name: "Add sheet" })).toBeVisible();
  await page.getByRole("combobox", { name: "Reference kind" }).selectOption("character");
  await page.getByRole("textbox", { name: "Reference name" }).fill(MASTER_SHEET);
  await page.getByRole("button", { name: "Add sheet" }).click();

  // The sheet's negative tokens are what the plate is generated against, so
  // the shapes the master must not be are refused here rather than in prose.
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

test("types the seventy-nine beats in", async ({ page }) => {
  test.setTimeout(60 * 60_000);
  await page.goto("/story");
  await page.getByRole("combobox", { name: "Switch project" })
    .selectOption({ label: EPISODE });
  await stage(page, "Storyboard");

  await page.getByRole("button", { name: "Add Scene" }).click();
  await page.getByRole("button", { name: /^Edit scene / }).click();
  await page.getByLabel("Scene title").fill("Rice, salt, and somebody's hands");
  await page.getByLabel("Scene planned duration in seconds")
    .fill(String(Math.round(TOTAL_SEC)));
  await page.getByRole("button", { name: "Save scene" }).click();
  await expect(page.getByText("Rice, salt, and somebody's hands")).toBeVisible();

  const rows = page.locator("tbody").first().locator("tr");
  for (const [index, beat] of BEATS.entries()) {
    await page.getByRole("button", { name: "Add Shot" }).first().click();
    await expect(rows).toHaveCount(index + 1);
    const row = rows.nth(index);
    await row.getByRole("button", { name: /^Edit shot / }).click();

    await page.getByLabel("Shot subject").fill(beat.d.slice(0, 56));
    await page.getByLabel("Planned duration in seconds")
      .fill(holdSeconds(beat.t).toFixed(1));
    await page.getByLabel("Image prompt").fill(
      beat.plate
        ? beat.d + STYLE_PLATE
        : IDENTITY + beat.d + STYLE,
    );
    await page.getByLabel("Shot negative prompt")
      .fill(beat.plate ? NEGATIVE_PLATE : NEGATIVE);
    await page.getByLabel("Shot workflow").selectOption({
      // A beat with nobody in it must not carry an identity reference: an
      // attached character gets drawn into the frame whatever the prompt says.
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

test("draws Nori's history", async ({ page }) => {
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

test("cuts and renders Nori's history", async ({ page }) => {
  test.setTimeout(120 * 60_000);
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
  await expect(page.getByText(new RegExp(`${BEATS.length} items`)))
    .toBeVisible({ timeout: 60_000 });

  // English captions, so the plain preset rather than the Thai one.
  await page.getByLabel("Subtitle mode").selectOption("burn_in");
  await page.getByLabel("Style preset").selectOption("clean");
  await page.getByRole("button", { name: /Save settings/ }).click();
  await expect(page.getByText(/Saved|saved/).first()).toBeVisible({ timeout: 30_000 });

  await page.getByText("Narrate", { exact: true }).click();
  await page.getByRole("combobox").filter({ hasText: "OpenAI voice" }).first()
    .selectOption("openai");
  const render = page.getByRole("button", { name: "Render Review" });
  await render.click();
  await expect(render).toBeDisabled({ timeout: 30_000 });
  await expect(render).toBeEnabled({ timeout: 60 * 60_000 });
});
