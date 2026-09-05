"""The films this repository knows how to produce.

Kept apart from the producer so a new short is a data change, not a copy of a
script. Each entry carries everything the run needs: the canvas, the cast, the
house look, and the shot list.

One lesson is baked into the look strings. The first film asked for "slow
gentle camera drift" and got exactly that - twenty-three held paintings with a
push in. If the shots are meant to move, the prompt has to describe what
*happens*, not how the camera behaves, and the look must not quietly ask for
stillness.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# The Cartographer of Small Things - 1.8:1, held compositions, narrated
# ---------------------------------------------------------------------------

CARTOGRAPHER: dict[str, Any] = {
    "title": "The Cartographer of Small Things",
    "objective": "A three-minute narrated short about the value of small work.",
    "aspect_ratio": "9:5",
    "resolution": "864x480",
    "seconds_per_shot": 8.0,
    "look": (
        "painterly 2D animation, warm ink linework over muted watercolour, "
        "overcast northern light, deep teal and paper-white palette with one warm "
        "accent, film grain, slow gentle camera drift, no text, no captions"
    ),
    "cast": [{
        "name": "Ilva Reim",
        "appearance": (
            "woman in her late twenties, short copper hair cut blunt at the jaw, "
            "round brass-rimmed glasses, pale freckled skin, calm serious face"
        ),
        "proportions": "slight, upright, narrow shoulders",
        "wardrobe": (
            "slate-blue wool coat over a high-necked cream shirt, ink-stained "
            "fingers, canvas satchel of rolled paper"
        ),
        "palette": "slate blue, cream, copper, brass",
        "identity_tokens": "same woman, consistent face, consistent copper hair and glasses",
        "negative_tokens": "different face, changed hair colour, no glasses, extra limbs, text, watermark",
        "slots": ["full_body", "front", "three_quarter"],
    }],
    "identity_line": (
        "Keep the woman in the reference images identical: same face, same copper "
        "hair, same brass glasses, same slate-blue coat."
    ),
    "shots": [
        ("They gave her the smallest desk in the survey office, and told her to map whatever nobody else wanted.",
         "Ilva sits alone at a cramped wooden desk under a single lamp in a vast dim drafting hall, tall windows behind her"),
        ("So she mapped the crack in a teacup.",
         "close on Ilva's ink-stained hands drawing a hairline crack in a white teacup, fine pen, lamplight"),
    ],
}


# ---------------------------------------------------------------------------
# The Boy Who Swept the Sky - 9:16, and everything in it moves
# ---------------------------------------------------------------------------

#: No camera instruction at all, and "full animation" said outright. The whole
#: point of this one is that things move on their own.
SKY_LOOK = (
    "bright cel-shaded 2D cartoon animation, bold clean outlines, saturated "
    "storybook colours, expressive exaggerated character animation, full "
    "animation with strong squash and stretch, dynamic action pose, "
    "no text, no captions, no watermark"
)

SWEEPER: dict[str, Any] = {
    "title": "The Boy Who Swept the Sky",
    "objective": "A three-minute vertical cartoon with real character animation.",
    # 576x1024 reduces to exactly 9:16 and both sides are multiples of 32,
    # which is what the video model wants.
    "aspect_ratio": "9:16",
    "resolution": "576x1024",
    "seconds_per_shot": 8.0,
    # 576 pixels wide is a third of the usual canvas, so the line wraps at
    # roughly half the characters and the type stays readable.
    "subtitles": {"max_chars_per_line": 20, "vertical_margin": 120},
    "look": SKY_LOOK,
    "cast": [{
        "name": "Pim",
        "appearance": (
            "small boy about nine years old, messy black hair, big round dark "
            "eyes, wide grin, smudge of soot on one cheek, cartoon proportions "
            "with a large head"
        ),
        "proportions": "short, round-faced, stubby limbs, chunky cartoon build",
        "wardrobe": (
            "oversized mustard-yellow jacket with rolled sleeves, patched brown "
            "shorts, red canvas shoes, a tall straw broom always in hand"
        ),
        "palette": "mustard yellow, red, warm brown, sky blue",
        "identity_tokens": "same boy, consistent messy black hair, mustard jacket, straw broom",
        "negative_tokens": "adult, different hair colour, realistic photo, extra limbs, text, watermark",
        "slots": ["full_body", "front", "three_quarter"],
    }],
    "identity_line": (
        "Keep the boy identical to the reference image: same face, same messy "
        "black hair, same mustard-yellow jacket, same straw broom."
    ),
    #: Every line is something happening. Verbs first, camera never mentioned.
    "shots": [
        ("Every morning before the city woke, Pim swept the square.",
         "Pim sweeps a cobbled square with big energetic strokes, dust and leaves flying up around him in swirls, morning light"),
        ("He was very good at sweeping. Nobody had ever told him so.",
         "Pim sweeps faster and faster, spinning the broom in a circle, leaves whirling into a tall spiral around him"),
        ("One morning the broom slipped out of his hands.",
         "the broom flies out of Pim's grip and shoots upward, Pim's arms fly wide, his mouth open in surprise"),
        ("It did not come down.",
         "Pim stares straight up, hands over his eyes, as the broom hangs high above him spinning slowly"),
        ("It was sweeping the sky.",
         "high above the rooftops the broom sweeps back and forth on its own, pushing clouds aside in long streaks"),
        ("Pim jumped for it. He missed.",
         "Pim leaps high with both arms stretched up, misses the broom, and tumbles backwards onto the cobbles"),
        ("He climbed the water tower. He missed again.",
         "Pim scrambles up a rusty ladder on a water tower, lunges off the top, and drops through the air arms flailing"),
        ("So he did the only sensible thing.",
         "Pim plants his feet, cracks his knuckles, and grins a huge determined grin, sleeves rolled up"),
        ("He whistled.",
         "Pim puts two fingers in his mouth and whistles hard, cheeks puffed, sound rings visibly through the air"),
        ("The broom came back. It picked him up.",
         "the broom swoops down, Pim grabs the handle, and it yanks him off his feet into the air, legs kicking"),
        ("And up they went.",
         "Pim rockets upward clinging to the broom, jacket flapping wildly, rooftops shrinking below him"),
        ("The clouds were filthy.",
         "Pim hovers among grey grimy clouds, waving dust away from his face and coughing, soot on his cheeks"),
        ("So Pim did what Pim does.",
         "Pim sweeps the clouds with huge two-handed strokes, grey grime flying off in sheets, clouds turning white"),
        ("He swept until the sky was blue.",
         "Pim sweeps rapidly across a wide sky, a bright blue trail opening behind each stroke, clouds parting"),
        ("Below, the city looked up.",
         "far below, tiny people in a market square stop and point upward, hats falling off, mouths open"),
        ("They saw a boy on a broom, working.",
         "Pim scrubs at a stubborn dark cloud with both hands on the broom, feet braced, straining"),
        ("The cloud fought back.",
         "the dark cloud swells and shoves Pim, he spins backwards through the air still gripping the broom"),
        ("Pim did not let go.",
         "Pim swings back around, plants both feet on the cloud, and heaves the broom in a huge arc"),
        ("The last of the grey came away.",
         "a sheet of grey peels off and falls away, sunlight bursting through the gap onto Pim's face"),
        ("Then the broom set him down, gently, in the square.",
         "the broom lowers Pim slowly to the cobbles, he touches down and stumbles, laughing"),
        ("Nobody in the market said anything. They were still looking up.",
         "Pim stands in the square holding his broom, dozens of townspeople around him all staring upward"),
        ("So Pim swept the square. Same as every morning.",
         "Pim shrugs, turns, and sweeps the cobbles again with big cheerful strokes, dust flying"),
        ("But he swept a little taller.",
         "Pim sweeps with his chin high and a wide grin, broom whirling, blue sky bright above him"),
    ],
}


FILMS: dict[str, dict[str, Any]] = {
    "cartographer": CARTOGRAPHER,
    "sweeper": SWEEPER,
}
