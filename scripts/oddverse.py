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
    # SF01 happens in one place, so it carries no scenes list and the producer
    # builds a single scene from these two. The plate prompt is kept verbatim
    # so re-running the episode rebuilds the station it was made with.
    "location_name": "The abandoned station",
    "plate_prompt": (
        "Wide establishing photograph of the whole station at night, no people."
    ),
    "pillar": "strange_files",
    "hook_type": "H01",
    "one_strange_thing": (
        "A train arrives at an abandoned station every night at 3:17."
    ),
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
            # Two views: the film shows him from behind, and the newspaper
            # front page needs his face. A canonical sheet has to carry the
            # view a composite will ask for, not only the view a shot will.
            "slots": ["full_body", "front"],
        },
    },
    #: (seconds, name, image prompt, (what happens, camera), narration,
    #:  emphasis, cast)
    #:
    #: The motion is a pair because a video model does not weigh the two
    #: clauses evenly. The first cut of this episode said "locked-off
    #: camera... nothing else moves" and came back 86% identical frames.
    #: Every direction below names what happens, with verbs, and leaves
    #: out what does not.
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
            ("Mist rolls across the platform in slow visible drifts. The "
             "weeds between the rails bend and spring back in the wind. A "
             "platform lamp flickers and steadies. Far down the track a "
             "headlight grows larger and brighter.",
             "Locked-off camera at eye level.",
             "cold night air, a low rail vibration far down the track, wind across an empty platform"),
            "Every night at exactly 3:17, a train arrives at this abandoned station.",
            "EVERY NIGHT / AT 3:17 AM", [],
        ),
        (
            2.0, "3:17",
            "Close-up of an old analog railway station clock beneath a weathered "
            "canopy, chipped cream-painted metal frame, condensation on the "
            "glass, weak tungsten light, abandoned station blurred behind, "
            "85mm lens, shallow depth of field.",
            ("The second hand sweeps round the dial. A bead of condensation "
             "runs down the glass and stops.",
             "Very slow push in with slight handheld micro-movement.",
             "an old station clock ticking close, faint wind behind it"),
            "", "3:17 AM", [],
        ),
        (
            4.0, "The Train",
            "Old unbranded British passenger train emerging slowly from darkness "
            "toward an abandoned rural platform, modest white headlights, "
            "weathered exterior, believable proportions, wet rails reflecting "
            "weak station lights, empty platform, long lens 70mm view.",
            ("The train rolls into the platform and grows larger in frame, "
             "its headlights sweeping bright across the wet rails. Dust and "
             "steam blow past the lens. The train slows and comes to a stop.",
             "Long lens, subtle vibration as it passes.",
             "a diesel rumble growing louder, steel wheels on rail, brakes beginning to bite"),
            "That's impossible.", "THE TRAIN RETURNS.", [],
        ),
        (
            3.0, "Closed 30 Years Ago",
            "Medium documentary shot along a neglected railway platform: boarded "
            "ticket office window, rusted bench, peeling paint, weeds and moss "
            "through the paving, an old timetable frame with faded illegible "
            "paper, part of a stationary train softly out of focus behind, "
            "50mm lens.",
            ("Weeds and moss shift in the wind. A loose sheet of paper in the "
             "timetable frame lifts and flaps against the glass. Light from "
             "the stationary train shifts slowly across the peeling paint.",
             "Slow restrained lateral drift along the platform.",
             "a stationary train idling low, a loose sheet of paper flapping against glass, wind"),
            "The station closed thirty years ago.", "CLOSED 30 YEARS AGO.", [],
        ),
        (
            4.0, "Nobody Gets Off",
            "Side view of a stationary old passenger train at a dark platform. "
            "One carriage door stands open, warm dim interior light spilling "
            "against the cold dark platform, no passenger visible, realistic "
            "worn interior, 50mm lens.",
            ("The carriage door slides fully open with a pneumatic push. Warm "
             "interior light spills out across the platform and widens. The "
             "interior lamp flickers twice. Steam curls out from beneath the "
             "carriage.",
             "Locked-off camera.",
             "a pneumatic door hissing open, a low engine idle, the hum of an interior light"),
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
            ("The woman steps down from the carriage onto the platform, one "
             "foot then the other, and walks two unhurried paces forward. Her "
             "long coat swings with the movement. She shifts the folded "
             "newspaper to her other hand.",
             "Locked-off camera at eye level.",
             "two unhurried footsteps on wet concrete, a heavy coat moving, the train idling behind"),
            "Until last night.", "UNTIL LAST NIGHT.", ["CHAR01"],
        ),
        (
            4.0, "The Newspaper",
            "Medium close-up of a woman in a charcoal overcoat holding a folded "
            "old-fashioned newspaper on a dark railway platform, a man's dark "
            "shoulder out of focus in the extreme foreground, natural practical "
            "station lighting, 70mm lens, shallow depth of field.",
            ("The woman lifts the folded newspaper up toward her chest. The "
             "pages ripple and lift in the breeze. She turns her head "
             "slightly and looks down at it.",
             "70mm lens, shallow focus, camera steady.",
             "newsprint rustling in a breeze, quiet night wind, a distant train idle"),
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
            ("The newspaper page lifts and settles in the night air. The "
             "hands adjust their grip and turn the page a little toward the "
             "light, and the paper flexes across its fold.",
             "85mm lens, shallow focus, camera steady.",
             "paper flexing and creasing close to the microphone, almost nothing else"),
            "", "DATED TOMORROW.", [],
        ),
        (
            5.0, "The Reveal",
            "An old-fashioned newspaper front page held toward the camera on a "
            "dark railway platform, a large grainy monochrome press photograph "
            "of a man in a dark brown jacket filling the upper half of the page, "
            "blank unreadable placeholder areas where the headline would be, "
            "worn newsprint, shallow depth of field.",
            ("The hands raise the newspaper toward the camera and hold it "
             "there. The page flexes and steadies. The photograph on the "
             "front page fills more of the frame.",
             "Slow push in that comes to rest for the final half second.",
             "the ambience falling away to almost nothing, then one low sub-bass swell"),
            "But that wasn't the strange part. The photograph on the front "
            "page... was him.",
            "IT WAS HIM.", ["CHAR02"],
        ),
    ],
    #: Appendix A: "do not let AI generate critical text/date/newspaper
    #: layout; composite in post". These are those composites, keyed by beat.
    #: Placed in fractions of the frame, so the same recipe survives the key
    #: image being regenerated at another size.
    #:
    #: Each starts with a patch, because the model does not leave a blank area
    #: when asked - it writes a plausible smear, and a real headline drawn over
    #: a fake one is two headlines.
    #: Cleared for the v3 run. The corners below were measured on frames from
    #: a previous set of key images and describe planes the new paper is not
    #: on; they are placed again after this run's frames exist.
    "composites": {},
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


