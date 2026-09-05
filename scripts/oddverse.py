"""ODDVERSE SF01 - "The 3:17 Train", as the blueprint specifies it.

Kept apart from the producer so an episode is a data change. The shape differs
from `films.py` in three ways the blueprint forces, and each one is a real
production decision rather than a formatting preference:

* **Every beat is a key image and then a clip.** The blueprint's look is
  grounded documentary realism with restrained motion, and its camera language
  is composed shot by shot. That is the route where a human decides the
  composition: generate a still, look at it, approve it, animate that. It is
  roughly four times slower than reference-to-video and it is the reason the
  frames are framed.
* **Most shots have nobody in them.** Five of the nine are a station, a clock,
  a train, a platform and an open carriage door. A cast is a per-shot fact.
* **Beats are not the same length.** 4, 2, 4, 3, 4, 3, 4, 3, 5 seconds.

What this file cannot yet express, and the producer therefore cannot do, is
listed in ``KNOWN_GAPS`` rather than quietly approximated.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# House look - Section 6 of the blueprint, verbatim in intent
# ---------------------------------------------------------------------------

GLOBAL_STYLE = (
    "Vertical 9:16 cinematic documentary photograph, grounded contemporary "
    "realism, restrained indie mystery film aesthetic. Natural practical "
    "lighting, realistic exposure, muted neutral tones, subtle 35mm film grain, "
    "authentic weathered materials, believable human proportions, understated "
    "composition, subtle atmospheric mist and realistic camera imperfections. "
    "Ordinary believable world photographed naturally. No fantasy lighting. "
    "The image should resemble a frame captured from a serious low-budget "
    "British mystery drama rather than AI-generated artwork."
)

GLOBAL_NEGATIVE = (
    "cyberpunk, neon, blue-orange cinematic grading, fantasy, supernatural "
    "glow, horror monster, ghost, zombie, excessive fog, dramatic volumetric "
    "light, glossy skin, fashion photography, glamour, perfect symmetry, "
    "oversaturated, HDR, surreal anatomy, extra fingers, distorted face, "
    "floating objects, text, logo, watermark, AI art aesthetic"
)

WORLD = (
    "Small abandoned rural railway station in northern England, "
    "early-twentieth-century architecture, weathered dark brick, faded cream "
    "wooden details, old metal benches, analog clock, neglected platform, weeds "
    "through cracks, no modern digital displays, cold damp late-autumn night, "
    "slight mist."
)


SF01: dict[str, Any] = {
    "key": "sf01",
    "title": "The 3:17 Train",
    "series": "STRANGE FILE #001 | ODDVERSE",
    "objective": (
        "A 32-second vertical mystery short: an impossible train, a newspaper "
        "dated tomorrow, and a photograph of the man watching."
    ),
    "aspect_ratio": "9:16",
    # The delivery canvas the blueprint asks for. The video model runs at
    # 576x1024 on a 16 GB card, so the source is upscaled to reach it - a real
    # cost of this hardware, recorded rather than hidden.
    "resolution": "1080x1920",
    "source_resolution": "576x1024",
    "frame_rate": 30.0,
    "style": GLOBAL_STYLE,
    "negative": GLOBAL_NEGATIVE,
    "world": WORLD,
    # 576 wide at delivery scale: the line has to wrap early to stay readable.
    "subtitles": {"max_chars_per_line": 24, "vertical_margin": 180},
    "cast": {
        "CHAR01": {
            "name": "CHAR01 - The Woman",
            "appearance": (
                "Caucasian woman, approximately 38, pale natural complexion, "
                "narrow oval face, shoulder-length slightly messy dark brown "
                "hair, tired neutral expression, calm and ordinary, no horror "
                "expression"
            ),
            "proportions": "average height, unremarkable build, upright, still",
            "wardrobe": (
                "charcoal wool overcoat below the knees, plain black trousers, "
                "worn dark leather shoes, no jewellery, no hat, no umbrella"
            ),
            "palette": "charcoal, black, muted brown, cold grey",
            "identity_tokens": (
                "same woman, consistent narrow oval face, consistent "
                "shoulder-length dark brown hair, charcoal overcoat"
            ),
            "negative_tokens": (
                "different face, blonde hair, young woman, glamour, makeup, "
                "smiling, horror expression, text, watermark"
            ),
            # One view, not three. A key image is conditioned on the world
            # plate *and* the character, and a two-input edit has room for
            # exactly one of each. One full-body view is what holds an
            # identity anyway; three of the same person in two slots is how a
            # shot ends up with two of them.
            "slots": ["full_body"],
        },
        "CHAR02": {
            "name": "CHAR02 - The Observer",
            "appearance": (
                "man, approximately 32, average build, short dark hair, plain "
                "unremarkable face, seen mostly from behind or out of focus"
            ),
            "proportions": "average height, average build",
            "wardrobe": "dark brown jacket over a plain grey shirt",
            "palette": "dark brown, grey, black",
            "identity_tokens": (
                "same man, consistent short dark hair, dark brown jacket over "
                "grey shirt"
            ),
            "negative_tokens": (
                "different face, long hair, bright clothing, smiling, text, "
                "watermark"
            ),
            # One view, not three. A key image is conditioned on the world
            # plate *and* the character, and a two-input edit has room for
            # exactly one of each. One full-body view is what holds an
            # identity anyway; three of the same person in two slots is how a
            # shot ends up with two of them.
            "slots": ["full_body"],
        },
    },
    #: (seconds, name, image prompt, motion direction, narration, emphasis, cast)
    "shots": [
        (
            4.0, "The Station",
            "Empty abandoned rural railway station at night, viewed from across "
            "the railway tracks. Weathered dark brick station building, old cream "
            "wooden trim, neglected platform, weeds growing between cracks, one "
            "old analog station clock beneath the canopy, weak warm tungsten "
            "platform lamps, cold damp autumn night, slight ground mist, no "
            "people, distant train headlights barely visible far down the track. "
            "Wide establishing shot, eye level, 35mm lens.",
            "Locked-off observational camera. Mist drifts slowly across the "
            "platform, weeds move slightly in the wind, one lamp flickers "
            "naturally. Nothing else moves.",
            "Every night at exactly 3:17, a train arrives at this abandoned station.",
            "EVERY NIGHT / AT 3:17 AM", [],
        ),
        (
            2.0, "3:17",
            "Close-up of an old analog railway station clock beneath a weathered "
            "canopy, chipped cream-painted metal frame, condensation on the "
            "glass, weak tungsten light, abandoned station blurred behind, "
            "85mm lens, shallow depth of field.",
            "Very slow natural push-in with slight handheld micro-movement. The "
            "second hand ticks.",
            "", "3:17 AM", [],
        ),
        (
            4.0, "The Train",
            "Old unbranded British passenger train emerging slowly from darkness "
            "toward an abandoned rural platform, modest white headlights, "
            "weathered exterior, believable proportions, wet rails reflecting "
            "weak station lights, empty platform, long lens 70mm view.",
            "The train moves slowly and realistically toward the platform, its "
            "headlights brightening the wet rails, with a subtle camera "
            "vibration as it passes.",
            "That's impossible.", "THE TRAIN RETURNS.", [],
        ),
        (
            3.0, "Closed 30 Years Ago",
            "Medium documentary shot along a neglected railway platform: boarded "
            "ticket office window, rusted bench, peeling paint, weeds and moss "
            "through the paving, an old timetable frame with faded illegible "
            "paper, part of a stationary train softly out of focus behind, "
            "50mm lens.",
            "Slow restrained lateral camera drift along the platform. Weeds move "
            "slightly. Nothing else changes.",
            "The station closed thirty years ago.", "CLOSED 30 YEARS AGO.", [],
        ),
        (
            4.0, "Nobody Gets Off",
            "Side view of a stationary old passenger train at a dark platform. "
            "One carriage door stands open, warm dim interior light spilling "
            "against the cold dark platform, no passenger visible, realistic "
            "worn interior, 50mm lens.",
            "The carriage door finishes opening with a realistic pneumatic "
            "motion. The interior light flickers subtly. Nobody appears.",
            "The train isn't on any schedule, and nobody has ever stepped off.",
            "NO ONE EVER GETS OFF.", [],
        ),
        (
            3.0, "Until Last Night",
            "A woman steps calmly down from an open train door onto an abandoned "
            "railway platform at night, full-body three-quarter view, charcoal "
            "wool overcoat, a folded newspaper held at her side, ordinary tired "
            "expression, warm train interior light behind her, cold platform "
            "lamps, 50mm lens.",
            "She takes two slow natural steps onto the platform. Her coat moves "
            "subtly. She does not look at the camera.",
            "Until last night.", "UNTIL LAST NIGHT.", ["CHAR01"],
        ),
        (
            4.0, "The Newspaper",
            "Medium close-up of a woman in a charcoal overcoat holding a folded "
            "old-fashioned newspaper on a dark railway platform, a man's dark "
            "shoulder out of focus in the extreme foreground, natural practical "
            "station lighting, 70mm lens, shallow depth of field.",
            "The woman raises the newspaper slightly. The paper moves naturally "
            "in the breeze. The man in the foreground stays still.",
            "A woman walked onto the platform carrying a newspaper dated tomorrow.",
            "", ["CHAR01"],
        ),
        (
            3.0, "Tomorrow",
            "Extreme close-up of a folded old-fashioned newspaper held by "
            "realistic hands, traditional monochrome broadsheet layout with "
            "blank unreadable placeholder areas where the headline and date "
            "would be, worn newsprint texture, railway platform heavily out of "
            "focus behind, 85mm lens.",
            "Minimal natural paper movement in the night air. The hands stay "
            "steady.",
            "", "DATED TOMORROW.", [],
        ),
        (
            5.0, "The Reveal",
            "An old-fashioned newspaper front page held toward the camera on a "
            "dark railway platform, a large grainy monochrome press photograph "
            "of a man in a dark brown jacket filling the upper half of the page, "
            "blank unreadable placeholder areas where the headline would be, "
            "worn newsprint, shallow depth of field.",
            "Slow push toward the photograph on the front page, stopping "
            "completely for the final half second.",
            "But that wasn't the strange part. The photograph on the front "
            "page... was him.",
            "IT WAS HIM.", ["CHAR02"],
        ),
    ],
    #: Section 6 of the blueprint, as an instruction a hosted voice can take.
    #: A platform voice has a name and a rate slider and no opinion about how
    #: a sentence should land; this is the reason to pay for one.
    "voice_direction": (
        "Read as a calm male documentary narrator, aged 30 to 40. Natural "
        "conversational English, neutral international accent, quiet "
        "confidence, controlled curiosity, slightly unsettling without "
        "sounding frightening. Around 150 words per minute. Pause before "
        "'Until last night', before 'But that wasn't the strange part', and "
        "before 'was him'. Let the final phrase fall quieter, not louder."
    ),
    "publishing": {
        "title": "A Train Arrives Here Every Night at 3:17 AM",
        "description": (
            "A train. An abandoned station. And a newspaper dated tomorrow."
        ),
        "hashtags": "#shorts #mystery #scifi",
    },
}


#: What the blueprint asks for that this application cannot do yet. Written
#: down beside the episode rather than approximated in it, so a trial run
#: proves what the pipeline does and does not cover.
KNOWN_GAPS: list[str] = [
    "Emphasis text is a second, separately styled caption track (1-2 lines, "
    "3-6 words). The app has one subtitle track, so the emphasis strings here "
    "are carried as data and not yet rendered.",
    "Shots 8 and 9 are meant to be composited in post: the date is "
    "publish_date + 1 and the front-page photograph is a separate portrait of "
    "CHAR02 converted to halftone. There is no compositing stage, so both are "
    "generated whole and the newspaper text will be unreadable.",
    "The audio timeline (clock tick at 0:04, pneumatic door at 0:14, "
    "footsteps at 0:17) needs timed SFX cues. Per-shot mute/gain and a music "
    "bed exist; timed cues do not.",
    "The blueprint's assembly spec has a 4-6 frame dissolve between shots 8 "
    "and 9 and a 3-5 frame black tail before the loop. The renderer only cuts.",
    "The video model runs at 576x1024 on this card, so the 1080x1920 delivery "
    "is an upscale rather than a native render.",
]

EPISODES: dict[str, dict[str, Any]] = {"sf01": SF01}
