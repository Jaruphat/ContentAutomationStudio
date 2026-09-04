# The Cartographer of Small Things

A three-minute narrated short, produced end to end by Content Automation Studio.

## Why this story

The system's real strength is that one approved character survives every shot,
so the story is built around a single protagonist in a series of tableaux
rather than around action continuity the generator cannot hold. Narration
carries the plot; each shot only has to be a beautiful, legible moment. The
turn at the end is the kind that makes a short worth finishing.

## Look

Painterly 2D animation, warm ink lines over muted watercolour. Overcast
northern light, deep teals and paper-white, one recurring warm accent
(lamplight, brass, marigold). Every shot is a held composition with slow
camera drift - the grammar this generator is good at.

## Character

**Ilva Reim**, a cartographer in her late twenties. Short copper hair cut
blunt at the jaw. Round brass-rimmed glasses. A slate-blue wool coat over a
high-necked cream shirt, ink-stained fingers, a canvas satchel of rolled
paper. Slight, upright, always looking down at something small.

## Script

Twenty-three shots at roughly eight seconds each.

| # | Narration | Shot |
|---|-----------|------|
| 1 | They gave her the smallest desk in the survey office, and told her to map whatever nobody else wanted. | Ilva at a cramped desk in a vast drafting hall, alone under one lamp. |
| 2 | So she mapped the crack in a teacup. | Close on her hands drawing a hairline crack in fine detail. |
| 3 | She mapped where the light fell at four in the afternoon, and how it moved by winter. | Light crossing a wooden floor, chalk marks tracking it. |
| 4 | She mapped one ant's road across a courtyard, and gave it a name. | Ilva crouched on cobbles, tiny chalk lines around her. |
| 5 | The other cartographers mapped coastlines. Their work was hung in halls. | Grand wall maps of coastlines in a gallery, admired by figures in coats. |
| 6 | Hers was kept in a drawer that stuck. | A jammed drawer stuffed with small rolled papers. |
| 7 | Twelve years. Nine hundred maps of things too small to matter. | Ilva older, surrounded by towering stacks of small scrolls. |
| 8 | Then the river came. | Dark water rising along a narrow street at night. |
| 9 | It took the harbour, the market, the street where she was born. | Floodwater over a market square, awnings half-submerged. |
| 10 | When the water went down, the city was still there. But it was not the same city. | Grey mud-covered streets, dawn, everything drained of colour. |
| 11 | The great maps still showed the coastline. Coastlines had not changed. | The gallery, wall maps intact, hall empty and silted. |
| 12 | What was gone was smaller than a coastline. | Ilva standing alone in the ruined market, looking at her hands. |
| 13 | The angle of a doorway. The name a family painted above a shop. | A broken doorframe, faded painted lettering barely legible. |
| 14 | Where the light fell at four in the afternoon. | The same wooden floor, now bare and wrecked, no chalk marks left. |
| 15 | So they came, at last, to the drawer that stuck. | Officials in the archive, forcing the jammed drawer open. |
| 16 | And in nine hundred small maps, they found the city. | Small maps spread across a huge table, filling it edge to edge. |
| 17 | Every doorway. Every sign. Every path an ant had taken across a courtyard. | Close on a delicate map of a courtyard, the ant's route inked. |
| 18 | They rebuilt from her drawer. | Scaffolding rising, workers holding small paper maps up to walls. |
| 19 | Not from the coastlines. From the crack in a teacup. | A rebuilt shopfront, sign repainted exactly, Ilva watching. |
| 20 | She never got the large desk. She said she did not want it. | Ilva back at the same small desk, quietly working. |
| 21 | She said the small desk was closer to the small things. | Warm lamplight, her hands drawing, glasses catching the light. |
| 22 | There is a child in the survey office now, mapping the shadow of a railing. | A young girl crouched on a step, chalk in hand, drawing a shadow. |
| 23 | Nobody has told her it does not matter. | Wide shot: the girl small in a great hall, morning light, hopeful. |

Runtime: 23 x 8s = 184 seconds.

## Production notes

- Reference-to-video is the route: it takes the approved canonical views
  directly and composes each scene, which is four times faster here than
  generating a key image and animating it, and needs no key image at all.
- Narration is synthesised locally with the Windows speech voices, so the run
  costs nothing. A hosted voice would sound better; that is a decision with a
  price on it and is left to the user.
- Subtitles come from each shot's dialogue field through the app's own
  subtitle service, burned or soft as configured.

## What was actually produced

Rendered 2026-09-05 from project `cb5ffdc1`. 23 shots, 23 approved takes,
184.0 seconds, 864x480 h264 at 24fps with AAC stereo, 24 MB. Narration
present, no line overran its shot and none failed to be spoken. Evidence and
the contact sheet are under `docs/release_evidence/2026-09-05/short-film/`.

Each shot took about 155 seconds end to end, so the film cost roughly an hour
of GPU. Reference-to-video is what made that possible: measured against the
image-to-video route on the same machine it is four times faster (80s against
349s) and needs no key image at all.

### What did not come out well

Worth recording, because none of it is a pipeline fault and all of it is
fixable in the next pass.

- **Invented lettering.** Shots that call for a painted sign get one, and the
  model cannot spell: a shop front reads "ILVA REREIM", a pediment "NERDA
  KRRSEIM". The prompt asked for no text and got some anyway, because the
  scene description asked for a sign. Either accept it, describe signage
  without naming it, or composite real lettering afterwards.
- **The child in shot 22 reads as an adult.** Every shot is conditioned on the
  same canonical adult, so a second, younger character has nowhere to come
  from. A second character set, approved and bound only to that shot, is the
  fix - which is exactly what character sets are for.
- **Shot 3 is legible but not literal.** "Where the light fell at four in the
  afternoon" came back as a lit floor rather than a floor with chalk marks
  tracking the light. A more concrete description would land it.

### The one real limitation found

A shot cannot be given more than one character set on a one-reference
workflow, so a scene with two named characters needs a multi-reference video
route. The image side already has one; the video side does not yet.