# ---------------------------------------------------------------------------
# SF02 - "The Extra Room". Hook H04, Discovery.
# ---------------------------------------------------------------------------
# SF01 happens in one place, so one approved plate of that place held all nine
# shots together. This episode moves: a street, a kitchen table, an upstairs
# hall, and the room at the end of it. Four places is four plates, and a plate
# belongs to a scene rather than to an episode - which is what a Scene is for
# and what SF01 never made the producer prove.

SF02_WORLD = (
    "An ordinary 1970s British semi-detached house on a quiet suburban street, "
    "red-brown brick, white uPVC windows, a low garden wall, worn interiors "
    "with woodchip wallpaper and patterned carpet, warm domestic lamps, cold "
    "damp night outside. Nothing decorative, nothing expensive, nothing new."
)

SF02: dict[str, Any] = {
    "key": "sf02",
    "title": "The Extra Room",
    "series": "STRANGE FILE #002 | ODDVERSE",
    "objective": (
        "A 32-second vertical mystery short: a house with one more room than "
        "its floor plan, and a delivery label dated next year."
    ),
    "pillar": "strange_files",
    "hook_type": "H04",
    "one_strange_thing": (
        "There is a room in this house that does not appear on any floor plan."
    ),
    "aspect_ratio": "9:16",
    "resolution": "1080x1920",
    "source_resolution": "576x1024",
    "frame_rate": 30.0,
    "style": GLOBAL_STYLE,
    "negative": GLOBAL_NEGATIVE,
    "world": SF02_WORLD,
    # 28, not SF01's 24. Measured against this episode's nine narration lines:
    # at 24 two of them break into a second cue with an orphan line reading
    # "rooms."; at 28 every line is one cue that breaks at its own full stop.
    "subtitles": {"max_chars_per_line": 28, "vertical_margin": 180},
    #: Beats whose key image is a detail rather than a view of the place, and
    #: which are therefore generated from the prompt alone. Beat 9 was one
    #: until the guidance scale turned out to be what held the framing wide:
    #: raised to 9 it goes close *and* keeps the room, so it gave up its place
    #: for nothing. Empty now, and kept because a shot with no place - a hand
    #: against black, a title card - would still want it.
    "detail_beats": set(),
    "cast": {
        "CHAR01": {
            "name": "CHAR01 - The Homeowner",
            "appearance": (
                "man, approximately 42, average build, short greying dark "
                "hair, plain unremarkable face, tired ordinary expression, "
                "seen mostly from behind"
            ),
            "proportions": "average height, average build, slightly stooped",
            "wardrobe": (
                "faded navy crew-neck jumper over a grey t-shirt, dark jeans, "
                "grey socks, no shoes indoors, no jewellery"
            ),
            "palette": "faded navy, grey, dark denim",
            "identity_tokens": (
                "same man, consistent short greying dark hair, faded navy "
                "jumper, seen from behind"
            ),
            "negative_tokens": (
                "different face, long hair, bright clothing, uniform, smiling, "
                "heroic posture, text, watermark"
            ),
            # One view, for the same reason SF01's woman has one: the key
            # image is a two-input edit, and the second input is the plate.
            "slots": ["full_body"],
        },
    },
    #: Four scenes, in the order the film plays them. Each carries the place
    #: it happens in and the plate every key image in it is edited from, so
    #: three shots of the same hallway are three shots of one hallway.
    "scenes": [
        {
            "key": "street",
            "title": "The house",
            "purpose": "Establish an ordinary house and state the anomaly.",
            "location": "The street outside",
            "time_of_day": "night",
            "world": (
                "An ordinary 1970s British semi-detached brick house seen from "
                "the pavement across a quiet suburban street at night, low "
                "garden wall, wheelie bin, a parked hatchback, one sodium "
                "streetlamp, wet tarmac, bare autumn hedge, no people."
            ),
            "plate_prompt": (
                "Wide establishing photograph of the whole house from across "
                "the street at night, one upstairs window lit, no people."
            ),
        },
        {
            "key": "table",
            "title": "The kitchen table",
            "purpose": "The paperwork disagrees with the house.",
            "location": "The kitchen table",
            "time_of_day": "night",
            "world": (
                "An ordinary British kitchen table at night under a single "
                "warm pendant lamp, architectural drawings spread flat, a "
                "yellowed folded land survey, a chipped blue-striped mug, a "
                "pencil, a steel tape measure, dark kitchen out of focus "
                "behind, no people."
            ),
            "plate_prompt": (
                "Overhead photograph of the whole table under the pendant "
                "lamp, papers spread flat, no people."
            ),
        },
        {
            "key": "hall",
            "title": "The upstairs hall",
            "purpose": "The door that is not on the plan.",
            "location": "The upstairs landing",
            "time_of_day": "night",
            "world": (
                "A narrow upstairs landing and hallway in an ordinary British "
                "house at night, patterned worn carpet, woodchip wallpaper "
                "painted magnolia, a radiator, two white panel doors along one "
                "side and a single closed white panel door at the far end, one "
                "weak warm landing light, no window."
            ),
            "plate_prompt": (
                "Photograph looking down the whole length of the upstairs "
                "hallway toward the closed door at the far end, no people."
            ),
        },
        {
            "key": "room",
            "title": "The room",
            "purpose": "The payoff: the room is furnished, and not yet paid for.",
            "location": "The room at the end of the hall",
            "time_of_day": "night",
            "world": (
                "A small plain furnished sitting room inside a British house, "
                "a two-seat grey fabric sofa, a low wooden coffee table, a "
                "standing floor lamp, a patterned rug, plain curtains drawn "
                "across a wall with no window behind them, everything clean "
                "and completely unused, no dust on the furniture, no "
                "decoration, no television, no people."
            ),
            "plate_prompt": (
                "Photograph of the whole small room from the doorway, floor "
                "lamp on, everything new and unused, no people."
            ),
        },
    ],
    #: (seconds, name, image prompt, (what happens, camera), narration,
    #:  emphasis, cast, scene key)
    #:
    #: Durations are the edit's, not the model's: 4, 3, 3, 4, 3, 4, 3, 3, 5.
    #: Each narration line is short enough to be spoken inside its own shot -
    #: the dialogue-fit check reads these at 150 words per minute and refuses
    #: a line that runs past the cut it belongs to.
    "shots": [
        (
            4.0, "The House",
            "An ordinary 1970s British semi-detached brick house at night seen "
            "from the pavement across a quiet suburban street, one upstairs "
            "window lit warm behind thin curtains, every other window dark, a "
            "sodium streetlamp, wet tarmac, a parked hatchback, a wheelie bin "
            "by the low garden wall, no people. Wide establishing shot, eye "
            "level, 35mm lens.",
            ("Fine rain drifts down through the cone of streetlamp light. The "
             "curtain in the lit upstairs window shifts and falls back. The "
             "bare hedge moves in the wind and water runs off the wall.",
             "Locked-off camera from across the street, eye level.",
             "fine rain falling on wet tarmac, wind moving through a bare hedge, a distant car passing on a wet road"),
            # Every line below was measured with the narrator that speaks
            # them, because word count does not predict this voice: "This
            # house has seven rooms." (five words) took 3.60 seconds and
            # "There are seven rooms in this house." (seven) took 2.55, from
            # the same voice under the same direction. The first cut of this
            # line was one sentence too long and came back at 9.15 seconds
            # for eight words - the narrator put a held pause at the full
            # stop, which is good reading and does not fit four seconds.
            "There are seven rooms in this house.",
            "SEVEN ROOMS. / SIX ON THE PLAN.", [], "street",
        ),
        (
            3.0, "The Floor Plan",
            "Close overhead view of a printed architectural floor plan lying "
            "flat on a kitchen table under a warm pendant lamp, thin black "
            "line work, a rectangular printed title block in the lower area of "
            "the sheet left blank and unreadable, a pencil and a steel tape "
            "measure resting across one corner, a man's hands at the edge of "
            "frame, dark kitchen out of focus behind, 50mm lens.",
            ("A hand slides the pencil across the plan and taps it twice "
             "against the paper. The corner of the sheet lifts in the draught "
             "and settles back flat.",
             "Overhead, camera steady.",
             "the small tap of a pencil on paper, a sheet of paper shifting on a table, a fridge humming in a quiet kitchen"),
            # The second half of the opening fact, moved off shot 1 so
            # neither line has to carry a full stop. The measuring this shot
            # used to narrate is in the picture: a tape measure and a pencil.
            "The floor plan shows six.", "", [], "table",
        ),
        (
            3.0, "The Survey",
            "Close-up of a yellowed folded land survey document being drawn "
            "out from beneath an architectural floor plan on a kitchen table, "
            "brittle aged paper, faint printed line work, a blank unreadable "
            "rectangular stamp area in one corner, warm pendant lamp light, "
            "shallow depth of field, 85mm lens.",
            ("A hand draws the old survey out from under the plan and presses "
             "it flat. The brittle paper flexes, springs back at the fold, and "
             "settles.",
             "85mm lens, shallow focus, camera steady.",
             "brittle old paper unfolding and creasing, a clock ticking somewhere else in the house"),
            # "1974" costs four and a half seconds on its own: the narrator
            # says "nineteen seventy-four" and holds after it. The date is on
            # the emphasis card instead, where text costs no time at all -
            # which is what having two caption tracks is for.
            "It isn't on the survey.", "NOT ON THE 1974 SURVEY.",
            [], "table",
        ),
        (
            4.0, "The Hall",
            "A narrow upstairs hallway in an ordinary British house at night "
            "seen from the top of the stairs, patterned worn carpet, magnolia "
            "woodchip wallpaper, a radiator, two white panel doors along one "
            "side, a single closed white panel door at the far end, one weak "
            "warm landing light, a man in a faded navy jumper standing halfway "
            "along the hall with his back to camera. Wide shot, eye level, "
            "35mm lens.",
            ("The man walks three unhurried steps down the hall toward the "
             "closed door and stops. His shadow stretches away across the "
             "carpet as he moves. The landing light dims briefly and steadies.",
             "Locked-off camera at the top of the stairs.",
             "slow socked footsteps on worn carpet, the faint hum of a landing light, an old house settling at night"),
            "There's a door at the end of the upstairs hall.",
            "A DOOR AT THE END.", ["CHAR01"], "hall",
        ),
        (
            3.0, "Nobody Opened It",
            "Close-up of a plain white panel door at the end of a dark "
            "upstairs hallway, chipped brass handle, painted-over hinges, a "
            "thin line of dim light along the floor at the threshold, worn "
            "carpet, weak warm landing light from behind camera, 50mm lens.",
            ("A thin line of light under the door brightens, wavers, and "
             "fades. Dust turns slowly through the landing light. The brass "
             "handle shifts a few millimetres and stops.",
             "Very slow push in.",
             "near silence, the faint electrical hum of a light fitting, one small metallic click from a door handle"),
            "For three weeks, nobody opened it.", "THREE WEEKS.", [], "hall",
        ),
        (
            4.0, "Last Sunday",
            # Rewritten after the first attempt put him beside a side door "
            # while the door at the end of the hall stood open behind him. The
            # framing and the door are both stated twice, because the scene
            # plate keeps pulling the composition back to its own wide view.
            "Close view from directly behind a man's head and shoulders, which "
            "fill the lower half of the frame. He stands immediately in front "
            "of the single white panel door at the far end of an upstairs "
            "hallway, close enough to touch it. His right hand grips its "
            "chipped brass handle. That door is open a few inches and warm "
            "light spills through the narrow gap onto his shoulder. Every "
            "other door in the hallway is shut. Faded navy jumper, dark jeans, "
            "seen from behind at shoulder height, 35mm lens.",
            ("The man turns the handle and pushes the door inward. The door "
             "swings open and warm light spreads across his shoulders, up the "
             "wallpaper and along the carpet. He takes one step forward.",
             "Locked-off camera behind him at shoulder height.",
             "a brass handle turning, a door easing open on dry hinges, one step forward onto carpet"),
            "Last Sunday, I opened it.", "LAST SUNDAY.", ["CHAR01"], "hall",
        ),
        (
            3.0, "Already Furnished",
            "The interior of a small plain sitting room seen from the doorway, "
            "a two-seat grey fabric sofa, a low wooden coffee table, a "
            "standing floor lamp lit, a patterned rug, plain curtains drawn "
            "across a wall, everything clean and completely unused, no "
            "television, no decoration, no people, 35mm lens.",
            ("Light from the floor lamp spreads further across the rug as the "
             "door opens wider behind camera. Dust turns slowly through the "
             "lamplight. The drawn curtain moves once and hangs still.",
             "Slow push forward through the doorway.",
             "a door swinging wider, then the flat dead quiet of a small carpeted room with no echo"),
            "The room was already furnished.", "ALREADY FURNISHED.",
            [], "room",
        ),
        (
            3.0, "Our Furniture",
            "Medium close-up across a low wooden coffee table in a small plain "
            "sitting room, a chipped blue-striped mug standing on the bare "
            "wood, a folded newspaper beside it, the grey fabric sofa behind, "
            "warm floor lamp light from one side, shallow depth of field, "
            "50mm lens.",
            ("Steam rises from the mug and drifts sideways through the "
             "lamplight. The lamp flickers once and the shadows shift across "
             "the sofa cushions.",
             "Slow lateral drift.",
             "very quiet room tone, the faint tick of a cooling lamp"),
            "With our furniture.", "OUR FURNITURE.", [], "room",
        ),
        (
            5.0, "Not Yet",
            # Conditioned on the room plate at guidance 3.5 this came back as
            # a wide view of the room with the label too small to read. The
            # plate was not the reason: at guidance 9 the same conditioning
            # goes where the prompt says.
            "Extreme close-up photograph of a printed white self-adhesive "
            "delivery label taped to the padded arm of a grey fabric sofa. The "
            "label fills most of the frame and carries a blank unreadable "
            "printed area. Clean unused grey upholstery around it, one corner "
            "of the label lifting away from the fabric, warm lamp light from "
            "the left, everything behind it thrown completely out of focus. "
            "85mm macro lens, very shallow depth of field.",
            ("The taped corner of the label lifts and falls in the draught "
             "from the open door and comes to rest. The lamplight steadies "
             "across the fabric.",
             "Slow push in that comes to rest for the final half second.",
             "almost complete silence, one paper corner lifting in a draught, a single low room tone"),
            "We haven't bought it yet.", "WE HAVEN'T / BOUGHT IT YET.",
            [], "room",
        ),
    ],
    #: The one thing in this episode that has to be *read*. The plan and the
    #: survey were composited too at first, and both came back as white
    #: stickers laid over the props rather than printing on them - the corners
    #: were written before the frame existed, so they described a plane the
    #: paper was not on. Both were dropped rather than fixed: the narration
    #: already says "the plan shows six" and "the survey from 1974", so
    #: neither needed to be legible. The delivery date does. It is the payoff,
    #: nobody says it aloud, and no model spells it.
    #:
    #: Its corners were measured off the generated key image, which is the
    #: only order that works: generate, look, place, then animate.
    #:
    #: No patch under it. The model left the label genuinely blank this time -
    #: at guidance 3.5 it wrote a plausible smear and a patch was the only way
    #: to have one surface instead of two.
    "composites": {
        9: [
            {"type": "text", "text": "DELIVERY", "colour": "#1f1c18",
             "size": 0.022,
             "corners": [[0.450, 0.664], [0.730, 0.661],
                         [0.730, 0.698], [0.448, 0.701]]},
            {"type": "text", "text": "{next_year}", "colour": "#1f1c18",
             "size": 0.026,
             "corners": [[0.450, 0.703], [0.730, 0.700],
                         [0.730, 0.742], [0.448, 0.745]]},
        ],
    },
    "voice_direction": (
        "Read as a calm male documentary narrator, aged 30 to 40, describing "
        "something that happened to him and that he has not finished thinking "
        "about. Natural conversational English, neutral international accent, "
        "quiet confidence, controlled curiosity, slightly unsettling without "
        "sounding frightening. Around 150 words per minute. Pause before 'Last "
        "Sunday, I opened it', and before 'We haven't bought it yet'. Let the "
        "final line fall quieter and flatter, not louder."
    ),
    "publishing": {
        "title": "Our House Has One More Room Than the Floor Plan",
        "description": (
            "Seven rooms. Six on the plan. And a delivery label dated next "
            "year. A short fiction from the ODDVERSE."
        ),
        "hashtags": "#shorts #mystery #strangefiles",
    },
}


#: What the blueprint asks for that this application still cannot do. Written
#: down beside the episodes rather than approximated in them, so a production
#: run proves what the pipeline does and does not cover.
KNOWN_GAPS: list[str] = [
    "The video model runs at 576x1024 on this card, so the blueprint's "
    "1080x1920 delivery is an upscale rather than a native render.",
    "Sound cues are placed against a shot and an offset, so the blueprint's "
    "audio timeline has to be re-entered per episode; there is no library of "
    "reusable ambience beds shared across a channel.",
]

EPISODES: dict[str, dict[str, Any]] = {"sf01": SF01, "sf02": SF02}
